from user_service.app.application.interfaces.db.admin_repo import AdminRepositoryInterface
from user_service.app.application.interfaces.db.admin_cache_repo import (
    AdminCacheRepositoryInterface,
)
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface


class AddAdminUseCase:
    def __init__(
        self,
        admin_repo: AdminRepositoryInterface,
        admin_cache_repo: AdminCacheRepositoryInterface,
        user_repo: UserRepositoryInterface,
    ) -> None:
        self.admin_repo = admin_repo
        self.admin_cache_repo = admin_cache_repo
        self.user_repo = user_repo

    async def __call__(self, actor_user_id: int, target_user_id: int) -> str | bool:
        if not await self._is_superadmin(actor_user_id):
            return "forbidden"

        target_user = await self.user_repo.get_user_by_id(target_user_id)
        if target_user is None:
            return "user_not_found"

        role = await self.admin_repo.get_role(target_user_id)
        if role == "superadmin":
            return "cannot_change_superadmin"
        if role == "admin":
            return "already_admin"

        created = await self.admin_repo.set_admin(target_user_id)
        if created:
            await self._sync_cache()
        return created

    async def _is_superadmin(self, user_id: int) -> bool:
        role = await self.admin_repo.get_role(user_id)
        return role == "superadmin"

    async def _sync_cache(self) -> None:
        admins = await self.admin_repo.get_all_admins()
        await self.admin_cache_repo.set_all_admins(admins)
