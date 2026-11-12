"""Safe logistics response projections; provider payloads are never serialized directly."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class LogisticsEvent(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    occurred_at: datetime | None
    time_text: str
    description: str
    state_code: str | None
    state_name: str | None
    area_name: str | None


class LogisticsRoutePoint(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    latitude: float
    longitude: float
    state_name: str | None = None
    name: str | None = None


class LogisticsRoute(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    current_name: str | None = None
    points: list[LogisticsRoutePoint]


class LogisticsSnapshot(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    order_id: str
    shipment_id: str
    shipment_version: int
    provider: Literal["kuaidi100"]
    source: Literal["fake", "live"] | None
    courier_code: str
    tracking_no: str
    query_status: Literal[
        "pending",
        "available",
        "stale",
        "no_record",
        "verification_failed",
        "permission_denied",
        "service_error",
        "config_required",
    ]
    state_code: str | None
    state_name: str | None
    events: list[LogisticsEvent]
    updated_at: datetime | None
    next_query_at: datetime | None
    estimated_arrival_text: str | None = None
    route: LogisticsRoute | None = None
    map_available: bool
    error_code: str | None = None


class AdminLogisticsSnapshot(LogisticsSnapshot):
    map_url: str | None = None


class LogisticsRefreshResult(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    command_id: str | None
    scheduled: bool
    snapshot: LogisticsSnapshot
