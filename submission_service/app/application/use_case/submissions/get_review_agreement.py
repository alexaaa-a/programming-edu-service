from submission_service.app.application.evaluation import (
    AgreementReport,
    evaluate,
    observations_from_submissions,
)
from submission_service.app.application.interfaces.db.submissions_db import (
    SubmissionsDBInterface,
)


class GetReviewAgreementUseCase:
    def __init__(self, submissions_db: SubmissionsDBInterface) -> None:
        self._submissions_db = submissions_db

    async def __call__(self, limit: int = 1000) -> AgreementReport:
        getter = getattr(self._submissions_db, "get_reviewed_submissions", None)
        if getter is None:
            return AgreementReport()
        submissions = await getter(limit)
        return evaluate(observations_from_submissions(submissions or []))
