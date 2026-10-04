import asyncio
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from submission_service.app.application.drills.bank import DRILLS, DRILLS_BY_SKILL, DRILL_BY_ID
from submission_service.app.application.drills.models import DrillRun
from submission_service.app.application.drills.select import (
    SKILL_COOLDOWN_HOURS,
    choose_drill,
)
from submission_service.app.application.dto.submission import (
    CriterionResultDTO,
    ReviewDTO,
    SubmissionDTO,
)
from submission_service.app.application.trajectory.evidence import drill_opportunities
from submission_service.app.application.trajectory.formula import (
    compute_knowledge,
    compute_trajectory,
)
from submission_service.app.application.trajectory.knowledge import trace_knowledge
from submission_service.app.application.trajectory.skills import SKILL_BY_ID
from submission_service.app.application.use_case.drills.get_drill import GetDrillUseCase
from submission_service.app.application.use_case.drills.record_drill_run import (
    RecordDrillRunUseCase,
)


NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _submission(
        submission_id: int,
        at: datetime,
        skill_id: str,
        passed: bool,
        task_id: int = 1,
) -> SubmissionDTO:
    return SubmissionDTO(
        submission_id=submission_id,
        user_id=7,
        task_id=task_id,
        code="x",
        status="reviewed",
        review=ReviewDTO(
            score=9 if passed else 4,
            feedback="",
            suggestions=[],
            criteria=[
                CriterionResultDTO(
                    id=f"c{i}",
                    text=f"Критерий {i}",
                    passed=passed,
                    skills=[],
                )
                for i in range(1, 4)
            ],
        ),
        created_at=at,
        reviewed_at=at,
    )


def _mastered_long_ago(skill_id: str, days: int = 200) -> list:
    rows = []
    for index in range(4):
        at = NOW - timedelta(days=days + (3 - index))
        row = _submission(index + 1, at, skill_id, passed=True, task_id=index + 1)
        for criterion in row.review.criteria:
            object.__setattr__(criterion, "skills", [])
        rows.append(row)
    return rows


def _knowledge_with(skill_id: str, outcomes: list[tuple[int, bool]]):
    from submission_service.app.application.trajectory.knowledge import (
        Observation,
        Opportunity,
    )

    opportunities = [
        Opportunity(
            at=NOW - timedelta(days=days),
            task_id=index + 1,
            submission_id=index + 1,
            observations=(
                Observation(skill_id=skill_id, outcome=1.0 if ok else 0.0, weight=1.0, source="criterion"),
            ),
        )
        for index, (days, ok) in enumerate(outcomes)
    ]
    return trace_knowledge(opportunities, now=NOW)


def test_a_fading_skill_gets_a_drill():
    knowledge = _knowledge_with("algorithms", [(400, True), (399, True), (398, True), (397, True)])
    assert knowledge.get("algorithms").status == "fading"

    pick = choose_drill(knowledge, [], now=NOW)

    assert pick is not None
    assert pick.skill_id == "algorithms"
    assert pick.kind == "review"
    assert pick.drill.skill_id == "algorithms"
    assert pick.days_since > 300
    assert "забывание" in pick.reason


def test_a_fresh_skill_gets_nothing():
    knowledge = _knowledge_with("algorithms", [(1, True), (0, True)])
    assert choose_drill(knowledge, [], now=NOW) is None


def test_a_gap_skill_is_offered_after_the_fading_ones():
    knowledge = _knowledge_with("validation", [(2, False), (1, False), (0, False)])
    assert knowledge.get("validation").status == "gap"

    pick = choose_drill(knowledge, [], now=NOW)

    assert pick is not None and pick.kind == "gap"
    assert "не закрыт" in pick.reason


def test_the_same_skill_is_not_offered_twice_in_a_day():
    knowledge = _knowledge_with("algorithms", [(400, True), (399, True), (398, True), (397, True)])
    done = DrillRun(
        drill_id="algorithms-top",
        skill_id="algorithms",
        passed=3,
        total=3,
        at=NOW - timedelta(hours=SKILL_COOLDOWN_HOURS - 1),
    )
    assert choose_drill(knowledge, [done], now=NOW) is None
    # через сутки навык снова можно трогать
    later = NOW + timedelta(hours=6)
    assert choose_drill(knowledge, [done], now=later) is not None


def test_a_failed_drill_does_not_block_a_retry():
    knowledge = _knowledge_with("algorithms", [(400, True), (399, True), (398, True), (397, True)])
    failed = DrillRun(
        drill_id="algorithms-top",
        skill_id="algorithms",
        passed=1,
        total=3,
        at=NOW - timedelta(minutes=5),
    )
    assert choose_drill(knowledge, [failed], now=NOW) is not None


def test_drills_rotate_inside_one_skill():
    knowledge = _knowledge_with("algorithms", [(400, True), (399, True), (398, True), (397, True)])
    done = DrillRun(
        drill_id="algorithms-top",
        skill_id="algorithms",
        passed=3,
        total=3,
        at=NOW - timedelta(days=30),
    )
    pick = choose_drill(knowledge, [done], now=NOW)
    assert pick is not None and pick.drill.id != "algorithms-top"


