from abc import abstractmethod
import asyncio
import logging
from typing import Any, Protocol

from agent_service.app.application.dto import (
    ChallengeResult,
    CriterionResult,
    PathStepResult,
    Review,
    TaskTestsResult,
)
from agent_service.app.application.graph_memory.episodes import review_episode
from agent_service.app.application.interfaces import (
    LLMInterface,
    MemoryEpisodeQueue,
    MemoryInterface,
    StudentProfileRepository,
)
from agent_service.app.application.observability.llm_trace import LlmTracer, get_noop_tracer
from agent_service.app.application.review.acceptance import (
    AcceptanceRubric,
    CriterionCheck,
    build_rubric,
    build_rubric_heuristic,
    format_checks_for_feedback,
    grade_rubric,
)
from agent_service.app.application.review.anchor import anchor_line
from agent_service.app.application.review.adversarial import (
    ChallengeVerdict,
    challenge_suggestions,
    format_challenges_for_feedback,
)
from agent_service.app.application.review.agent_path import (
    AgentPath,
    PathVerdict,
    evaluate_review_path,
    format_path_for_feedback,
)
from agent_service.app.application.review.checkpoints import review_graph_thread_id
from agent_service.app.application.review.context_compact import (
    compact_agent_results,
    compact_team_summary,
    compact_tool_facts,
)
from agent_service.app.application.review.draft_select import (
    draft_count_for_case,
    select_best_draft,
    variant_hints,
)
from agent_service.app.application.review.scorecard import ScoreCard, compose_score
from agent_service.app.application.tools.models import ToolReport
from agent_service.app.application.tools.past_reviews import save_review_memory
from agent_service.app.application.tools.toolkit import ReviewToolkit


class ReviewerAgentProtocol(Protocol):
    @abstractmethod
    async def run(self, code: str, task_description: str, tool_facts: str = "") -> Review:
        raise NotImplementedError


class BugAgentProtocol(Protocol):
    @abstractmethod
    async def run(self, code: str, tool_facts: str = "") -> Review:
        raise NotImplementedError


class AdversarialAgentProtocol(Protocol):
    @abstractmethod
    async def run(
            self,
            code: str,
            task_description: str,
            team_summary: str,
            tool_facts: str = "",
            team_task_score: int = 5,
            team_reliability_score: int = 5,
            tool_findings_errors: int = 0,
            syntax_ok: bool = True,
            compile_ok: bool = True,
            tests_failed: bool = False,
    ) -> ChallengeVerdict:
        raise NotImplementedError


class MentorAgentProtocol(Protocol):
    @abstractmethod
    async def run(self, code: str, results: Any, tool_facts: str = "") -> str:
        raise NotImplementedError


