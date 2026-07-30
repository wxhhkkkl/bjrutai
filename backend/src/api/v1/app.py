"""App-level endpoints, e.g. bootstrap for client initialisation."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...schemas.auth import BootstrapResponse, SessionResponse
from ...services.auth_service import get_auth_service

router = APIRouter(prefix="/app", tags=["app"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# GET /app/bootstrap
# ──────────────────────────────────────────────────────────────────
@router.get("/bootstrap")
async def bootstrap(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return bootstrap data for the mobile / web client.

    Includes session info when the request carries a valid access token;
    otherwise returns a minimal bootstrap payload (entry, feature flags, etc.).
    """
    session = None

    # Attempt to extract and validate the token; do NOT fail if missing.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header[len("Bearer "):]
            payload = await _try_validate_token(token, db)
            if payload is not None:
                user_id = int(payload["sub"])
                user_type = payload.get("user_type", "promoter")
                token_exp = payload.get("exp", datetime.now(timezone.utc).timestamp() + 3600)

                svc = get_auth_service()
                session = await svc.get_session(db, user_id, user_type, token_exp)
        except Exception:
            pass  # Token invalid — return minimal bootstrap

    return _ok(BootstrapResponse(
        session=session,
        entry=None,
        unreadNotificationCount=0,
        privacyAgreementVersion=None,
        workbenchSummary=None,
        featureFlags={},
    ).model_dump())


async def _try_validate_token(token: str, db: AsyncSession):
    """Decode the JWT and verify the user still exists.  Returns payload or None."""
    from ...core.security import verify_token
    from jose import JWTError

    try:
        payload = verify_token(token)
    except (JWTError, Exception):
        return None

    if payload.get("type") != "access":
        return None

    return payload
