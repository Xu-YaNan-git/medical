#!/usr/bin/env bash
# M9 黄金路径一键演示冒烟（患者→预约→预问诊→图文接诊→医生代理→随访/消息）
# 用法: bash /workspace/medical-e2e-smoke/golden-path.sh
# 说明: demo/reset 若 404 → SKIP（后端未就绪），不当 FAIL；仅 FAIL>0 时 exit 1
set -u
P_API="${P_API:-http://127.0.0.1:8001}"
D_API="${D_API:-http://127.0.0.1:8000}"
P_UI="${P_UI:-http://127.0.0.1:8765}"
D_UI="${D_UI:-http://127.0.0.1:36967}"
START_ALL="${START_ALL:-/workspace/medical-start-all.sh}"
REPORT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
SKIP=0
RESULTS=()
TODAY=$(date +%Y-%m-%d)
DOCTOR_USER="${DOCTOR_USER:-doctor}"
DOCTOR_PASS="${DOCTOR_PASS:-demo123}"

json_get() {
  local raw="$1"
  local expr="$2"
  python3 -c "
import json,sys
raw=sys.argv[1]
expr=sys.argv[2]
d=json.loads(raw)
v=eval(expr, {'d': d, 'json': json})
if v is None:
  print('')
elif isinstance(v,(dict,list)):
  print(json.dumps(v, ensure_ascii=False))
else:
  print(v)
" "$raw" "$expr" 2>/dev/null
}

has_disclaimer_ok() {
  local s="$1"
  echo "$s" | python3 -c "
import sys,json
t=sys.stdin.read()
try:
  d=json.loads(t)
  if isinstance(d,dict) and d.get('disclaimer'):
    t=str(d.get('disclaimer'))+' '+t
except Exception:
  pass
keys=['仅供参考','仅供','不能替代','不替代','不构成诊断','须医生确认','辅助','演示','以医院实际','非真实','不发生真实','参考，','就医参考']
ok = any(k in t for k in keys)
sys.exit(0 if ok else 1)
" 2>/dev/null
}

record() {
  local id="$1" status="$2" detail="$3"
  RESULTS+=("$status|$id|$detail")
  if [[ "$status" == "PASS" ]]; then
    PASS=$((PASS+1))
    echo "PASS  $id  $detail"
  elif [[ "$status" == "SKIP" ]]; then
    SKIP=$((SKIP+1))
    echo "SKIP  $id  $detail"
  else
    FAIL=$((FAIL+1))
    echo "FAIL  $id  $detail"
  fi
}

http_code() {
  local method="$1" url="$2"; shift 2
  local tmp
  tmp=$(mktemp)
  LAST_CODE=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" "$url" "$@" || echo "000")
  LAST_BODY=$(cat "$tmp")
  rm -f "$tmp"
}

