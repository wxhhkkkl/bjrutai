"""Typed adjustment record shape shared by the admin review API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PerformanceAdjustmentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(alias="expectedVersion", ge=1)


class PerformanceAdjustmentRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(alias="expectedVersion", ge=1)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class PerformanceAdjustmentReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(alias="expectedVersion", ge=1)
    evidence_file_ids: list[str] = Field(alias="evidenceFileIds", min_length=1, max_length=5)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("evidence_file_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: list[str]) -> list[str]:
        if any(not value.isascii() or not value.isdigit() or int(value) <= 0 for value in values):
            raise ValueError("evidenceFileIds must contain positive decimal IDs")
        if len(set(values)) != len(values):
            raise ValueError("evidenceFileIds must not contain duplicates")
        return values

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class PerformanceAdjustmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^[1-9][0-9]*$")
    origin_period: str = Field(alias="originPeriod", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    origin_evidence_id: str = Field(alias="originEvidenceId", pattern=r"^[1-9][0-9]*$")
    origin_result_id: str | None = Field(
        default=None, alias="originResultId", pattern=r"^[1-9][0-9]*$"
    )
    origin_result_presence: str = Field(alias="originResultPresence")
    beneficiary_id: str = Field(alias="beneficiaryId", pattern=r"^[1-9][0-9]*$")
    adjustment_no: str = Field(alias="adjustmentNo", min_length=1, max_length=32)
    rule_type: Literal["intra_org", "org_management"] = Field(alias="ruleType")
    original_commission_cent: int = Field(alias="originalCommissionCent", ge=0)
    replayed_commission_cent: int = Field(alias="replayedCommissionCent", ge=0)
    prior_confirmed_adjustment_cent: int = Field(alias="priorConfirmedAdjustmentCent")
    delta_cent: int = Field(alias="deltaCent")
    remaining_cent: int = Field(alias="remainingCent")
    status: str
    evidence_status: Literal["complete", "manual_required"] = Field(alias="evidenceStatus")
    evidence_file_ids: list[str] = Field(alias="evidenceFileIds", max_length=5)
    reason: str
    version: int = Field(ge=1)
