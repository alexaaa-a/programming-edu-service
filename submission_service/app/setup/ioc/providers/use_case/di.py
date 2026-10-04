from dishka import provide, provide_all, Provider, Scope

from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.interfaces.decisions import DecisionModelInterface
from submission_service.app.application.use_case.drills.get_drill import GetDrillUseCase
from submission_service.app.application.use_case.drills.record_drill_run import RecordDrillRunUseCase
from submission_service.app.application.use_case.tasks.get_task_submissions import GetTaskSubmissionsUseCase
from submission_service.app.application.use_case.submissions.get_submission import GetSubmissionUseCase
from submission_service.app.application.use_case.submissions.get_submission_review import GetSubmissionReviewUseCase
from submission_service.app.application.use_case.submissions.get_user_submission_stats import GetUserSubmissionStatsUseCase
from submission_service.app.application.use_case.submissions.get_review_agreement import GetReviewAgreementUseCase
from submission_service.app.application.use_case.submissions.get_user_trajectory import GetUserTrajectoryUseCase
from submission_service.app.application.use_case.submissions.process_review_result import ProcessReviewResultUseCase
from submission_service.app.application.use_case.submissions.submit_solution import SubmitSubmissionUseCase
from submission_service.app.application.use_case.well_known.healthcheck import HealthCheckUseCase
from submission_service.app.config import Settings


class UseCaseProvider(Provider):
    scope = Scope.REQUEST

    interactors = provide_all(
        GetTaskSubmissionsUseCase,
        GetSubmissionReviewUseCase,
        GetSubmissionUseCase,
        GetUserSubmissionStatsUseCase,
        GetReviewAgreementUseCase,
        GetUserTrajectoryUseCase,
        GetDrillUseCase,
        RecordDrillRunUseCase,
        HealthCheckUseCase,
        SubmitSubmissionUseCase
    )

    @provide(scope=Scope.REQUEST)
    def process_review_result(
            self,
            submissions_db: SubmissionsDBInterface,
            decisions: DecisionModelInterface,
            task_cache: TaskCacheInterface,
            settings: Settings,
    ) -> ProcessReviewResultUseCase:
        return ProcessReviewResultUseCase(
            submissions_db=submissions_db,
            decisions=decisions,
            task_cache=task_cache,
            min_confidence=settings.jev_settings.min_confidence,
        )
