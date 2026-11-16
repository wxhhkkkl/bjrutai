"""Private mall files use purpose/owner checks and a real object HEAD result."""

from dataclasses import dataclass

import pytest

from src.api.mall_deps import MallActor
from src.core.exceptions import ForbiddenException, ValidationException


@dataclass
class FakeObjectStore:
    head_result: dict | None

    async def issue_upload_ticket(self, **_kwargs):
        return {"uploadToken": "opaque-upload-token"}

    async def head(self, _object_key):
        return self.head_result

    async def finalize(self, source_key, destination_key):
        self.finalized = (source_key, destination_key)

    async def sign_get(self, object_key, *, expires_seconds):
        return "https://storage.invalid/short-lived"


@pytest.mark.asyncio
async def test_changed_copy_is_rejected_and_does_not_bind_mutable_source(db_session):
    from src.services.mall_file_service import issue_mall_upload_ticket, verify_mall_file

    class ChangedCopy(FakeObjectStore):
        async def head(self, key):
            return (
                {**self.head_result, "sha256": "b" * 64}
                if key.startswith("mall/verified/")
                else self.head_result
            )

    owner = MallActor("user", 7, frozenset())
    store = ChangedCopy({"mime": "image/jpeg", "size": 32, "sha256": "a" * 64})
    ticket = await issue_mall_upload_ticket(
        db_session,
        actor=owner,
        purpose="aftersale_proof",
        object_key="mall/staging/proof",
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        storage=store,
    )
    with pytest.raises(ValidationException, match="转存校验"):
        await verify_mall_file(db_session, actor=owner, file_id=ticket.file.id, storage=store)
    assert ticket.file.object_key == "mall/staging/proof"
    assert ticket.file.status == "uploading"


