"""Pydantic schemas for contribution query and team views (US6).

All response fields use camelCase as per project convention.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Overview response
# ---------------------------------------------------------------------------
class ContributionOverviewResponse(BaseModel):
    """Overview of a promoter's contributions for a given month."""

    monthlyPoints: str = Field(..., description="Total points for the month (e.g. '500.00')")
    totalPoints: str = Field(..., description="All-time total points")
    growthRate: Optional[float] = Field(None, description="Month-over-month growth rate (null if no previous month)")
    statusCounts: dict = Field(..., description="Count of contributions by status, e.g. {pending: 3, settled: 10}")

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Trend response
# ---------------------------------------------------------------------------
class TrendResponse(BaseModel):
    """Monthly contribution trend data."""

    categories: list[str] = Field(..., description="Month labels (e.g. ['2026-02', '2026-03', ...])")
    values: list[str] = Field(..., description="Points per month, aligned with categories")

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Composition response
# ---------------------------------------------------------------------------
class CompositionItem(BaseModel):
    """A single category in the contribution composition breakdown."""

    label: str = Field(..., description="Category display label")
    category: str = Field(..., description="Category enum value (bill, binding, followup, service, adjustment)")
    points: str = Field(..., description="Total points for this category")
    percent: float = Field(..., description="Percentage of total (0-100)")


class CompositionResponse(BaseModel):
    """Contribution composition breakdown by category."""

    categories: list[CompositionItem] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# List response (cursor-paginated)
# ---------------------------------------------------------------------------
class ContributionListItem(BaseModel):
    """Summary item in a contribution list."""

    id: int
    title: str
    points: str
    status: str
    category: str
    sourceType: Optional[str] = None
    occurredAt: Optional[datetime] = None
    settledAt: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContributionListResponse(BaseModel):
    """Cursor-paginated list of contribution records."""

    items: list[ContributionListItem]
    nextCursor: Optional[str] = None
    hasMore: bool = False

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Detail response
# ---------------------------------------------------------------------------
class ContributionDetailResponse(BaseModel):
    """Full detail of a single contribution record."""

    id: int
    title: str
    points: str
    status: str
    category: str
    sourceType: Optional[str] = None
    sourceId: Optional[str] = None
    calculationBase: Optional[str] = Field(None, description="Calculation base amount in yuan (e.g. '800.00')")
    coefficient: Optional[str] = Field(None, description="Coefficient used (e.g. '1.0')")
    calculationDescription: Optional[str] = Field(None, description="Human-readable description of the calculation")
    adjustmentReason: Optional[str] = None
    occurredAt: Optional[datetime] = None
    settledAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Team summary response
# ---------------------------------------------------------------------------
class TeamMemberItem(BaseModel):
    """Summary of a team member's contributions."""

    promoterId: int
    name: str
    nodeName: Optional[str] = None
    monthlyPoints: str = Field(default="0.00")
    statusCounts: dict = Field(default_factory=dict)


class TeamSummaryResponse(BaseModel):
    """Team contribution summary for the current promoter."""

    teamMonthlyPoints: str = Field(..., description="Total points from all direct team members")
    directMemberCount: int = Field(default=0)
    members: list[TeamMemberItem] = Field(default_factory=list)

    class Config:
        from_attributes = True
