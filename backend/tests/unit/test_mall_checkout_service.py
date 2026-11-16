from datetime import timedelta

import pytest

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.models.mall_base import utc_now
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


@pytest.mark.parametrize(
    "field,value",
    [
        ("phone", None),
        ("phone", "138****1234"),
        ("addressLine", ""),
        ("recipientName", " "),
        ("regionCodes", ["11", "110100", "110101"]),
    ],
)
def test_address_patch_rejects_null_masked_values_and_incomplete_fields(field, value):
    from pydantic import ValidationError

    from src.schemas.mall_checkout import AddressPatch

    with pytest.raises(ValidationError):
        AddressPatch(**{"expectedVersion": 1, field: value})


def test_quote_rejects_duplicate_lines_and_boolean_quantities():
    from pydantic import ValidationError

    from src.schemas.mall_checkout import QuoteRequest

    with pytest.raises(ValidationError):
        QuoteRequest(addressId="1", items=[{"skuId": "1", "quantity": 1}] * 2)
    with pytest.raises(ValidationError):
        QuoteRequest(addressId="1", items=[{"skuId": "1", "quantity": True}])


def test_consent_downgrade_refuses_existing_facts(monkeypatch):
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock

    path = Path(__file__).resolve().parents[2] / "migrations/versions/027_mall_consent_scenes.py"
    spec = importlib.util.spec_from_file_location("mall_consent_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    operations = MagicMock()
    operations.get_bind.return_value.scalar.return_value = 1
    monkeypatch.setattr(migration, "op", operations)
    with pytest.raises(RuntimeError, match="lossy downgrade"):
        migration.downgrade()
    operations.alter_column.assert_not_called()


@pytest.mark.asyncio
async def test_address_default_lock_masking_and_patch_omission_preserve_original(db_session):
    from src.schemas.mall_checkout import AddressPatch, AddressWrite
    from src.services.mall_address_service import save_address, serialize_address

    actor, _, _, _ = await checkout_seed(db_session)
    one = await save_address(db_session, actor, AddressWrite(**ADDRESS, isDefault=True))
    two = await save_address(db_session, actor, AddressWrite(**ADDRESS, isDefault=True))
    assert two.is_default and not one.is_default
    assert one.version == 2
    await save_address(
        db_session,
        actor,
        AddressPatch(expectedVersion=two.version, recipientName="新收件人"),
        address_id=two.id,
    )
    assert two.phone == ADDRESS["phone"] and two.address_line == ADDRESS["addressLine"]
    public = serialize_address(two)
    assert public["phoneMasked"] == "138****1234"
    assert "phone" not in public and "addressLine" not in public
    assert ADDRESS["addressLine"] not in str(public)
    with pytest.raises(NotFoundException):
        await save_address(
            db_session,
            MallActor("user", actor.actor_id + 999, frozenset()),
            AddressPatch(expectedVersion=two.version),
            address_id=two.id,
        )


@pytest.mark.asyncio
async def test_address_consent_is_new_purpose_not_reused_registration(db_session):
    from src.models.consent import ConsentRecord
    from src.schemas.mall_checkout import AddressWrite
    from src.services.mall_address_service import save_address

    actor, _, _, _ = await checkout_seed(db_session)
    with pytest.raises(ConflictException, match="告知"):
        await save_address(db_session, actor, AddressWrite(**{**ADDRESS, "consentVersion": "old"}))
    address = await save_address(db_session, actor, AddressWrite(**ADDRESS))
    consent = await db_session.get(ConsentRecord, address.consent_record_id)
    assert consent.scene.value == "mall_address"
    assert consent.confirmed and consent.scopes == {
        "mall_recipient": True,
        "mall_address": True,
        "recipient_name": True,
        "recipient_phone": True,
        "recipient_region": True,
        "delivery_address": True,
    }
    from src.services.mall_consent_service import MALL_NOTICE_COPY_VERSION

    assert consent.agreement_versions == {
        "mall_policy": "mall-test-v1",
        "mall_recipient_notice": "mall-test-v1",
        "mall_notice_copy": MALL_NOTICE_COPY_VERSION,
    }


@pytest.mark.asyncio
async def test_cart_add_merge_is_not_inventory_reservation_and_invalidates(db_session):
    from src.schemas.mall_checkout import BuyItem, CartPatch
    from src.services.mall_cart_service import add_cart_item, serialize_cart_item, update_cart_item

    actor, _, product, skus = await checkout_seed(db_session)
    row = await add_cart_item(db_session, actor, BuyItem(skuId=str(skus[0].id), quantity=2))
    merged = await add_cart_item(db_session, actor, BuyItem(skuId=str(skus[0].id), quantity=3))
    assert row.id == merged.id and merged.quantity == 5
    assert skus[0].available_qty == 10 and skus[0].reserved_qty == 0
    product.status = "off_sale"
    await db_session.flush()
    result = await serialize_cart_item(db_session, row)
    assert not result["valid"] and result["invalidReason"] == "product_unavailable"
    with pytest.raises(ConflictException):
        await update_cart_item(db_session, actor, row.id, CartPatch(expectedVersion=1, quantity=4))


@pytest.mark.asyncio
async def test_quote_charges_one_freight_and_binds_buyer_without_pii(db_session, monkeypatch):
    from src.core.config import get_settings
    from src.schemas.mall_checkout import AddressWrite, QuoteRequest
    from src.services.mall_address_service import save_address
    from src.services.mall_checkout_service import quote_order, validate_quote

    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    actor, _, _, skus = await checkout_seed(db_session)
    address = await save_address(db_session, actor, AddressWrite(**ADDRESS))
    body = QuoteRequest(
        addressId=str(address.id),
        items=[
            {"skuId": str(skus[0].id), "quantity": 1},
            {"skuId": str(skus[1].id), "quantity": 2},
        ],
    )
    result = await quote_order(db_session, actor, body)
    assert (
        result["goodsAmountCent"],
        result["freightAmountCent"],
        result["payableAmountCent"],
    ) == (20000, 1000, 21000)
    assert ADDRESS["phone"] not in str(result) and ADDRESS["addressLine"] not in str(result)
    await validate_quote(db_session, actor, result["quoteToken"])
    with pytest.raises(ConflictException):
        await validate_quote(
            db_session, MallActor("user", actor.actor_id + 1, frozenset()), result["quoteToken"]
        )
    assert all(s.available_qty == 10 and s.reserved_qty == 0 for s in skus)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "price",
        "address",
        "policy",
        "expired",
        "tampered",
        "blocked",
        "off_sale",
        "stock",
        "closed",
        "consent_revoked",
    ],
)
async def test_quote_rejects_changed_or_untrusted_facts(db_session, monkeypatch, change):
    from src.core.config import get_settings
    from src.models.consent import ConsentRecord
    from src.schemas.mall_checkout import AddressWrite, QuoteRequest
    from src.services import mall_checkout_service as checkout
    from src.services.mall_address_service import save_address

    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    actor, settings, product, skus = await checkout_seed(db_session)
    address = await save_address(db_session, actor, AddressWrite(**ADDRESS))
    body = QuoteRequest(
        addressId=str(address.id), items=[{"skuId": str(skus[0].id), "quantity": 1}]
    )
    result = await checkout.quote_order(db_session, actor, body)
    token = result["quoteToken"]
    if change == "price":
        skus[0].sale_price_cent += 1
        skus[0].version += 1
    elif change == "address":
        address.address_line = "另一个虚构地址"
        address.version += 1
    elif change == "policy":
        settings.freight_cent += 100
        settings.version += 1
    elif change == "expired":
        monkeypatch.setattr(checkout, "utc_now", lambda: utc_now() + timedelta(seconds=301))
    elif change == "tampered":
        token = ("A" if token[0] != "A" else "B") + token[1:]
    elif change == "blocked":
        settings.blocked_regions = [address.province_code]
    elif change == "off_sale":
        product.status = "off_sale"
    elif change == "stock":
        skus[0].available_qty = 0
    elif change == "closed":
        settings.purchase_enabled = False
    elif change == "consent_revoked":
        (await db_session.get(ConsentRecord, address.consent_record_id)).status = "revoked"
    await db_session.flush()
    with pytest.raises((ConflictException, ForbiddenException)):
        await checkout.validate_quote(db_session, actor, token)
