"""Unit tests for org_qualification_service (US2)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.exceptions import BadRequestException, NotFoundException
from src.models.org_qualification import OrgQualStatus
from src.schemas.org_qualification import OrgQualificationCreate, OrgQualificationReview
from src.services import org_qualification_service, organization_service
from src.schemas.organization import OrgCreate


async def _seed_org(db) -> int:
    org = await organization_service.create_org(
        db, OrgCreate(name="总部", orgType="headquarters")
    )
    return org.id


def _create_data():
    return OrgQualificationCreate(
        legalEntityName="北京儒泰测试公司",
        qualificationTypes=["business_license"],
        creditCode="91110000TEST000001",
        fileUrls=[{"url": "https://cos.example.com/q.pdf", "type": "pdf", "size": 12345}],
        validUntil=(datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d"),
    )


@pytest.mark.asyncio
async def test_create_qualification_reviewing(db_session):
    org_id = await _seed_org(db_session)
    q = await org_qualification_service.create_qualification(db_session, org_id, _create_data())
    assert q["status"] == "reviewing"
    assert q["orgId"] == str(org_id)


@pytest.mark.asyncio
async def test_approve_qualification(db_session):
    org_id = await _seed_org(db_session)
    q = await org_qualification_service.create_qualification(db_session, org_id, _create_data())
    qid = int(q["qualificationId"])
    reviewed = await org_qualification_service.review_qualification(
        db_session, qid, OrgQualificationReview(action="approve"), reviewer_id=1
    )
    assert reviewed["status"] == "approved"
    assert reviewed["reviewedBy"] == "1"


@pytest.mark.asyncio
async def test_reject_qualification_requires_comment(db_session):
    org_id = await _seed_org(db_session)
    q = await org_qualification_service.create_qualification(db_session, org_id, _create_data())
    qid = int(q["qualificationId"])
    with pytest.raises(BadRequestException):
        await org_qualification_service.review_qualification(
            db_session, qid, OrgQualificationReview(action="reject")
        )
    reviewed = await org_qualification_service.review_qualification(
        db_session, qid, OrgQualificationReview(action="reject", comment="资料不完整")
    )
    assert reviewed["status"] == "rejected"


@pytest.mark.asyncio
async def test_list_and_history(db_session):
    org_id = await _seed_org(db_session)
    await org_qualification_service.create_qualification(db_session, org_id, _create_data())
    items = await org_qualification_service.list_qualifications(db_session, org_id)
    assert len(items) == 1
    history = await org_qualification_service.get_history(db_session, org_id)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_missing_org_raises_not_found(db_session):
    with pytest.raises(NotFoundException):
        await org_qualification_service.create_qualification(
            db_session, 99999, _create_data()
        )


@pytest.mark.asyncio
async def test_invalid_valid_until_rejected(db_session):
    org_id = await _seed_org(db_session)
    data = _create_data()
    data.valid_until = "not-a-date"
    with pytest.raises(BadRequestException):
        await org_qualification_service.create_qualification(db_session, org_id, data)


@pytest.mark.asyncio
async def test_approved_qualification_unblocks_business(db_session):
    org_id = await _seed_org(db_session)
    q = await org_qualification_service.create_qualification(db_session, org_id, _create_data())
    qid = int(q["qualificationId"])
    await org_qualification_service.review_qualification(
        db_session, qid, OrgQualificationReview(action="approve")
    )
    reasons = await organization_service.get_org_business_blocked_reasons(db_session, org_id)
    assert reasons == []
