"""Shared timestamps for preserving the first unresolved funds observation."""

from datetime import datetime

from ..models.mall_base import utc_now


def mark_funds_unknown(record, *, now: datetime | None = None):
    """Start an unknown interval once; retries and repeated queries do not reset it."""
    if record.status != "unknown" or record.unknown_since is None:
        record.unknown_since = now or utc_now()
    record.status = "unknown"
    return record


def clear_funds_unknown(record):
    """Close an unknown interval once a definitive/non-unknown state is known."""
    record.unknown_since = None
    return record
