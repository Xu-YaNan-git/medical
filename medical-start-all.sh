#!/usr/bin/env bash
set -euo pipefail
# Pull up patient API, doctor API, and static UIs for demo.
ROOT=/workspace
mkdir -p /tmp/medical-logs
export LLM_MODEL="${LLM_MODEL:-gpt-5.6-sol}"

# Ensure a project venv exists and has its requirements installed.
# Re-installs when requirements.txt is newer than the install stamp.
ensure_venv() {
  local dir="$1"
  local stamp="$dir/.venv/.requirements.installed"
  if [ ! -x "$dir/.venv/bin/python" ]; then
    echo "creating venv in $dir/.venv"
    python3 -m venv "$dir/.venv"
    rm -f "$stamp"
  fi
  if [ -f "$dir/requirements.txt" ] && { [ ! -f "$stamp" ] || [ "$dir/requirements.txt" -nt "$stamp" ]; }; then
    echo "installing requirements for $dir"
    "$dir/.venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
    "$dir/.venv/bin/pip" install -q -r "$dir/requirements.txt"
    touch "$stamp"
  fi
}

if ! curl -sf http://127.0.0.1:8001/health >/dev/null; then
  cd "$ROOT/medical-patient-api"
  ensure_venv "$ROOT/medical-patient-api"
  source .venv/bin/activate
  STORE_BACKEND=sqlite nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/medical-logs/patient-8001.log 2>&1 &
  echo "started patient api :8001"
fi

if ! curl -sf http://127.0.0.1:8000/health >/dev/null && ! curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
  cd "$ROOT/medical-assistant-api"
  ensure_venv "$ROOT/medical-assistant-api"
  source .venv/bin/activate
  export PATIENT_API_BASE=http://127.0.0.1:8001
  export STORE_BACKEND=sqlite
  nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/medical-logs/doctor-8000.log 2>&1 &
  echo "started doctor api :8000"
fi

if ! curl -sf -o /dev/null http://127.0.0.1:8765/; then
  cd "$ROOT/medical-patient-triage"
  nohup python3 -m http.server 8765 > /tmp/medical-logs/patient-ui-8765.log 2>&1 &
  echo "started patient ui :8765"
fi

if ! curl -sf -o /dev/null http://127.0.0.1:36967/; then
  cd "$ROOT/medical-assistant-prototype"
  nohup python3 -m http.server 36967 > /tmp/medical-logs/doctor-ui-36967.log 2>&1 &
  echo "started doctor ui :36967"
fi

echo "patient ui http://127.0.0.1:8765/"
echo "doctor ui  http://127.0.0.1:36967/  (doctor/demo123)"
echo "patient api http://127.0.0.1:8001/docs"
echo "doctor api  http://127.0.0.1:8000/docs"
