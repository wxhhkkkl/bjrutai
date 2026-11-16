"""Invoice PDFs remain private, verified, purpose-bound objects."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest

from src.api.mall_deps import MallActor
from src.core.exceptions import ForbiddenException, ValidationException
from src.models.mall_base import utc_now
from src.models.mall_finance import MallInvoice, MallInvoiceRequest
from src.models.mall_operations import MallFile
from src.services.mall_file_service import (
    get_mall_file_access,
    issue_mall_upload_ticket,
    verify_mall_file,
)
from tests.conftest import seed_admin
from tests.unit.test_mall_aftersale_service import paid_order


@dataclass
class InvoiceObjectStore:
    metadata: dict | None

    async def issue_upload_ticket(self, **_kwargs):
        return {"uploadToken": "opaque-invoice-upload"}

    async def head(self, _object_key):
        return self.metadata

    async def finalize(self, source_key, destination_key):
        self.finalized = source_key, destination_key

    async def sign_get(self, _object_key, *, expires_seconds):
        self.expires_seconds = expires_seconds
        return "https://storage.invalid/short-lived-invoice"


@pytest.mark.asyncio
async def test_invoice_upload_rejects_wrong_mime_expiry_checksum_and_missing_storage(db_session):
    actor = MallActor("admin", 4101, frozenset({"mall.invoices.write"}))
    checksum = "a" * 64
    metadata = {"mime": "application/pdf", "size": 4096, "sha256": checksum}
    store = InvoiceObjectStore(metadata)

    with pytest.raises(ValidationException, match="文件类型"):
        await issue_mall_upload_ticket(
            db_session,
            actor=actor,
            purpose="invoice_pdf",
            object_key="mall/invoice/wrong-mime.png",
            mime="image/png",
            size=4096,
            sha256=checksum,
            storage=store,
        )
    with pytest.raises(ValidationException, match="凭据"):
        await issue_mall_upload_ticket(
            db_session,
            actor=actor,
            purpose="invoice_pdf",
            object_key="mall/invoice/no-storage.pdf",
            mime="application/pdf",
            size=4096,
            sha256=checksum,
            storage=None,
        )

    ticket = await issue_mall_upload_ticket(
        db_session,
        actor=actor,
        purpose="invoice_pdf",
        object_key="mall/invoice/expired.pdf",
        mime="application/pdf",
        size=4096,
        sha256=checksum,
        storage=store,
    )
    ticket.file.expires_at = utc_now() - timedelta(seconds=1)
    with pytest.raises(ValidationException, match="失效"):
        await verify_mall_file(
            db_session, actor=actor, file_id=ticket.file.id, storage=store
        )

    fresh = await issue_mall_upload_ticket(
        db_session,
        actor=actor,
        purpose="invoice_pdf",
        object_key="mall/invoice/checksum.pdf",
        mime="application/pdf",
        size=4096,
        sha256=checksum,
        storage=store,
    )
    store.metadata = {**metadata, "sha256": "b" * 64}
    with pytest.raises(ValidationException, match="实际上传校验"):
        await verify_mall_file(
            db_session, actor=actor, file_id=fresh.file.id, storage=store
        )
    assert fresh.file.status == "uploading"
    assert fresh.file.object_key == "mall/invoice/checksum.pdf"


@pytest.mark.asyncio
async def test_buyer_gets_only_bound_valid_invoice_file_through_short_private_link(
    db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    admin_id = await seed_admin(db_session, username="invoice-file-owner-" + uuid4().hex)
    file = MallFile(
        object_key=f"mall/verified/invoice/{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        order_id=order.id,
        mime="application/pdf",
        size=4096,
        sha256="c" * 64,
        status="bound",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(file)
    await db_session.flush()

    from src.models.mall_finance import MallPayment

    request = MallInvoiceRequest(
        request_no=f"IR{uuid4().hex[:28]}",
        order_id=order.id,
        buyer_user_id=buyer.actor_id,
        buyer_type="personal",
        title="个人",
        invoice_type="digital_normal",
        requested_goods_cent=order.goods_amount_cent,
        requested_freight_cent=order.freight_amount_cent,
        source_order_version=order.version,
        status="delivered",
        active_slot=1,
    )
    db_session.add(request)
    await db_session.flush()
    invoice = MallInvoice(
        request_id=request.id,
        order_id=order.id,
        kind="blue",
        seller_identity="测试销售主体",
        invoice_no=f"INV-{uuid4().hex[:20]}",
        issued_at=utc_now(),
        total_cent=order.paid_amount_cent,
        seller_snapshot={"name": "测试主体"},
        file_id=file.id,
        status="red_pending",
        recorded_by=admin_id,
    )
    db_session.add(invoice)
    await db_session.flush()

    actor = MallActor("user", buyer.actor_id, frozenset())
    store = InvoiceObjectStore(
        {"mime": file.mime, "size": file.size, "sha256": file.sha256}
    )
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(
            db_session, actor=actor, file_id=file.id, storage=store
        )

    invoice.status = "valid"
    with pytest.raises(ValidationException, match="凭据"):
        await get_mall_file_access(
            db_session, actor=actor, file_id=file.id, storage=None
        )
    result = await get_mall_file_access(
        db_session, actor=actor, file_id=file.id, storage=store
    )
    assert result == {"accessUrl": "https://storage.invalid/short-lived-invoice", "expiresIn": 60}
    assert store.expires_seconds == 60
    assert "objectKey" not in result and "taxNo" not in result
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(
            db_session,
            actor=MallActor("user", buyer.actor_id + 1000, frozenset()),
            file_id=file.id,
            storage=store,
        )

