from dishka import provide_all, Provider, Scope

from user_service.app.application.use_case.authorization.register import RegisterUseCase
from user_service.app.application.use_case.authorization.refresh import RefreshUseCase
from user_service.app.application.use_case.authorization.login import LoginUseCase
from user_service.app.application.use_case.authorization.logout import LogoutUseCase
from user_service.app.application.use_case.well_known.health import HealthUseCase
from user_service.app.application.use_case.users import (ChangePasswordUseCase, UpdateProfileUseCase,
                                                         GetCurrentUserUseCase, AddAdminUseCase,
                                                         RemoveAdminUseCase, GetAdminsUseCase,
                                                         GetMyAdminRoleUseCase)


class UseCaseProvider(Provider):
    scope = Scope.REQUEST

    interactors = provide_all(
        RefreshUseCase,
        LoginUseCase,
        HealthUseCase,
        LogoutUseCase,
        RegisterUseCase,
        UpdateProfileUseCase,
        ChangePasswordUseCase,
        GetCurrentUserUseCase,
        AddAdminUseCase,
        RemoveAdminUseCase,
        GetAdminsUseCase,
        GetMyAdminRoleUseCase,
    )
