"""Mall audit entries keep the administrator identity out of users.id."""

import pytest
from sqlalchemy import select

from src.models.audit import AuditLog
from tests.conftest import seed_admin


@pytest.mark.asyncio
async def test_admin_mall_audit_uses_detail_identity_and_redacts_personal_values(db_session):
    from src.api.mall_deps import MallActor
    from src.services.mall_audit_service import record_mall_admin_audit

    admin_id = await seed_admin(db_session)
    log = await record_mall_admin_audit(
        db_session,
        actor=MallActor(actor_type="admin", actor_id=admin_id, permissions=frozenset()),
        action="mall_order_close",
        entity_type="mall_order",
        entity_id="MO202611040001",
        detail={
            "reasonCode": "buyer_request",
            "phone": "13800138000",
            "address": "北京市朝阳区示例路1号",
            "nested": {"taxNo": "911100001", "safe": "kept"},
        },
    )
    await db_session.flush()

    stored = (await db_session.execute(select(AuditLog).where(AuditLog.id == log.id))).scalar_one()
    assert stored.user_id is None
    assert stored.detail == {
        "adminAccountId": str(admin_id),
        "reasonCode": "buyer_request",
        "nested": {"safe": "kept"},
    }