def test_a_skill_without_drills_is_skipped():
    knowledge = _knowledge_with("no_such_skill", [(400, True), (399, True), (398, True), (397, True)])
    assert choose_drill(knowledge, [], now=NOW) is None


def test_a_passed_drill_refreshes_the_skill():
    outcomes = [(400, True), (399, True), (398, True), (397, True)]
    before = _knowledge_with("algorithms", outcomes).get("algorithms")
    assert before.status == "fading"

    runs = [DrillRun("algorithms-top", "algorithms", passed=3, total=3, at=NOW - timedelta(hours=1))]
    opportunities = drill_opportunities(runs)
    from submission_service.app.application.trajectory.knowledge import (
        Observation,
        Opportunity,
    )

    history = [
        Opportunity(
            at=NOW - timedelta(days=days),
            task_id=index + 1,
            submission_id=index + 1,
            observations=(Observation(skill_id="algorithms", outcome=1.0, weight=1.0, source="criterion"),),
        )
        for index, (days, _) in enumerate(outcomes)
    ]
    after = trace_knowledge(history + opportunities, now=NOW).get("algorithms")

    assert after.retention > before.retention
    assert after.p_now > before.p_now
    assert after.status != "fading"
    assert after.half_life_days > before.half_life_days


def test_a_failed_drill_lowers_the_estimate_but_counts_as_practice():
    outcomes = [(400, True), (399, True), (398, True), (397, True)]
    before = _knowledge_with("algorithms", outcomes).get("algorithms")
    runs = [DrillRun("algorithms-top", "algorithms", passed=0, total=3, at=NOW - timedelta(hours=1))]

    from submission_service.app.application.trajectory.knowledge import (
        Observation,
        Opportunity,
    )

    history = [
        Opportunity(
            at=NOW - timedelta(days=days),
            task_id=index + 1,
            submission_id=index + 1,
            observations=(Observation(skill_id="algorithms", outcome=1.0, weight=1.0, source="criterion"),),
        )
        for index, (days, _) in enumerate(outcomes)
    ]
    after = trace_knowledge(history + drill_opportunities(runs), now=NOW).get("algorithms")

    assert after.p_known < before.p_known
    assert after.last_practiced_at is not None


def test_a_partial_drill_is_partial_credit():
    runs = [DrillRun("algorithms-top", "algorithms", passed=2, total=4, at=NOW)]
    observation = drill_opportunities(runs)[0].observations[0]
    assert observation.outcome == 0.5
    assert observation.weight == 0.5
    assert observation.source == "drill"


def test_empty_runs_are_not_observations():
    assert drill_opportunities([DrillRun("x", "algorithms", 0, 0, NOW)]) == []


def test_drill_runs_reach_the_trajectory():
    runs = [DrillRun("algorithms-top", "algorithms", passed=3, total=3, at=NOW - timedelta(hours=2))]
    result = compute_trajectory([], now=NOW, drill_runs=runs)
    ids = {skill.id for skill in result.skills}
    assert "algorithms" in ids


def test_knowledge_can_be_computed_from_drills_alone():
    runs = [DrillRun("security-redact", "security", passed=4, total=4, at=NOW - timedelta(hours=2))]
    knowledge = compute_knowledge([], drill_runs=runs, now=NOW)
    assert knowledge.get("security").opportunities == 1


class _DrillsDB:
    def __init__(self, runs: list[DrillRun] | None = None, ok: bool = True) -> None:
        self.runs = list(runs or [])
        self.ok = ok

    async def add_run(self, user_id: int, run: DrillRun) -> bool:
        if self.ok:
            self.runs.append(run)
        return self.ok

    async def list_runs(self, user_id: int, limit: int = 200) -> list[DrillRun]:
        return list(self.runs)


def test_a_result_is_stored_with_the_skill_of_the_drill():
    db = _DrillsDB()
    result = asyncio.run(RecordDrillRunUseCase(db)(user_id=7, drill_id="security-redact", passed=4, total=4))
    assert result.stored is True
    assert db.runs[0].skill_id == "security"
    assert db.runs[0].ok is True


def test_an_unknown_drill_is_refused():
    db = _DrillsDB()
    result = asyncio.run(RecordDrillRunUseCase(db)(user_id=7, drill_id="nope", passed=1, total=1))
    assert (result.stored, result.error) == (False, "unknown_drill")
    assert db.runs == []


def test_counts_are_clamped_to_the_run():
    db = _DrillsDB()
    asyncio.run(RecordDrillRunUseCase(db)(user_id=7, drill_id="security-redact", passed=99, total=4))
    assert db.runs[0].passed == 4


def test_an_empty_run_is_not_evidence():
    db = _DrillsDB()
    result = asyncio.run(RecordDrillRunUseCase(db)(user_id=7, drill_id="security-redact", passed=0, total=0))
    assert (result.stored, result.error) == (False, "empty_run")


