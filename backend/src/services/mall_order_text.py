"""Mask identifier-like text in optional order notes; raw notes stay inside the backend."""

import re


def safe_order_text(value):
    if not value:
        return None
    value = re.sub(
        r"((?:医保|医疗)(?:账户|账号)?\s*[:：]?\s*)[A-Za-z0-9-]{6,}", r"\1[账号已隐藏]", value
    )
    text = re.sub(r"(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?![\dXx])", r"\1********\2", value)
    text = re.sub(r"(?<!\d)(1[3-9]\d)[ -]?(\d{4})[ -]?(\d{4})(?!\d)", r"\1****\3", text)
    text = re.sub(r"[0-9]{7,}", "[号码已隐藏]", text)
    return text
