"""Consult follows the latest symptom, and LLM failure is explicitly marked.

No network. The model is a fake. Run:
  GUARDRAILS_LLM=0 python tests/test_consult_dynamic.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(prefix="consult-dyn-"), "t.db")
os.environ["GUARDRAILS_LLM"] = "0"
os.environ.pop("LLM_API_KEY", None)

from app import ai_service, llm  # noqa: E402
from app.llm import sanitize_error  # noqa: E402

HEADACHE = "我头痛两天了"
STOMACH = "现在改成肚子痛，还拉肚子"
CHEST = "胸口压榨样疼痛，喘不上气"


def _session() -> dict:
    return {"id": "s-test", "messages": [], "facts": {}, "status": "active", "turns": 0}


def _remember(session: dict, role: str, content: str) -> None:
    session.setdefault("messages", []).append({"role": role, "content": content})


class _LlmPatch:
    def __init__(self, configured: bool, chat):
        self.configured = configured
        self.chat = chat
        self.calls: list[dict] = []
        self._old_configured = llm.is_configured
        self._old_chat = llm.chat_json_messages

    def __enter__(self):
        calls = self.calls

        def _chat(system, messages, temperature=0.2):
            calls.append({"system": system, "messages": [dict(m) for m in messages]})
            return self.chat(system, messages)

        llm.is_configured = lambda: self.configured
        llm.chat_json_messages = _chat
        return self

    def __exit__(self, *exc):
        llm.is_configured = self._old_configured
        llm.chat_json_messages = self._old_chat


def _dynamic_model(system, messages):
    last = messages[-1]["content"]
    if "喘不上气" in last or "胸口" in last:
        return {
            "reply": "您现在说的是胸口压榨样疼痛并喘不上气，和先前的头痛不是同一件事。请马上停止活动。",
            "done": False,
            "triage": {
                "chiefComplaint": "头痛",
                "accompanying": ["呼吸困难"],
                "departments": [
                    {"id": "dept-er", "name": "急诊科", "reason": "胸痛伴气促", "rank": 1}
                ],
                "urgency": "routine",
                "suggestOnline": True,
                "nextSteps": ["尽快评估"],
                "summary": "当前主诉已变为胸痛伴呼吸困难",
            },
        }
    if "拉肚子" in last or "肚子痛" in last:
        return {
            "reply": "先前的头痛先记下。您刚改口说肚子痛还拉肚子，今天拉了几次？",
            "done": False,
            "triage": None,
        }
    return {
        "reply": "您提到的是头痛。是整个头还是一侧？",
        "done": False,
        "triage": None,
    }


class ConsultDynamicTests(unittest.TestCase):
    def test_each_turn_sends_full_history_and_reply_tracks_new_symptom(self):
        session = _session()
        with _LlmPatch(True, _dynamic_model) as patch:
            with self.assertLogs("app.ai_service", level="INFO") as logs:
                _remember(session, "user", HEADACHE)
                first = ai_service.consult_turn(session, HEADACHE)
                _remember(session, "assistant", first["reply"])
                _remember(session, "user", STOMACH)
                second = ai_service.consult_turn(session, STOMACH)

        self.assertIn("头痛", first["reply"])
        self.assertNotIn("拉肚子", first["reply"])
        self.assertIn("拉肚子", second["reply"])
        self.assertNotEqual(first["reply"], second["reply"])
        self.assertEqual(second["status"], "active")
        self.assertFalse(second["fallback"])
        self.assertTrue(second["llmCalled"])
        self.assertEqual(second["llmStatus"], "ok")
        self.assertEqual(second["source"], "llm")

        self.assertEqual(len(patch.calls), 2)
        first_msgs = patch.calls[0]["messages"]
        second_msgs = patch.calls[1]["messages"]
        self.assertEqual([m["role"] for m in first_msgs], ["user"])
        self.assertEqual(first_msgs[-1]["content"], HEADACHE)
        self.assertEqual(
            [m["role"] for m in second_msgs],
            ["user", "assistant", "user"],
        )
        self.assertEqual(second_msgs[0]["content"], HEADACHE)
        self.assertEqual(second_msgs[-1]["content"], STOMACH)
        self.assertNotIn("勿再问", patch.calls[1]["system"])
        joined = "\n".join(line for line in logs.output)
        self.assertIn("llm_called=true", joined)
        self.assertIn("llm_status=ok", joined)
        self.assertIn("fallback=false", joined)
        self.assertNotIn(HEADACHE, joined)
        self.assertNotIn(STOMACH, joined)

    def test_emergency_notice_survives_model_omission_and_updates_chief(self):
        session = _session()
        _remember(session, "user", HEADACHE)
        with _LlmPatch(True, _dynamic_model):
            ai_service.consult_turn(session, HEADACHE)
            _remember(session, "assistant", "先问头痛")
            _remember(session, "user", CHEST)
            result = ai_service.consult_turn(session, CHEST)

        self.assertTrue(result["llmCalled"])
        self.assertFalse(result["fallback"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["triage"]["urgency"], "emergency")
        self.assertFalse(result["triage"]["suggestOnline"])
        self.assertTrue("急诊" in result["reply"] or "120" in result["reply"])
        self.assertIn("胸口", result["reply"])
        self.assertIn("胸口", result["triage"]["chiefComplaint"])

    def test_llm_failure_is_marked_and_logs_are_redacted(self):
        secret = "sk-testsecretvalue"
        bearer = "super-token-value"

        def boom(system, messages, temperature=0.2):
            raise RuntimeError(f"upstream failed {secret} Bearer {bearer}")

        session = _session()
        with _LlmPatch(True, boom):
            with self.assertLogs("app.ai_service", level="INFO") as logs:
                _remember(session, "user", HEADACHE)
                first = ai_service.consult_turn(session, HEADACHE)
                _remember(session, "assistant", first["reply"])
                _remember(session, "user", STOMACH)
                second = ai_service.consult_turn(session, STOMACH)

        for result in (first, second):
            self.assertTrue(result["fallback"])
            self.assertTrue(result["llmCalled"])
            self.assertEqual(result["llmStatus"], "error")
            self.assertEqual(result["source"], "mock")
            self.assertEqual(result["error"], "llm_fallback")
            self.assertNotIn(secret, result["message"] or "")
            self.assertNotIn(bearer, result["message"] or "")
            self.assertNotIn(secret, result["reply"])
            self.assertNotIn(bearer, result["reply"])
        self.assertIn("头痛", first["reply"])
        self.assertTrue("肚子痛" in second["reply"] or "拉肚子" in second["reply"])
        self.assertNotEqual(first["reply"], second["reply"])
        blob = "\n".join(logs.output)
        self.assertIn("llm_called=true", blob)
        self.assertIn("llm_status=error", blob)
        self.assertIn("fallback=true", blob)
        self.assertIn("error_code=llm_fallback", blob)
        self.assertNotIn(secret, blob)
        self.assertNotIn(bearer, blob)
        self.assertNotIn(HEADACHE, blob)

    def test_missing_key_skips_model_and_marks_fallback(self):
        def forbidden(system, messages):
            raise AssertionError("model must not be called")

        session = _session()
        with _LlmPatch(False, forbidden):
            with self.assertLogs("app.ai_service", level="INFO") as logs:
                result = ai_service.consult_turn(session, "咳嗽三天")
        self.assertFalse(result["llmCalled"])
        self.assertEqual(result["llmStatus"], "skipped")
        self.assertTrue(result["fallback"])
        self.assertEqual(result["error"], "llm_not_configured")
        self.assertIn("咳嗽", result["reply"])
        self.assertIn("llm_called=false", "\n".join(logs.output))
        self.assertIn("fallback=true", "\n".join(logs.output))

    def test_stream_uses_same_dynamic_reply(self):
        session = _session()
        _remember(session, "user", STOMACH)
        with _LlmPatch(True, _dynamic_model):
            events = list(ai_service.consult_turn_stream(session, STOMACH))
        finals = [e for e in events if e.get("type") == "final"]
        self.assertEqual(len(finals), 1)
        self.assertIn("拉肚子", finals[0]["reply"])
        self.assertFalse(finals[0]["fallback"])
        text = "".join(e.get("text", "") for e in events if e.get("type") == "token")
        self.assertEqual(text, finals[0]["reply"])

    def test_sanitize_error_strips_key_and_bearer(self):
        os.environ["LLM_API_KEY"] = "sk-envkeyvalue123"
        try:
            msg = sanitize_error(
                RuntimeError("bad sk-envkeyvalue123 and sk-othersecret Bearer abc.def")
            )
        finally:
            os.environ.pop("LLM_API_KEY", None)
        self.assertNotIn("sk-envkeyvalue123", msg)
        self.assertNotIn("sk-othersecret", msg)
        self.assertNotIn("abc.def", msg)


class ConsultRouteTests(unittest.TestCase):
    """Call the route function directly so the suite does not need httpx."""

    @classmethod
    def setUpClass(cls):
        import asyncio

        from starlette.requests import Request

        from app import store
        from app.models import PostMessageRequest
        from app.routes import consult as consult_routes

        cls.asyncio = asyncio
        cls.store = store
        cls.PostMessageRequest = PostMessageRequest
        cls.consult_routes = consult_routes

    def _request(self):
        from starlette.requests import Request

        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 123),
                "server": ("test", 80),
            }
        )

    def _send(self, session_id: str, content: str) -> dict:
        return self.asyncio.run(
            self.consult_routes.post_message(
                session_id,
                self.PostMessageRequest(content=content),
                self._request(),
                None,
            )
        )

    def test_route_marks_fallback_and_changes_with_symptom(self):
        secret = "sk-routesecretvalue"

        def boom(system, messages):
            raise RuntimeError(f"nope {secret} Bearer route-token")

        with _LlmPatch(True, boom):
            with self.assertLogs("app.ai_service", level="INFO") as logs:
                sid = self.store.create_session()["id"]
                body1 = self._send(sid, HEADACHE)
                body2 = self._send(sid, STOMACH)
        for body in (body1, body2):
            self.assertTrue(body["fallback"])
            self.assertTrue(body["llmCalled"])
            self.assertEqual(body["llmStatus"], "error")
            self.assertEqual(body["source"], "mock")
            self.assertNotIn(secret, str(body))
            self.assertNotIn("route-token", str(body))
        self.assertNotEqual(body1["reply"]["content"], body2["reply"]["content"])
        self.assertIn("头痛", body1["reply"]["content"])
        self.assertTrue(
            "肚子痛" in body2["reply"]["content"] or "拉肚子" in body2["reply"]["content"]
        )
        blob = "\n".join(logs.output)
        self.assertIn("fallback=true", blob)
        self.assertNotIn(secret, blob)

    def test_route_passes_history_into_mocked_model(self):
        with _LlmPatch(True, _dynamic_model) as patch:
            sid = self.store.create_session()["id"]
            body1 = self._send(sid, HEADACHE)
            body2 = self._send(sid, STOMACH)
        self.assertIn("头痛", body1["reply"]["content"])
        self.assertIn("拉肚子", body2["reply"]["content"])
        self.assertFalse(body2["fallback"])
        self.assertTrue(body2["llmCalled"])
        self.assertEqual(body2["llmStatus"], "ok")
        self.assertEqual(body2["status"], "active")
        self.assertGreaterEqual(len(patch.calls), 2)
        roles = [m["role"] for m in patch.calls[1]["messages"]]
        self.assertEqual(roles[0], "user")
        self.assertEqual(roles[-1], "user")
        self.assertIn("assistant", roles)
        self.assertEqual(patch.calls[1]["messages"][-1]["content"], STOMACH)
        self.assertIn(HEADACHE, [m["content"] for m in patch.calls[1]["messages"]])

    def test_redflag_skips_model_and_keeps_emergency_copy(self):
        def forbidden(system, messages):
            raise AssertionError("redflag must not call the model")

        with _LlmPatch(True, forbidden):
            with self.assertLogs("app.ai_service", level="INFO") as logs:
                sid = self.store.create_session()["id"]
                body = self._send(sid, "突发胸痛伴大汗，喘不上气")
        self.assertEqual(body["source"], "guardrail")
        self.assertFalse(body["llmCalled"])
        self.assertEqual(body["llmStatus"], "skipped")
        self.assertFalse(body["fallback"])
        self.assertTrue("120" in body["reply"]["content"] or "急诊" in body["reply"]["content"])
        blob = "\n".join(logs.output)
        self.assertIn("llm_called=false", blob)
        self.assertIn("error_code=guardrail", blob)
        self.assertNotIn("突发胸痛", blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