class ReviewOrchestrator:
    def __init__(
            self,
            reviewer_agent: ReviewerAgentProtocol,
            bug_agent: BugAgentProtocol,
            mentor_agent: MentorAgentProtocol,
            adversarial_agent: AdversarialAgentProtocol | None = None,
            toolkit: ReviewToolkit | None = None,
            memory: MemoryInterface | None = None,
            llm: LLMInterface | None = None,
            tracer: LlmTracer | None = None,
            review_graph: Any | None = None,
            student_profiles: StudentProfileRepository | None = None,
            episode_queue: MemoryEpisodeQueue | None = None,
    ) -> None:
        self._reviewer_agent = reviewer_agent
        self._bug_agent = bug_agent
        self._mentor_agent = mentor_agent
        self._adversarial_agent = adversarial_agent
        self._toolkit = toolkit
        self._memory = memory
        self._student_profiles = student_profiles
        self._episode_queue = episode_queue
        self._llm = llm
        self._tracer = tracer or get_noop_tracer()
        if review_graph is None:
            raise ValueError("review_graph is required")
        self._review_graph = review_graph

    async def run(
            self,
            code: str,
            task_description: str,
            task_id: str | None = None,
            submission_id: str | None = None,
            user_id: str | None = None,
            attempt: int | None = None,
            previous_feedback: str | None = None,
            hidden_tests: str | None = None,
    ) -> Review:
        logger = logging.getLogger("agent_service")
        try:
            from agent_service.app.application.observability.tracing import ensure_trace_id

            trace_id = ensure_trace_id()
        except Exception:
            trace_id = "unknown"

        thread_id = review_graph_thread_id(
            submission_id=submission_id,
            attempt=attempt,
            code=code,
            task_description=task_description,
            user_id=user_id,
        )
        from agent_service.app.application.graphs.runner import ainvoke_graph
        from agent_service.app.application.graphs.state import ReviewGraphRuntime

        logger.info(
            "pipeline.trace trace_id=%s step=LangGraphReview nodes=full thread=%s",
            trace_id,
            thread_id,
        )
        out = await ainvoke_graph(
            self._review_graph,
            {
                "code": code,
                "task_description": task_description,
                "task_id": task_id,
                "submission_id": submission_id,
                "user_id": user_id,
                "attempt": attempt,
                "previous_feedback": previous_feedback,
                "hidden_tests": hidden_tests,
                "trace_id": trace_id,
                "path": AgentPath(),
                "tool_facts": "",
            },
            context=ReviewGraphRuntime(
                orchestrator=self,
                logger=logger,
                trace_id=trace_id,
                tracer=self._tracer,
            ),
            tracer=self._tracer,
            thread_id=thread_id,
            graph_name="review",
        )
        review = out.get("review")
        if not isinstance(review, Review):
            raise RuntimeError("langgraph review graph produced no Review")
        return review

    async def step_tools(
            self,
            code: str,
            task_description: str,
            task_id: str | None,
            user_id: str | None,
            attempt: int | None,
            previous_feedback: str | None,
            path: AgentPath,
            logger: logging.Logger,
            trace_id: str,
            hidden_tests: str | None = None,
    ) -> tuple[ToolReport | None, str, AgentPath]:
        report = await self._inspect(
            code=code,
            task_description=task_description,
            task_id=task_id,
            user_id=user_id,
            logger=logger,
            trace_id=trace_id,
            path=path,
            hidden_tests=hidden_tests,
        )
        tool_facts = report.as_prompt_block() if report is not None else ""
        revision_block = _revision_block(attempt=attempt, previous_feedback=previous_feedback)
        if revision_block:
            tool_facts = f"{revision_block}\n{tool_facts}".strip()
            path.record("revision", kind="step", status="ok", detail=f"attempt={attempt}")
            logger.info(
                "pipeline.trace trace_id=%s step=Revision attempt=%s",
                trace_id,
                attempt,
            )
        return report, tool_facts, path

    async def step_acceptance_rubric(
            self,
            task_description: str,
            tool_facts: str,
            path: AgentPath,
            logger: logging.Logger,
            trace_id: str,
    ) -> tuple[AcceptanceRubric, str, AgentPath]:
        logger.info("pipeline.trace trace_id=%s step=AcceptanceRubric start", trace_id)
        try:
            rubric = await build_rubric(self._llm, task_description)
            path.record(
                "acceptance_rubric",
                kind="step",
                status="ok",
                detail=f"criteria={len(rubric.criteria)}",
            )
        except Exception:
            logger.exception("pipeline.trace trace_id=%s step=AcceptanceRubric error", trace_id)
            path.record("acceptance_rubric", kind="step", status="error")
            rubric = build_rubric_heuristic(task_description)
        rubric_block = rubric.as_prompt_block()
        if rubric_block:
            tool_facts = f"{rubric_block}\n{tool_facts}".strip()
        logger.info(
            "pipeline.trace trace_id=%s step=AcceptanceRubric end criteria=%s",
            trace_id,
            len(rubric.criteria),
        )
        return rubric, tool_facts, path

    async def step_reviewer_bug(
            self,
            code: str,
            task_description: str,
            tool_facts: str,
            path: AgentPath,
            logger: logging.Logger,
            trace_id: str,
    ) -> tuple[Review, Review, AgentPath]:
        logger.info("pipeline.trace trace_id=%s step=Reviewer+Bug start", trace_id)
        agent_facts = compact_tool_facts(tool_facts)
        try:
            reviewer_review, bug_review = await asyncio.gather(
                self._reviewer_agent.run(
                    code=code,
                    task_description=task_description,
                    tool_facts=agent_facts,
                ),
                self._bug_agent.run(code=code, tool_facts=agent_facts),
            )
            path.record("reviewer", kind="agent", status="ok", detail=f"score={reviewer_review.score}")
            path.record("bug", kind="agent", status="ok", detail=f"score={bug_review.score}")
        except Exception:
            logger.exception("pipeline.trace trace_id=%s step=Reviewer+Bug error", trace_id)
            path.record("reviewer", kind="agent", status="error")
            path.record("bug", kind="agent", status="error")
            raise
        logger.info(
            "pipeline.trace trace_id=%s step=Reviewer+Bug end reviewer=%s bug=%s",
            trace_id,
            reviewer_review.score,
            bug_review.score,
        )
        return reviewer_review, bug_review, path

    async def step_grade_rubric(
            self,
            code: str,
            task_description: str,
            tool_facts: str,
            rubric: AcceptanceRubric | None,
            path: AgentPath,
            logger: logging.Logger,
            trace_id: str,
    ) -> tuple[list[CriterionCheck], AgentPath]:
        if rubric is None:
            rubric = await build_rubric(self._llm, task_description)
        logger.info("pipeline.trace trace_id=%s step=GradeRubric start", trace_id)
        try:
            checks = await grade_rubric(
                self._llm,
                code=code,
                task_description=task_description,
                rubric=rubric,
                tool_facts=compact_tool_facts(tool_facts, max_chars=2800),
            )
            path.record(
                "grade_rubric",
                kind="step",
                status="ok",
                detail=f"passed={sum(1 for item in checks if item.passed)}/{len(checks)}",
            )
        except Exception:
            logger.exception("pipeline.trace trace_id=%s step=GradeRubric error", trace_id)
            path.record("grade_rubric", kind="step", status="error")
            checks = []
        logger.info(
            "pipeline.trace trace_id=%s step=GradeRubric end passed=%s/%s",
            trace_id,
            sum(1 for item in checks if item.passed),
            len(checks),
        )
        return checks, path

    async def step_adversarial(
            self,
            code: str,
            task_description: str,
            tool_facts: str,
            reviewer_review: Review,
            bug_review: Review,
            checks: list[CriterionCheck],
            report: ToolReport | None,
            path: AgentPath,
            logger: logging.Logger,
            trace_id: str,
    ) -> tuple[ChallengeVerdict | None, AgentPath]:
        challenge = await self._challenge_team(
            code=code,
            task_description=task_description,
            tool_facts=compact_tool_facts(tool_facts, max_chars=2800),
            reviewer_review=reviewer_review,
            bug_review=bug_review,
            checks=checks,
            report=report,
            logger=logger,
            trace_id=trace_id,
            path=path,
        )
        return challenge, path

    def step_scorecard_draft(
            self,
            reviewer_review: Review,
            bug_review: Review,
            report: ToolReport | None,
            checks: list[CriterionCheck],
            challenge: ChallengeVerdict | None,
            logger: logging.Logger,
            trace_id: str,
    ) -> ScoreCard:
        draft_card = compose_score(
            task=reviewer_review.score,
            reliability=bug_review.score,
            report=report,
            checks=checks,
            adversarial=challenge,
        )
        logger.info(
            "pipeline.trace trace_id=%s step=ScoreCardDraft final=%s",
            trace_id,
            draft_card.final,
        )
        return draft_card

    def step_mentor_plan(
            self,
            draft_card: ScoreCard | None,
            checks: list[CriterionCheck],
            challenge: ChallengeVerdict | None,
            report: ToolReport | None,
    ) -> int:
        if draft_card is None:
            return 1
        return draft_count_for_case(
            draft_final=draft_card.final,
            checks=checks,
            challenge=challenge,
            report=report,
        )

    async def step_mentor(
            self,
            code: str,
            tool_facts: str,
            reviewer_review: Review,
            bug_review: Review,
            report: ToolReport | None,
            checks: list[CriterionCheck],
            challenge: ChallengeVerdict | None,
            draft_card: ScoreCard,
            path: AgentPath,
            logger: logging.Logger,
            trace_id: str,
            n_drafts: int | None = None,
    ) -> tuple[str, bool, AgentPath]:
        logger.info("pipeline.trace trace_id=%s step=Mentor start", trace_id)
        mentor_facts = (tool_facts + "\n\n" + draft_card.as_prompt_block()).strip()
        checks_block = format_checks_for_feedback(checks)
        if checks_block:
            mentor_facts = f"{mentor_facts}\n\n{checks_block}".strip()
        challenge_block = format_challenges_for_feedback(challenge)
        if challenge_block:
            mentor_facts = f"{mentor_facts}\n\n{challenge_block}".strip()
        mentor_facts = compact_tool_facts(mentor_facts, max_chars=3600)
        results: dict[str, Any] = {
            "reviewer_review": reviewer_review,
            "bug_review": bug_review,
            "scorecard": draft_card.as_dict(),
            "acceptance_criteria": [item.as_dict() for item in checks],
            "agent_path": path.as_dict(),
        }
        if challenge is not None:
            results["adversarial_challenge"] = challenge.as_dict()
        if report is not None:
            results["tool_report"] = report.as_dict()
        compact_results = compact_agent_results(results)
        mentor_ok = True
        try:
            n_drafts = (
                n_drafts
                if n_drafts is not None
                else draft_count_for_case(
                    draft_final=draft_card.final,
                    checks=checks,
                    challenge=challenge,
                    report=report,
                )
            )
            hints = variant_hints(n_drafts)
            if n_drafts == 1:
                final_feedback = await self._mentor_agent.run(
                    code=code,
                    results=compact_results,
                    tool_facts=mentor_facts,
                )
                path.record("draft_select", kind="step", status="ok", detail="single")
            else:
                logger.info(
                    "pipeline.trace trace_id=%s step=MentorDrafts count=%s",
                    trace_id,
                    n_drafts,
                )
                draft_results = await asyncio.gather(
                    *[
                        self._mentor_agent.run(
                            code=code,
                            results=compact_results,
                            tool_facts=f"{hint}\n\n{mentor_facts}".strip(),
                        )
                        for hint in hints
                    ],
                    return_exceptions=True,
                )
                drafts: list[str] = []
                for item in draft_results:
                    if isinstance(item, BaseException) and not isinstance(item, Exception):
                        raise item
                    if isinstance(item, Exception):
                        logger.exception(
                            "pipeline.trace trace_id=%s step=MentorDraft error",
                            trace_id,
                        )
                        continue
                    text = str(item or "").strip()
                    if text:
                        drafts.append(text)
                if not drafts:
                    raise RuntimeError("all mentor drafts failed")
                selected = select_best_draft(
                    drafts,
                    checks=checks,
                    challenge=challenge,
                    report=report,
                    final_score=draft_card.final,
                )
                final_feedback = selected.text
                path.record(
                    "draft_select",
                    kind="step",
                    status="ok",
                    detail=(
                        f"picked={selected.index + 1}/{selected.candidates} "
                        f"score={selected.score}"
                    ),
                )
                logger.info(
                    "pipeline.trace trace_id=%s step=MentorDraftSelect "
                    "picked=%s/%s score=%s reasons=%s",
                    trace_id,
                    selected.index + 1,
                    selected.candidates,
                    selected.score,
                    ";".join(selected.reasons[:3]),
                )
            logger.info("pipeline.trace trace_id=%s step=Mentor end", trace_id)
        except Exception:
            mentor_ok = False
            logger.exception(
                "pipeline.trace trace_id=%s step=Mentor error; using fallback feedback",
                trace_id,
            )
            reviewer_feedback = reviewer_review.feedback.strip()
            bug_feedback = bug_review.feedback.strip()
            parts = [p for p in [reviewer_feedback, bug_feedback] if p]
            final_feedback = "\n\n".join(parts) if parts else "Review completed with fallback feedback."
            if report is not None and (not report.syntax_ok or not report.compile_ok):
                final_feedback = (
                    "Код не компилируется или содержит синтаксическую ошибку. " + final_feedback
                )
        path.record(
            "mentor",
            kind="agent",
            status="ok" if mentor_ok else "error",
            detail=f"chars={len(final_feedback)}",
        )
        return final_feedback, mentor_ok, path

    def step_process_eval(
            self,
            path: AgentPath,
            report: ToolReport | None,
            mentor_feedback: str,
            logger: logging.Logger,
            trace_id: str,
    ) -> tuple[PathVerdict, AgentPath]:
        path_verdict = _evaluate_path(path, report, mentor_feedback)
        path.record(
            "process_eval",
            kind="step",
            status="ok" if path_verdict.ok else "warn",
            detail=f"score={path_verdict.score}",
        )
        logger.info(
            "pipeline.trace trace_id=%s step=ProcessEval score=%s cap=%s violations=%s path=%s",
            trace_id,
            path_verdict.score,
            path_verdict.cap,
            len(path_verdict.violations),
            ",".join(path.names()),
        )
        return path_verdict, path

    async def step_finalize(
            self,
            reviewer_review: Review,
            bug_review: Review,
            report: ToolReport | None,
            checks: list[CriterionCheck],
            challenge: ChallengeVerdict | None,
            path: AgentPath,
            path_verdict: PathVerdict,
            mentor_feedback: str,
            task_id: str | None,
            submission_id: str | None,
            user_id: str | None,
            logger: logging.Logger,
            trace_id: str,
            code: str = "",
    ) -> Review:
        card = compose_score(
            task=reviewer_review.score,
            reliability=bug_review.score,
            report=report,
            checks=checks,
            adversarial=challenge,
            path=path_verdict,
        )
        logger.info(
            "pipeline.trace trace_id=%s step=ScoreCard task=%s reliability=%s tools=%s "
            "rubric=%s adversarial_cap=%s process=%s process_cap=%s final=%s",
            trace_id,
            card.task,
            card.reliability,
            card.tools,
            card.rubric,
            card.adversarial_cap,
            card.process,
            card.process_cap,
            card.final,
        )
        suggestions = list(
            dict.fromkeys(
                _failed_criteria_suggestions(checks)
                + challenge_suggestions(challenge)
                + _path_suggestions(path_verdict)
                + _tool_suggestions(report)
                + reviewer_review.suggestions
                + bug_review.suggestions,
            ),
        )
        review = Review(
            score=card.final,
            feedback=_with_scorecard_and_extras(
                mentor_feedback,
                card,
                checks,
                challenge,
                path,
                path_verdict,
            ),
            suggestions=suggestions,
            criteria=[
                CriterionResult(
                    id=item.id,
                    text=item.text,
                    passed=item.passed,
                    note=item.note,
                    line=None
                    if item.passed
                    else anchor_line(f"{item.note} {item.text}", code, item.line),
                )
                for item in checks
            ],
            challenges=_challenge_results(challenge, code),
            agent_path=[
                PathStepResult(
                    kind=step.kind,
                    name=step.name,
                    status=step.status,
                    detail=step.detail,
                )
                for step in path.steps
            ],
            tests=_tests_result(report),
        )
        await self._remember_review(
            review=review,
            task_id=task_id,
            submission_id=submission_id,
            user_id=user_id,
            logger=logger,
        )
        await self._queue_graph_episode(
            review=review,
            report=report,
            task_id=task_id,
            submission_id=submission_id,
            user_id=user_id,
            logger=logger,
        )
        return review

    async def _challenge_team(
            self,
            code: str,
            task_description: str,
            tool_facts: str,
            reviewer_review: Review,
            bug_review: Review,
            checks: list[CriterionCheck],
            report: ToolReport | None,
            logger: logging.Logger,
            trace_id: str,
            path: AgentPath,
    ) -> ChallengeVerdict | None:
        if self._adversarial_agent is None:
            path.record("adversarial", kind="agent", status="skip", detail="disabled")
            return None
        logger.info("pipeline.trace trace_id=%s step=Adversarial start", trace_id)
        team_summary = _team_summary(reviewer_review, bug_review, checks)
        error_count = 0
        syntax_ok = True
        compile_ok = True
        tests_failed = False
        if report is not None:
            error_count = sum(1 for item in report.findings if item.severity == "error")
            syntax_ok = report.syntax_ok
            compile_ok = report.compile_ok
            tests_failed = bool(report.tests_run and report.tests_passed is False)
        try:
            verdict = await self._adversarial_agent.run(
                code=code,
                task_description=task_description,
                team_summary=team_summary,
                tool_facts=tool_facts,
                team_task_score=reviewer_review.score,
                team_reliability_score=bug_review.score,
                tool_findings_errors=error_count,
                syntax_ok=syntax_ok,
                compile_ok=compile_ok,
                tests_failed=tests_failed,
            )
            path.record(
                "adversarial",
                kind="agent",
                status="ok",
                detail=f"agrees={verdict.agrees},severity={verdict.severity}",
            )
        except Exception:
            logger.exception("pipeline.trace trace_id=%s step=Adversarial error", trace_id)
            path.record("adversarial", kind="agent", status="error")
            return None
        logger.info(
            "pipeline.trace trace_id=%s step=Adversarial end agrees=%s severity=%s cap=%s challenges=%s",
            trace_id,
            verdict.agrees,
            verdict.severity,
            verdict.score_cap,
            len(verdict.challenges) + len(verdict.missed),
        )
        return verdict

    async def _inspect(
            self,
            code: str,
            task_description: str,
            task_id: str | None,
            user_id: str | None,
            logger: logging.Logger,
            trace_id: str,
            path: AgentPath,
            hidden_tests: str | None = None,
    ) -> ToolReport | None:
        if self._toolkit is None:
            path.record("tools", kind="tool", status="skip", detail="toolkit missing")
            return None
        logger.info("pipeline.trace trace_id=%s step=Tools start", trace_id)
        try:
            with self._tracer.observation(
                "tools",
                as_type="tool",
                metadata={"task_id": task_id or "", "user_id": user_id or ""},
            ) as obs:
                report = await self._toolkit.inspect(
                    code=code,
                    task_description=task_description,
                    task_id=task_id,
                    user_id=user_id,
                    hidden_tests=hidden_tests,
                )
                obs.update(
                    output={
                        "language": report.language,
                        "syntax_ok": report.syntax_ok,
                        "compile_ok": report.compile_ok,
                        "tests_run": report.tests_run,
                        "score_cap": report.score_cap,
                    }
                )
        except Exception:
            logger.exception("pipeline.trace trace_id=%s step=Tools error", trace_id)
            path.record("tools", kind="tool", status="error")
            return None
        path.record(
            "tools",
            kind="tool",
            status="ok",
            detail=(
                f"lang={report.language},syntax={report.syntax_ok},"
                f"compile={report.compile_ok},tests={report.tests_run}"
            ),
        )
        if report.language in {"python", "javascript"}:
            path.record("static", kind="tool", status="ok" if report.syntax_ok else "warn")
            path.record(
                "sandbox",
                kind="tool",
                status="ok" if report.compile_ok else "warn",
                detail="compile/tests",
            )
        logger.info(
            "pipeline.trace trace_id=%s step=Tools end syntax_ok=%s compile_ok=%s cap=%s",
            trace_id,
            report.syntax_ok,
            report.compile_ok,
            report.score_cap,
        )
        return report

    async def _remember_review(
            self,
            review: Review,
            task_id: str | None,
            submission_id: str | None,
            user_id: str | None,
            logger: logging.Logger,
    ) -> None:
        if self._memory is None:
            return
        try:
            await save_review_memory(
                self._memory,
                task_id=task_id,
                submission_id=submission_id,
                user_id=user_id,
                score=review.score,
                feedback=review.feedback,
                suggestions=review.suggestions,
                profiles=self._student_profiles,
            )
        except Exception:
            logger.exception("tools.past_reviews.save_failed")

    async def _queue_graph_episode(
            self,
            review: Review,
            report: ToolReport | None,
            task_id: str | None,
            submission_id: str | None,
            user_id: str | None,
            logger: logging.Logger,
    ) -> None:
        if self._episode_queue is None or not user_id:
            return
        try:
            episode = review_episode(
                user_id=str(user_id),
                review=review,
                report=report,
                task_id=task_id,
                submission_id=submission_id,
            )
            await self._episode_queue.enqueue(episode)
        except Exception:
            logger.exception("graph_memory.enqueue_failed submission=%s", submission_id)


