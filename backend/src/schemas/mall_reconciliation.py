"""Strict request schemas for daily settlement reconciliation."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mall_finance import FinanceInput

_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_ID_PATTERN = r"^[1-9][0-9]*$"


class ReconciliationCreate(FinanceInput):
    business_date: date
    statement_file_id: str = Field(pattern=_ID_PATTERN)
    expected_paid_cent: int = Field(ge=0, le=_MAX_SAFE_INTEGER)
    expected_refund_cent: int = Field(ge=0, le=_MAX_SAFE_INTEGER)
    evidence_note: str = Field(min_length=1, max_length=1000)

    @field_validator("business_date", mode="before")
    @classmethod
    def parse_iso_business_date(cls, value):
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("对账日期必须为YYYY-MM-DD") from exc
        return value


class DifferenceCreate(FinanceInput):
    order_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    external_reference: str | None = Field(default=None, min_length=1, max_length=128)
    difference_type: Literal[
        "channel_only",
        "local_only",
        "amount_mismatch",
        "unlinked",
        "duplicate",
        "fee_or_settlement_timing",
    ]
    expected_cent: int = Field(ge=0, le=_MAX_SAFE_INTEGER)
    actual_cent: int = Field(ge=0, le=_MAX_SAFE_INTEGER)
    assigned_to: str | None = Field(default=None, pattern=_ID_PATTERN)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_reference(self):
        if not self.order_id and not self.external_reference:
            raise ValueError("差异必须关联本地订单或保留渠道流水号")
        if self.difference_type == "unlinked" and not self.external_reference:
            raise ValueError("未关联差异必须保留渠道流水号")
        return self


class DifferenceUpdate(FinanceInput):
    expected_version: int = Field(ge=1)
    target_status: Literal["processing", "review", "closed"]
    assigned_to: str | None = Field(default=None, pattern=_ID_PATTERN)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_file_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_evidence(self):
        if len(set(self.evidence_file_ids)) != len(self.evidence_file_ids):
            raise ValueError("核对证据不能重复")
        return self
