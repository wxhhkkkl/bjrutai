"""Pydantic schemas for promotion code endpoints (US10)."""

from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Promotion Code
# ──────────────────────────────────────────────
class PromotionCodeResponse(BaseModel):
    refToken: str
    sourceCode: str
    qrImageUrl: Optional[str] = None
    shareTitle: Optional[str] = None
    sharePath: Optional[str] = None
    status: str
    scanCount: int
    leadCount: int
    bindCount: int
    createdAt: str
    updatedAt: str


class RefreshResponse(BaseModel):
    refToken: str
    oldRefToken: Optional[str] = None
    sourceCode: str
    qrImageUrl: Optional[str] = None
    shareTitle: Optional[str] = None
    sharePath: Optional[str] = None
    status: str
    refreshReason: Optional[str] = None
    refreshedAt: str


# ──────────────────────────────────────────────
# Statistics
# ──────────────────────────────────────────────
class StatisticsResponse(BaseModel):
    period: str
    scanCount: int
    leadCount: int
    bindCount: int
    conversionRate: float


# ──────────────────────────────────────────────
# Poster
# ──────────────────────────────────────────────
class PosterResponse(BaseModel):
    posterUrl: str
    qrImageUrl: Optional[str] = None
    shareTitle: Optional[str] = None
    sharePath: Optional[str] = None
    sourceCode: str
