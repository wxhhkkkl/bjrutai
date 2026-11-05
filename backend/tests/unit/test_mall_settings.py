"""One-store settings start closed and use optimistic version checks."""

import pytest

from src.core.exceptions import ConflictException, ForbiddenException


@pytest.mark.asyncio
async def test_settings_default_closed_and_purchase_requires_an_explicit_open(db_session):
    from src.services.mall_settings_service import get_mall_settings, require_mall_purchase_open

    settings = await get_mall_settings(db_session)
    assert not settings.enabled
    assert not settings.purchase_enabled
    with pytest.raises(ForbiddenException, match="未开放"):
        require_mall_purchase_open(settings)


@pytest.mark.asyncio
async def test_settings_update_checks_version_and_hides_warehouse_addresses(db_session):
    from src.services.mall_settings_service import (
        get_mall_settings,
        serialize_mall_settings,
        update_mall_settings,
    )

    settings = await get_mall_settings(db_session)
    initial_version = settings.version
    updated = await update_mall_settings(
        db_session,
        expected_version=initial_version,
        enabled=True,
        purchase_enabled=True,
        dispatch_address_snapshot={"address": "仓库完整地址"},
        return_address_snapshot={"address": "退货完整地址"},
    )
    assert updated.version == initial_version + 1
    public = serialize_mall_settings(updated)
    assert public["purchaseEnabled"]
    assert "dispatchAddress" not in public and "returnAddress" not in public

    with pytest.raises(ConflictException, match="版本"):
        await update_mall_settings(
            db_session,
            expected_version=0,
            enabled=False,
            purchase_enabled=False,
        )
