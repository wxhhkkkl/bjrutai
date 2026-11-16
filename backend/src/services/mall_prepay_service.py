"""Authenticated prepay storage, bound to immutable payment facts; no signatures cached."""

import base64
import json
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..integrations.wechat_pay_types import PaymentGatewayError


class PrepayVault:
    def __init__(self, keys, active_key):
        try:
            self._keys = {}
            for name, value in keys.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name):
                    raise ValueError()
                raw = base64.b64decode(value, altchars=b"-_", validate=True)
                if len(raw) != 32:
                    raise ValueError()
                self._keys[name] = AESGCM(raw)
            if active_key not in self._keys:
                raise ValueError()
            self._active = active_key
        except (ValueError, TypeError, AttributeError):
            raise PaymentGatewayError("prepay_key_unavailable") from None

    @staticmethod
    def _context(payment):
        return json.dumps(
            [
                "mall-prepay-v1",
                payment.id,
                payment.out_trade_no,
                payment.appid_snapshot,
                payment.mchid_snapshot,
                payment.amount_cent,
                payment.currency,
                payment.expires_at.isoformat(),
            ],
            separators=(",", ":"),
        ).encode()

    def seal(self, payment, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", token):
            raise PaymentGatewayError("prepay_unavailable")
        nonce = os.urandom(12)
        payload = self._keys[self._active].encrypt(nonce, token.encode(), self._context(payment))
        return "v1." + self._active + "." + base64.urlsafe_b64encode(nonce + payload).decode()

    def open(self, payment):
        try:
            version, name, payload = payment.prepay_ciphertext.split(".")
            if version != "v1":
                raise ValueError()
            raw = base64.b64decode(payload, altchars=b"-_", validate=True)
            token = self._keys[name].decrypt(raw[:12], raw[12:], self._context(payment)).decode()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", token):
                raise ValueError()
            return token
        except Exception:
            raise PaymentGatewayError("prepay_unavailable") from None
