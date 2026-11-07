import pytest

from guardrails import llm_judge


@pytest.fixture(autouse=True)
def _no_llm_by_default(monkeypatch):
    """Unit tests never touch the network: LLM judge off unless a test turns it on."""
    monkeypatch.setenv("GUARDRAILS_LLM", "0")
    monkeypatch.setattr(llm_judge, "_post", _forbidden)
    llm_judge.reset()
    yield
    llm_judge.reset()


def _forbidden(*a, **k):
    raise AssertionError("network call in unit test")
