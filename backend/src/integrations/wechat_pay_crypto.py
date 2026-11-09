"""RSA request signatures and pinned, overlapping platform verification keys."""

import base64
import binascii
import re
import time
from datetime import datetime, timezone

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .wechat_pay_types import PaymentGatewayError


def load_merchant_key(pem):
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size != 2048:
        raise ValueError("merchant RSA2048 key required")
    return key


def sign(key, message):
    return base64.b64encode(key.sign(message, padding.PKCS1v15(), hashes.SHA256())).decode()


class WechatPayVerifier:
    """Only operator-provisioned keys are trusted. Never fetch a key from a reply."""

    def __init__(self, entries):
        self.keys = {}
        for serial, pem in entries.items():
            before, after = None, None
            if "BEGIN CERTIFICATE" in pem:
                certificate = x509.load_pem_x509_certificate(pem.encode())
                if serial != format(certificate.serial_number, "X"):
                    raise ValueError("platform certificate serial mismatch")
                key = certificate.public_key()
                before, after = certificate.not_valid_before_utc, certificate.not_valid_after_utc
            else:
                if not re.fullmatch(r"PUB_KEY_ID_[0-9]+", serial):
                    raise ValueError("pinned public key ID required")
                key = serialization.load_pem_public_key(pem.encode())
            if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 2048:
                raise ValueError("platform RSA2048 key required")
            self.keys[serial] = (key, before, after)

    def verify(self, headers, body):
        try:
            serial, stamp, nonce = (
                headers[name]
                for name in ("Wechatpay-Serial", "Wechatpay-Timestamp", "Wechatpay-Nonce")
            )
            if not re.fullmatch(r"[0-9]{1,12}", stamp) or abs(int(time.time()) - int(stamp)) > 300:
                raise ValueError()
            if not 0 < len(nonce) <= 256 or "\r" in nonce or "\n" in nonce:
                raise ValueError()
            if (
                headers.get("Wechatpay-Signature-Type", "WECHATPAY2-SHA256-RSA2048")
                != "WECHATPAY2-SHA256-RSA2048"
            ):
                raise ValueError()
            key, before, after = self.keys[serial]
            now, signed_at = datetime.now(timezone.utc), datetime.fromtimestamp(
                int(stamp), timezone.utc
            )
            if before and not (before <= now <= after and before <= signed_at <= after):
                raise ValueError()
            signature = base64.b64decode(headers["Wechatpay-Signature"], validate=True)
            key.verify(
                signature,
                stamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n",
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (KeyError, TypeError, ValueError, binascii.Error, InvalidSignature):
            raise PaymentGatewayError("response_verification_failed") from None
