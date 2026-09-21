"""Dependency-free local moderation for article comments."""

from dataclasses import dataclass
import re
import unicodedata

from ..core.exceptions import BadRequestException


RULE_VERSION = "local-2026-09-v1"

# These are intentionally conservative starter rules.  The complete local
# dictionary remains backend-only and can be expanded without changing the API.
_RULES: dict[str, tuple[str, ...]] = {
    "sexual": ("色情", "淫秽", "裸体", "卖淫", "强奸"),
    "violence": ("暴力", "杀人", "砍人", "炸弹", "自杀"),
    "political": ("恐怖主义", "分裂国家", "政治暴动", "推翻政府"),
}
_URL_RE = re.compile(r"(?:https?://|www\.|[a-z0-9.-]+\.(?:com|cn|net|org)(?:/|\b))", re.I)
_HTML_RE = re.compile(r"<[^>]+>|(?:javascript|data):", re.I)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class ModerationResult:
    status: str
    category: str | None = None
    reason: str | None = None
    rule_version: str = RULE_VERSION


def normalize_content(content: str) -> str:
    """Normalize Unicode/spacing without changing the stored display text."""

    normalized = unicodedata.normalize("NFKC", content).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", normalized)
    return normalized


def validate_comment_text(content: str) -> str:
    """Validate the transport-safe plain-text comment boundary."""

    if not isinstance(content, str):
        raise BadRequestException(message="评论内容格式不正确")
    normalized = normalize_content(content)
    if not normalized:
        raise BadRequestException(message="评论内容不能为空")
    if len(normalized) > 500:
        raise BadRequestException(message="评论内容不能超过 500 字")
    if _CONTROL_RE.search(normalized):
        raise BadRequestException(message="评论内容包含不支持的控制字符")
    if _URL_RE.search(normalized) or _HTML_RE.search(normalized):
        raise BadRequestException(message="评论不支持链接或富文本")
    return normalized


def moderate_content(content: str) -> ModerationResult:
    """Return a safe local moderation decision without exposing matched text."""

    normalized = normalize_content(content).lower()
    for category, terms in _RULES.items():
        if any(term.lower() in normalized for term in terms):
            return ModerationResult(
                status="flagged",
                category=category,
                reason="内容需要人工审核",
            )
    return ModerationResult(status="passed")
