"""Request fields for evidence-backed attribution of an unassigned Mall source."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AttributionConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(alias="expectedVersion", ge=1)
    distributor_id: str = Field(alias="distributorId", pattern=r"^[1-9][0-9]*$")
    customer_id: str | None = Field(default=None, alias="customerId", pattern=r"^[1-9][0-9]*$")
    evidence_file_ids: list[str] = Field(
        default_factory=list,
        alias="evidenceFileIds",
        max_length=5,
    )
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("evidence_file_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: list[str]) -> list[str]:
        if any(not value.isascii() or not value.isdigit() or int(value) <= 0 for value in values):
            raise ValueError("evidenceFileIds must contain positive decimal IDs")
        if len(set(values)) != len(values):
            raise ValueError("evidenceFileIds must not contain duplicates")
        return values
