"""Smoke tests against local medical-assistant-api (http://127.0.0.1:8000)."""

from __future__ import annotations

import os
import re

import httpx
import pytest

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("API_USER", "doctor")
PASSWORD = os.environ.get("API_PASS", "demo123")

DISCLAIMER_HINTS = ("辅助决策", "不替代", "仅供参考", "医生确认")
# AI calls may hit real LLM; allow generous timeout.
AI_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def _assert_disclaimer(text: str) -> None:
    assert text, "disclaimer 为空"
    for hint in DISCLAIMER_HINTS:
        assert hint in text, f"disclaimer 缺少「{hint}」: {text!r}"


def _assert_source(src: str | None) -> None:
    assert src in ("llm", "mock"), f"unexpected source: {src!r}"


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE, timeout=DEFAULT_TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
def token(client: httpx.Client) -> str:
    r = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("token"), data
    assert "displayName" in data
    return data["token"]


@pytest.fixture(scope="session")
def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- health / auth anomalies ----------


def test_health(client: httpx.Client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert isinstance(body.get("llmConfigured"), bool)
    # Never leak secrets
    dumped = r.text.lower()
    assert "api_key" not in dumped
    assert "sk-" not in dumped
    assert "llm_api_key" not in dumped


def test_login_ok(client: httpx.Client) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["token"]
    assert data.get("displayName") == "张医生"


def test_login_wrong_password(client: httpx.Client) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": "wrong-password"},
    )
    assert r.status_code == 401
    body = r.json()
    assert body.get("error") == "invalid_credentials"


def test_login_missing_field(client: httpx.Client) -> None:
    r = client.post("/api/auth/login", json={"username": USERNAME})
    assert r.status_code == 422
    body = r.json()
    assert body.get("error") == "validation_error"


def test_visits_no_token(client: httpx.Client) -> None:
    r = client.get("/api/visits")
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


def test_visits_invalid_token(client: httpx.Client) -> None:
    r = client.get(
        "/api/visits",
        headers={"Authorization": "Bearer invalid-token-xyz"},
    )
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


# ---------- happy path ----------


