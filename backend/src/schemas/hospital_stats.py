"""Inputs for internet-hospital visit statistics."""

from typing import Literal

from pydantic import BaseModel, Field


class HospitalEventIn(BaseModel):
    event: Literal["entry_tap", "qr_longpress"]
    source: Literal["internet_hospital"] = "internet_hospital"