@pytest.mark.asyncio
async def test_private_access_requires_owner_and_expired_upload_ticket(db_session):
    from datetime import timedelta

    from src.models.mall_base import utc_now
    from src.models.mall_operations import MallFile
    from src.services.mall_file_service import get_mall_file_access

    file = MallFile(
        object_key="mall/aftersale/proof.jpg",
        purpose="aftersale_proof",
        owner_actor_type="user",
        owner_actor_id=7,
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(file)
    await db_session.flush()
    actor = MallActor("user", 7, frozenset())
    with pytest.raises(ValidationException):
        await get_mall_file_access(
            db_session, actor=actor, file_id=file.id, storage=FakeObjectStore(None)
        )
    file.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(
            db_session,
            actor=MallActor("user", 8, frozenset()),
            file_id=file.id,
            storage=FakeObjectStore(None),
        )
    result = await get_mall_file_access(
        db_session,
        actor=actor,
        file_id=file.id,
        storage=FakeObjectStore({"mime": "image/jpeg", "size": 32, "sha256": "a" * 64}),
    )
    assert result["expiresIn"] == 60 and "objectKey" not in result


@pytest.mark.asyncio
async def test_file_ticket_and_head_verification_are_private_and_owner_scoped(db_session):
    from src.services.mall_file_service import issue_mall_upload_ticket, verify_mall_file

    owner = MallActor(actor_type="user", actor_id=7, permissions=frozenset())
    storage = FakeObjectStore(
        {
            "mime": "image/jpeg",
            "size": 32,
            "sha256": "a" * 64,
        }
    )
    ticket = await issue_mall_upload_ticket(
        db_session,
        actor=owner,
        purpose="aftersale_proof",
        object_key="mall/aftersale/file-1.jpg",
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        storage=storage,
    )
    assert ticket.upload_token == "opaque-upload-token"
    assert not hasattr(ticket, "file_url")

    verified = await verify_mall_file(
        db_session, actor=owner, file_id=ticket.file.id, storage=storage
    )
    assert verified.status == "verified"
    assert verified.object_key.startswith("mall/verified/")
    assert storage.finalized[0] == "mall/aftersale/file-1.jpg"
    from src.services.mall_file_service import get_mall_file_access

    assert (
        await get_mall_file_access(db_session, actor=owner, file_id=verified.id, storage=storage)
    )["expiresIn"] == 60
    with pytest.raises(ForbiddenException, match="本人"):
        await verify_mall_file(
            db_session,
            actor=MallActor(actor_type="user", actor_id=8, permissions=frozenset()),
            file_id=ticket.file.id,
            storage=storage,
        )


@pytest.mark.asyncio
async def test_file_upload_rejects_wrong_purpose_checksum_and_missing_credentials(db_session):
    from src.services.mall_file_service import issue_mall_upload_ticket, verify_mall_file

    buyer = MallActor(actor_type="user", actor_id=7, permissions=frozenset())
    with pytest.raises(ForbiddenException, match="用途"):
        await issue_mall_upload_ticket(
            db_session,
            actor=buyer,
            purpose="product_image",
            object_key="mall/product/file.jpg",
            mime="image/jpeg",
            size=32,
            sha256="a" * 64,
            storage=FakeObjectStore(None),
        )
    with pytest.raises(ValidationException, match="凭据"):
        await issue_mall_upload_ticket(
            db_session,
            actor=MallActor(
                actor_type="admin", actor_id=1, permissions=frozenset({"mall.invoices.write"})
            ),
            purpose="invoice_pdf",
            object_key="mall/invoice/file.pdf",
            mime="application/pdf",
            size=32,
            sha256="a" * 64,
            storage=None,
        )

    storage = FakeObjectStore({"mime": "image/jpeg", "size": 32, "sha256": "b" * 64})
    ticket = await issue_mall_upload_ticket(
        db_session,
        actor=buyer,
        purpose="aftersale_proof",
        object_key="mall/aftersale/file-2.jpg",
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        storage=storage,
    )
    with pytest.raises(ValidationException, match="校验"):
        await verify_mall_file(db_session, actor=buyer, file_id=ticket.file.id, storage=storage)


@pytest.mark.asyncio
async def test_admin_upload_requires_domain_permission(db_session):
    from src.services.mall_file_service import issue_mall_upload_ticket

    with pytest.raises(ForbiddenException):
        await issue_mall_upload_ticket(
            db_session,
            actor=MallActor("admin", 1, frozenset({"mall.files.write"})),
            purpose="invoice_pdf",
            object_key="mall/invoice/test.pdf",
            mime="application/pdf",
            size=32,
            sha256="a" * 64,
            storage=FakeObjectStore(None),
        )


@pytest.mark.asyncio
async def test_attribution_evidence_file_requires_its_domain_permission(db_session):
    from src.services.mall_file_service import issue_mall_upload_ticket

    with pytest.raises(ForbiddenException):
        await issue_mall_upload_ticket(
            db_session,
            actor=MallActor("admin", 2, frozenset({"mall.files.write"})),
            purpose="attribution_evidence",
            object_key="mall/attribution/evidence-denied.pdf",
            mime="application/pdf",
            size=64,
            sha256="a" * 64,
            storage=FakeObjectStore(None),
        )
    ticket = await issue_mall_upload_ticket(
        db_session,
        actor=MallActor("admin", 2, frozenset({"mall.attribution.write"})),
        purpose="attribution_evidence",
        object_key="mall/attribution/evidence.pdf",
        mime="application/pdf",
        size=64,
        sha256="a" * 64,
        storage=FakeObjectStore(None),
    )
    assert ticket.file.purpose == "attribution_evidence"


@pytest.mark.asyncio
async def test_bound_invoice_file_uses_order_buyer_not_uploading_admin(db_session):
    from datetime import timedelta

    from src.models.mall_base import utc_now
    from src.models.mall_finance import MallInvoice
    from src.models.mall_operations import MallFile
    from src.models.mall_trade import MallOrder
    from src.services.mall_file_service import get_mall_file_access
    from tests.conftest import seed_user

    buyer_id = await seed_user(db_session, user_type="personal")
    order = MallOrder(
        order_no="invoice-file-test",
        buyer_user_id=buyer_id,
        goods_amount_cent=100,
        payable_amount_cent=100,
        expires_at=utc_now(),
    )
    db_session.add(order)
    await db_session.flush()
    file = MallFile(
        object_key="mall/invoice/bound.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=99,
        order_id=order.id,
        mime="application/pdf",
        size=32,
        sha256="a" * 64,
        status="bound",
        expires_at=utc_now() - timedelta(minutes=1),
    )
    db_session.add(file)
    await db_session.flush()
    store = FakeObjectStore({"mime": "application/pdf", "size": 32, "sha256": "a" * 64})
    actor = MallActor("user", buyer_id, frozenset())
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(db_session, actor=actor, file_id=file.id, storage=store)
    db_session.add(
        MallInvoice(
            request_id=1,
            order_id=order.id,
            kind="blue",
            seller_identity="test",
            invoice_no="TEST-INVOICE",
            issued_at=utc_now(),
            total_cent=100,
            file_id=file.id,
            recorded_by=99,
        )
    )
    await db_session.flush()
    result = await get_mall_file_access(db_session, actor=actor, file_id=file.id, storage=store)
    assert result["expiresIn"] == 60
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(
            db_session,
            actor=MallActor("user", buyer_id + 1, frozenset()),
            file_id=file.id,
            storage=store,
        )


@pytest.mark.asyncio
async def test_admin_may_access_only_proofs_attached_to_an_aftersale(db_session, monkeypatch):
    from datetime import timedelta

    from sqlalchemy import select

    from src.models.mall_base import utc_now
    from src.models.mall_operations import MallFile
    from src.schemas.mall_aftersale import AftersaleCreate
    from src.services.mall_aftersale_service import apply_aftersale
    from src.services.mall_file_service import get_mall_file_access
    from tests.unit.test_mall_aftersale_service import paid_order

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    file = MallFile(
        object_key="mall/verified/aftersale-proof.jpg",
        purpose="aftersale_proof",
        owner_actor_type="user",
        owner_actor_id=buyer.actor_id,
        order_id=order.id,
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(minutes=1),
    )
    db_session.add(file)
    await db_session.flush()
    aftersale = await apply_aftersale(
        db_session,
        buyer,
        AftersaleCreate(
            orderId=str(order.id),
            expectedOrderVersion=order.version,
            method="refund_only",
            items=[{"orderItemId": str(items[1].id), "quantity": 1}],
            reason="包装损坏",
            proofFileIds=[str(file.id)],
        ),
        key="proof-access-aftersale-001",
    )
    reviewer = MallActor("admin", 9, frozenset({"mall.files.read", "mall.aftersales.read"}))
    storage = FakeObjectStore({"mime": "image/jpeg", "size": 32, "sha256": "a" * 64})
    result = await get_mall_file_access(
        db_session, actor=reviewer, file_id=file.id, storage=storage
    )
    assert result["accessUrl"] == "https://storage.invalid/short-lived"

    detached = MallFile(
        object_key="mall/verified/detached-proof.jpg",
        purpose="aftersale_proof",
        owner_actor_type="user",
        owner_actor_id=buyer.actor_id,
        order_id=order.id,
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(minutes=1),
    )
    db_session.add(detached)
    await db_session.flush()
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(db_session, actor=reviewer, file_id=detached.id, storage=storage)
    without_aftersale_scope = MallActor("admin", 10, frozenset({"mall.files.read"}))
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(
            db_session, actor=without_aftersale_scope, file_id=file.id, storage=storage
        )
    assert (
        await db_session.scalar(
            select(MallFile.id).where(MallFile.id == file.id, MallFile.order_id == order.id)
        )
        == file.id
    )
    assert aftersale.proof_file_ids == [file.id]
