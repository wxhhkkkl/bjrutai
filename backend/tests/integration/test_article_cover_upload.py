"""Regression tests for article-cover uploads through the API."""

import pytest
from httpx import AsyncClient


class _FakeCOSClient:
    def generate_upload_token(self, **kwargs):
        assert kwargs["key_prefix"] == "articles/"
        assert kwargs["file_size"] == len(b"cover-image")
        return {
            "uploadUrl": "https://cos.example.test/upload",
            "fileUrl": "https://cos.example.test/articles/cover.jpg",
        }


class _FakeCOSResponse:
    status_code = 200


class _FakeHTTPClient:
    uploaded = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def put(self, url, *, content, headers):
        self.__class__.uploaded = {"url": url, "content": content, "headers": headers}
        return _FakeCOSResponse()


@pytest.mark.asyncio
async def test_article_cover_upload_is_proxied_through_backend(
    client: AsyncClient, admin_auth_headers: dict, monkeypatch
):
    """The browser posts the file to our API, so no COS browser CORS is needed."""
    from src.api.v1 import cos_upload

    monkeypatch.setattr(cos_upload, "get_cos_client", lambda: _FakeCOSClient())
    monkeypatch.setattr(cos_upload.httpx, "AsyncClient", _FakeHTTPClient)

    response = await client.post(
        "/api/v1/admin/articles/upload-image-file",
        files={"file": ("cover.jpg", b"cover-image", "image/jpeg")},
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["fileUrl"] == "https://cos.example.test/articles/cover.jpg"
    assert _FakeHTTPClient.uploaded == {
        "url": "https://cos.example.test/upload",
        "content": b"cover-image",
        "headers": {"Content-Type": "image/jpeg"},
    }

