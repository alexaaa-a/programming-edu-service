from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from submission_service.app.application.interfaces.services.token_service import TokenServiceInterface
from submission_service.app.application.use_case.submissions.get_submission import GetSubmissionUseCase
from submission_service.app.application.use_case.submissions.get_submission_review import GetSubmissionReviewUseCase
from submission_service.app.application.use_case.submissions.get_user_submission_stats import GetUserSubmissionStatsUseCase
from submission_service.app.application.use_case.submissions.submit_solution import SubmitSubmissionUseCase
from submission_service.app.presentation.api.v1.submissions.schema import (
    Submission,
    Review,
    Submit,
    UserSubmissionStats,
)
from submission_service.app.presentation.api.deps import get_current_user_id_or_401


router = APIRouter(route_class=DishkaRoute)


def _review_or_none(review) -> Review | None:
    if review is None:
        return None
    return Review(
        score=review.score,
        feedback=review.feedback,
        suggestions=review.suggestions,
    )


@router.get(
    "/submissions/me/stats",
    status_code=status.HTTP_200_OK,
    response_model=UserSubmissionStats,
    description="Получить агрегированную статистику сабмишенов текущего пользователя"
)
async def get_my_submission_stats(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetUserSubmissionStatsUseCase]
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    stats = await uc(user_id=user_id)
    return UserSubmissionStats(**stats)


@router.get(
    "/submissions/{submission_id}",
    status_code=status.HTTP_200_OK,
    response_model=Submission,
    description="Получить конкретный submission"
)
async def get_submission(
        request: Request,
        submission_id: int,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetSubmissionUseCase]
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    submission = await uc(user_id, submission_id)
    if not submission:
        raise HTTPException(
            status_code=404,
            detail="Не найдено"
        )

    return Submission(
        submission_id=submission_id,
        user_id=user_id,
        task_id=submission.task_id,
        code=submission.code,
        status=submission.status,
        review=_review_or_none(submission.review),
        created_at=submission.created_at,
        reviewed_at=submission.reviewed_at,
    )


@router.get(
    "/submissions/{submission_id}/review",
    status_code=status.HTTP_200_OK,
    response_model=Review,
    description="Получить результат проверки"
)
async def get_submission_review(
        request: Request,
        submission_id: int,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetSubmissionReviewUseCase]
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    review = await uc(submission_id, user_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Не найдено"
        )

    return Review(
        score=review.score,
        feedback=review.feedback,
        suggestions=review.suggestions,
    )


@router.post(
    "/submissions",
    status_code=status.HTTP_201_CREATED,
    description="Отправка решения пользователем"
)
async def create_submission(
        request: Request,
        body: Submit,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[SubmitSubmissionUseCase]
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    submit_submission = await uc(
        body.task_id,
        body.code,
        user_id
    )

    if not submit_submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Не найдено"
        )

    return submit_submission
