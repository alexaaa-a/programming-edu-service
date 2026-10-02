import asyncio

import pytest

from submission_service.app.application.decisions import (
    parse_answers,
    read_tags,
    skill_options,
    tagging_questions,
    tagging_state,
)
from submission_service.app.application.decisions.questions import Answers
from submission_service.app.application.dto.submission import (
    CriterionResultDTO,
    ReviewDTO,
    SkillShareDTO,
    SubmissionDTO,
)
from submission_service.app.application.trajectory.evidence import (
    criterion_skills,
    submission_observations,
)
from submission_service.app.application.trajectory.skills import SKILLS, SKILL_BY_ID
from submission_service.app.application.use_case.submissions.process_review_result import (
    ProcessReviewResultUseCase,
)
from submission_service.app.infrastructure.mongo.submissions_db import _skills_from_doc
import datetime


class _Decisions:
    def __init__(self, answers: Answers, enabled: bool = True) -> None:
        self._answers = answers
        self._enabled = enabled
        self.states: list[object] = []
        self.questions: list[int] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ask(self, state, questions, label: str = "") -> Answers:
        self.states.append(state)
        self.questions.append(len(questions))
        return self._answers


class _SubmissionsDB:
    def __init__(self, submission: SubmissionDTO) -> None:
        self.submission = submission
        self.saved: ReviewDTO | None = None

    async def get_submission_by_id(self, submission_id: int) -> SubmissionDTO:
        return self.submission

    async def update_submission_with_review(self, submission_id, review, status) -> bool:
        self.saved = review
        return True


class _TaskCache:
    def __init__(self, description: str = "Отдавай заказы постранично.") -> None:
        self.description = description
        self.calls: list[tuple[int, int]] = []

    async def get_task_description(self, task_id: int, user_id: int) -> str:
        self.calls.append((task_id, user_id))
        return self.description


def _submission(criteria: list[CriterionResultDTO]) -> SubmissionDTO:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    return SubmissionDTO(
        submission_id=1,
        user_id=7,
        task_id=104,
        code="print(1)",
        status="pending",
        review=None,
        created_at=now,
        reviewed_at=None,
    )


def _review(criteria: list[CriterionResultDTO]) -> ReviewDTO:
    return ReviewDTO(score=6, feedback="ок", suggestions=[], criteria=criteria)


def _answers(probabilities: dict[int, dict[str, float]], confidence: float = 0.9) -> Answers:
    questions = tagging_questions(["x"] * len(probabilities))
    body = {
        "answers": {
            f"criterion_{index}": {
                "type": "choice",
                "choice": max(probs, key=probs.get),
                "confidence": confidence,
                "probabilities": probs,
            }
            for index, probs in probabilities.items()
        }
    }
    return parse_answers(body, questions)


def test_every_skill_is_an_option_with_a_description():
    options = skill_options()
    assert set(options) == {skill.id for skill in SKILLS}
    assert all(len(text) > 20 for text in options.values())
    # перечисление закрытое: модель не может вернуть навык вне таксономии
    assert len(options) == len(SKILLS) >= 2


def test_questions_and_state_are_capped_and_aligned():
    texts = [f"критерий {index}" for index in range(20)]
    questions = tagging_questions(texts)
    state = tagging_state(texts, task_description="бриф")
    assert len(questions) == 12
    assert len(state["criteria"]) == 12
    assert state["task_description"] == "бриф"


def test_read_tags_keeps_two_skills_when_the_model_hesitates():
    answers = _answers({0: {"edge_cases": 0.55, "validation": 0.40, "requirements": 0.05}})
    tags = read_tags(answers, count=1, min_confidence=0.6)
    assert set(dict(tags[0])) == {"edge_cases", "validation"}
    assert sum(share for _, share in tags[0]) == pytest.approx(1.0)
    assert tags[0][0][0] == "edge_cases"


def test_read_tags_keeps_one_skill_when_the_model_is_sure():
    answers = _answers({0: {"edge_cases": 0.95, "validation": 0.03, "requirements": 0.02}})
    tags = read_tags(answers, count=1, min_confidence=0.6)
    assert tags[0] == [("edge_cases", 1.0)]


def test_read_tags_skips_unconfident_criteria():
    answers = _answers({0: {"edge_cases": 0.4, "validation": 0.35}}, confidence=0.4)
    assert read_tags(answers, count=1, min_confidence=0.6) == {}
    assert read_tags(Answers.unavailable("cooldown"), count=1, min_confidence=0.6) == {}


