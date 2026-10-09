import logging

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent_service.app.application.interfaces import GraphMemoryInterface
from agent_service.app.config import Settings
from agent_service.app.infrastructure.http import HttpAdminRoleGateway, is_admin
from agent_service.app.presentation.api.deps import get_current_user_id_or_401

_logger = logging.getLogger("agent_service.memory")

router = APIRouter(route_class=DishkaRoute)


class MemoryFactOut(BaseModel):
    statement: str
    relation: str
    target: str
    source: str
    confidence: float
    occurrences: int
    recorded_at: str
    closed_at: str = ""


class MemoryViewOut(BaseModel):
    enabled: bool
    user_id: str
    facts: list[MemoryFactOut] = Field(default_factory=list)


class ForgetOut(BaseModel):
    user_id: str
    removed_nodes: int


@router.get(
    "/memory/me",
    status_code=status.HTTP_200_OK,
    response_model=MemoryViewOut,
    description="Что команда помнит об этом студенте",
)
async def my_memory(
        request: Request,
        graph: FromDishka[GraphMemoryInterface],
        settings: FromDishka[Settings],
        include_closed: bool = False,
) -> MemoryViewOut:
    user_id = get_current_user_id_or_401(request, settings)
    if not graph.enabled:
        return MemoryViewOut(enabled=False, user_id=user_id)
    facts = await graph.all_facts(user_id, include_closed=include_closed)
    return MemoryViewOut(
        enabled=True,
        user_id=user_id,
        facts=[_as_out(fact) for fact in facts],
    )


@router.delete(
    "/memory/me",
    status_code=status.HTTP_200_OK,
    response_model=ForgetOut,
    description="Удалить свою память команды без возврата",
)
async def forget_me(
        request: Request,
        graph: FromDishka[GraphMemoryInterface],
        settings: FromDishka[Settings],
) -> ForgetOut:
    user_id = get_current_user_id_or_401(request, settings)
    removed = await graph.forget_student(user_id)
    _logger.info("graph_memory.forget_self user=%s nodes=%s", user_id, removed)
    return ForgetOut(user_id=user_id, removed_nodes=removed)


@router.delete(
    "/memory/{target_user_id}",
    status_code=status.HTTP_200_OK,
    response_model=ForgetOut,
    description="Удалить память о студенте (admin/superadmin)",
)
async def forget_student(
        request: Request,
        target_user_id: str,
        graph: FromDishka[GraphMemoryInterface],
        roles: FromDishka[HttpAdminRoleGateway],
        settings: FromDishka[Settings],
) -> ForgetOut:
    caller = get_current_user_id_or_401(request, settings)
    if str(target_user_id) != caller:
        role = await roles.get_my_role(request.headers.get("Authorization") or "")
        if not is_admin(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Удаление чужой памяти доступно только admin/superadmin.",
            )
    removed = await graph.forget_student(str(target_user_id))
    _logger.info(
        "graph_memory.forget_other caller=%s target=%s nodes=%s",
        caller,
        target_user_id,
        removed,
    )
    return ForgetOut(user_id=str(target_user_id), removed_nodes=removed)


def _as_out(fact) -> MemoryFactOut:
    return MemoryFactOut(
        statement=fact.statement,
        relation=fact.relation,
        target=f"{fact.target.kind}:{fact.target.key}",
        source=fact.source.value,
        confidence=round(float(fact.confidence), 3),
        occurrences=int(fact.occurrences),
        recorded_at=fact.occurred_at.isoformat(),
        closed_at=fact.valid_until.isoformat() if fact.valid_until else "",
    )


__all__ = ["router"]
