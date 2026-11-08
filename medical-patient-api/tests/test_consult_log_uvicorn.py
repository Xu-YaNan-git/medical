"""consult_llm must show up on stdout under the real Uvicorn startup.

Docker runs ``uvicorn app.main:app`` with Uvicorn's default log config, which
drops application INFO logs. This test starts that command and reads the
process stdout. It does not call a live model.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYMPTOM = "头痛两天电话13812345678"
SECRET = "sk-shouldnotappear"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


class UvicornConsultLogTests(unittest.TestCase):
    def test_consult_llm_line_on_stdout(self):
        port = _free_port()
        db_dir = tempfile.mkdtemp(prefix="consult-log-")
        env = os.environ.copy()
        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "PYTHONPATH": ROOT,
                "SQLITE_PATH": os.path.join(db_dir, "app.db"),
                "GUARDRAILS_LLM": "0",
                "APP_ENV": "dev",
            }
        )
        env.pop("LLM_API_KEY", None)
        env.pop("LLM_BASE_URL", None)

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        def _drain(pipe, bucket: list[str]) -> None:
            if pipe is None:
                return
            for line in pipe:
                bucket.append(line)

        threads = [
            threading.Thread(target=_drain, args=(proc.stdout, stdout_parts), daemon=True),
            threading.Thread(target=_drain, args=(proc.stderr, stderr_parts), daemon=True),
        ]
        for thread in threads:
            thread.start()
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 30
            up = False
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(base + "/health", timeout=1) as resp:
                        if resp.status == 200:
                            up = True
                            break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(0.2)
            stderr_now = "".join(stderr_parts)
            self.assertTrue(up, "uvicorn did not become healthy\n" + textwrap.shorten(stderr_now, 800))

            created = _post(base + "/api/consult/sessions", {})
            _post(
                base + f"/api/consult/sessions/{created['id']}/messages",
                {"content": f"{SYMPTOM} {SECRET}"},
            )
            seen = time.time() + 5
            while time.time() < seen and not any("consult_llm" in row for row in stdout_parts):
                time.sleep(0.1)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=5)
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()

        combined = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
        self.assertIn("consult_llm", combined, textwrap.shorten(stderr, 500))
        line = next(row for row in combined.splitlines() if "consult_llm" in row)
        self.assertIn("llm_called=false", line)
        self.assertIn("llm_status=skipped", line)
        self.assertIn("fallback=true", line)
        self.assertIn("error_code=llm_not_configured", line)
        self.assertNotIn(SYMPTOM, combined)
        self.assertNotIn(SECRET, combined)
        self.assertNotIn(SECRET, stderr or "")
        self.assertNotIn("13812345678", combined)
        self.assertNotIn("13812345678", stderr or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