def test_happy_path_smoke(client: httpx.Client, auth_headers: dict[str, str]) -> None:
    sources: dict[str, str | None] = {}

    # List
    r = client.get("/api/visits", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # Create
    r = client.post(
        "/api/visits",
        headers=auth_headers,
        json={
            "name": "冒烟测试患者",
            "gender": "男",
            "age": 45,
            "chief": "反复咳嗽伴低热 3 天",
            "status": "waiting",
        },
    )
    assert r.status_code == 201, r.text
    visit = r.json()
    visit_id = visit["id"]
    assert visit_id
    assert visit["name"] == "冒烟测试患者"

    # Update chart fields
    r = client.put(
        f"/api/visits/{visit_id}",
        headers=auth_headers,
        json={
            "hpi": "3 天前受凉后出现咳嗽，痰少，伴低热，无胸痛。",
            "pmh": "否认慢病史",
            "allergy": "青霉素过敏",
            "pe": "咽充血，双肺呼吸音粗",
            "labs": "",
            "status": "in_progress",
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["allergy"] == "青霉素过敏"
    assert updated["status"] == "in_progress"

    raw_text = (
        "患者男，45岁。主诉：反复咳嗽伴低热3天。"
        "现病史：受凉后起病，干咳为主，体温最高37.8℃。"
        "既往史：体健。过敏史：青霉素过敏。"
        "查体：咽充血，双肺呼吸音粗，未闻及干湿啰音。"
    )

    # parse-text
    r = client.post(
        f"/api/visits/{visit_id}/parse-text",
        headers=auth_headers,
        json={"rawText": raw_text},
        timeout=AI_TIMEOUT,
    )
    assert r.status_code == 200, r.text
    parsed = r.json()
    _assert_disclaimer(parsed.get("disclaimer", ""))
    _assert_source(parsed.get("source"))
    sources["parse-text"] = parsed.get("source")
    assert "chief" in parsed

    # differential
    r = client.post(
        f"/api/visits/{visit_id}/differential",
        headers=auth_headers,
        timeout=AI_TIMEOUT,
    )
    assert r.status_code == 200, r.text
    diff = r.json()
    _assert_disclaimer(diff.get("disclaimer", ""))
    _assert_source(diff.get("source"))
    sources["differential"] = diff.get("source")
    items = diff.get("items") or []
    assert len(items) >= 1, diff
    item_id = items[0]["id"]

    # accept first, reject second if present
    r = client.post(
        f"/api/visits/{visit_id}/differential/decision",
        headers=auth_headers,
        json={"itemId": item_id, "decision": "accept"},
    )
    assert r.status_code == 200, r.text
    decided = r.json()
    _assert_disclaimer(decided.get("disclaimer", ""))
    matched = [i for i in decided["items"] if i["id"] == item_id]
    assert matched and matched[0]["decision"] == "accept"

    if len(items) >= 2:
        r = client.post(
            f"/api/visits/{visit_id}/differential/decision",
            headers=auth_headers,
            json={"itemId": items[1]["id"], "decision": "reject"},
        )
        assert r.status_code == 200, r.text

    # orders suggest
    r = client.post(
        f"/api/visits/{visit_id}/orders/suggest",
        headers=auth_headers,
        timeout=AI_TIMEOUT,
    )
    assert r.status_code == 200, r.text
    sug = r.json()
    _assert_disclaimer(sug.get("disclaimer", ""))
    _assert_source(sug.get("source"))
    sources["orders/suggest"] = sug.get("source")
    assert isinstance(sug.get("exams"), list)
    assert isinstance(sug.get("drugs"), list)

    # write orders from suggest (or fallback single item)
    write_items = []
    for e in (sug.get("exams") or [])[:2]:
        write_items.append(
            {
                "type": e.get("type") or "检查",
                "text": e["text"],
                "conflict": e.get("conflict"),
                "warn": e.get("warn"),
            }
        )
    for d in (sug.get("drugs") or [])[:2]:
        write_items.append(
            {
                "type": d.get("type") or "药品",
                "text": d["text"],
                "conflict": d.get("conflict"),
                "warn": d.get("warn"),
            }
        )
    if not write_items:
        write_items = [{"type": "检查", "text": "血常规"}]

    r = client.post(
        f"/api/visits/{visit_id}/orders",
        headers=auth_headers,
        json={"items": write_items},
    )
    assert r.status_code == 200, r.text
    with_orders = r.json()
    assert len(with_orders.get("orders") or []) >= 1

    # note generate
    r = client.post(
        f"/api/visits/{visit_id}/note/generate",
        headers=auth_headers,
        timeout=AI_TIMEOUT,
    )
    assert r.status_code == 200, r.text
    note = r.json()
    _assert_disclaimer(note.get("disclaimer", ""))
    _assert_source(note.get("source"))
    sources["note/generate"] = note.get("source")
    assert note.get("fullText")
    assert isinstance(note.get("sections"), dict)

    # note polish
    r = client.post(
        f"/api/visits/{visit_id}/note/polish",
        headers=auth_headers,
        json={"style": "concise", "content": note["fullText"]},
        timeout=AI_TIMEOUT,
    )
    assert r.status_code == 200, r.text
    polished = r.json()
    _assert_disclaimer(polished.get("disclaimer", ""))
    _assert_source(polished.get("source"))
    sources["note/polish"] = polished.get("source")
    assert polished.get("text")

    # export.md
    r = client.get(f"/api/visits/{visit_id}/export.md", headers=auth_headers)
    assert r.status_code == 200, r.text
    ctype = r.headers.get("content-type", "")
    assert "markdown" in ctype or "text/" in ctype
    assert len(r.text) > 20

    # Attach observed sources for report consumers (pytest capsys / print)
    print(f"\n[AI_SOURCE_OBS] {sources}")


# ---------- more anomalies ----------


def test_parse_empty_raw_text(
    client: httpx.Client, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/visits",
        headers=auth_headers,
        json={"name": "空文案患者", "chief": "咳嗽"},
    )
    assert r.status_code == 201
    vid = r.json()["id"]
    r = client.post(
        f"/api/visits/{vid}/parse-text",
        headers=auth_headers,
        json={"rawText": "   "},
    )
    assert r.status_code == 400
    assert r.json().get("error") == "bad_request"


def test_visit_not_found(client: httpx.Client, auth_headers: dict[str, str]) -> None:
    r = client.get("/api/visits/does-not-exist-999", headers=auth_headers)
    assert r.status_code == 404
    assert r.json().get("error") == "not_found"


def test_differential_without_chief(
    client: httpx.Client, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/visits",
        headers=auth_headers,
        json={"name": "无主诉", "chief": "（待填写）"},
    )
    assert r.status_code == 201
    vid = r.json()["id"]
    # Clear chief to empty to trigger guard
    r = client.put(
        f"/api/visits/{vid}",
        headers=auth_headers,
        json={"chief": ""},
    )
    assert r.status_code == 200
    r = client.post(f"/api/visits/{vid}/differential", headers=auth_headers)
    assert r.status_code == 400
    assert r.json().get("error") == "bad_request"


def test_orders_missing_body(
    client: httpx.Client, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/visits",
        headers=auth_headers,
        json={"name": "医嘱缺参", "chief": "发热"},
    )
    assert r.status_code == 201
    vid = r.json()["id"]
    r = client.post(f"/api/visits/{vid}/orders", headers=auth_headers, json={})
    assert r.status_code == 400
    assert r.json().get("error") == "bad_request"


def test_decision_before_differential(
    client: httpx.Client, auth_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/visits",
        headers=auth_headers,
        json={"name": "未鉴别", "chief": "头痛"},
    )
    assert r.status_code == 201
    vid = r.json()["id"]
    r = client.post(
        f"/api/visits/{vid}/differential/decision",
        headers=auth_headers,
        json={"itemId": "x", "decision": "accept"},
    )
    assert r.status_code == 400
    assert r.json().get("error") == "bad_request"
