"""Cross-buyer isolation for mall orders, invoices and private evidence."""

from datetime import timedelta
from uuid import uuid4

import pytest

from src.models.mall_base import utc_now
from src.models.mall_operations import MallFile
from src.models.user import ActivationStatus
from tests.conftest import auth_header, make_access_token, seed_user
from tests.contract.test_mall_invoices import create_request
from tests.unit.test_mall_aftersale_service import paid_order


class PrivateStore:
    def __init__(self):
        self.read_attempts = 0

    async def head(self, _object_key):
        self.read_attempts += 1
        return {"mime": "application/pdf", "size": 128, "sha256": "a" * 64}

    async def sign_get(self, _object_key, *, expires_seconds):
        assert expires_seconds == 60
        return "https://storage.invalid/private"


@pytest.mark.asyncio
async def test_second_buyer_cannot_read_order_invoice_or_private_file(
    client, db_session, monkeypatch
):
    from src.api.v1.mall_files import get_mall_store
    from src.main import app

    owner, order, _, _ = await paid_order(db_session, monkeypatch)
    invoice = await create_request(
        client,
        owner,
        order,
        key="privacy-boundary-invoice-create-001",
    )
    other_id = await seed_user(
        db_session,
        user_type="personal",
        openid=f"mall-privacy-other-{uuid4().hex}",
        activation_status=ActivationStatus.ACTIVE.value,
    )
    file = MallFile(
        object_key=f"mall/invoice_pdf/user/{owner.actor_id}/{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="user",
        owner_actor_id=owner.actor_id,
        order_id=order.id,
        mime="application/pdf",
        size=128,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(file)
    await db_session.commit()

    store = PrivateStore()
    app.dependency_overrides[get_mall_store] = lambda: store
    try:
        headers = auth_header(make_access_token(user_id=other_id, user_type="personal"))
        assert (
            await client.get(f"/api/v1/mall/orders/{order.id}", headers=headers)
        ).status_code == 404
        assert (
            await client.get(
                f"/api/v1/mall/invoice-requests/{invoice['id']}", headers=headers
            )
        ).status_code == 404
        assert (
            await client.get(
                f"/api/v1/mall/orders/{order.id}/invoices", headers=headers
            )
        ).status_code == 404
        file_access = await client.get(
            f"/api/v1/mall/files/{file.id}/access", headers=headers
        )
        assert file_access.status_code == 403
        assert store.read_attempts == 0
        assert "orderNo" not in file_access.text and "taxNo" not in file_access.text
    finally:
        app.dependency_overrides.pop(get_mall_store, None)

