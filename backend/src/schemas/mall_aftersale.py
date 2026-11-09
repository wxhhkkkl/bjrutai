"""Buyer and warehouse inputs for quantity-based aftersales."""

from typing import Literal

from pydantic import Field, model_validator

from .mall_catalog import CatalogInput, VersionAction


class AftersaleLineInput(CatalogInput):
    order_item_id: str = Field(pattern=r"^[1-9][0-9]*$")
    quantity: int = Field(ge=1, le=999)


class AftersaleCreate(CatalogInput):
    order_id: str = Field(pattern=r"^[1-9][0-9]*$")
    expected_order_version: int = Field(ge=1)
    method: Literal["refund_only", "return_refund"]
    items: list[AftersaleLineInput] = Field(min_length=0, max_length=50)
    reason: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    proof_file_ids: list[str] = Field(default_factory=list, max_length=3)
    scope: Literal["goods", "freight_only"] = "goods"

    @model_validator(mode="after")
    def validate_scope(self):
        if len(set(self.proof_file_ids)) != len(self.proof_file_ids):
            raise ValueError("凭证不能重复")
        if self.scope == "freight_only":
            if self.items or self.method != "refund_only":
                raise ValueError("仅运费申请不能包含商品或退货")
        elif not self.items:
            raise ValueError("商品申请至少选择一件商品")
        if len({line.order_item_id for line in self.items}) != len(self.items):
            raise ValueError("同一商品明细只能申请一次")
        return self


class AftersaleDecision(VersionAction):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=1, max_length=500)
    freight_refund_cent: int | None = Field(default=None, ge=0, le=9007199254740991)
    return_address_version: int | None = Field(default=None, ge=1)


class ReasonAction(VersionAction):
    reason: str = Field(min_length=1, max_length=500)


class ReturnShipment(VersionAction):
    courier_code: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    tracking_no: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class SellableReturnLine(CatalogInput):
    aftersale_item_id: str = Field(pattern=r"^[1-9][0-9]*$")
    quantity: int = Field(ge=0, le=999)


class ReturnReceipt(VersionAction):
    result: Literal["accepted", "partially_accepted", "disputed"]
    sellable_items: list[SellableReturnLine] = Field(default_factory=list, max_length=50)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_items(self):
        if len({line.aftersale_item_id for line in self.sellable_items}) != len(
            self.sellable_items
        ):
            raise ValueError("同一售后明细只能验收一次")
        return self
