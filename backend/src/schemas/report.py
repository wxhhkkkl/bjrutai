"""Pydantic schemas for reconciliation report endpoints (US8).

All response fields use camelCase as per project convention.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Valid dimensions
# ---------------------------------------------------------------------------
VALID_DIMENSIONS = {"binding", "revenue", "discount", "allocation"}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class ReportGenerateRequest(BaseModel):
    """Request to generate a multi-dimensional reconciliation report."""

    startDate: str = Field(..., description="Start date (YYYY-MM-DD)")
    endDate: str = Field(..., description="End date (YYYY-MM-DD)")
    dimensions: list[str] = Field(..., min_length=1, description="Report dimensions: binding, revenue, discount, allocation")

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, v: list[str]) -> list[str]:
        invalid = [d for d in v if d not in VALID_DIMENSIONS]
        if invalid:
            raise ValueError(f"Invalid dimensions: {', '.join(invalid)}. Valid: {', '.join(sorted(VALID_DIMENSIONS))}")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class ReportListItem(BaseModel):
    """Summary item in the report list."""

    reportId: str
    dateRange: dict = Field(default_factory=dict, description="{startDate, endDate}")
    dimensions: list[str] = Field(default_factory=list)
    generatedAt: Optional[datetime] = None
    generatedBy: Optional[str] = None

    class Config:
        from_attributes = True


class ReportListResponse(BaseModel):
    """List of historical reports."""

    items: list[ReportListItem] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ReportSection(BaseModel):
    """A single dimension section within a report."""

    title: str
    summary: dict = Field(default_factory=dict)
    details: list[dict] = Field(default_factory=list)


class ReportDetailResponse(BaseModel):
    """Full report detail with all dimension sections."""

    reportId: str
    dateRange: dict = Field(default_factory=dict)
    dimensions: list[str] = Field(default_factory=list)
    sections: dict[str, ReportSection] = Field(default_factory=dict)
    generatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReportGenerateResponse(BaseModel):
    """Response after generating a new report."""

    reportId: str
    generatedAt: datetime
    dimensions: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True
