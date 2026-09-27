from user_service.app.application.dto import AdminDTO
from user_service.app.application.interfaces.db.admin_cache_repo import (
    AdminCacheRepositoryInterface,
)
from user_service.app.application.interfaces.db.admin_repo import AdminRepositoryInterface


class GetAdminsUseCase:
    def __init__(
            self,
            admin_repo: AdminRepositoryInterface,
            admin_cache_repo: AdminCacheRepositoryInterface,
    ) -> None:
        self.admin_repo = admin_repo
        self.admin_cache_repo = admin_cache_repo

    async def __call__(self, actor_user_id: int) -> list[AdminDTO] | str:
        if not await self._is_superadmin(actor_user_id):
            return "forbidden"

        cached = await self.admin_cache_repo.get_all_admins()
        if cached is not None:
            return cached

        admins = await self.admin_repo.get_all_admins()
        await self.admin_cache_repo.set_all_admins(admins)
        return admins

    async def _is_superadmin(self, user_id: int) -> bool:
        role = await self.admin_repo.get_role(user_id)
        return role == "superadmin"
