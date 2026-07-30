"""Compliance endpoints (T173).

GET  /agreements/latest     – latest agreement versions
GET  /agreements/{id}       – agreement detail
POST /consents              – record user consent
GET  /me/consents           – user consent status
PUT  /me/privacy-settings   – update privacy preferences
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.exceptions import BadRequestException, NotFoundException
from ...models.consent import (
    Agreement,
    AgreementType,
    ConsentRecord,
    ConsentScene,
    EvidenceType,
    SubjectType,
)
from ...models.user import User

router = APIRouter(tags=["compliance"])
agreements_router = APIRouter(prefix="/agreements", tags=["agreements"])
consents_router = APIRouter(prefix="/consents", tags=["consents"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class ConsentCreateRequest(BaseModel):
    agreementId: int
    scene: str = Field(..., description="registration, binding, promotion, followup")
    confirmed: bool = True
    evidenceType: Optional[str] = Field(None, description="click, signature, sms, facial")
    subjectType: str = Field("user", description="user or customer")


class PrivacySettingsRequest(BaseModel):
    maskSensitive: bool = True
    personalized: bool = False
    version: int = Field(..., ge=1)


# =============================================================================
# Agreements endpoints
# =============================================================================


@agreements_router.get("/latest")
async def get_latest_agreements(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the latest version of each agreement type."""
    from sqlalchemy import tuple_

    # Subquery: max version per type
    subq = (
        select(
            Agreement.type,
            func_max := __import__("sqlalchemy").sql.func.max(Agreement.version).label("max_version"),
        )
        .group_by(Agreement.type)
        .subquery()
    )

    result = await db.execute(
        select(Agreement).join(
            subq,
            (Agreement.type == subq.c.type) & (Agreement.version == subq.c.max_version),
        )
    )
    agreements = result.scalars().all()

    # Fallback: fetch all and group manually
    all_result = await db.execute(
        select(Agreement).order_by(Agreement.type, desc(Agreement.version))
    )
    all_rows = all_result.scalars().all()

    # Manual grouping
    latest_by_type = {}
    for a in all_rows:
        type_key = a.type.value if hasattr(a.type, "value") else str(a.type)
        if type_key not in latest_by_type:
            latest_by_type[type_key] = a

    items = []
    for type_key, a in sorted(latest_by_type.items()):
        items.append({
            "id": str(a.id),
            "type": type_key,
            "title": a.title,
            "version": a.version,
            "summary": a.summary,
            "contentUrl": a.content_url,
            "effectiveAt": a.effective_at.isoformat() if a.effective_at else None,
        })

    return _ok({"items": items})


@agreements_router.get("/{agreement_id}")
async def get_agreement_detail(
    agreement_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return detail of a specific agreement."""
    result = await db.execute(select(Agreement).where(Agreement.id == agreement_id))
    agreement = result.scalars().first()
    if agreement is None:
        raise NotFoundException(message="Agreement not found")

    return _ok({
        "id": str(agreement.id),
        "type": agreement.type.value if hasattr(agreement.type, "value") else str(agreement.type),
        "title": agreement.title,
        "version": agreement.version,
        "summary": agreement.summary,
        "contentUrl": agreement.content_url,
        "effectiveAt": agreement.effective_at.isoformat() if agreement.effective_at else None,
        "createdAt": agreement.created_at.isoformat() if agreement.created_at else None,
    })


# =============================================================================
# Consents endpoints
# =============================================================================


@consents_router.post("")
async def record_consent(
    body: ConsentCreateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Record a user consent action."""
    user_id = int(payload["sub"])

    # Validate agreement exists
    result = await db.execute(select(Agreement).where(Agreement.id == body.agreementId))
    agreement = result.scalars().first()
    if agreement is None:
        raise NotFoundException(message="Agreement not found")

    # Validate scene
    try:
        scene = getattr(ConsentScene, body.scene.upper())
    except (AttributeError, KeyError):
        raise BadRequestException(message=f"Invalid scene: {body.scene}")

    # Validate subject type
    try:
        subject_type = getattr(SubjectType, body.subjectType.upper())
    except (AttributeError, KeyError):
        raise BadRequestException(message=f"Invalid subjectType: {body.subjectType}")

    # Validate evidence type
    evidence_type = None
    if body.evidenceType:
        try:
            evidence_type = getattr(EvidenceType, body.evidenceType.upper())
        except (AttributeError, KeyError):
            pass

    consent = ConsentRecord(
        user_id=user_id,
        subject_type=subject_type,
        scene=scene,
        agreement_versions={agreement.type.value if hasattr(agreement.type, "value") else str(agreement.type): agreement.version},
        scopes={"basic": True},
        confirmed=body.confirmed,
        evidence_type=evidence_type,
        status="active",
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)

    return _ok({
        "id": str(consent.id),
        "agreementId": str(body.agreementId),
        "scene": scene.value if hasattr(scene, "value") else str(scene),
        "confirmed": consent.confirmed,
        "consentedAt": consent.consented_at.isoformat() if consent.consented_at else None,
        "status": consent.status,
    })


# =============================================================================
# /me/consents and /me/privacy-settings
# =============================================================================
me_consents_router = APIRouter(prefix="/me", tags=["me-consents"])


@me_consents_router.get("/consents")
async def get_my_consents(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get the consent status for the current user."""
    user_id = int(payload["sub"])

    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id)
        .order_by(desc(ConsentRecord.consented_at))
        .limit(20)
    )
    consents = result.scalars().all()

    items = []
    for c in consents:
        items.append({
            "id": str(c.id),
            "scene": c.scene.value if hasattr(c.scene, "value") else str(c.scene),
            "confirmed": c.confirmed,
            "status": c.status,
            "consentedAt": c.consented_at.isoformat() if c.consented_at else None,
            "expiresAt": c.expires_at.isoformat() if c.expires_at else None,
        })

    return _ok({"items": items})


@me_consents_router.put("/privacy-settings")
async def update_privacy_settings(
    body: PrivacySettingsRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Update privacy preferences for the current user.

    Note: In production these settings would be stored in a dedicated table.
    Currently stored as a consent record with scene=privacy_settings.
    """
    user_id = int(payload["sub"])

    # Record the privacy settings update as a consent action
    consent = ConsentRecord(
        user_id=user_id,
        subject_type=SubjectType.USER,
        scene=ConsentScene.REGISTRATION,
        agreement_versions={"privacy_settings": str(body.version)},
        scopes={
            "maskSensitive": body.maskSensitive,
            "personalized": body.personalized,
        },
        confirmed=True,
        status="active",
    )
    db.add(consent)
    await db.commit()

    return _ok({
        "maskSensitive": body.maskSensitive,
        "personalized": body.personalized,
        "version": body.version,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })
