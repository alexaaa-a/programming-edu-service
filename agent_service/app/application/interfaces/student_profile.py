from typing import Protocol

from agent_service.app.application.dto.student_profile import StudentProfile


class StudentProfileRepository(Protocol):
    async def get(self, user_id: str) -> StudentProfile | None:
        raise NotImplementedError

    async def save(
            self,
            user_id: str,
            facts: list[str],
            task_id: str | None = None,
    ) -> None:
        raise NotImplementedError
