"""Public patient scan endpoints for customer binding codes."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...core.error_handler import _build_response
from ...integrations.wechat_client import get_wechat_client
from ...services import customer_binding_code_service

router = APIRouter(prefix="/customer-binding-codes", tags=["customer-binding-codes"])


class CustomerClaimRequest(BaseModel):
    wechat_code: str = Field(..., min_length=1, max_length=256, alias="wechatCode")
    phone_code: str = Field(..., min_length=1, max_length=256, alias="phoneCode")
    name: str | None = Field(None, max_length=100)
    consent_confirmed: bool = Field(..., alias="consentConfirmed")

    class Config:
        populate_by_name = True


@router.get("/{ref_token}")
async def get_code_info(ref_token: str, db: AsyncSession = Depends(get_db)):
    result = await customer_binding_code_service.get_code_info(db, ref_token)
    return _build_response(0, "success", result)


@router.post("/{ref_token}/claim")
async def claim_customer(
    ref_token: str,
    body: CustomerClaimRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await customer_binding_code_service.claim_customer(
        db,
        ref_token,
        wechat_code=body.wechat_code,
        phone_code=body.phone_code,
        name=body.name,
        consent_confirmed=body.consent_confirmed,
    )
    await db.commit()
    return _build_response(0, "success", result)


@router.get("/{ref_token}/image")
async def get_code_image(ref_token: str, db: AsyncSession = Depends(get_db)):
    await customer_binding_code_service.get_code_info(db, ref_token, record_scan=False)
    image = await get_wechat_client().get_unlimited_wxacode(
        ref_token,
        "pages/patient-binding/index",
    )
    return Response(content=image, media_type="image/jpeg")
