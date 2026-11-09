"""Read only the caller's own durable mall command result."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...api.mall_deps import MallActor, get_mall_buyer, require_mall_admin_permission
from ...core.error_handler import _build_response
from ...core.exceptions import ForbiddenException, NotFoundException
from ...models.mall_operations import MallCommand

router = APIRouter(prefix="/mall/commands", tags=["mall-commands"])
admin_router = APIRouter(prefix="/admin/mall/commands", tags=["admin-mall-commands"])


def _serialize(command: MallCommand) -> dict[str, object]:
    result = {
        "commandId": str(command.id),
        "status": command.status,
        "version": command.version,
    }
    if command.entity_id is not None:
        result["entityId"] = str(command.entity_id)
    return result


@router.get("/{command_id}")
async def get_my_mall_command(
    command_id: int,
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    command = await db.get(MallCommand, command_id)
    if command is None:
        raise NotFoundException(message="商城异步请求不存在")
    if command.actor_type != actor.actor_type or command.actor_id != actor.actor_id:
        raise ForbiddenException(message="只能访问本人商城资料")
    if command.action == "cancelMallOrder":
        from ...services.mall_order_action_service import cancel_progress
        from .mall_checkout import response

        return response(await cancel_progress(db, command))
    return _build_response(0, "success", _serialize(command))


@admin_router.get("/{command_id}")
async def get_admin_mall_command(
    command_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Only an original actor with the original action permission may replay."""
    if payload.get("user_type") != "admin":
        raise ForbiddenException(message="仅后台管理员可查询")
    command = await db.get(MallCommand, command_id)
    if command is None:
        raise NotFoundException(message="商城异步请求不存在")
    from ...services.mall_command_service import ADMIN_COMMAND_PERMISSIONS

    permission = ADMIN_COMMAND_PERMISSIONS.get(command.action)
    if permission is None:
        raise ForbiddenException(message="原动作权限未注册")
    actor = await require_mall_admin_permission(payload, db, permission)
    if command.actor_type != "admin" or command.actor_id != actor.actor_id:
        raise ForbiddenException(message="只能访问本人商城请求")
    if command.action == "cancelAdminMallOrder":
        from ...services.mall_order_action_service import cancel_progress
        from .mall_checkout import response

        return response(await cancel_progress(db, command))
    return _build_response(0, "success", _serialize(command))
