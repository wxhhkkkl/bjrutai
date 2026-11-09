"""Strict finance query and export input contracts."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class FinanceInput(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class FinanceExport(FinanceInput):
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    status: (
        Literal[
            "creating",
            "pending",
            "unknown",
            "succeeded",
            "closed",
            "failed",
            "prepared",
            "processing",
            "abnormal",
            "rejected_unaccepted",
        ]
        | None
    ) = None
    format: Literal["csv", "xlsx"]

    @field_validator("from_at", "to_at", mode="before")
    @classmethod
    def parse_iso_datetime(cls, value):
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("导出时间必须是ISO日期时间") from exc
        return value

    @model_validator(mode="after")
    def validate_explicit_range(self):
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.from_at, self.to_at)
        ):
            raise ValueError("导出时间必须包含时区")
        start = self.from_at.astimezone(timezone.utc)
        end = self.to_at.astimezone(timezone.utc)
        if start >= end:
            raise ValueError("导出开始时间必须早于结束时间")
        if end - start > timedelta(days=31):
            raise ValueError("单次导出范围最多31天")
        return self
