import hashlib

import httpx
import pytest

from src.integrations.cos_client import COSClient


@pytest.mark.asyncio
async def test_mall_cos_checks_actual_bytes_and_never_returns_public_url():
    from src.integrations.cos_client import MallCOSStore

    client = COSClient()
    client._bucket, client._region = "test-123", "ap-beijing"
    client._secret_id, client._secret_key = "test-id", "test-key"
    content = b"actual-test-content"

    def respond(request):
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": str(len(content)),
                "ETag": '"test-etag"',
            },
            stream=httpx.ByteStream(content if request.method == "GET" else b""),
        )

    store = MallCOSStore(client, outbound_enabled=True, transport=httpx.MockTransport(respond))
    ticket = await store.issue_upload_ticket(
        object_key="mall/test/sample.pdf",
        mime="application/pdf",
        size=len(content),
        sha256="a" * 64,
    )
    assert "fileUrl" not in ticket and "uploadToken" in ticket
    actual = await store.head("mall/test/sample.pdf")
    assert actual == {
        "mime": "application/pdf",
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


@pytest.mark.asyncio
async def test_mall_cos_default_denies_remote_calls():
    from src.integrations.cos_client import MallCOSStore

    store = MallCOSStore(COSClient())
    with pytest.raises(ValueError, match="未开启"):
        await store.head("mall/test.pdf")
