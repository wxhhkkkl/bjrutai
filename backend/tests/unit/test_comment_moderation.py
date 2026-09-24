"""US4 tests for dependency-free local comment moderation."""

import pytest


def test_normalizes_nfkc_spacing_and_keeps_display_text_separate():
    from src.services.comment_moderation import normalize_content, validate_comment_text

    assert normalize_content("  Ｈｅｌｌｏ\u200b   世界  ") == "Hello 世界"
    assert validate_comment_text("  文章很实用。😊  ") == "文章很实用。😊"


@pytest.mark.parametrize(
    "content",
    [
        "<b>富文本</b>",
        "https://example.com/article",
        "请看 www.example.com",
        "javascript:alert(1)",
        "包含\x00控制字符",
        " " * 3,
        "a" * 501,
    ],
)
def test_rejects_non_plain_or_unsafe_content(content):
    from src.core.exceptions import BadRequestException
    from src.services.comment_moderation import validate_comment_text

    with pytest.raises(BadRequestException):
        validate_comment_text(content)


@pytest.mark.parametrize(
    ("category", "content"),
    [
        ("sexual", "这段色情内容需要拦截"),
        ("violence", "暴力威胁内容需要审核"),
        ("political", "恐怖主义内容需要审核"),
    ],
)
def test_flags_required_local_moderation_categories(category, content):
    from src.services.comment_moderation import RULE_VERSION, moderate_content

    result = moderate_content(content)
    assert result.status == "flagged"
    assert result.category == category
    assert result.rule_version == RULE_VERSION
    assert "色情" not in (result.reason or "")


def test_safe_content_passes_local_moderation():
    from src.services.comment_moderation import moderate_content

    result = moderate_content("今天的健康建议很有帮助。😊")
    assert result.status == "passed"
    assert result.category is None
