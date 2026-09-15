"""Public homepage banner endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...services.banner_service import list_public

router = APIRouter(prefix="/banners", tags=["banners"])


@router.get("")
async def list_banners(db: AsyncSession = Depends(get_db)):
    """Return enabled homepage banners in configured display order."""
    return _build_response(0, "success", {"items": await list_public(db)})
