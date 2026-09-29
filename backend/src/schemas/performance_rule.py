"""Pydantic schemas for performance rule configuration."""

from typing import Optional

from pydantic import BaseModel, Field


class Tier(BaseModel):
    minCent: int = Field(..., ge=0)
    maxCent: Optional[int] = Field(None)  # null = 上不封顶
    ratio: float = Field(..., gt=0, le=1)


class PerformanceRuleUpdateRequest(BaseModel):
    tiers: list[Tier] = Field(..., min_length=1, max_length=20)


class PersonalPerformanceRuleUpdateRequest(BaseModel):
    """Tier ladder replacing the org's intra-org rule for one distributor."""

    tiers: list[Tier] = Field(..., min_length=1, max_length=20)
