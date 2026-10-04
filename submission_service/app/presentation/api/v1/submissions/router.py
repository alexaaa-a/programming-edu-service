from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from submission_service.app.application.interfaces.services.token_service import TokenServiceInterface
from submission_service.app.application.use_case.submissions.get_submission import GetSubmissionUseCase
from submission_service.app.application.use_case.submissions.get_submission_review import GetSubmissionReviewUseCase
from submission_service.app.application.use_case.submissions.get_user_submission_stats import GetUserSubmissionStatsUseCase
from submission_service.app.application.use_case.drills.get_drill import GetDrillUseCase
from submission_service.app.application.use_case.submissions.get_user_trajectory import GetUserTrajectoryUseCase
from submission_service.app.application.use_case.submissions.submit_solution import SubmitSubmissionUseCase
from submission_service.app.presentation.api.v1.submissions.schema import (
    DrillOffer,
    TrajectoryNudge,
    Submission,
    Review,
    Submit,
    TrajectoryFocus,
    TrajectoryRecommendation,
    TrajectorySkill,
    UserSubmissionStats,
    UserTrajectory,
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
        criteria=[
            {
                "id": item.id,
                "text": item.text,
                "passed": item.passed,
                "note": item.note,
                "line": item.line,
            }
            for item in (review.criteria or [])
        ],
        challenges=[
            {
                "text": item.text,
                "severity": item.severity,
                "line": item.line,
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
        tests=_tests_or_none(getattr(review, "tests", None)),
    )


def _tests_or_none(tests) -> dict | None:
    if tests is None:
        return None
    return {
        "status": tests.status,
        "total": tests.total,
        "passed": tests.passed,
        "failed_names": list(tests.failed_names),
        "detail": tests.detail,
    }


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
    "/submissions/me/trajectory",
    status_code=status.HTTP_200_OK,
    response_model=UserTrajectory,
    description="Траектория студента: мастерство, трудность, темп и следующий шаг",
)
async def get_my_trajectory(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetUserTrajectoryUseCase],
        task_id: int | None = None,
        can_pick_task: bool = False,
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    result = await uc(user_id=user_id, task_id=task_id, can_pick_task=can_pick_task)
    focus = result.focus
    return UserTrajectory(
        mastery=result.mastery,
        difficulty=result.difficulty,
        pace=result.pace,
        readiness=result.readiness,
        action=result.action,
        reason=result.reason,
        block_close=result.block_close,
        block_next_sprint=result.block_next_sprint,
        window_tasks=result.window_tasks,
        reviewed_in_window=result.reviewed_in_window,
        current_task_id=result.current_task_id,
        current_attempts=result.current_attempts,
        current_score=result.current_score,
        failed_criteria=result.failed_criteria,
        velocity=result.velocity,
        readiness_threshold=result.readiness_threshold,
        skills=[TrajectorySkill(**asdict(item)) for item in result.skills],
        focus=TrajectoryFocus(**asdict(focus)) if focus is not None else None,
        recommendations=[TrajectoryRecommendation(**asdict(item)) for item in result.recommendations],
        next_task_id=result.next_task_id,
        nudge=TrajectoryNudge(**result.nudge.as_dict()) if result.nudge is not None else None,
        model=result.model,
    )


@router.get(
    "/submissions/me/drill",
    status_code=status.HTTP_200_OK,
    response_model=DrillOffer | None,
    description="Короткое упражнение на навык, который начал забываться",
)
async def get_my_drill(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetDrillUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    pick = await uc(user_id=user_id)
    if pick is None:
        return None
    return DrillOffer(
        drill_id=pick.drill.id,
        title=pick.drill.title,
        prompt=pick.drill.prompt,
        starter=pick.drill.starter,
        minutes=pick.drill.minutes,
        skill_id=pick.skill_id,
        skill_title=pick.skill_title,
        kind=pick.kind,
        reason=pick.reason,
        days_since=pick.days_since,
        retention=round(pick.retention, 3),
    )


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
    return _review_or_none(review)


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
    result = await uc(
        body.task_id,
        body.code,
        user_id
    )

    if result.submission_id is not None:
        return result.submission_id

    if result.error == "pending_exists":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Предыдущая сдача ещё на проверке. Дождись ревью.",
        )
    if result.error == "max_rounds":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Лимит попыток исчерпан. Для этой задачи доступно не больше двух сдач.",
        )
    if result.error == "create_failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сохранить сдачу",
        )
    if result.error == "produce_failed":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось поставить сдачу в очередь проверки. Попробуйте ещё раз.",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Задача не найдена или недоступна для сдачи",
    )
