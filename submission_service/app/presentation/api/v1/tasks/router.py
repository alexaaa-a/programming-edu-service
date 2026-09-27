from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from submission_service.app.application.interfaces.services.token_service import TokenServiceInterface
from submission_service.app.application.use_case.tasks.get_task_submissions import GetTaskSubmissionsUseCase
from submission_service.app.presentation.api.deps import get_current_user_id_or_401
from submission_service.app.presentation.api.v1.tasks.schema import Submission, Review


router = APIRouter(route_class=DishkaRoute)


def _review_or_none(review) -> Review | None:
    if review is None:
        return None
    return Review(
        score=review.score,
        feedback=review.feedback,
        suggestions=review.suggestions,
        criteria=[
            {
                "id": item.id,
                "text": item.text,
                "passed": item.passed,
                "note": item.note,
            }
            for item in (review.criteria or [])
        ],
        challenges=[
            {
                "text": item.text,
                "severity": item.severity,
            }
            for item in (review.challenges or [])
        ],
        agent_path=[
            {
                "kind": item.kind,
                "name": item.name,
                "status": item.status,
                "detail": item.detail,
            }
            for item in (review.agent_path or [])
        ],
    )


@router.get(
    "/tasks/{task_id}/submissions",
    status_code=status.HTTP_200_OK,
    response_model=list[Submission],
    description="Получить все сабмишены задачи"
)
async def get_task_submissions(
        request: Request,
        task_id: int,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetTaskSubmissionsUseCase]
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    submissions = await uc(task_id=task_id, user_id=user_id)

    if not submissions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Не найдено"
        )

    ans = []
    for submission in submissions:
        ans.append(
            Submission(
                submission_id=submission.submission_id,
                user_id=user_id,
                task_id=task_id,
                code=submission.code,
                status=submission.status,
                review=_review_or_none(submission.review),
                created_at=submission.created_at,
                reviewed_at=submission.reviewed_at,
            )
        )

    return ans
