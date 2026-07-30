"""Tencent Cloud COS client – pre-signed upload URL generation.

Generates temporary upload credentials for qualification files so clients can
upload directly to COS without sharing long-lived secrets.
"""

import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from ..core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Allowed content types for qualification file uploads
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_TOKEN_TTL_MINUTES = 10


class COSClient:
    """Generates pre-signed upload URLs for Tencent Cloud COS (Cloud Object Storage)."""

    def __init__(self) -> None:
        self._secret_id = settings.cos_secret_id
        self._secret_key = settings.cos_secret_key
        self._bucket = settings.cos_bucket
        self._region = settings.cos_region

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_upload_token(
        self,
        *,
        user_id: int,
        file_name: str,
        content_type: str,
        file_size: int,
    ) -> dict:
        """Validate and generate a pre-signed upload URL + file key.

        Args:
            user_id: The authenticated user's ID (used in the object key path).
            file_name: Original file name (must end with .jpg/.jpeg/.png/.pdf).
            content_type: MIME type (image/jpeg, image/png, application/pdf).
            file_size: File size in bytes (must be <= 10 MB).

        Returns:
            dict with keys: ``fileId``, ``uploadUrl``, ``expiresAt``, ``contentType``.

        Raises:
            ValueError: When content_type or extension is not allowed, or file too large.
        """
        # --- validation ---
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"Unsupported file type: {content_type}. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}"
            )

        if file_size <= 0 or file_size > MAX_FILE_SIZE:
            raise ValueError(
                f"File size {file_size} exceeds maximum allowed ({MAX_FILE_SIZE} bytes)"
            )

        ext = self._extract_extension(file_name)
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # --- build object key ---
        now = datetime.now(timezone.utc)
        date_prefix = now.strftime("%Y/%m")
        unique_id = uuid.uuid4().hex[:16]
        safe_name = self._sanitize_filename(file_name, unique_id)
        object_key = f"qualifications/{user_id}/{date_prefix}/{safe_name}"

        # --- generate pre-signed URL ---
        expires_at_dt = now + timedelta(minutes=UPLOAD_TOKEN_TTL_MINUTES)
        expires_at = expires_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        expire_seconds = UPLOAD_TOKEN_TTL_MINUTES * 60

        upload_url = self._build_presigned_put_url(
            object_key=object_key,
            content_type=content_type,
            expire_seconds=expire_seconds,
        )

        return {
            "fileId": object_key,
            "uploadUrl": upload_url,
            "expiresAt": expires_at,
            "contentType": content_type,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_extension(file_name: str) -> str:
        """Return the lowercase file extension including the dot (e.g. '.jpg')."""
        idx = file_name.rfind(".")
        if idx == -1:
            return ""
        return file_name[idx:].lower()

    @staticmethod
    def _sanitize_filename(file_name: str, unique_id: str) -> str:
        """Sanitize filename: keep only safe chars, prepend unique id."""
        ext = COSClient._extract_extension(file_name)
        base = file_name[: file_name.rfind(ext)] if ext else file_name
        # Only allow alphanumeric and underscores in the base name
        safe_base = "".join(c for c in base if c.isalnum() or c in "_-")
        if not safe_base:
            safe_base = "file"
        return f"{unique_id}_{safe_base}{ext}"

    def _build_presigned_put_url(
        self,
        object_key: str,
        content_type: str,
        expire_seconds: int,
    ) -> str:
        """Build a pre-signed PUT URL for uploading to COS.

        Uses COS signature v1 (q-sign-algorithm=sha1). The client should PUT
        the file body to the returned URL.
        """
        host = f"{self._bucket}.cos.{self._region}.myqcloud.com"
        path = "/" + object_key.lstrip("/")

        # Time parameters
        now_ts = int(time.time())
        sign_start = now_ts
        sign_end = now_ts + expire_seconds
        key_time = f"{sign_start};{sign_end}"

        # Step 1: SignKey
        sign_key = hmac.new(
            self._secret_key.encode("utf-8"),
            key_time.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()

        # Step 2: HttpString = {method}\n{path}\n\nhost={host}\n
        http_method = "put"
        http_uri = quote(path, safe="/")
        http_headers = f"content-type={quote(content_type, safe='')}&host={host}"
        http_string = f"{http_method}\n{http_uri}\n\n{http_headers}\n"

        # Step 3: StringToSign
        sha1_http_string = hashlib.sha1(http_string.encode("utf-8")).hexdigest()
        string_to_sign = f"sha1\n{key_time}\n{sha1_http_string}\n"

        # Step 4: Signature
        signature = hmac.new(
            sign_key.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()

        # Build authorization parameter
        q_header_list = "content-type;host"
        q_url_param_list = ""
        auth = (
            f"q-sign-algorithm=sha1"
            f"&q-ak={quote(self._secret_id, safe='')}"
            f"&q-sign-time={key_time}"
            f"&q-key-time={key_time}"
            f"&q-header-list={quote(q_header_list, safe='')}"
            f"&q-url-param-list={quote(q_url_param_list, safe='')}"
            f"&q-signature={signature}"
        )

        # COS pre-signed URL with the authorization as a query param
        upload_url = f"https://{host}{http_uri}?{auth}"

        return upload_url


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
_default_cos_client: Optional[COSClient] = None


def get_cos_client() -> COSClient:
    """Return the module-level COSClient singleton."""
    global _default_cos_client
    if _default_cos_client is None:
        _default_cos_client = COSClient()
    return _default_cos_client
