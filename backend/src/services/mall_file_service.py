"""Purpose-scoped upload intents and verified private object metadata."""

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor
from ..core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ..models.mall_base import utc_now
from ..models.mall_finance import MallInvoice
from ..models.mall_operations import MallFile
from ..models.mall_trade import MallOrder


class MallObjectStore(Protocol):
    async def issue_upload_ticket(self, **kwargs: Any) -> dict: ...
    async def head(self, object_key: str) -> dict | None: ...
    async def sign_get(self, object_key: str, *, expires_seconds: int) -> str: ...


async def get_mall_file_access(
    db: AsyncSession,
    *,
    actor: MallActor,
    file_id: int,
    storage: MallObjectStore | None,
) -> dict:
    file = await db.get(MallFile, file_id, populate_existing=True)
    if file is None:
        raise NotFoundException(message="文件不存在")
    owns_file = file.owner_actor_type == actor.actor_type and file.owner_actor_id == actor.actor_id
    bound_access = False
    if file.status == "bound" and actor.actor_type == "admin":
        bound_access = True  # domain permission below still required
    if (
        file.status == "bound"
        and actor.actor_type == "user"
        and file.purpose == "invoice_pdf"
        and file.order_id is not None
    ):
        order = await db.get(MallOrder, file.order_id, populate_existing=True)
        invoice = (
            await db.execute(
                select(MallInvoice.id).where(
                    MallInvoice.file_id == file.id,
                    MallInvoice.order_id == file.order_id,
                    MallInvoice.status == "valid",
                )
            )
        ).scalar_one_or_none()
        bound_access = bool(order and order.buyer_user_id == actor.actor_id and invoice)
    if not owns_file and not bound_access:
        raise ForbiddenException(message="只能访问本人文件")
    if actor.actor_type == "admin":
        required = {
            "product_image": "mall.products.read",
            "invoice_pdf": "mall.invoices.read",
            "aftersale_proof": "mall.aftersales.read",
            "reconciliation_evidence": "mall.reconciliations.read",
            "finance_export": "mall.finance.export",
        }.get(file.purpose)
        if required not in actor.permissions or "mall.files.read" not in actor.permissions:
            raise ForbiddenException(message="缺少文件用途权限")
    if file.status not in {"verified", "bound"} or file.expires_at > utc_now():
        raise ValidationException(message="文件尚未核验或上传凭证尚未过期")
    if storage is None:
        raise ValidationException(message="私有存储凭据未配置")
    actual = await storage.head(file.object_key)
    if not actual or any(
        actual.get(field) != getattr(file, field) for field in ("mime", "size", "sha256")
    ):
        raise ValidationException(message="文件内容已变化，请重新核验")
    return {
        "accessUrl": await storage.sign_get(file.object_key, expires_seconds=60),
        "expiresIn": 60,
    }


@dataclass(frozen=True)
class MallUploadTicket:
    file: MallFile
    upload_token: str


_LIMITS = {
    "product_image": ({"image/jpeg", "image/png", "image/webp"}, 5 * 1024 * 1024),
    "aftersale_proof": ({"image/jpeg", "image/png"}, 5 * 1024 * 1024),
    "invoice_pdf": ({"application/pdf"}, 10 * 1024 * 1024),
    "reconciliation_evidence": ({"image/jpeg", "image/png", "application/pdf"}, 10 * 1024 * 1024),
    "finance_export": ({"text/csv"}, 10 * 1024 * 1024),
}


def require_file_write_purpose(actor: MallActor, purpose: str):
    if actor.actor_type == "admin":
        permission = {
            "product_image": "mall.products.write",
            "invoice_pdf": "mall.invoices.write",
            "aftersale_proof": "mall.aftersales.review",
            "reconciliation_evidence": "mall.reconciliations.write",
        }.get(purpose)
        if permission not in actor.permissions:
            raise ForbiddenException(message="缺少文件用途权限")


async def issue_mall_upload_ticket(
    db: AsyncSession,
    *,
    actor: MallActor,
    purpose: str,
    object_key: str,
    mime: str,
    size: int,
    sha256: str,
    storage: MallObjectStore | None,
) -> MallUploadTicket:
    """Create an owned intent; API callers must generate the object key server-side."""
    if purpose not in _LIMITS or (actor.actor_type == "user" and purpose != "aftersale_proof"):
        raise ForbiddenException(message="不允许此文件用途")
    if actor.actor_type not in {"admin", "user"}:
        raise ForbiddenException(message="不允许此文件用途")
    require_file_write_purpose(actor, purpose)
    types, limit = _LIMITS[purpose]
    if mime not in types or not 0 < size <= limit or not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValidationException(message="文件类型、大小或校验摘要不合法")
    if not object_key.startswith("mall/") or ".." in object_key or len(object_key) > 512:
        raise ValidationException(message="文件对象路径不合法")
    if storage is None:
        raise ValidationException(message="私有存储凭据未配置")
    ticket = await storage.issue_upload_ticket(
        object_key=object_key, mime=mime, size=size, sha256=sha256
    )
    file = MallFile(
        object_key=object_key,
        purpose=purpose,
        owner_actor_type=actor.actor_type,
        owner_actor_id=actor.actor_id,
        mime=mime,
        size=size,
        sha256=sha256,
        status="uploading",
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db.add(file)
    await db.flush()
    return MallUploadTicket(file=file, upload_token=ticket["uploadToken"])


async def verify_mall_file(
    db: AsyncSession,
    *,
    actor: MallActor,
    file_id: int,
    storage: MallObjectStore | None,
) -> MallFile:
    file = await db.get(MallFile, file_id)
    if file is None:
        raise NotFoundException(message="文件不存在")
    if file.owner_actor_type != actor.actor_type or file.owner_actor_id != actor.actor_id:
        raise ForbiddenException(message="只能核验本人文件")
    require_file_write_purpose(actor, file.purpose)
    if file.status != "uploading" or file.expires_at <= utc_now():
        raise ValidationException(message="上传凭证已失效或文件已核验")
    if storage is None:
        raise ValidationException(message="私有存储凭据未配置")
    actual = await storage.head(file.object_key)
    if not actual or any(
        actual.get(field) != getattr(file, field) for field in ("mime", "size", "sha256")
    ):
        raise ValidationException(message="文件实际上传校验失败")
    file.status = "verified"
    file.version += 1
    await db.flush()
    return file
