"""Buyer-only address/cart inputs and server-authoritative checkout intent."""

from typing import Annotated

from pydantic import Field, model_validator

from .mall_catalog import CatalogInput, VersionAction

Identity = Annotated[str, Field(pattern=r"^[1-9][0-9]*$", max_length=20)]
Region = Annotated[str, Field(pattern=r"^[0-9]{6}$")]
RegionName = Annotated[str, Field(min_length=1, max_length=20)]
Phone = Annotated[str, Field(pattern=r"^1[3-9][0-9]{9}$")]


class AddressWrite(CatalogInput):
    recipient_name: str = Field(min_length=1, max_length=50)
    phone: Phone
    region_codes: list[Region] = Field(min_length=3, max_length=3)
    region_names: list[RegionName] | None = Field(default=None, min_length=3, max_length=3)
    address_line: str = Field(min_length=1, max_length=200)
    is_default: bool = False
    consent_version: str = Field(min_length=1, max_length=128)
    consent_confirmed: bool


class AddressPatch(VersionAction):
    recipient_name: str | None = Field(default=None, min_length=1, max_length=50)
    phone: Phone | None = None
    region_codes: list[Region] | None = Field(default=None, min_length=3, max_length=3)
    region_names: list[RegionName] | None = Field(default=None, min_length=3, max_length=3)
    address_line: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_null(self):
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("省略字段以保留原值，不能提交null")
        return self


class BuyItem(CatalogInput):
    sku_id: Identity
    quantity: int = Field(ge=1, le=999)


class CartPatch(VersionAction):
    quantity: int = Field(ge=1, le=999)


class QuoteRequest(CatalogInput):
    address_id: Identity | None = None
    items: list[BuyItem] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_skus(self):
        if len({item.sku_id for item in self.items}) != len(self.items):
            raise ValueError("同一SKU只能出现一次，请合并数量")
        return self


class OrderCreate(CatalogInput):
    quote_token: str = Field(min_length=1, max_length=32768)
    buyer_note: str = Field(default="", max_length=200)
    invoice_intent: bool = False
    consent_version: str = Field(min_length=1, max_length=128)
    consent_confirmed: bool


class OrderCancel(VersionAction):
    reason: str = Field(min_length=1, max_length=500)


class OrderAddressChange(VersionAction):
    address_id: Identity
    reason: str = Field(min_length=1, max_length=200)
