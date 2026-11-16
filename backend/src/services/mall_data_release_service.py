"""Shared controls for purpose-limited mall data release actions."""

import hashlib
from datetime import timedelta, timezone

from sqlalchemy import select

from ..api.mall_deps import MallActor, require_mall_admin_permission
from ..core.config import get_settings
from ..models.consent import ConsentRecord, ConsentScene, SubjectType
from ..models.mall_base import utc_now
from .mall_audit_service import record_mall_admin_audit


def raw_data_release_runtime_ready(settings=None) -> bool:
    """Fail closed unless feature and both governance references are configured."""
    settings = settings or get_settings()
    return bool(
        settings.mall_data_release_enabled
        and settings.mall_data_release_retention_policy_ref.strip()
        and settings.mall_data_release_notice_approved_version.strip()
    )


def release_expires_at() -> str:
    return (utc_now() + timedelta(seconds=60)).replace(tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


async def record_release_audit(
    db,
    *,
    actor: MallActor,
    action: str,
    entity_type: str,
    entity_id: str,
    purpose: str,
    reason_code: str,
    expected_version: int,
    event_key: str,
    settings,
    actual_version: int | None = None,
):
    """Persist a metadata-only access decision and return its audit row."""
    digest = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    audit = await record_mall_admin_audit(
        db,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail={
            "purposeCode": purpose,
            "reasonCode": reason_code,
            "expectedVersion": expected_version,
            "actualVersion": actual_version,
            "eventKeyHash": digest,
            "retentionPolicyRef": settings.mall_data_release_retention_policy_ref.strip(),
            "noticeVersion": settings.mall_data_release_notice_approved_version.strip(),
        },
    )
    await db.flush()
    return audit


async def current_release_actor(db, actor: MallActor, permission: str) -> MallActor:
    """Lock and recheck the administrator account and role in this transaction."""
    return await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        permission,
        current=True,
    )


async def active_release_consent(
    db,
    *,
    consent_id: int | None,
    user_id: int,
    scene: ConsentScene,
    required_scopes: set[str],
    notice_version: str,
    now,
) -> bool:
    """Require the exact buyer, scene, active notice version and declared scopes."""
    if not consent_id:
        return False
    consent = await db.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.id == consent_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if consent is None:
        return False
    scopes = consent.scopes if isinstance(consent.scopes, dict) else {}
    versions = consent.agreement_versions if isinstance(consent.agreement_versions, dict) else {}
    return bool(
        consent.user_id == user_id
        and consent.subject_type == SubjectType.USER
        and consent.scene == scene
        and consent.confirmed is True
        and consent.status == "active"
        and (consent.expires_at is None or consent.expires_at > now)
        and versions.get("mall_notice_copy") == notice_version
        and all(scopes.get(scope) is True for scope in required_scopes)
    )
