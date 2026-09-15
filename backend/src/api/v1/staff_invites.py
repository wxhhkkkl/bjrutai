"""Organization-admin staff invite code endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db, require_org_admin
from ...core.error_handler import _build_response
from ...integrations.wechat_client import get_wechat_client
from ...models.distributor import Distributor
from ...services import staff_invite_service


router = APIRouter(tags=["staff-invites"])


class StaffJoinRequest(BaseModel):
    phone_code: str = Field(..., min_length=1, max_length=256, alias="phoneCode")
    name: str = Field(..., min_length=1, max_length=64)
    consent_confirmed: bool = Field(..., alias="consentConfirmed")

    class Config:
        populate_by_name = True


@router.get("/staff-invite-code")
async def get_my_invite_code(
    db: AsyncSession = Depends(get_db),
    inviter: Distributor = Depends(require_org_admin),
):
    result = await staff_invite_service.get_or_create_code(db, inviter)
    await db.commit()
    return _build_response(0, "success", result)


@router.post("/staff-invite-code/refresh")
async def refresh_my_invite_code(
    db: AsyncSession = Depends(get_db),
    inviter: Distributor = Depends(require_org_admin),
):
    result = await staff_invite_service.refresh_code(db, inviter)
    await db.commit()
    return _build_response(0, "success", result)


@router.post("/staff-invite-code/revoke")
async def revoke_my_invite_code(
    db: AsyncSession = Depends(get_db),
    inviter: Distributor = Depends(require_org_admin),
):
    await staff_invite_service.revoke_code(db, inviter)
    await db.commit()
    return _build_response(0, "success", None)


@router.get("/staff-invite-codes/{ref_token}")
async def get_invite_info(ref_token: str, db: AsyncSession = Depends(get_db)):
    result = await staff_invite_service.get_code_info(db, ref_token)
    return _build_response(0, "success", result)


@router.post("/staff-invite-codes/{ref_token}/join")
async def join_organization(
    ref_token: str,
    body: StaffJoinRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await staff_invite_service.join_organization(
        db,
        ref_token,
        phone_code=body.phone_code,
        name=body.name,
        consent_confirmed=body.consent_confirmed,
    )
    await db.commit()
    return _build_response(0, "success", result)


@router.get("/staff-invite-codes/{ref_token}/image")
async def get_invite_image(ref_token: str, db: AsyncSession = Depends(get_db)):
    await staff_invite_service.get_code_info(db, ref_token)
    image = await get_wechat_client().get_unlimited_wxacode(
        ref_token,
        "pages/staff-join/index",
    )
    return Response(content=image, media_type="image/jpeg")
