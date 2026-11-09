"""Safe audit creation for mall actions.

``audit_logs.user_id`` is a foreign key to mini-program users.  Backend
operator identities therefore belong in the structured, redacted detail field
instead of being written into that incompatible foreign key.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor
from ..core.exceptions import ForbiddenException
from ..models.audit import AuditLog

_SENSITIVE_DETAIL_KEYS = {
    "address",
    "addressline",
    "addresssnapshot",
    "authorization",
    "ciphertext",
    "email",
    "externalreference",
    "idcard",
    "invoiceemail",
    "invoicetitle",
    "buyername",
    "companyname",
    "recipient",
    "phone",
    "prepayciphertext",
    "recipientname",
    "trackingno",
    "trackingnumber",
    "beforetrackingno",
    "aftertrackingno",
    # Free-form operational text is stored on its authorized business record;
    # it is deliberately omitted from the broader, append-only audit stream.
    "reason",
    "resolution",
    "description",
    "note",
    "remark",
    "comment",
    "internalnote",
    "secret",
    "signature",
    "taxno",
    "token",
}


def _normalized_key(value: object) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def redact_mall_audit_detail(value: Any) -> Any:
    """Remove personal/contact/credential and free-form text recursively."""
    if isinstance(value, dict):
        return {
            str(key): redact_mall_audit_detail(item)
            for key, item in value.items()
            if _normalized_key(key) not in _SENSITIVE_DETAIL_KEYS
        }
    if isinstance(value, list):
        return [redact_mall_audit_detail(item) for item in value]
    return value


async def record_mall_admin_audit(
    db: AsyncSession,
    *,
    actor: MallActor,
    action: str,
    entity_type: str,
    entity_id: str | None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Queue a redacted administrator audit row in the caller's transaction."""
    if actor.actor_type != "admin":
        raise ForbiddenException(message="商城后台审计必须使用管理员身份")

    safe_detail = redact_mall_audit_detail(detail or {})
    safe_detail["adminAccountId"] = str(actor.actor_id)
    log = AuditLog(
        # Never write an AdminAccount ID into audit_logs.user_id.
        user_id=None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=safe_detail,
    )
    db.add(log)
    return log