def test_tagging_writes_shares_into_the_review_before_saving():
    async def _run() -> None:
        criteria = [
            CriterionResultDTO(id="c1", text="Пустой список возвращает [] и 200", passed=False),
            CriterionResultDTO(id="c2", text="Отрицательный limit отклоняется с 422", passed=False),
        ]
        review = _review(criteria)
        db = _SubmissionsDB(_submission(criteria))
        cache = _TaskCache()
        decisions = _Decisions(
            _answers(
                {
                    0: {"edge_cases": 0.9, "validation": 0.1},
                    1: {"validation": 0.88, "edge_cases": 0.12},
                }
            )
        )
        use_case = ProcessReviewResultUseCase(db, decisions=decisions, task_cache=cache)

        assert await use_case(1, review) == "applied"
        assert [item.skill_id for item in review.criteria[0].skills] == ["edge_cases"]
        assert [item.skill_id for item in review.criteria[1].skills] == ["validation"]
        assert db.saved is review
        assert decisions.questions == [2]
        assert cache.calls == [(104, 7)]
        assert decisions.states[0]["task_description"] == "Отдавай заказы постранично."

    asyncio.run(_run())


def test_tagging_is_skipped_when_the_model_is_off():
    async def _run() -> None:
        criteria = [CriterionResultDTO(id="c1", text="Пустой список", passed=True)]
        review = _review(criteria)
        decisions = _Decisions(Answers.unavailable("disabled"), enabled=False)
        db = _SubmissionsDB(_submission(criteria))

        assert await use_case_result(db, decisions, review) == "applied"
        assert review.criteria[0].skills == []
        assert decisions.states == []

    async def use_case_result(db, decisions, review):
        return await ProcessReviewResultUseCase(db, decisions=decisions)(1, review)

    asyncio.run(_run())


def test_failed_review_is_not_tagged():
    async def _run() -> None:
        db = _SubmissionsDB(_submission([]))
        decisions = _Decisions(_answers({0: {"edge_cases": 0.9, "validation": 0.1}}))
        assert await ProcessReviewResultUseCase(db, decisions=decisions)(1, None) == "applied"
        assert decisions.states == []

    asyncio.run(_run())


def test_stored_tags_win_over_word_matching():
    row = CriterionResultDTO(
        id="c1",
        text="После удаления последнего заказа страница пустая",
        passed=False,
        skills=[SkillShareDTO(skill_id="edge_cases", share=0.75),
                SkillShareDTO(skill_id="validation", share=0.25)],
    )
    shares = dict(criterion_skills(row, row.text))
    assert shares["edge_cases"] == pytest.approx(0.75)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_word_matching_covers_criteria_without_tags():
    row = CriterionResultDTO(id="c1", text="Нет валидации входных данных", passed=False)
    shares = criterion_skills(row, row.text)
    assert shares and all(skill_id in SKILL_BY_ID for skill_id, _ in shares)
    assert sum(share for _, share in shares) == pytest.approx(1.0)


def test_unknown_skill_in_tags_falls_back_to_word_matching():
    row = CriterionResultDTO(
        id="c1",
        text="Нет валидации входных данных",
        passed=False,
        skills=[SkillShareDTO(skill_id="not_a_skill", share=1.0)],
    )
    assert criterion_skills(row, row.text) == criterion_skills(
        CriterionResultDTO(id="c1", text=row.text, passed=False), row.text
    )


def test_observations_use_tagged_shares_as_weights():
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    criterion = CriterionResultDTO(
        id="c1",
        text="Пустая выдача не роняет ручку",
        passed=False,
        skills=[SkillShareDTO(skill_id="edge_cases", share=0.8),
                SkillShareDTO(skill_id="error_handling", share=0.2)],
    )
    submission = SubmissionDTO(
        submission_id=1,
        user_id=7,
        task_id=104,
        code="x",
        status="reviewed",
        review=_review([criterion]),
        created_at=now,
        reviewed_at=now,
    )
    observations = {obs.skill_id: obs for obs in submission_observations(submission)}
    assert observations["edge_cases"].weight == pytest.approx(0.8)
    assert observations["error_handling"].weight == pytest.approx(0.2)
    assert observations["edge_cases"].outcome == 0.0


def test_mongo_reader_drops_broken_skill_rows():
    rows = _skills_from_doc(
        [
            {"skill_id": "edge_cases", "share": 0.8},
            {"skill_id": "", "share": 1.0},
            {"skill_id": "validation", "share": "nope"},
            "мусор",
        ]
    )
    assert [(item.skill_id, item.share) for item in rows] == [("edge_cases", 0.8)]
    assert _skills_from_doc(None) == []