wait_health() {
  local i
  for i in $(seq 1 30); do
    if curl -sf "$P_API/health" >/dev/null 2>&1 && curl -sf "$D_API/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "=== medical M9 golden-path $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo "P_API=$P_API  D_API=$D_API  P_UI=$P_UI  D_UI=$D_UI"
echo

# ---- 0 readiness ----
http_code GET "$P_API/health"
PH_CODE="$LAST_CODE"
http_code GET "$D_API/health"
DH_CODE="$LAST_CODE"

if [[ "$PH_CODE" != "200" || "$DH_CODE" != "200" ]]; then
  echo "health fail (patient=$PH_CODE doctor=$DH_CODE); trying $START_ALL"
  if [[ -x "$START_ALL" || -f "$START_ALL" ]]; then
    if [[ -x "$START_ALL" ]]; then "$START_ALL" || true; else bash "$START_ALL" || true; fi  # S2: 可执行文件直接跑（支持 START_ALL=/bin/true）
    wait_health || true
    http_code GET "$P_API/health"; PH_CODE="$LAST_CODE"
    http_code GET "$D_API/health"; DH_CODE="$LAST_CODE"
  fi
fi

if [[ "$PH_CODE" == "200" && "$DH_CODE" == "200" ]]; then
  record "GP-00" "PASS" "health patient=$PH_CODE doctor=$DH_CODE"
else
  record "GP-00" "FAIL" "health patient=$PH_CODE doctor=$DH_CODE; abort"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  {
    echo "PASS=$PASS"
    echo "FAIL=$FAIL"
    echo "SKIP=$SKIP"
    echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
    for r in "${RESULTS[@]}"; do echo "$r"; done
  } > "$REPORT_DIR/golden-path.last.env"
  exit 1
fi

# ---- 1 demo reset (404 → SKIP 后端未就绪) ----
http_code POST "$P_API/api/demo/reset" -H 'Content-Type: application/json' -d '{}'
PR_CODE="$LAST_CODE"; PR_BODY="$LAST_BODY"
if [[ "$PR_CODE" == "200" ]]; then
  record "GP-01a" "PASS" "patient demo/reset HTTP 200 seed=$(json_get "$PR_BODY" "d.get('seedVersion')")"
elif [[ "$PR_CODE" == "404" ]]; then
  record "GP-01a" "SKIP" "patient demo/reset 404 — 后端未就绪（演示重置 API 未部署）"
else
  record "GP-01a" "FAIL" "patient demo/reset unexpected HTTP $PR_CODE body=${PR_BODY:0:160}"
fi

# doctor login first (needed for Bearer reset + later proxy)
http_code POST "$D_API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$DOCTOR_USER\",\"password\":\"$DOCTOR_PASS\"}"
LG_CODE="$LAST_CODE"; LG_BODY="$LAST_BODY"
TOKEN=$(json_get "$LG_BODY" "d.get('token')")
if [[ "$LG_CODE" == "200" && -n "$TOKEN" ]]; then
  record "GP-01b" "PASS" "doctor login ok token_len=${#TOKEN}"
else
  record "GP-01b" "FAIL" "doctor login HTTP $LG_CODE body=${LG_BODY:0:160}"
  TOKEN=""
fi

if [[ -n "$TOKEN" ]]; then
  http_code POST "$D_API/api/demo/reset" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d '{}'
  DR_CODE="$LAST_CODE"; DR_BODY="$LAST_BODY"
  if [[ "$DR_CODE" == "200" ]]; then
    record "GP-01c" "PASS" "doctor demo/reset HTTP 200 seed=$(json_get "$DR_BODY" "d.get('seedVersion')")"
  elif [[ "$DR_CODE" == "404" ]]; then
    record "GP-01c" "SKIP" "doctor demo/reset 404 — 后端未就绪（演示重置 API 未部署）"
  else
    record "GP-01c" "FAIL" "doctor demo/reset unexpected HTTP $DR_CODE body=${DR_BODY:0:160}"
  fi
else
  record "GP-01c" "SKIP" "doctor demo/reset skipped — no token"
fi

# ---- 2 triage ----
http_code POST "$P_API/api/triage/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"chief":"咳嗽发热","duration":"2天","bodyPart":"咽喉","severity":"中等","age":32}'
T_CODE="$LAST_CODE"; T_BODY="$LAST_BODY"
DEPTS=$(json_get "$T_BODY" "d.get('departments')")
SRC=$(json_get "$T_BODY" "d.get('source')")
if [[ "$T_CODE" == "200" && -n "$DEPTS" && "$DEPTS" != "null" && "$DEPTS" != "[]" ]]; then
  if has_disclaimer_ok "$T_BODY"; then
    record "GP-02" "PASS" "导诊 HTTP $T_CODE source=$SRC departments_ok disclaimer_ok"
  else
    record "GP-02" "FAIL" "导诊 HTTP $T_CODE missing disclaimer"
  fi
else
  record "GP-02" "FAIL" "导诊 HTTP $T_CODE body=${T_BODY:0:200}"
fi

# ---- 3 appointment ----
http_code GET "$P_API/api/departments"
DEPT_BODY="$LAST_BODY"; DEPT_CODE="$LAST_CODE"
DEPT_ID=$(json_get "$DEPT_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
http_code GET "$P_API/api/departments/$DEPT_ID/doctors"
DOC_BODY="$LAST_BODY"
DOC_ID=$(json_get "$DOC_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
http_code GET "$P_API/api/doctors/$DOC_ID/slots?date=$TODAY"
SLOT_BODY="$LAST_BODY"
SLOT_ID=$(json_get "$SLOT_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
if [[ -z "$SLOT_ID" || "$SLOT_ID" == "None" ]]; then
  for i in 0 1 2 3 4; do
    DAY=$(date -d "+$i day" +%Y-%m-%d 2>/dev/null || echo "$TODAY")
    http_code GET "$P_API/api/doctors/$DOC_ID/slots?date=$DAY"
    SLOT_ID=$(json_get "$LAST_BODY" "next((x.get('id') for x in (d if isinstance(d,list) else d.get('items') or []) if x.get('available',True) and x.get('remaining',1)>0), '')")
    [[ -n "$SLOT_ID" ]] && break
  done
fi
http_code POST "$P_API/api/appointments" \
  -H 'Content-Type: application/json' \
  -d "{\"departmentId\":\"$DEPT_ID\",\"doctorId\":\"$DOC_ID\",\"slotId\":\"$SLOT_ID\",\"patientName\":\"黄金路径患者\",\"phone\":\"13800000088\",\"chief\":\"咳嗽发热\"}"
AP_CODE="$LAST_CODE"; AP_BODY="$LAST_BODY"
AP_ID=$(json_get "$AP_BODY" "d.get('id')")
http_code GET "$P_API/api/appointments/$AP_ID"
AD_CODE="$LAST_CODE"
if [[ "$DEPT_CODE" == "200" && -n "$DEPT_ID" && -n "$DOC_ID" && -n "$SLOT_ID" && "$AP_CODE" == "200" && -n "$AP_ID" && "$AD_CODE" == "200" ]]; then
  record "GP-03" "PASS" "预约 dept=$DEPT_ID doc=$DOC_ID slot=$SLOT_ID appt=$AP_ID"
else
  record "GP-03" "FAIL" "预约 dept=$DEPT_CODE/$DEPT_ID doc=$DOC_ID slot=$SLOT_ID create=$AP_CODE id=$AP_ID detail=$AD_CODE body=${AP_BODY:0:160}"
fi

# ---- 4 preconsult / previsit ----
PRE_OK=0
PRE_NOTE=""
# try session-based first
http_code POST "$P_API/api/consult/sessions" \
  -H 'Content-Type: application/json' \
  -d '{"chief":"反复上腹痛3天","patientId":"pat-1"}'
S_CODE="$LAST_CODE"; S_BODY="$LAST_BODY"
SID=$(json_get "$S_BODY" "d.get('id') or d.get('sessionId')")
if [[ -z "$SID" ]]; then
  http_code POST "$P_API/api/consult/sessions" -H 'Content-Type: application/json' -d '{}'
  S_CODE="$LAST_CODE"; S_BODY="$LAST_BODY"
  SID=$(json_get "$S_BODY" "d.get('id') or d.get('sessionId')")
fi
if [[ -n "$SID" ]]; then
  http_code POST "$P_API/api/consult/sessions/$SID/preconsult-report" \
    -H 'Content-Type: application/json' -d '{}'
  if [[ "$LAST_CODE" == "200" ]] && has_disclaimer_ok "$LAST_BODY"; then
    PRE_OK=1
    PRE_NOTE="session-preconsult sid=$SID source=$(json_get "$LAST_BODY" "d.get('source')")"
  fi
fi
if [[ "$PRE_OK" -eq 0 ]]; then
  http_code POST "$P_API/api/previsit/report" \
    -H 'Content-Type: application/json' \
    -d '{"chiefComplaint":"反复上腹痛3天","duration":"3天","bodyPart":"上腹","accompanying":["反酸"],"allergies":"青霉素"}'
  if [[ "$LAST_CODE" == "200" ]] && has_disclaimer_ok "$LAST_BODY"; then
    PRE_OK=1
    PRE_NOTE="previsit/report source=$(json_get "$LAST_BODY" "d.get('source')")"
  else
    PRE_NOTE="HTTP $LAST_CODE body=${LAST_BODY:0:160}"
  fi
fi
if [[ "$PRE_OK" -eq 1 ]]; then
  record "GP-04" "PASS" "预问诊 $PRE_NOTE"
else
  record "GP-04" "FAIL" "预问诊 $PRE_NOTE"
fi

# ---- 5 doctor-consult (图文接诊) ----
http_code POST "$P_API/api/doctor-consult/sessions" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"text","patientId":"pat-1","chiefComplaint":"黄金路径图文接诊","departmentName":"全科"}'
DC_CODE="$LAST_CODE"; DC_BODY="$LAST_BODY"
DC_ID=$(json_get "$DC_BODY" "d.get('id')")
if [[ -z "$DC_ID" ]]; then
  http_code GET "$P_API/api/doctor-consult/sessions?status=waiting_doctor"
  DC_ID=$(json_get "$LAST_BODY" "next((x.get('id') for x in (d.get('items') if isinstance(d,dict) else d or []) if x.get('status') in ('waiting_doctor','queued')), '')")
  DC_CODE="$LAST_CODE"
fi
http_code POST "$P_API/api/doctor-consult/sessions/$DC_ID/accept" \
  -H 'X-Role: doctor' -H 'Content-Type: application/json' -d '{}'
ACC_CODE="$LAST_CODE"; ACC_ST=$(json_get "$LAST_BODY" "d.get('status')")
http_code POST "$P_API/api/doctor-consult/sessions/$DC_ID/messages" \
  -H 'X-Role: doctor' -H 'Content-Type: application/json' \
  -d '{"role":"doctor","content":"黄金路径：注意休息，不适随诊。"}'
MSGD_CODE="$LAST_CODE"
if [[ -n "$DC_ID" && "$ACC_CODE" == "200" && "$MSGD_CODE" == "200" ]]; then
  record "GP-05" "PASS" "图文接诊 id=$DC_ID create=$DC_CODE accept=$ACC_CODE/$ACC_ST msg=$MSGD_CODE"
else
  record "GP-05" "FAIL" "图文接诊 id=$DC_ID create=$DC_CODE accept=$ACC_CODE msg=$MSGD_CODE body=${DC_BODY:0:120}"
fi

# ---- 6 doctor preconsult proxy + workbench ----
if [[ -n "$TOKEN" ]]; then
  http_code GET "$D_API/api/preconsult/reports" -H "Authorization: Bearer $TOKEN"
  PREC_CODE="$LAST_CODE"
  http_code GET "$D_API/api/workbench/summary" -H "Authorization: Bearer $TOKEN"
  WB_CODE="$LAST_CODE"; WB_BODY="$LAST_BODY"
  WB_OK=$(json_get "$WB_BODY" "d.get('patientApiOk')")
  if [[ "$PREC_CODE" == "200" && "$WB_CODE" == "200" ]]; then
    record "GP-06" "PASS" "医生预问诊代理 preconsult=$PREC_CODE workbench=$WB_CODE patientApiOk=$WB_OK"
  else
    record "GP-06" "FAIL" "医生预问诊代理 pre=$PREC_CODE wb=$WB_CODE"
  fi
else
  record "GP-06" "FAIL" "医生预问诊代理 skipped — no token"
fi

# ---- 7 followup surveys + messages spot check ----
http_code GET "$P_API/api/followups/surveys"
FU_CODE="$LAST_CODE"; FU_N=$(json_get "$LAST_BODY" "len(d.get('items') if isinstance(d,dict) else d)")
http_code GET "$P_API/api/messages"
MSG_CODE="$LAST_CODE"; MSG_N=$(json_get "$LAST_BODY" "len(d.get('items') if isinstance(d,dict) else d)")
UNREAD=$(json_get "$LAST_BODY" "d.get('unreadCount') if isinstance(d,dict) else ''")
if [[ "$FU_CODE" == "200" && "$MSG_CODE" == "200" ]]; then
  record "GP-07" "PASS" "随访 surveys=$FU_CODE(n=$FU_N) 消息 messages=$MSG_CODE(n=$MSG_N unread=$UNREAD)"
else
  record "GP-07" "FAIL" "随访 surveys=$FU_CODE 消息 messages=$MSG_CODE"
fi

# ---- 8 UI spot (optional light) ----
http_code GET "$P_UI/"
PU_CODE="$LAST_CODE"
http_code GET "$D_UI/"
DU_CODE="$LAST_CODE"
if [[ "$PU_CODE" == "200" && "$DU_CODE" == "200" ]]; then
  record "GP-08" "PASS" "UI patient=$PU_CODE doctor=$DU_CODE"
else
  record "GP-08" "FAIL" "UI patient=$PU_CODE doctor=$DU_CODE"
fi

echo
echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
echo "Results:"
for r in "${RESULTS[@]}"; do
  echo "  $r"
done

{
  echo "PASS=$PASS"
  echo "FAIL=$FAIL"
  echo "SKIP=$SKIP"
  echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
  for r in "${RESULTS[@]}"; do
    echo "$r"
  done
} > "$REPORT_DIR/golden-path.last.env"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
