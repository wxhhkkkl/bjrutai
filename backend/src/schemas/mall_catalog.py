"""Strict catalog inputs; publishing is separate from draft persistence."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CatalogInput(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class CategoryWrite(CatalogInput):
    name: str = Field(min_length=1, max_length=64)
    parent_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    sort: int = 0
    status: Literal["enabled", "disabled"]


class OptionWrite(CatalogInput):
    name: str = Field(min_length=1, max_length=32)
    value: str = Field(min_length=1, max_length=64)


class SkuWrite(CatalogInput):
    id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    sku_code: str = Field(min_length=1, max_length=64)
    options: list[OptionWrite] = Field(default_factory=list, max_length=2)
    price_cent: int = Field(ge=1, le=9007199254740991)
    initial_stock: int | None = Field(default=None, ge=0, le=2147483647)
    warning_quantity: int = Field(default=0, ge=0, le=2147483647)


class ProductWrite(CatalogInput):
    category_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    name: str = Field(min_length=1, max_length=64)
    summary: str = Field(default="", max_length=128)
    cover_file_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$")
    gallery_file_ids: list[str] = Field(default_factory=list, max_length=8)
    description: str = Field(default="", max_length=100000)
    instructions: str = Field(default="", max_length=10000)
    sort: int = 0
    skus: list[SkuWrite] | None = Field(default=None, min_length=1, max_length=20)


class StockAdjustment(CatalogInput):
    expected_version: int = Field(ge=1)
    delta_available_quantity: int = Field(ge=-2147483647, le=2147483647)
    reason: str = Field(min_length=1, max_length=200)


class VersionAction(CatalogInput):
    expected_version: int = Field(ge=1)


class CategoryPatch(VersionAction):
    category: CategoryWrite


class ProductPatch(VersionAction):
    product: ProductWrite


class StatusChange(VersionAction):
    target_status: Literal["on_sale", "off_sale", "archived"]
    reason: str = Field(default="", max_length=200)
