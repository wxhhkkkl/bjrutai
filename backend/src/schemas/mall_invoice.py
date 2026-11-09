"""Strict buyer and finance inputs for invoice facts and correction chains."""

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mall_catalog import CatalogInput

_TAX_NO = re.compile(r"^[A-Za-z0-9]{8,32}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvoiceCreate(CatalogInput):
    order_id: str = Field(pattern=r"^[1-9][0-9]*$")
    expected_order_version: int = Field(ge=1)
    buyer_type: Literal["personal", "company"]
    title: str = Field(min_length=1, max_length=200)
    tax_no: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    invoice_type: Literal["digital_normal", "manual_special_request"]
    consent_version: str = Field(min_length=1, max_length=128)
    consent_confirmed: bool

    @field_validator("tax_no")
    @classmethod
    def validate_tax_number(cls, value):
        if value is not None and not _TAX_NO.fullmatch(value):
            raise ValueError("纳税人识别号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value is not None and not _EMAIL.fullmatch(value):
            raise ValueError("邮箱格式不正确")
        return value

    @model_validator(mode="after")
    def validate_buyer_fields(self):
        if self.buyer_type == "personal" and self.tax_no:
            raise ValueError("个人抬头不能填写纳税人识别号")
        return self


class InvoicePatch(CatalogInput):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    tax_no: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    consent_version: str = Field(min_length=1, max_length=128)
    consent_confirmed: bool

    @field_validator("tax_no")
    @classmethod
    def validate_tax_number(cls, value):
        if value is not None and not _TAX_NO.fullmatch(value):
            raise ValueError("纳税人识别号格式不正确")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value is not None and not _EMAIL.fullmatch(value):
            raise ValueError("邮箱格式不正确")
        return value

    @model_validator(mode="after")
    def reject_empty_patch_values(self):
        for field in ("title", "tax_no", "email"):
            if field in self.model_fields_set and getattr(self, field) is None and field == "title":
                raise ValueError("发票抬头不能为空")
        return self


class InvoiceIssueRecord(CatalogInput):
    expected_version: int = Field(ge=1)
    invoice_no: str = Field(min_length=1, max_length=64)
    issued_at: datetime = Field(strict=False)
    seller_identity: str = Field(min_length=1, max_length=64)
    total_cent: int = Field(ge=1, le=9007199254740991)
    file_id: str = Field(pattern=r"^[1-9][0-9]*$")
    reason: str = Field(default="", max_length=500)
    replacement_for_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")

    @field_validator("invoice_no", "seller_identity", mode="before")
    @classmethod
    def trim_identifiers(cls, value):
        return value.strip() if isinstance(value, str) else value


class RedPendingUpdate(CatalogInput):
    expected_version: int = Field(ge=1)
    target_status: Literal["red_pending", "awaiting_counterparty"]
    reason: str = Field(min_length=1, max_length=500)


class RedInvoiceRecord(CatalogInput):
    expected_version: int = Field(ge=1)
    invoice_no: str = Field(min_length=1, max_length=64)
    issued_at: datetime = Field(strict=False)
    total_cent: int = Field(ge=1, le=9007199254740991)
    file_id: str = Field(pattern=r"^[1-9][0-9]*$")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("invoice_no", mode="before")
    @classmethod
    def trim_invoice_number(cls, value):
        return value.strip() if isinstance(value, str) else value


class InvoiceFileReplace(CatalogInput):
    expected_version: int = Field(ge=1)
    file_id: str = Field(pattern=r"^[1-9][0-9]*$")
    reason: str = Field(min_length=1, max_length=500)


class BillingReleaseRequest(CatalogInput):
    expected_version: int = Field(ge=1)
    purpose: Literal["invoice_issue"]
    reason: str = Field(min_length=1, max_length=200)