def _evaluate_path(
        path: AgentPath,
        report: ToolReport | None,
        mentor_feedback: str,
) -> PathVerdict:
    language = report.language if report is not None else None
    tools_ran = path.status_of("tools") == "ok"
    syntax_checked = path.has("static") or (
        report is not None and report.language in {"python", "javascript"}
    )
    compile_checked = path.has("sandbox") or (
        report is not None and report.language in {"python", "javascript"}
    )
    sandbox_eligible = (language or "") in {"python", "javascript"}
    return evaluate_review_path(
        path,
        language=language,
        tools_ran=tools_ran,
        syntax_checked=bool(syntax_checked),
        compile_checked=bool(compile_checked),
        sandbox_eligible=sandbox_eligible,
        mentor_feedback=mentor_feedback,
    )


def _revision_block(attempt: int | None, previous_feedback: str | None) -> str:
    text = (previous_feedback or "").strip()
    if not text:
        return ""
    round_no = attempt if attempt and attempt > 1 else 2
    clipped = text if len(text) <= 900 else text[:899] + "…"
    return (
        f"Повторная сдача (попытка {round_no}).\n"
        f"Прошлое ревью:\n{clipped}\n"
        "Сфокусируйся: что из замечаний исправлено, что осталось открытым. "
        "Не повторяй закрытые претензии. Если прогресс есть — отрази это в оценке и фидбеке."
    )


