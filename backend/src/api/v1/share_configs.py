"""Public Mini Program share-card configuration endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...services.share_config_service import get_public_share_config, list_share_configs

router = APIRouter(prefix="/share-configs", tags=["share-configs"])


@router.get("")
async def public_share_configs(db: AsyncSession = Depends(get_db)):
    return _build_response(0, "success", {"items": await list_share_configs(db)})


@router.get("/{page_key}")
async def public_share_config(page_key: str, db: AsyncSession = Depends(get_db)):
    return _build_response(0, "success", await get_public_share_config(db, page_key))
