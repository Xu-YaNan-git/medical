import pytest

from guardrails import mask_pii


def test_masks_phone_and_id(monkeypatch):
    monkeypatch.delenv("MASK_SENSITIVE", raising=False)
    s = mask_pii("电话13812345678 身份证11010119900307123X 旧证110101900307123")
    assert "138****5678" in s
    assert "**************123X" in s
    assert "***********123" in s
    assert "13812345678" not in s


def test_phone_with_prefix_and_dashes(monkeypatch):
    monkeypatch.delenv("MASK_SENSITIVE", raising=False)
    assert mask_pii("+86 138-1234-5678") == "+86 138****5678"


def test_non_pii_numbers_untouched(monkeypatch):
    monkeypatch.delenv("MASK_SENSITIVE", raising=False)
    assert mask_pii("体温38.5度，血压140/90，订单123456") == "体温38.5度，血压140/90，订单123456"


@pytest.mark.parametrize("val", ["0", "false", "FALSE", "no", "off"])
def test_mask_sensitive_off(monkeypatch, val):
    monkeypatch.setenv("MASK_SENSITIVE", val)
    assert mask_pii("13812345678") == "13812345678"


@pytest.mark.parametrize("val", ["1", "true", ""])
def test_mask_sensitive_on(monkeypatch, val):
    monkeypatch.setenv("MASK_SENSITIVE", val)
    assert mask_pii("13812345678") == "138****5678"


def test_none():
    assert mask_pii(None) == ""