def _team_summary(
        reviewer_review: Review,
        bug_review: Review,
        checks: list[CriterionCheck],
) -> str:
    return compact_team_summary(
        reviewer_score=reviewer_review.score,
        reviewer_feedback=reviewer_review.feedback,
        bug_score=bug_review.score,
        bug_feedback=bug_review.feedback,
        checks=[
            {
                "id": item.id,
                "text": item.text,
                "passed": item.passed,
                "note": item.note,
            }
            for item in checks
        ],
    )


def _with_scorecard_and_extras(
        feedback: str,
        card: ScoreCard,
        checks: list[CriterionCheck],
        challenge: ChallengeVerdict | None,
        path: AgentPath,
        path_verdict: PathVerdict,
) -> str:
    line = card.as_feedback_line()
    checks_block = format_checks_for_feedback(checks)
    challenge_block = format_challenges_for_feedback(challenge)
    path_block = format_path_for_feedback(path, path_verdict)
    text = (feedback or "").strip()
    parts = [line]
    if checks_block:
        parts.append(checks_block)
    if challenge_block:
        parts.append(challenge_block)
    if path_block:
        parts.append(path_block)
    if text and not text.startswith("**Итог"):
        parts.append(text)
    elif text.startswith("**Итог") and (checks_block or challenge_block or path_block):
        rest = text.split("\n", 1)
        if len(rest) > 1 and rest[1].strip():
            parts = [line]
            if checks_block:
                parts.append(checks_block)
            if challenge_block:
                parts.append(challenge_block)
            if path_block:
                parts.append(path_block)
            parts.append(rest[1].strip())
    return "\n\n".join(parts)


