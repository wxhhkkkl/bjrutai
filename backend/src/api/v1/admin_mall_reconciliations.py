"""Administrative daily reconciliation and difference workflow routes."""

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...schemas.mall_aftersale import ReasonAction
from ...schemas.mall_reconciliation import DifferenceCreate, DifferenceUpdate, ReconciliationCreate
from ...services import mall_reconciliation_service as reconciliation
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/reconciliations", tags=["admin-mall-reconciliations"])
difference_router = APIRouter(prefix="/admin/mall/differences", tags=["admin-mall-reconciliations"])
read_reconciliations = require_mall_admin("mall.reconciliations.read")
write_reconciliations = require_mall_admin("mall.reconciliations.write")


@router.post("", operation_id="createMallReconciliation")
async def create_one(
    body: ReconciliationCreate,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    try:
        batch = await reconciliation.create_reconciliation(db, actor, body, key=key)
        result = reconciliation.serialize_reconciliation(batch, open_difference_count=0)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("", operation_id="listMallReconciliations")
async def list_all(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(read_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    result = await reconciliation.list_reconciliations(
        db, actor, cursor=cursor, page_size=page_size
    )
    await db.commit()
    return response(result)


@router.get("/{batchId}", operation_id="getMallReconciliation")
async def get_one(
    identity: int = Path(alias="batchId", gt=0),
    actor: MallActor = Depends(read_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    result = await reconciliation.get_reconciliation(db, actor, identity)
    await db.commit()
    return response(result)


@router.post("/{batchId}/differences", operation_id="addMallDifference")
async def add_one_difference(
    body: DifferenceCreate,
    batch_identity: int = Path(alias="batchId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    try:
        difference = await reconciliation.add_difference(db, actor, batch_identity, body, key=key)
        result = reconciliation.serialize_difference(difference)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("/{batchId}/differences", operation_id="listMallDifferences")
async def list_differences(
    batch_identity: int = Path(alias="batchId", gt=0),
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(read_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    result = await reconciliation.list_differences(
        db, actor, batch_identity, cursor=cursor, page_size=page_size
    )
    await db.commit()
    return response(result)


@difference_router.patch("/{differenceId}", operation_id="updateMallDifference")
async def update_one_difference(
    body: DifferenceUpdate,
    identity: int = Path(alias="differenceId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    try:
        difference = await reconciliation.update_difference(db, actor, identity, body, key=key)
        result = reconciliation.serialize_difference(difference)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{batchId}/close", operation_id="closeMallReconciliation")
async def close_one(
    body: ReasonAction,
    identity: int = Path(alias="batchId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_reconciliations),
    db: AsyncSession = Depends(get_db),
):
    try:
        batch = await reconciliation.close_reconciliation(db, actor, identity, body, key=key)
        result = reconciliation.serialize_reconciliation(batch, open_difference_count=0)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise
