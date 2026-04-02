from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface


class GetUserSubmissionStatsUseCase:
    def __init__(self, submissions_db: SubmissionsDBInterface) -> None:
        self.submissions_db = submissions_db

    async def __call__(self, user_id: int) -> dict:
        submissions = await self.submissions_db.get_all_user_submissions(user_id=user_id)
        if not submissions:
            return {
                "total_submissions": 0,
                "reviewed_submissions": 0,
                "pending_submissions": 0,
                "failed_submissions": 0,
                "average_score": None,
                "best_score": None,
                "tasks_attempted": 0,
            }

        reviewed_scores: list[int] = []
        pending_submissions = 0
        failed_submissions = 0
        attempted_tasks: set[int] = set()

        for submission in submissions:
            attempted_tasks.add(submission.task_id)
            if submission.status == "pending":
                pending_submissions += 1
            elif submission.status == "failed":
                failed_submissions += 1

            if submission.review is not None:
                reviewed_scores.append(submission.review.score)

        average_score = (
            round(sum(reviewed_scores) / len(reviewed_scores), 2)
            if reviewed_scores
            else None
        )
        best_score = max(reviewed_scores) if reviewed_scores else None

        return {
            "total_submissions": len(submissions),
            "reviewed_submissions": len(reviewed_scores),
            "pending_submissions": pending_submissions,
            "failed_submissions": failed_submissions,
            "average_score": average_score,
            "best_score": best_score,
            "tasks_attempted": len(attempted_tasks),
        }