def _tests_result(report: ToolReport | None) -> TaskTestsResult | None:
    run = getattr(report, "hidden", None) if report is not None else None
    if run is None:
        return None
    return TaskTestsResult(
        status=str(getattr(run, "status", "")),
        total=int(getattr(run, "total", 0) or 0),
        passed=int(getattr(run, "passed", 0) or 0),
        failed_names=list(getattr(run, "failed_names", []))[:10],
        detail=str(getattr(run, "detail", "") or ""),
    )


def _challenge_results(
        challenge: ChallengeVerdict | None,
        code: str = "",
) -> list[ChallengeResult]:
    if challenge is None or not challenge.has_objections:
        return []
    severity = challenge.severity if challenge.severity in {"low", "medium", "high"} else "medium"
    items: list[ChallengeResult] = []
    seen: set[str] = set()
    for text in challenge.challenges + [f"упущено: {m}" for m in challenge.missed]:
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            ChallengeResult(text=text, severity=severity, line=anchor_line(text, code))
        )
        if len(items) >= 6:
            break
    return items


def _path_suggestions(verdict: PathVerdict) -> list[str]:
    return list(verdict.violations[:3])


def _failed_criteria_suggestions(checks: list[CriterionCheck]) -> list[str]:
    items: list[str] = []
    for check in checks:
        if check.passed:
            continue
        tip = check.note.strip() or f"Закрой критерий: {check.text}"
        if check.text.lower() not in tip.lower():
            tip = f"{check.text}: {tip}"
        items.append(tip)
        if len(items) >= 4:
            break
    return items


def _tool_suggestions(report: ToolReport | None) -> list[str]:
    if report is None:
        return []
    items: list[str] = []
    for finding in report.findings:
        if finding.tool == "memory":
            continue
        if finding.severity in {"error", "warning"}:
            items.append(finding.message)
        if len(items) >= 4:
            break
    return items
