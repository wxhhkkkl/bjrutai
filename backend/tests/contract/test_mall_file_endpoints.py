import pytest

from src.models.mall_operations import MallFile
from tests.conftest import auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin


class Store:
    calls = 0

    async def issue_upload_ticket(self, **kwargs):
        self.calls += 1
        return {"uploadToken": "https://storage.invalid/upload"}

    async def head(self, key):
        return {"mime": "image/jpeg", "size": 32, "sha256": "a" * 64}

    async def finalize(self, source_key, destination_key):
        pass

    async def sign_get(self, key, *, expires_seconds):
        return "https://storage.invalid/download"


@pytest.mark.asyncio
async def test_upload_retry_verify_and_cross_buyer_denial(client, db_session):
    from src.api.v1.mall_files import get_mall_store
    from src.main import app

    store = Store()
    app.dependency_overrides[get_mall_store] = lambda: store
    user_id = await seed_user(db_session, user_type="personal")
    other_id = await seed_user(db_session, user_type="personal", openid="other-file-buyer")
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=user_id, user_type="personal"))
    headers["Idempotency-Key"] = "file-upload-probe-001"
    body = {
        "purpose": "aftersale_proof",
        "fileName": "proof.jpg",
        "contentType": "image/jpeg",
        "fileSize": 32,
        "sha256": "a" * 64,
    }
    url = "/api/v1/mall/files/upload-ticket"
    first = await client.post(url, headers=headers, json=body)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    file_id = first.json()["data"]["fileId"]
    replay = await client.post(url, headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["data"]["fileId"] == file_id
    assert "fileUrl" not in replay.json()["data"]
    verify_url = f"/api/v1/mall/files/{file_id}/verify"
    verified = await client.post(verify_url, headers=headers)
    assert verified.status_code == 200
    assert (await client.post(verify_url, headers=headers)).status_code == 200
    other = auth_header(make_access_token(user_id=other_id, user_type="personal"))
    other["Idempotency-Key"] = "other-file-probe-001"
    assert (await client.post(verify_url, headers=other)).status_code == 403
    assert (
        await client.get(f"/api/v1/mall/files/{file_id}/access", headers=other)
    ).status_code == 403
    record = await db_session.get(MallFile, int(file_id))
    assert record.version == 2


@pytest.mark.asyncio
async def test_default_storage_is_closed_without_outbound_permission(client, db_session):
    user_id = await seed_user(db_session, user_type="personal")
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=user_id, user_type="personal"))
    headers["Idempotency-Key"] = "file-default-off-probe"
    response = await client.post(
        "/api/v1/mall/files/upload-ticket",
        headers=headers,
        json={
            "purpose": "aftersale_proof",
            "fileName": "proof.jpg",
            "contentType": "image/jpeg",
            "fileSize": 32,
            "sha256": "a" * 64,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reconciliation_bill_accepts_private_csv_upload_ticket(client, db_session):
    from src.api.v1.mall_files import get_mall_store
    from src.main import app

    class EvidenceStore:
        async def issue_upload_ticket(self, **_kwargs):
            return {"uploadToken": "https://storage.invalid/reconciliation-upload"}

    store = EvidenceStore()
    app.dependency_overrides[get_mall_store] = lambda: store
    _, _, headers = await admin(
        db_session, ["mall.reconciliations.write", "mall.files.write"]
    )
    response = await client.post(
        "/api/v1/admin/mall/files/upload-ticket",
        headers={**headers, "Idempotency-Key": "reconciliation-csv-ticket-001"},
        json={
            "purpose": "reconciliation_evidence",
            "fileName": "synthetic-daily-statement.csv",
            "contentType": "text/csv",
            "fileSize": 1024,
            "sha256": "b" * 64,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["contentType"] == "text/csv"
