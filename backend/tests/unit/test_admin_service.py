"""Unit tests for admin account protections.

TDD: Tests written FIRST, expected to FAIL until protections are implemented.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_access_token, seed_admin


def _admin_auth(user_id: int = 1) -> dict:
    token = make_access_token(
        user_id=user_id,
        user_type="admin",
        permissions=["accounts.read", "accounts.write"],
    )
    return {"Authorization": f"Bearer {token}"}


# ────────────────────────────────────────────────────────────────
# T010: Disable default admin → error
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_disable_default_admin_returns_error(
    db_session: AsyncSession, client: AsyncClient
):
    """Disabling the default admin (username="admin") must be rejected."""
    admin_id = await seed_admin(db_session, username="admin")

    resp = await client.post(
        f"/api/v1/admin/accounts/{admin_id}/disable",
        headers=_admin_auth(),
    )
    data = resp.json()
    assert resp.status_code == 400
    assert data.get("code") == 40303
