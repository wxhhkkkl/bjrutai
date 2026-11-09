"""Provider-protocol callback routes; the only envelope exception is this pair."""

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...core.exceptions import ConflictException, NotFoundException
from ...integrations.wechat_pay_types import PaymentGatewayError
from ...services.mall_gateway_callback_service import (
    MAX_CALLBACK_BODY_BYTES,
    CallbackFailureError,
    accept_verified_callback,
    validate_callback_fact,
    verify_and_decrypt_callback,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mall-gateway/wechat", tags=["mall-gateway-callbacks"])


async def _read_notification_body(request: Request) -> bytes:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise CallbackFailureError(400, "invalid_content_type")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            declared_size = int(length)
        except ValueError:
            raise CallbackFailureError(400, "invalid_content_length") from None
        if declared_size <= 0 or declared_size > MAX_CALLBACK_BODY_BYTES:
            raise CallbackFailureError(413, "callback_body_too_large")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_CALLBACK_BODY_BYTES:
            raise CallbackFailureError(413, "callback_body_too_large")
    if not body:
        raise CallbackFailureError(400, "empty_callback_body")
    return bytes(body)


def _failure(status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": "FAIL", "message": "通知接收失败"},
    )


async def _receive(kind: str, request: Request, db: AsyncSession):
    try:
        async with asyncio.timeout(4.5):
            body = await _read_notification_body(request)
            callback = verify_and_decrypt_callback(request.headers, body, kind=kind)
            await validate_callback_fact(db, callback)
            await accept_verified_callback(db, callback)
            # Provider success is returned only after the inbox and recoverable job
            # share a durable commit. The worker owns the separate business transaction.
            await db.commit()
        return Response(status_code=204)
    except CallbackFailureError as exc:
        await db.rollback()
        logger.warning("mall_wechat_callback_rejected kind=%s code=%s", kind, exc.code)
        return _failure(exc.status_code)
    except (ConflictException, NotFoundException):
        await db.rollback()
        logger.warning("mall_wechat_callback_rejected kind=%s code=business_mismatch", kind)
        return _failure(400)
    except PaymentGatewayError:
        await db.rollback()
        logger.warning("mall_wechat_callback_rejected kind=%s code=invalid_provider_fact", kind)
        return _failure(400)
    except TimeoutError:
        await db.rollback()
        logger.warning("mall_wechat_callback_failed kind=%s code=processing_timeout", kind)
        return _failure(503)
    except Exception as exc:
        await db.rollback()
        logger.error(
            "mall_wechat_callback_failed kind=%s error_type=%s",
            kind,
            type(exc).__name__,
        )
        return _failure(500)


@router.post("/payment-notify", operation_id="wechatPaymentNotify")
async def payment_notify(request: Request, db: AsyncSession = Depends(get_db)):
    return await _receive("payment", request, db)


@router.post("/refund-notify", operation_id="wechatRefundNotify")
async def refund_notify(request: Request, db: AsyncSession = Depends(get_db)):
    return await _receive("refund", request, db)
