from user_service.app.application.interfaces.db.admin_repo import AdminRepositoryInterface


class GetMyAdminRoleUseCase:
    def __init__(self, admin_repo: AdminRepositoryInterface) -> None:
        self.admin_repo = admin_repo

    async def __call__(self, user_id: int) -> str:
        role = await self.admin_repo.get_role(user_id)
        if role in {"admin", "superadmin"}:
            return role
        return "user"
