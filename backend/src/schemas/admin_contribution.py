"""Schemas for admin manual-consumption entry."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ManualConsumptionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    customer_id: str = Field(..., alias="customerId")
    customer_version: int = Field(..., ge=1, alias="customerVersion")
    consumed_at: datetime = Field(..., alias="consumedAt")
    amount_cent: int = Field(..., gt=0, alias="amountCent")
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit() or int(value) <= 0:
            raise ValueError("客户 ID 无效")
        return value

    @field_validator("consumed_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("消费时间必须包含时区")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EligibleCustomerItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    customer_id: str = Field(..., alias="customerId")
    customer_version: int = Field(..., alias="customerVersion")
    name: Optional[str]
    phone_masked: Optional[str] = Field(None, alias="phoneMasked")
    id_card_masked: Optional[str] = Field(None, alias="idCardMasked")
    distributor_id: str = Field(..., alias="distributorId")
    person_name: Optional[str] = Field(None, alias="personName")
    org_id: str = Field(..., alias="orgId")
    org_name: Optional[str] = Field(None, alias="orgName")


class ManualConsumptionResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    record_no: str = Field(..., alias="recordNo")
    customer_id: str = Field(..., alias="customerId")
    customer_name: Optional[str] = Field(None, alias="customerName")
    phone_masked: Optional[str] = Field(None, alias="phoneMasked")
    distributor_id: str = Field(..., alias="distributorId")
    person_name: Optional[str] = Field(None, alias="personName")
    org_id: str = Field(..., alias="orgId")
    org_name: Optional[str] = Field(None, alias="orgName")
    amount_cent: int = Field(..., alias="amountCent")
    status: str
    source: str
    consumed_at: datetime = Field(..., alias="consumedAt")
    replayed: bool
