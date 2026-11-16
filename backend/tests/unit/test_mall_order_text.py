import pytest


@pytest.mark.parametrize(
    "text,secret",
    [
        ("联系13800001234", "13800001234"),
        ("联系138-0000-1234", "138-0000-1234"),
        ("证件110101199001011234", "110101199001011234"),
        ("医保账户：YB12AB3456", "YB12AB3456"),
        ("医疗账号 AB12CD34", "AB12CD34"),
    ],
)
def test_order_text_masks_structured_identifiers_embedded_in_notes(text, secret):
    from src.services.mall_order_text import safe_order_text

    assert secret not in safe_order_text(text)


def test_regular_order_notes_and_empty_notes_are_preserved():
    from src.services.mall_order_text import safe_order_text

    assert safe_order_text("核实包装后处理") == "核实包装后处理"
    assert safe_order_text("") is None
