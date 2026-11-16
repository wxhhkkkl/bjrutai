"""Bounded asynchronous finance exports remain private and replay-safe."""

import hashlib
import io

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import func, select

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException, ForbiddenException
from src.models.mall_finance import MallFinanceExportRequest
from src.models.mall_operations import MallCommand, MallFile, MallJob
from src.services.mall_file_service import get_mall_file_access
from tests.unit.test_mall_aftersale_service import admin_actor


class MemoryPrivateStore:
    def __init__(self):
        self.objects = {}
        self.signed_for = None

    async def put_private_bytes(self, object_key, content, *, mime):
        self.objects[object_key] = (bytes(content), mime)

    async def head(self, object_key):
        item = self.objects.get(object_key)
        if item is None:
            return None
        content, mime = item
        return {"mime": mime, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}

    async def sign_get(self, object_key, *, expires_seconds):
        self.signed_for = object_key, expires_seconds
        return "https://private.invalid/short"


def request(**changes):
    from src.schemas.mall_finance import FinanceExport

    payload = {
        "from": "2026-11-01T00:00:00+08:00",
        "to": "2026-11-02T00:00:00+08:00",
        "format": "csv",
    }
    payload.update(changes)
    return FinanceExport.model_validate_json(__import__("json").dumps(payload))


def test_finance_export_requires_timezone_nonempty_range_and_at_most_31_days():
    from src.schemas.mall_finance import FinanceExport

    request()
    with pytest.raises(ValidationError):
        FinanceExport.model_validate_json(
            '{"from":"2026-11-01T00:00:00","to":"2026-11-02T00:00:00+08:00","format":"csv"}'
        )
    with pytest.raises(ValidationError):
        request(to="2026-11-01T00:00:00+08:00")
    with pytest.raises(ValidationError):
        request(to="2026-12-03T00:00:00+08:00")


def test_csv_and_xlsx_export_escape_formula_text_and_never_invent_fee_columns():
    from src.services.mall_export_service import render_finance_export

    row = {
        "orderNo": "=1+1",
        "buyerName": "  @SUM(A1:A2)",
        "outTradeNo": "+cmd",
        "amountCent": 900,
        "refundSucceededCent": 0,
        "netReceivedCent": 900,
        "status": "succeeded",
        "confirmedAt": "2026-11-01T00:00:00Z",
        "createdAt": "2026-11-01T00:00:00Z",
    }
    csv_content, csv_mime = render_finance_export("payments", [row], "csv")
    assert csv_mime == "text/csv"
    csv_text = csv_content.decode("utf-8-sig")
    assert "'=1+1" in csv_text and "'  @SUM(A1:A2)" in csv_text and "'+cmd" in csv_text
    assert "费用" not in csv_text and "feeCent" not in csv_text
    assert "支付金额（元）" in csv_text and "支付成功" in csv_text
    assert ",9.00,0.00,9.00," in csv_text
    assert len(csv_text.splitlines()) == 2

    xlsx_content, xlsx_mime = render_finance_export("payments", [row], "xlsx")
    assert xlsx_mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    sheet = load_workbook(io.BytesIO(xlsx_content), read_only=True, data_only=False).active
    values = next(sheet.iter_rows(min_row=2, values_only=True))
    assert "=1+1" in values
    assert "支付成功" in values
    assert values[7:10] == (9, 0, 9)
    assert all(cell.data_type != "f" for row_cells in sheet.iter_rows() for cell in row_cells)


@pytest.mark.asyncio
async def test_export_replay_keeps_scope_and_rechecks_permission(db_session):
    from src.services.mall_export_service import create_finance_export

    actor = await admin_actor(db_session, ["mall.finance.export"])
    body = request()
    first = await create_finance_export(
        db_session, actor, "payments", body, key="finance-export-unit-0001"
    )
    replay = await create_finance_export(
        db_session, actor, "payments", body, key="finance-export-unit-0001"
    )
    assert first["requestId"] == replay["requestId"]
    assert first["jobId"] == replay["jobId"]
    assert await db_session.scalar(select(func.count()).select_from(MallFinanceExportRequest)) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(MallJob.kind == "mall_finance_export")
    ) == 1

    with pytest.raises(ConflictException):
        await create_finance_export(
            db_session,
            actor,
            "payments",
            request(status="unknown"),
            key="finance-export-unit-0001",
        )
    revoked = MallActor("admin", actor.actor_id, frozenset())
    with pytest.raises(ForbiddenException):
        await create_finance_export(
            db_session, revoked, "payments", body, key="finance-export-unit-0001"
        )


@pytest.mark.asyncio
async def test_generated_export_is_private_verified_and_download_rechecks_both_permissions(
    db_session
):
    from src.services.mall_export_service import create_finance_export, process_finance_export

    actor = await admin_actor(db_session, ["mall.finance.export", "mall.files.read"])
    export = await create_finance_export(
        db_session, actor, "payments", request(), key="finance-export-unit-0002"
    )
    store = MemoryPrivateStore()
    await process_finance_export(db_session, int(export["requestId"]), store)

    file = await db_session.get(MallFile, int(export["fileId"]))
    command = await db_session.get(MallCommand, int(export["commandId"]))
    assert file.status == "verified" and file.purpose == "finance_export"
    assert file.object_key.startswith("mall/verified/finance-exports/")
    assert command.status == "completed" and command.entity_id == file.id
    assert file.sha256 == hashlib.sha256(store.objects[file.object_key][0]).hexdigest()

    access = await get_mall_file_access(db_session, actor=actor, file_id=file.id, storage=store)
    assert access == {"accessUrl": "https://private.invalid/short", "expiresIn": 60}
    assert store.signed_for == (file.object_key, 60)
    revoked = MallActor("admin", actor.actor_id, frozenset({"mall.files.read"}))
    with pytest.raises(ForbiddenException):
        await get_mall_file_access(db_session, actor=revoked, file_id=file.id, storage=store)


@pytest.mark.asyncio
async def test_failed_export_replay_reuses_same_private_file_and_job(db_session):
    from src.services.mall_export_service import create_finance_export

    actor = await admin_actor(db_session, ["mall.finance.export"])
    body = request()
    first = await create_finance_export(
        db_session, actor, "payments", body, key="finance-export-unit-0003"
    )
    export = await db_session.get(MallFinanceExportRequest, int(first["requestId"]))
    job = await db_session.scalar(
        select(MallJob).where(MallJob.kind == "mall_finance_export", MallJob.entity_id == export.id)
    )
    export.status, export.error_code = "failed", "generation_failed"
    job.status, job.attempts = "manual", 5
    await db_session.flush()

    replay = await create_finance_export(
        db_session, actor, "payments", body, key="finance-export-unit-0003"
    )
    assert replay["jobId"] == first["jobId"]
    assert replay["fileId"] == first["fileId"]
    await db_session.refresh(job)
    assert job.status == "ready" and job.attempts == 0
    assert export.status == "queued" and export.error_code is None
