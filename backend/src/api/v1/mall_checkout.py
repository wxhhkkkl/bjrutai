"""Private buyer address/cart writes and non-reserving quotes."""

from fastapi import APIRouter, Depends, Header, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...core.error_handler import _build_response
from ...core.exceptions import ConflictException
from ...core.config import get_settings
from ...schemas.mall_catalog import VersionAction
from ...schemas.mall_checkout import AddressPatch, AddressWrite, BuyItem, CartPatch, QuoteRequest
from ...services import mall_address_service as addresses
from ...services import mall_cart_service as cart
from ...services.mall_checkout_service import quote_order
from ...services.mall_command_service import complete_mall_command, reserve_mall_command
from ...services.mall_settings_service import get_mall_settings

router = APIRouter(prefix="/mall", tags=["mall-checkout"])


def response(data, *, status_code=200):
    return JSONResponse(
        _build_response(0, "success", data),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


async def mutate(db, actor, action, key, payload, entity_type, apply, reload, project):
    try:
        intent = await reserve_mall_command(
            db, actor=actor, action=action, key=key, payload=payload
        )
        if intent.created:
            row = await apply()
            await complete_mall_command(db, intent, entity_type=entity_type, entity_id=row.id)
        else:
            if intent.command.status != "completed":
                raise ConflictException(message="原操作仍在处理中")
            row = await reload(intent.command.entity_id)
        await db.commit()
        return response(await project(row))
    except Exception:
        await db.rollback()
        raise


@router.get("/addresses", operation_id="listMallAddresses")
async def list_addresses(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    result = await addresses.list_addresses(db, actor, cursor=cursor, page_size=page_size)
    await db.commit()
    return response(result)


@router.get("/checkout/settings", operation_id="getMallCheckoutSettings")
async def checkout_settings(db: AsyncSession = Depends(get_db)):
    """Expose only the policy version and pricing rule needed to start checkout."""
    settings = await get_mall_settings(db)
    runtime = get_settings()
    result = {
        "purchasingAvailable": bool(
            runtime.mall_enabled
            and runtime.mall_purchase_enabled
            and settings.enabled
            and settings.purchase_enabled
        ),
        "freightMode": settings.freight_mode,
        "freightCent": settings.freight_cent,
        "policyVersion": settings.policy_versions.get("policy", ""),
    }
    await db.commit()
    return response(result)


async def address_write(db, actor, action, key, body, identity=None):
    async def apply():
        return await addresses.save_address(db, actor, body, address_id=identity)

    async def reload(saved_id):
        return await addresses.owned_address(db, actor, saved_id, include_archived=True)

    async def project(row):
        return addresses.serialize_address(row)

    payload = body.model_dump(mode="json", exclude_unset=True)
    if identity:
        payload["addressId"] = identity
    return await mutate(db, actor, action, key, payload, "mall_address", apply, reload, project)


@router.post("/addresses", operation_id="createMallAddress")
async def create_address(
    body: AddressWrite,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    return await address_write(db, actor, "createMallAddress", key, body)


@router.patch("/addresses/{addressId}", operation_id="updateMallAddress")
async def update_address(
    body: AddressPatch,
    identity: int = Path(alias="addressId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    return await address_write(db, actor, "updateMallAddress", key, body, identity)


@router.post("/addresses/{addressId}/archive", operation_id="archiveMallAddress")
async def archive_address(
    body: VersionAction,
    identity: int = Path(alias="addressId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    async def apply():
        return await addresses.archive_address(db, actor, identity, body.expected_version)

    async def reload(saved_id):
        return await addresses.owned_address(db, actor, saved_id, include_archived=True)

    async def project(row):
        return {"id": str(row.id), "status": "archived", "version": row.version}

    return await mutate(
        db,
        actor,
        "archiveMallAddress",
        key,
        {**body.model_dump(), "addressId": identity},
        "mall_address",
        apply,
        reload,
        project,
    )


@router.get("/cart", operation_id="getMallCart")
async def get_cart(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    return response(await cart.list_cart(db, actor, cursor=cursor, page_size=page_size))


async def cart_write(db, actor, action, key, body, identity=None):
    async def apply():
        return (
            await cart.update_cart_item(db, actor, identity, body)
            if identity
            else await cart.add_cart_item(db, actor, body)
        )

    async def reload(saved_id):
        return await cart.owned_cart_item(db, actor, saved_id)

    async def project(row):
        return await cart.serialize_cart_item(db, row)

    payload = body.model_dump(mode="json")
    if identity:
        payload["cartItemId"] = identity
    return await mutate(db, actor, action, key, payload, "mall_cart_item", apply, reload, project)


@router.post("/cart", operation_id="addMallCartItem")
async def add_cart(
    body: BuyItem,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    return await cart_write(db, actor, "addMallCartItem", key, body)


@router.patch("/cart/{cartItemId}", operation_id="updateMallCartItem")
async def update_cart(
    body: CartPatch,
    identity: int = Path(alias="cartItemId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    return await cart_write(db, actor, "updateMallCartItem", key, body, identity)


@router.post("/cart/{cartItemId}/remove", operation_id="removeMallCartItem")
async def remove_cart(
    body: VersionAction,
    identity: int = Path(alias="cartItemId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        intent = await reserve_mall_command(
            db,
            actor=actor,
            action="removeMallCartItem",
            key=key,
            payload={**body.model_dump(), "cartItemId": identity},
        )
        if intent.created:
            await cart.remove_cart_item(db, actor, identity, body.expected_version)
            await complete_mall_command(
                db, intent, entity_type="mall_cart_item", entity_id=identity
            )
        elif intent.command.status != "completed":
            raise ConflictException(message="原操作仍在处理中")
        await db.commit()
        return response(
            {"id": str(identity), "status": "removed", "version": body.expected_version + 1}
        )
    except Exception:
        await db.rollback()
        raise


@router.post("/checkout/quote", operation_id="quoteMallOrder")
async def quote(
    body: QuoteRequest,
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await quote_order(db, actor, body)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise
