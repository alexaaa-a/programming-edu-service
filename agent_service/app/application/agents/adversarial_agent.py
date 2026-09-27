import logging

from agent_service.app.application.base_agent import BaseAgent
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.observability.tracing import ensure_trace_id
from agent_service.app.application.review.adversarial import (
    ChallengeVerdict,
    heuristic_challenge,
    parse_challenge_verdict,
)
from agent_service.app.application.skills import BuildAdversarialPromptsSkill, LLMGenerateSkill


class AdversarialAgent(BaseAgent):
    def __init__(
            self,
            llm: LLMInterface,
            memory: MemoryInterface | None = None,
    ) -> None:
        super().__init__(llm=llm, memory=memory)
        self.skills = [
            BuildAdversarialPromptsSkill(),
            LLMGenerateSkill(llm=llm),
        ]
        self._build_prompts = self.skills[0]
        self._llm_generate = self.skills[1]

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
        trace_id = ensure_trace_id()
        logger = logging.getLogger("agent_service")
        fallback = heuristic_challenge(
            team_task_score=team_task_score,
            team_reliability_score=team_reliability_score,
            tool_findings_errors=tool_findings_errors,
            syntax_ok=syntax_ok,
            compile_ok=compile_ok,
            tests_failed=tests_failed,
        )
        logger.info(
            "pipeline.trace trace_id=%s agent=Adversarial skill=BuildPrompts start",
            trace_id,
        )
        try:
            system_prompt, user_prompt = await self._build_prompts.run(
                code=code,
                task_description=task_description,
                team_summary=team_summary,
                tool_facts=tool_facts,
                trace_id=trace_id,
            )
            logger.info(
                "pipeline.trace trace_id=%s agent=Adversarial skill=BuildPrompts end",
                trace_id,
            )
            logger.info(
                "pipeline.trace trace_id=%s agent=Adversarial skill=LLMGenerate start",
                trace_id,
            )
            raw = await self._llm_generate.run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                trace_id=trace_id,
            )
            logger.info(
                "pipeline.trace trace_id=%s agent=Adversarial skill=LLMGenerate end",
                trace_id,
            )
            verdict = parse_challenge_verdict(raw)
            if verdict.agrees and fallback.has_objections and fallback.severity == "high":
                return fallback
            return verdict
        except Exception:
            logger.exception(
                "pipeline.error trace_id=%s agent=Adversarial stage=challenge_failed; using heuristic",
                trace_id,
            )
            return fallback
