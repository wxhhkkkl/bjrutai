"""Pydantic schemas for binding / customer management endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Selectable Promoter
# =============================================================================


class SelectablePromoterItem(BaseModel):
    """A promoter that a doctor can select for binding."""

    promoterId: str = Field(..., description="Promoter ID (stringified int)")
    promoterCode: Optional[str] = Field(None, description="Promoter referral code")
    displayName: Optional[str] = Field(None, description="Display name of the promoter")
    avatarUrl: Optional[str] = Field(None, description="Avatar URL")
    orgNodeName: Optional[str] = Field(None, description="Organization node name")
    bindingCount: int = Field(0, description="Number of existing bound customers")


class SelectablePromoterListData(BaseModel):
    items: list[SelectablePromoterItem] = []
    nextCursor: Optional[str] = Field(None, description="Cursor for next page, null if no more")
    hasMore: bool = Field(False, description="Whether there are more results")


# =============================================================================
# Binding Request – Create
# =============================================================================


class CustomerInfoInput(BaseModel):
    """Customer info submitted during binding request creation."""

    name: Optional[str] = Field(None, max_length=100, description="Customer name")
    phone: Optional[str] = Field(None, min_length=11, max_length=11, description="Customer phone")
    idCard: Optional[str] = Field(None, max_length=18, description="Customer ID card number")
    medicalAccount: Optional[str] = Field(None, max_length=64, description="Medical insurance account")
    familyPhone: Optional[str] = Field(None, max_length=20, description="Family contact phone")
    remark: Optional[str] = Field(None, max_length=500, description="Remark")


class BindingRequestCreate(BaseModel):
    """Request body for creating a new binding request."""

    promoterId: str = Field(..., min_length=1, max_length=64, description="Target promoter user ID (stringified)")
    promoterCode: Optional[str] = Field(None, min_length=6, max_length=32, description="Target promoter code")
    customerInfo: Optional[CustomerInfoInput] = Field(None, description="Customer information")
    consentRecordId: Optional[int] = Field(None, description="Consent record ID for authorization")
    sourceType: str = Field("manual", description="Source type: scan|manual|share|import")


class BindingRequestCreateData(BaseModel):
    """Response data for a created binding request."""

    requestId: str = Field(..., description="Binding request ID")
    status: str = Field(..., description="Status enum value")
    statusLabel: str = Field(..., description="Human-readable status label")
    promoterId: Optional[str] = Field(None, description="Promoter ID")
    promoterName: Optional[str] = Field(None, description="Promoter display name")
    matchLevel: Optional[str] = Field(None, description="Match level if available")
    submittedAt: str = Field(..., description="ISO 8601 timestamp")
    expiresAt: Optional[str] = Field(None, description="Expiration ISO 8601 timestamp")


# =============================================================================
# Binding Request – List / Detail
# =============================================================================


class CustomerInfoDisplay(BaseModel):
    """Masked customer info for display."""

    name: Optional[str] = Field(None, description="Customer name (masked)")
    phone: Optional[str] = Field(None, description="Customer phone (masked)")
    idCard: Optional[str] = Field(None, description="ID card (masked)")
    medicalAccount: Optional[str] = Field(None, description="Medical account (masked)")
    familyPhone: Optional[str] = Field(None, description="Family phone (masked)")
    remark: Optional[str] = Field(None, description="Remark")


class InitiatorInfo(BaseModel):
    userId: str = Field(..., description="Initiator user ID")
    displayName: Optional[str] = Field(None, description="Display name")
    avatarUrl: Optional[str] = Field(None)
    phone: Optional[str] = Field(None, description="Masked phone")


class TargetInfo(BaseModel):
    userId: str = Field(..., description="Target user ID (promoter)")
    displayName: Optional[str] = Field(None, description="Display name")
    avatarUrl: Optional[str] = Field(None)
    phone: Optional[str] = Field(None, description="Masked phone")


class BindingEvent(BaseModel):
    action: str = Field(..., description="Action type: submitted|accepted|rejected|cancelled|retried|unbound|transferred")
    actionLabel: str = Field(..., description="Human-readable label")
    operatorId: str = Field(..., description="Operator user ID")
    operatorName: Optional[str] = Field(None, description="Operator display name")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class BindingRequestItem(BaseModel):
    """A binding request item in the list response."""

    requestId: str = Field(..., description="Binding request ID")
    status: str = Field(..., description="Status enum value")
    statusLabel: str = Field(..., description="Human-readable status label")
    matchLevel: Optional[str] = Field(None, description="Match level")
    initiator: Optional[InitiatorInfo] = Field(None, description="Request initiator")
    target: Optional[TargetInfo] = Field(None, description="Target promoter")
    customerInfo: Optional[CustomerInfoDisplay] = Field(None, description="Customer info (masked)")
    submittedAt: str = Field(..., description="ISO 8601 timestamp")
    expiresAt: Optional[str] = Field(None, description="Expiration timestamp")
    resolvedAt: Optional[str] = Field(None, description="Resolution timestamp")
    retryCount: int = Field(0, description="Number of retries attempted")
    failureReason: Optional[str] = Field(None, description="Reason for last failure")


class BindingRequestDetail(BaseModel):
    """Full detail response for a single binding request."""

    requestId: str = Field(..., description="Binding request ID")
    status: str = Field(..., description="Status enum value")
    statusLabel: str = Field(..., description="Human-readable status label")
    matchLevel: Optional[str] = Field(None, description="Match level")
    initiator: Optional[InitiatorInfo] = Field(None, description="Request initiator")
    target: Optional[TargetInfo] = Field(None, description="Target promoter")
    customerInfo: Optional[CustomerInfoDisplay] = Field(None, description="Customer info (masked)")
    events: list[BindingEvent] = Field(default_factory=list, description="Audit trail of actions")
    submittedAt: str = Field(..., description="ISO 8601 timestamp")
    expiresAt: Optional[str] = Field(None)
    resolvedAt: Optional[str] = Field(None)
    retryCount: int = Field(0)
    failureReason: Optional[str] = Field(None)
    version: int = Field(1, description="Optimistic lock version")


class BindingRequestListData(BaseModel):
    items: list[BindingRequestItem] = []
    nextCursor: Optional[str] = Field(None, description="Cursor for next page")
    hasMore: bool = Field(False)


# =============================================================================
# Binding Summary
# =============================================================================


class BindingSummaryData(BaseModel):
    totalBindings: int = Field(0, description="Total binding request count")
    activeBindings: int = Field(0, description="Currently bound count")
    pendingRequests: int = Field(0, description="Pending requests count")
    rejectedRequests: int = Field(0, description="Rejected count")
    expiredRequests: int = Field(0, description="Expired count")
    lastBindingAt: Optional[str] = Field(None, description="Last binding timestamp")


# =============================================================================
# Customer Info Update
# =============================================================================


class CustomerInfoUpdateRequest(BaseModel):
    """Request to update customer info on a pending binding request."""

    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=11, max_length=11)
    idCard: Optional[str] = Field(None, max_length=18)
    medicalAccount: Optional[str] = Field(None, max_length=64)
    familyPhone: Optional[str] = Field(None, max_length=20)
    remark: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = Field(None, max_length=500, description="Reason for correction")
    version: int = Field(..., ge=1, description="Optimistic lock version")


class CustomerInfoUpdateData(BaseModel):
    requestId: str
    customerInfo: Optional[CustomerInfoDisplay] = None
    updatedAt: str


# =============================================================================
# Admin: Unbind
# =============================================================================


class UnbindRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for unbinding")


class UnbindData(BaseModel):
    requestId: str
    status: str
    statusLabel: str
    unboundAt: str
    reason: str


# =============================================================================
# Admin: Transfer
# =============================================================================


class TransferRequest(BaseModel):
    newPromoterId: str = Field(..., min_length=1, max_length=64, description="New promoter user ID (stringified)")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for transfer")


class TransferData(BaseModel):
    requestId: str
    previousPromoterId: Optional[str] = None
    newPromoterId: str
    transferredAt: str
    reason: Optional[str] = None
