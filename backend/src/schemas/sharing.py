"""Pydantic schemas for Sharing Rules and Contribution Coefficient."""

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ValidationInfo


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class SharingRuleCreate(BaseModel):
    """Schema for creating a new sharing rule (admin only)."""

    # Level refers to the org-tree depth (FR-005: arbitrary depth, no fixed L1-L6).
    level: int = Field(..., ge=1, description="Org level the rule applies to")
    rule_type: str = Field(
        ..., pattern=r"^(fixed_ratio|fixed_amount|tiered)$", description="Rule type"
    )
    base: str = Field(
        ..., pattern=r"^(paid_amount|total_amount)$", description="Calculation base"
    )
    value: str = Field(..., min_length=1, max_length=5000, description="Rule value")
    effective_at: datetime = Field(..., description="When the rule takes effect")
    expires_at: Optional[datetime] = Field(None, description="When the rule expires")

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str, info: ValidationInfo) -> str:
        rule_type = info.data.get("rule_type")
        if rule_type == "fixed_ratio":
            try:
                ratio = float(v)
                if ratio < 0 or ratio > 1:
                    raise ValueError("Ratio must be between 0 and 1")
            except ValueError:
                raise ValueError("Invalid ratio value: must be a decimal between 0 and 1")
        elif rule_type == "fixed_amount":
            try:
                amount = int(v)
                if amount <= 0:
                    raise ValueError("Amount must be a positive integer (in cents)")
            except ValueError:
                raise ValueError("Invalid amount value: must be a positive integer")
        elif rule_type == "tiered":
            try:
                tiers = json.loads(v)
                if not isinstance(tiers, list) or len(tiers) == 0:
                    raise ValueError("Tiered value must be a non-empty JSON array")
                for i, tier in enumerate(tiers):
                    if not isinstance(tier, dict):
                        raise ValueError(f"Tier {i} must be a JSON object")
                    if "threshold" not in tier or "ratio" not in tier:
                        raise ValueError(f"Tier {i} must contain 'threshold' and 'ratio'")
                    if not isinstance(tier["threshold"], (int, float)) or tier["threshold"] <= 0:
                        raise ValueError(f"Tier {i} threshold must be a positive number")
                    if not isinstance(tier["ratio"], (int, float)) or tier["ratio"] < 0 or tier["ratio"] > 1:
                        raise ValueError(f"Tier {i} ratio must be between 0 and 1")
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON for tiered rule value")
        return v


class SharingRuleUpdate(BaseModel):
    """Schema for updating an existing sharing rule with optimistic locking."""

    level: Optional[int] = Field(None, ge=1)
    rule_type: Optional[str] = Field(None, pattern=r"^(fixed_ratio|fixed_amount|tiered)$")
    base: Optional[str] = Field(None, pattern=r"^(paid_amount|total_amount)$")
    value: Optional[str] = Field(None, min_length=1, max_length=5000)
    effective_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    version: int = Field(..., ge=1, description="Current version for optimistic locking")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class SharingRuleResponse(BaseModel):
    """Response for a single sharing rule."""

    ruleId: str
    level: int
    rule_type: str
    base: str
    value: str
    effective_at: datetime
    expires_at: Optional[datetime] = None
    status: str
    statusLabel: str
    version: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SharingRuleListResponse(BaseModel):
    """Cursor-paginated list of sharing rules."""

    items: list[SharingRuleResponse]
    nextCursor: Optional[str] = None
    hasMore: bool = False
