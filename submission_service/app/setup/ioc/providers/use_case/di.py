from dishka import provide_all, Provider, Scope

from submission_service.app.application.use_case.tasks.get_task_submissions import GetTaskSubmissionsUseCase
from submission_service.app.application.use_case.submissions.get_submission import GetSubmissionUseCase
from submission_service.app.application.use_case.submissions.get_submission_review import GetSubmissionReviewUseCase
from submission_service.app.application.use_case.submissions.get_user_submission_stats import GetUserSubmissionStatsUseCase
from submission_service.app.application.use_case.submissions.get_user_trajectory import GetUserTrajectoryUseCase
from submission_service.app.application.use_case.submissions.process_review_result import ProcessReviewResultUseCase
from submission_service.app.application.use_case.submissions.submit_solution import SubmitSubmissionUseCase
from submission_service.app.application.use_case.well_known.healthcheck import HealthCheckUseCase


class UseCaseProvider(Provider):
    scope = Scope.REQUEST

    interactors = provide_all(
        GetTaskSubmissionsUseCase,
        GetSubmissionReviewUseCase,
        GetSubmissionUseCase,
        GetUserSubmissionStatsUseCase,
        GetUserTrajectoryUseCase,
        HealthCheckUseCase,
        ProcessReviewResultUseCase,
        SubmitSubmissionUseCase
    )
