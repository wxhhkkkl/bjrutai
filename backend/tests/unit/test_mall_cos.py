import hashlib
from urllib.parse import parse_qs, urlsplit

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
    signed_headers = parse_qs(urlsplit(ticket["uploadToken"]).query)["q-header-list"][0]
    assert signed_headers == "host;x-cos-acl"
    actual = await store.head("mall/test/sample.pdf")
    assert actual == {
        "mime": "application/pdf",
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def test_feedback_upload_ticket_pins_private_object_acl():
    client = COSClient()
    client._bucket, client._region = "test-123", "ap-beijing"
    client._secret_id, client._secret_key = "test-id", "test-key"

    token = client.generate_feedback_upload_token(
        user_id=7,
        file_name="feedback.jpg",
        content_type="image/jpeg",
        file_size=10,
    )

    assert "fileUrl" not in token
    assert parse_qs(urlsplit(token["uploadUrl"]).query)["q-header-list"][0] == "host;x-cos-acl"


@pytest.mark.asyncio
async def test_mall_cos_default_denies_remote_calls():
    from src.integrations.cos_client import MallCOSStore

    store = MallCOSStore(COSClient())
    with pytest.raises(ValueError, match="未开启"):
        await store.head("mall/test.pdf")


@pytest.mark.asyncio
async def test_mall_cos_puts_only_bounded_csv_or_xlsx_as_private_server_output():
    from src.integrations.cos_client import MallCOSStore

    client = COSClient()
    client._bucket, client._region = "test-123", "ap-beijing"
    client._secret_id, client._secret_key = "test-id", "test-key"
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200)

    store = MallCOSStore(client, outbound_enabled=True, transport=httpx.MockTransport(respond))
    body = b"paymentId,amountCent\r\n1,100\r\n"
    await store.put_private_bytes(
        "mall/verified/finance-exports/report.csv", body, mime="text/csv"
    )
    assert seen[0].method == "PUT"
    assert seen[0].content == body
    assert seen[0].headers["x-cos-acl"] == "private"
    assert seen[0].headers["content-type"] == "text/csv"
    with pytest.raises(ValueError):
        await store.put_private_bytes("mall/staging/report.csv", body, mime="text/csv")
    with pytest.raises(ValueError):
        await store.put_private_bytes(
            "mall/verified/finance-exports/report.pdf", body, mime="application/pdf"
        )
    with pytest.raises(ValueError):
        await store.put_private_bytes(
            "mall/verified/finance-exports/large.csv",
            b"x" * (10 * 1024 * 1024 + 1),
            mime="text/csv",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_finalize_conditions_copy_and_checks_xml_error_even_on_http_200(success):
    from src.integrations.cos_client import MallCOSStore

    client = COSClient()
    client._bucket, client._region = "test-123", "ap-beijing"
    client._secret_id, client._secret_key = "test-id", "test-key"
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "HEAD":
            return httpx.Response(200, headers={"ETag": '"current-version"'})
        body = (
            b'<CopyObjectResult><ETag>"copied"</ETag></CopyObjectResult>'
            if success
            else b"<Error><Code>InternalError</Code></Error>"
        )
        return httpx.Response(200, content=body)

    store = MallCOSStore(client, outbound_enabled=True, transport=httpx.MockTransport(respond))
    if success:
        await store.finalize("mall/staging/a.jpg", "mall/verified/a.jpg")
        assert requests[-1].headers["x-cos-copy-source-if-match"] == '"current-version"'
        assert requests[-1].headers["x-cos-acl"] == "private"
    else:
        with pytest.raises(ValueError, match="转存"):
            await store.finalize("mall/staging/a.jpg", "mall/verified/a.jpg")
    with pytest.raises(ValueError):
        await store.issue_upload_ticket(
            object_key="mall/verified/a.jpg", mime="image/jpeg", size=1, sha256="a" * 64
        )
