"""Versioned single-store settings contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class MallSettingsSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", strict=True
    )


class WarehouseAddressWrite(MallSettingsSchema):
    contact_name: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=1, max_length=20)
    region_codes: list[str] = Field(min_length=3, max_length=3)
    address_line: str = Field(min_length=1, max_length=200)


class MallSettingsView(MallSettingsSchema):
    version: int = Field(ge=1)
    enabled: bool
    purchase_enabled: bool
    freight_mode: Literal["free", "fixed"]
    freight_cent: int = Field(ge=0, le=9007199254740991)
    blocked_region_codes: list[str] = Field(default_factory=list)
    payment_minutes: int = Field(ge=1)
    auto_receive_days: int = Field(ge=1)
    aftersale_days: int = Field(ge=1)
    contact_text: str = Field(default="", max_length=500)
    policy_version: str
    dispatch_address_masked: str = ""
    return_address_masked: str = ""
    return_instructions: str = Field(default="", max_length=2000)


class MallSettingsUpdate(MallSettingsSchema):
    expected_version: int = Field(ge=1)
    settings: MallSettingsView
    reason: str = Field(min_length=1, max_length=500)
    dispatch_address: WarehouseAddressWrite | None = None
    return_address: WarehouseAddressWrite | None = None
