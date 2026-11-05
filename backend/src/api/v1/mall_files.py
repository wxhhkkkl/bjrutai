"""Private file contracts; signed responses are never cached or persisted."""

import uuid
from datetime import timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...core.config import get_settings
from ...core.error_handler import _build_response
from ...core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ...integrations.cos_client import MallCOSStore, get_cos_client
from ...models.mall_base import utc_now
from ...models.mall_operations import MallFile
from ...models.mall_trade import MallOrder
from ...services.mall_audit_service import record_mall_admin_audit
from ...services.mall_command_service import complete_mall_command, reserve_mall_command
from ...services.mall_file_service import (
    get_mall_file_access,
    issue_mall_upload_ticket,
    require_file_write_purpose,
    verify_mall_file,
)


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Literal["product_image", "aftersale_proof", "invoice_pdf", "reconciliation_evidence"]
    order_id: str | None = Field(default=None, alias="orderId", pattern=r"^[1-9][0-9]*$")
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    content_type: Literal["image/jpeg", "image/png", "application/pdf"] = Field(alias="contentType")
    file_size: int = Field(alias="fileSize", ge=1, le=10485760)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def get_mall_store():
    if not get_settings().mall_storage_outbound_enabled:
        raise ForbiddenException(message="商城存储出站未开启")
    return MallCOSStore(get_cos_client(), outbound_enabled=True)


def response(data):
    return JSONResponse(_build_response(0, "success", data), headers={"Cache-Control": "no-store"})


async def audit_file(db, actor, action, file_id):
    if actor.actor_type == "admin":
        await record_mall_admin_audit(
            db,
            actor=actor,
            action=action,
            entity_type="mall_file",
            entity_id=str(file_id),
            detail={},
        )
    else:
        from ...models.audit import AuditLog

        db.add(
            AuditLog(
                user_id=actor.actor_id,
                action=action,
                entity_type="mall_file",
                entity_id=str(file_id),
                detail={},
            )
        )


def build_file_router(prefix, buyer_dep, write_dep, read_dep, admin=False):
    router = APIRouter(prefix=prefix, tags=["mall-files"])

    @router.post(
        "/upload-ticket",
        operation_id="getAdminMallUploadTicket" if admin else "getBuyerMallUploadTicket",
    )
    async def upload(
        body: UploadRequest,
        key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
        actor: MallActor = Depends(write_dep),
        db: AsyncSession = Depends(get_db),
        storage=Depends(get_mall_store),
    ):
        try:
            require_file_write_purpose(actor, body.purpose)
            if body.order_id:
                order = await db.get(MallOrder, int(body.order_id))
                if order is None:
                    raise NotFoundException(message="订单不存在")
                if (
                    actor.actor_type == "user"
                    and order.buyer_user_id != actor.actor_id
                    or actor.actor_type == "admin"
                    and "mall.orders.read" not in actor.permissions
                ):
                    raise ForbiddenException(message="无权访问关联订单")
            action = "getAdminMallUploadTicket" if admin else "getBuyerMallUploadTicket"
            intent = await reserve_mall_command(
                db, actor=actor, action=action, key=key, payload=body.model_dump(mode="json")
            )
            if intent.created:
                ticket = await issue_mall_upload_ticket(
                    db,
                    actor=actor,
                    purpose=body.purpose,
                    object_key=f"mall/{body.purpose}/{actor.actor_type}/{actor.actor_id}/{uuid.uuid4().hex}",
                    mime=body.content_type,
                    size=body.file_size,
                    sha256=body.sha256,
                    storage=storage,
                )
                file, url = ticket.file, ticket.upload_token
                file.order_id = int(body.order_id) if body.order_id else None
                await complete_mall_command(db, intent, entity_type="mall_file", entity_id=file.id)
            else:
                file = await db.get(MallFile, intent.command.entity_id)
                if (
                    file is None
                    or file.owner_actor_id != actor.actor_id
                    or file.owner_actor_type != actor.actor_type
                ):
                    raise ForbiddenException(message="文件所有权不匹配")
                remaining = int((file.expires_at - utc_now()).total_seconds())
                if remaining < 1 or file.status != "uploading":
                    raise ConflictException(message="上传凭证已失效，请重新申请")
                ticket = await storage.issue_upload_ticket(
                    object_key=file.object_key,
                    mime=file.mime,
                    size=file.size,
                    sha256=file.sha256,
                    expires_seconds=remaining,
                )
                url = ticket["uploadToken"]
            await audit_file(db, actor, "mall_file_upload_ticket", file.id)
            await db.commit()
            return response(
                {
                    "fileId": str(file.id),
                    "uploadUrl": url,
                    "expiresAt": file.expires_at.isoformat() + "Z",
                    "contentType": file.mime,
                }
            )
        except (ValueError, httpx.HTTPError) as exc:
            await db.rollback()
            raise ValidationException(message="私有存储暂不可用") from exc
        except Exception:
            await db.rollback()
            raise

    @router.post(
        "/{fileId}/verify", operation_id="verifyAdminMallFile" if admin else "verifyBuyerMallFile"
    )
    async def verify(
        file_id: int = Path(alias="fileId", gt=0),
        key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
        actor: MallActor = Depends(write_dep),
        db: AsyncSession = Depends(get_db),
        storage=Depends(get_mall_store),
    ):
        try:
            file = await db.get(MallFile, file_id)
            if file is None:
                raise NotFoundException(message="文件不存在")
            if file.owner_actor_id != actor.actor_id or file.owner_actor_type != actor.actor_type:
                raise ForbiddenException(message="只能核验本人文件")
            require_file_write_purpose(actor, file.purpose)
            intent = await reserve_mall_command(
                db,
                actor=actor,
                action="verifyAdminMallFile" if admin else "verifyBuyerMallFile",
                key=key,
                payload={"fileId": str(file_id)},
            )
            if intent.created:
                file = await verify_mall_file(db, actor=actor, file_id=file_id, storage=storage)
                await complete_mall_command(db, intent, entity_type="mall_file", entity_id=file_id)
            await audit_file(db, actor, "mall_file_verify", file.id)
            await db.commit()
            return response({"id": str(file.id), "status": file.status, "version": file.version})
        except (ValueError, httpx.HTTPError) as exc:
            await db.rollback()
            raise ValidationException(message="私有存储核验失败") from exc
        except Exception:
            await db.rollback()
            raise

    @router.get(
        "/{fileId}/access",
        operation_id="getAdminMallFileAccess" if admin else "getBuyerMallFileAccess",
    )
    async def access(
        file_id: int = Path(alias="fileId", gt=0),
        actor: MallActor = Depends(read_dep),
        db: AsyncSession = Depends(get_db),
        storage=Depends(get_mall_store),
    ):
        try:
            data = await get_mall_file_access(db, actor=actor, file_id=file_id, storage=storage)
            await audit_file(db, actor, "mall_file_access", file_id)
            await db.commit()
            return response(
                {
                    "fileId": str(file_id),
                    "accessUrl": data["accessUrl"],
                    "expiresAt": (utc_now() + timedelta(seconds=60)).isoformat() + "Z",
                }
            )
        except (ValueError, httpx.HTTPError) as exc:
            raise ValidationException(message="私有文件暂不可访问") from exc

    return router


router = build_file_router("/mall/files", get_mall_buyer, get_mall_buyer, get_mall_buyer)
