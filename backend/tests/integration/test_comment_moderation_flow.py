"""US4 integration tests for the public visibility boundary."""

import pytest


@pytest.mark.asyncio
async def test_flagged_comment_is_pending_and_never_public(
    client, published_article, comment_user_auth_headers
):
    response = await client.post(
        f"/api/v1/articles/{published_article}/comments",
        headers={**comment_user_auth_headers, "Idempotency-Key": "moderation-flow-001"},
        json={"content": "这段暴力威胁内容需要审核"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert response.json()["data"]["moderationStatus"] == "flagged"

    listing = await client.get(
        f"/api/v1/articles/{published_article}/comments",
        headers=comment_user_auth_headers,
    )
    assert listing.status_code == 200
    assert "暴力威胁" not in str(listing.json())
