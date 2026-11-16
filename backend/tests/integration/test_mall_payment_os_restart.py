"""A killed worker resumes the same durable payment intent after restart."""

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select

from src.models.mall_base import utc_now
from src.models.mall_operations import MallJob
from tests.unit.test_mall_payment_service import payable, success

HANGING_WORKER = r'''
import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.wechat_pay_types import PrepayResult
from src.services.mall_payment_execution_service import MallPaymentExecutor
from src.services.mall_prepay_service import PrepayVault
from src.tasks.mall_tasks import run_mall_worker_once


class HangingGateway:
    appid = "wx-test"
    mchid = "test-merchant"

    async def prepay(self, **request):
        assert request["out_trade_no"]
        Path(os.environ["MALL_RESTART_MARKER"]).write_text("external_call_started")
        await asyncio.Future()

    async def query(self, identity):
        raise AssertionError("first attempt must stop during prepay")

    async def close(self, identity):
        raise AssertionError("first attempt must not close a live payment")


async def main():
    engine = create_async_engine(
        os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    vault = PrepayVault(
        {"k1": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="}, "k1"
    )
    executor = MallPaymentExecutor(
        sessions,
        lambda _payment: HangingGateway(),
        vault,
        "https://example.test/notify",
    )
    await run_mall_worker_once(
        sessions,
        handlers={"mall_payment_create": executor},
        enabled=True,
        timeout_seconds=50,
    )
    await engine.dispose()


asyncio.run(main())
'''


@pytest.mark.asyncio
async def test_killed_payment_worker_restarts_by_querying_original_trade_number(
    db_session, monkeypatch, tmp_path
):
    """Process A dies after the fake outbound call begins; process B recovers."""
    from tests.unit.test_mall_payment_execution import Channel, execute

    _, order, skus, payment = await payable(db_session, monkeypatch)
    payment_id, out_trade_no = payment.id, payment.out_trade_no
    database_url = str(db_session.get_bind().url)
    marker = tmp_path / "fake-payment-call.started"
    environment = {
        key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR") if key in os.environ
    }
    environment.update(
        DATABASE_URL=database_url,
        RATE_LIMIT_ENABLED="false",
        MALL_RESTART_MARKER=str(marker),
    )
    project_root = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = str(project_root)

    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        HANGING_WORKER,
        cwd=project_root,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        deadline = asyncio.get_running_loop().time() + 12
        while not marker.exists() and worker.returncode is None:
            if asyncio.get_running_loop().time() >= deadline:
                output, error = await worker.communicate()
                raise AssertionError(
                    "first worker did not reach the fake channel: "
                    f"stdout={output[-1000:]!r} stderr={error[-1000:]!r}"
                )
            await asyncio.sleep(0.05)
        assert marker.read_text() == "external_call_started"
        worker.terminate()
        await asyncio.wait_for(worker.wait(), timeout=5)
    finally:
        if worker.returncode is None:
            worker.kill()
            await worker.wait()

    await db_session.refresh(payment)
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_payment_create", MallJob.entity_id == payment_id
        )
    )
    await db_session.refresh(job)
    assert payment.status == "unknown" and payment.prepay_ciphertext is None
    assert job.status == "running"

    # Expired lease recovery models scheduler restart/reclaim; no process-local
    # state, cached channel response, or new merchant identity is available.
    job.lease_until = utc_now()
    job.next_run_at = utc_now()
    await db_session.commit()
    channel = Channel(payment, order)
    channel.fact = replace(success(payment, order, paid_at=utc_now()), state="NOTPAY")
    assert await execute(channel)

    await db_session.refresh(payment)
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    await db_session.refresh(job)
    assert channel.calls == ["query", "prepay"]
    assert payment.out_trade_no == out_trade_no
    assert payment.status == "pending" and payment.prepay_ciphertext
    assert channel.payment.out_trade_no == out_trade_no
    assert skus[0].reserved_qty == 1 and order.paid_amount_cent == 0
    assert job.status == "retry"
