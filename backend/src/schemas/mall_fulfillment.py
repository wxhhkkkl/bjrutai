"""Order administration inputs; no client-supplied totals or recipient originals."""

from typing import Literal

from pydantic import Field

from .mall_catalog import VersionAction


class OrderNote(VersionAction):
    internal_note: str = Field(max_length=200)


class FulfillmentReleaseRequest(VersionAction):
    purpose: Literal["shipping_label"]
    reason: str = Field(min_length=1, max_length=200)


class ShipmentCreate(VersionAction):
    courier_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    tracking_no: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class TrackingCorrection(VersionAction):
    shipment_version: int = Field(ge=1)
    courier_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    tracking_no: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    reason: str = Field(min_length=1, max_length=200)
