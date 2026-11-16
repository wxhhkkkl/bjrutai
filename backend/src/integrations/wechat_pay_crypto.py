"""WeChat Pay APIv2 XML signatures and encrypted refund notifications."""

import base64
import hashlib
import hmac
import re
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from .wechat_pay_types import PaymentGatewayError

SIGN_TYPES = {"MD5", "HMAC-SHA256"}


def _api_key_bytes(api_key: str) -> bytes:
    if not isinstance(api_key, str):
        raise ValueError("APIv2 key is invalid")
    raw = api_key.encode("utf-8")
    if len(raw) != 32:
        raise ValueError("APIv2 key must contain 32 bytes")
    return raw


def sign_v2(params: dict, api_key: str, sign_type: str = "MD5") -> str:
    """Sign non-empty APIv2 fields using the configured merchant key."""
    key = _api_key_bytes(api_key)
    if sign_type not in SIGN_TYPES:
        raise ValueError("unsupported APIv2 signature type")
    fields = []
    for name, value in params.items():
        if name == "sign" or value is None or value == "":
            continue
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError("invalid APIv2 parameter name")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("invalid APIv2 parameter value")
        fields.append((name, str(value)))
    fields.sort(key=lambda pair: pair[0])
    string_a = "&".join(f"{name}={value}" for name, value in fields)
    message = f"{string_a}&key={key.decode('utf-8')}".encode("utf-8")
    if sign_type == "HMAC-SHA256":
        return hmac.new(key, message, hashlib.sha256).hexdigest().upper()
    return hashlib.md5(message).hexdigest().upper()


def verify_v2_signature(
    params: dict, api_key: str, *, fallback_sign_type: str = "MD5"
) -> bool:
    try:
        sign_type = params.get("sign_type") or fallback_sign_type
        supplied = params.get("sign")
        if sign_type not in SIGN_TYPES or not isinstance(supplied, str):
            return False
        expected = sign_v2(params, api_key, sign_type)
        return hmac.compare_digest(supplied.upper(), expected)
    except (TypeError, ValueError, UnicodeError):
        return False


def build_v2_xml(params: dict) -> bytes:
    root = ET.Element("xml")
    for name, value in params.items():
        if value is None or value == "":
            continue
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ValueError("invalid APIv2 XML value")
        ET.SubElement(root, name).text = str(value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_v2_xml(body: bytes, *, allowed_roots=("xml", "root")) -> dict:
    """Parse bounded flat V2 XML while rejecting DTDs, entities and duplicates."""
    if not isinstance(body, bytes) or not 0 < len(body) <= 1_100_000:
        raise PaymentGatewayError("invalid_gateway_xml")
    upper = body.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise PaymentGatewayError("invalid_gateway_xml")
    try:
        root = ET.fromstring(body)
        if root.tag not in allowed_roots:
            raise ValueError()
        result = {}
        for child in root:
            if not isinstance(child.tag, str) or child.tag in result or len(child):
                raise ValueError()
            result[child.tag] = child.text or ""
        return result
    except (ET.ParseError, ValueError, UnicodeError):
        raise PaymentGatewayError("invalid_gateway_xml") from None


def decrypt_refund_req_info(ciphertext: str, api_key: str) -> dict:
    """Decrypt V2 refund `req_info` as documented by WeChat Pay."""
    raw_key = _api_key_bytes(api_key)
    if not isinstance(ciphertext, str) or not 0 < len(ciphertext) <= 8192:
        raise PaymentGatewayError("invalid_refund_notification")
    try:
        encrypted = base64.b64decode(ciphertext, validate=True)
        if not encrypted or len(encrypted) % 16:
            raise ValueError()
        # WeChat's V2 protocol uses the 32-byte lowercase hex MD5 string as the
        # AES-256 key (not the 16-byte raw MD5 digest).
        aes_key = hashlib.md5(raw_key).hexdigest().encode("ascii")
        decryptor = Cipher(algorithms.AES(aes_key), modes.ECB()).decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()
        unpadder = PKCS7(algorithms.AES.block_size).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
    except (ValueError, TypeError):
        raise PaymentGatewayError("invalid_refund_notification") from None
    return parse_v2_xml(plaintext, allowed_roots=("root", "xml"))
