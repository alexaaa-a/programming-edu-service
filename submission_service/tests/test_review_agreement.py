import asyncio
import datetime

import pytest

from submission_service.app.application.dto.submission import (
    ReviewDTO,
    SubmissionDTO,
    TaskTestsDTO,
)
from submission_service.app.application.evaluation import (
    Observation,
    evaluate,
    observations_from_submissions,
)
from submission_service.app.application.use_case.submissions.get_review_agreement import (
    GetReviewAgreementUseCase,
)


def _obs(score: float, passed: int, total: int) -> Observation:
    return Observation(
        score=score,
        tests_total=total,
        tests_passed=passed,
        tests_status="passed" if passed >= total and total > 0 else "failed",
    )


def test_full_agreement_gives_kappa_one():
    report = evaluate([_obs(9, 4, 4), _obs(10, 3, 3), _obs(5, 1, 4), _obs(3, 0, 2)])
    assert report.used == 4
    assert report.agreement == 1.0
    assert report.kappa == pytest.approx(1.0)
    assert (report.false_pass, report.false_fail) == (0, 0)


def test_the_two_mistakes_are_counted_apart():
    report = evaluate(
        [
            _obs(9, 1, 4),
            _obs(4, 3, 3),
            _obs(9, 2, 2),
            _obs(3, 0, 3),
        ]
    )
    assert (report.false_pass, report.false_fail) == (1, 1)
    assert report.agreement == 0.5
    assert report.false_pass_rate == 0.5
    assert report.false_fail_rate == 0.5


def test_kappa_is_zero_when_agreement_is_what_chance_would_give():
    report = evaluate([_obs(9, 2, 2), _obs(9, 1, 2)])
    assert report.agreement == 0.5
    assert report.kappa == pytest.approx(0.0)


def test_submissions_without_a_test_run_are_skipped():
    report = evaluate(
        [
            _obs(9, 2, 2),
            Observation(score=9, tests_total=0, tests_passed=0, tests_status="unavailable"),
            Observation(score=4, tests_total=0, tests_passed=0, tests_status="error"),
        ]
    )
    assert report.total == 3 and report.used == 1
    assert "С прогоном тестов" not in report.as_text()


def test_empty_input_does_not_divide_by_zero():
    report = evaluate([])
    assert report.used == 0
    assert report.agreement == 0.0 and report.kappa == 0.0
    assert "не на чем считать" in report.as_text()
    assert report.as_dict()["used"] == 0


def test_score_gap_shows_which_way_the_review_leans():
    high = evaluate([_obs(9, 1, 2)])
    assert high.score_gap == pytest.approx(3.5)
    low = evaluate([_obs(4, 2, 2)])
    assert low.score_gap == pytest.approx(-6.0)


def test_scores_out_of_a_hundred_are_normalised():
    assert evaluate([Observation(score=90, tests_total=2, tests_passed=2, tests_status="passed")]).both_pass == 1


def _submission(score: int, tests: TaskTestsDTO | None) -> SubmissionDTO:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    return SubmissionDTO(
        submission_id=1,
        user_id=7,
        task_id=1,
        code="x",
        status="reviewed",
        review=ReviewDTO(score=score, feedback="", suggestions=[], tests=tests),
        created_at=now,
        reviewed_at=now,
    )


def test_observations_are_read_from_stored_submissions():
    rows = [
        _submission(9, TaskTestsDTO(status="passed", total=3, passed=3)),
        _submission(5, TaskTestsDTO(status="failed", total=3, passed=1)),
        _submission(7, None),
    ]
    observations = observations_from_submissions(rows)
    assert len(observations) == 2
    assert evaluate(observations).agreement == 1.0


class _DB:
    def __init__(self, rows: list[SubmissionDTO]) -> None:
        self.rows = rows
        self.limit: int | None = None

    async def get_reviewed_submissions(self, limit: int = 1000) -> list[SubmissionDTO]:
        self.limit = limit
        return self.rows


def test_use_case_reads_the_database_and_reports():
    db = _DB([_submission(9, TaskTestsDTO(status="passed", total=2, passed=2))])
    report = asyncio.run(GetReviewAgreementUseCase(db)(limit=50))
    assert db.limit == 50
    assert report.used == 1 and report.both_pass == 1
