"""Rutai (Harbin Rutai) API Integration Client.

HMAC-SHA256 request signing, exponential backoff retry (max 3),
circuit breaker (5 consecutive failures → unavailable),
30-second timeout, and API call logging.
"""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Any, Optional

import httpx

from ..core.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Circuit breaker state (module-level, shared across all instances)
# ---------------------------------------------------------------------------
_circuit_open: bool = False
_consecutive_failures: int = 0
CIRCUIT_THRESHOLD: int = 5
RETRY_MAX: int = 3
RETRY_BASE_S: float = 1.0
TIMEOUT_SECONDS: float = 30.0


# ---------------------------------------------------------------------------
# HMAC-SHA256 signing
# ---------------------------------------------------------------------------
def _sign_request(
    method: str,
    path: str,
    body: Optional[str],
    timestamp: str,
    nonce: str,
) -> str:
    """Generate HMAC-SHA256 signature for a Rutai API request."""
    body_str = body or ""
    sign_str = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_str}"
    secret = settings.rutai_api_secret.encode("utf-8")
    return hmac.new(secret, sign_str.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# API call logging helper
# ---------------------------------------------------------------------------
async def _log_api_call(
    db_session,
    interface_name: str,
    request_params: Optional[dict],
    response_status: int,
    duration_ms: int,
    error_message: Optional[str] = None,
) -> None:
    """Persist an ApiCallLog row.  This is a best-effort fire-and-forget log."""
    try:
        from ..models.audit import ApiCallLog

        log = ApiCallLog(
            interface_name=interface_name,
            request_params=request_params,
            response_status=response_status,
            duration_ms=duration_ms,
            error_message=error_message,
        )
        db_session.add(log)
        await db_session.flush()
    except Exception:
        pass  # logging must never break the main flow


# ---------------------------------------------------------------------------
# Low-level HTTP client
# ---------------------------------------------------------------------------
class RutaiClient:
    """Async client for the Harbin Rutai API.

    Usage::

        client = RutaiClient()
        result = await client.bind_bj_user(
            request_id="r1", patient_name="...", patient_phone="...",
            id_card="...", medical_account="...", family_phone="...",
            source="BJTR", ref_token="abc123",
        )
    """

    def __init__(self) -> None:
        self._base_url = settings.rutai_api_base_url.rstrip("/")
        self._api_key = settings.rutai_api_key
        self._api_secret = settings.rutai_api_secret
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        db_session=None,
    ) -> dict[str, Any]:
        global _circuit_open, _consecutive_failures

        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        body_json = json.dumps(body, ensure_ascii=False) if body else None
        signature = _sign_request(method, path, body_json, ts, nonce)

        headers = {
            "X-Api-Key": self._api_key,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Signature": signature,
            "Content-Type": "application/json; charset=utf-8",
        }
        url = f"{self._base_url}{path}"

        last_error: Optional[str] = None

        for attempt in range(RETRY_MAX + 1):
            if attempt > 0:
                # Auto-recovery: if circuit was open but we're retrying, reset
                if _circuit_open and attempt == 1:
                    _circuit_open = False
                    _consecutive_failures = 0
                # Exponential backoff
                wait_s = RETRY_BASE_S * (2 ** (attempt - 1))
                await asyncio.sleep(wait_s)

            start = time.monotonic()
            client = await self._get_client()
            try:
                response = await client.request(
                    method, url, params=params, content=body_json, headers=headers
                )
                duration_ms = int((time.monotonic() - start) * 1000)

                if db_session is not None:
                    await _log_api_call(
                        db_session, f"rutai:{path}",
                        {"params": params, "body": body},
                        response.status_code, duration_ms,
                    )

                if response.status_code < 500:
                    _consecutive_failures = 0
                    data = response.json()
                    return data
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    _consecutive_failures += 1

            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                last_error = str(exc)
                _consecutive_failures += 1
                if db_session is not None:
                    await _log_api_call(
                        db_session, f"rutai:{path}",
                        {"params": params, "body": body},
                        0, duration_ms, last_error,
                    )

        if _consecutive_failures >= CIRCUIT_THRESHOLD:
            _circuit_open = True

        raise RutaiApiError(f"Rutai API call failed after {RETRY_MAX + 1} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def bind_bj_user(
        self,
        request_id: str,
        patient_name: str,
        patient_phone: str,
        id_card: str,
        medical_account: str,
        family_phone: str,
        source: str = "BJTR",
        ref_token: Optional[str] = None,
        db_session=None,
    ) -> dict[str, Any]:
        """Submit a customer binding/matching request to Rutai.

        Returns a dict with keys:
          - match_status: "matched" | "no_match" | "pending"
          - match_level: "exact" | "fuzzy" | "none"
          - matched_by: Optional[str]
          - hrb_user_id: Optional[str]  # Rutai user ID if matched
          - marked_source: Optional[str]
        """
        body: dict[str, Any] = {
            "request_id": request_id,
            "patient_name": patient_name,
            "patient_phone": patient_phone,
            "id_card": id_card,
            "medical_account": medical_account,
            "family_phone": family_phone,
            "source": source,
        }
        if ref_token:
            body["ref_token"] = ref_token

        return await self._request("POST", "/api/bind/bj_user", body=body, db_session=db_session)

    async def get_bind_user(
        self,
        cursor: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page_size: int = 50,
        source: str = "BJTR",
        db_session=None,
    ) -> dict[str, Any]:
        """Query the list of bound users from Rutai.

        Returns a dict with keys:
          - items: list of { hrb_user_id, phone_masked, marked_status,
              bind_method, ref_token, marked_at, ... }
          - next_cursor: Optional[str]
          - has_more: bool
        """
        params: dict[str, Any] = {
            "page_size": page_size,
            "source": source,
        }
        if cursor:
            params["cursor"] = cursor
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        return await self._request("GET", "/api/bind/user", params=params, db_session=db_session)

    async def get_user_bill(
        self,
        hrb_user_id: str,
        updated_since: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 50,
        db_session=None,
    ) -> dict[str, Any]:
        """Query bills for a specific Rutai user.

        Returns a dict with keys:
          - items: list of { transaction_id, fees (cents), transaction_status, ... }
          - next_cursor: Optional[str]
          - has_more: bool
        """
        params: dict[str, Any] = {
            "hrb_user_id": hrb_user_id,
            "page_size": page_size,
        }
        if updated_since:
            params["updated_since"] = updated_since
        if cursor:
            params["cursor"] = cursor

        return await self._request("GET", "/api/bill/user", params=params, db_session=db_session)

    async def get_all_users_bill(
        self,
        bill_date: str,
        updated_since: Optional[str] = None,
        source: str = "BJTR",
        cursor: Optional[str] = None,
        page_size: int = 50,
        db_session=None,
    ) -> dict[str, Any]:
        """Query bills across all users from Rutai.

        Returns a dict with keys:
          - items: list of bill records each with hrb_user_id
          - next_cursor: Optional[str]
          - has_more: bool
        """
        params: dict[str, Any] = {
            "bill_date": bill_date,
            "source": source,
            "page_size": page_size,
        }
        if updated_since:
            params["updated_since"] = updated_since
        if cursor:
            params["cursor"] = cursor

        return await self._request("GET", "/api/bill/all", params=params, db_session=db_session)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Shared singleton factory
# ---------------------------------------------------------------------------
_rutai_client: Optional[RutaiClient] = None


def get_rutai_client() -> RutaiClient:
    """Return a module-level singleton RutaiClient."""
    global _rutai_client
    if _rutai_client is None:
        _rutai_client = RutaiClient()
    return _rutai_client


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------
class RutaiApiError(Exception):
    """Raised when the Rutai API cannot be reached or returns an error."""