class _SubmissionsDB:
    def __init__(self, rows: list[SubmissionDTO]) -> None:
        self.rows = rows

    async def get_all_user_submissions(self, user_id: int) -> list[SubmissionDTO]:
        return self.rows


class _TaskCache:
    async def list_user_tasks(self, user_id: int) -> list:
        return []


def test_the_use_case_offers_a_drill_for_a_forgotten_skill():
    rows = [
        _submission(index + 1, NOW - timedelta(days=400 - index), "algorithms", passed=True, task_id=index + 1)
        for index in range(4)
    ]
    for row in rows:
        for criterion in row.review.criteria:
            object.__setattr__(criterion, "text", "Сложность алгоритма и производительность решения")

    uc = GetDrillUseCase(_SubmissionsDB(rows), _DrillsDB(), _TaskCache())
    pick = asyncio.run(uc(user_id=7, now=NOW))

    assert pick is not None
    assert pick.drill.id in DRILL_BY_ID
    assert pick.skill_title == SKILL_BY_ID[pick.skill_id].title


def test_the_use_case_says_nothing_when_there_is_nothing_to_refresh():
    uc = GetDrillUseCase(_SubmissionsDB([]), _DrillsDB(), _TaskCache())
    assert asyncio.run(uc(user_id=7, now=NOW)) is None


def test_every_drill_is_well_formed():
    assert len(DRILLS) >= 14
    ids = [drill.id for drill in DRILLS]
    assert len(set(ids)) == len(ids)
    for drill in DRILLS:
        assert drill.skill_id in SKILL_BY_ID, drill.id
        assert drill.minutes <= 10
        assert "from solution import" in drill.tests or "import solution" in drill.tests
        assert drill.tests.count("def test_") >= 3, drill.id
        assert drill.starter.strip().endswith("...")
        assert len(drill.prompt) > 80


def test_most_skills_have_a_drill():
    covered = set(DRILLS_BY_SKILL)
    missing = set(SKILL_BY_ID) - covered
    assert not missing, f"навыки без упражнения: {sorted(missing)}"


def _run_pytest(code: str, tests: str) -> int:
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, "solution.py"), "w", encoding="utf-8") as handle:
            handle.write(code)
        with open(os.path.join(folder, "test_drill.py"), "w", encoding="utf-8") as handle:
            handle.write(tests)
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "test_drill.py", "-q", "--tb=no", "-p", "no:cacheprovider"],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return done.returncode


@pytest.mark.parametrize("drill", DRILLS, ids=[drill.id for drill in DRILLS])
def test_the_drill_tests_pass_on_the_reference_and_fail_on_the_starter(drill):
    assert _run_pytest(drill.reference, drill.tests) == 0, f"эталон не проходит: {drill.id}"
    assert _run_pytest(drill.starter, drill.tests) != 0, f"заготовка проходит: {drill.id}"


class _Token:
    @staticmethod
    def decode_token(token: str) -> int | None:
        return 7 if token == "ok" else None


class _Request:
    def __init__(self) -> None:
        self.headers = {"Authorization": "Bearer ok"}


class _Offer:
    def __init__(self, pick) -> None:
        self.pick = pick

    async def __call__(self, user_id: int, now=None):
        return self.pick


def test_the_endpoint_never_hands_out_the_tests():
    from submission_service.app.presentation.api.v1.submissions.router import get_my_drill

    knowledge = _knowledge_with("algorithms", [(400, True), (399, True), (398, True), (397, True)])
    pick = choose_drill(knowledge, [], now=NOW)
    assert pick is not None

    offer = asyncio.run(get_my_drill(request=_Request(), token_service=_Token(), uc=_Offer(pick)))

    assert offer is not None
    body = offer.model_dump()
    assert "tests" not in body and "reference" not in body
    assert pick.drill.tests not in str(body)
    assert body["starter"].strip().endswith("...")
    assert body["skill_title"] == SKILL_BY_ID["algorithms"].title


def test_the_endpoint_answers_null_when_there_is_nothing():
    from submission_service.app.presentation.api.v1.submissions.router import get_my_drill

    assert asyncio.run(
        get_my_drill(request=_Request(), token_service=_Token(), uc=_Offer(None))
    ) is None


def test_the_internal_endpoint_needs_the_token():
    from fastapi import HTTPException

    from submission_service.app.presentation.api.v1.internal.router import drill_tests

    class _Settings:
        internal_settings = type("S", (), {"token": "secret"})()

    class _Req:
        def __init__(self, token: str | None) -> None:
            self.headers = {"X-Internal-Token": token} if token else {}

    tests = asyncio.run(drill_tests(request=_Req("secret"), drill_id="algorithms-top", settings=_Settings()))
    assert "def test_" in tests.tests and tests.skill_id == "algorithms"

    with pytest.raises(HTTPException) as error:
        asyncio.run(drill_tests(request=_Req("wrong"), drill_id="algorithms-top", settings=_Settings()))
    assert error.value.status_code == 401
