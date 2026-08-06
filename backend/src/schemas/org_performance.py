"""Pydantic schemas for org performance endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class OrgMemberPerformance(BaseModel):
    """Per-distributor 消费金额 (this month + cumulative, cents)."""

    distributor_id: str = Field(..., alias="distributorId")
    org_id: str = Field(..., alias="orgId")
    name: Optional[str] = None
    this_month: int = Field(0, alias="thisMonth")
    cumulative: int = Field(0)


class OrgPerformanceResponse(BaseModel):
    """Response for the org performance view."""

    org_id: str = Field(..., alias="orgId")
    org_name: Optional[str] = Field(None, alias="orgName")
    period: Optional[str] = None
    summary: dict = Field(default_factory=dict)
    sub_orgs: list[dict] = Field(default_factory=list, alias="subOrgs")
    members: list[OrgMemberPerformance] = Field(default_factory=list)

    class Config:
        populate_by_name = True
