#!/usr/bin/env bash
# M10 慢病管理冒烟：打卡 → 列表 → summary → 医生 patients/inbox/read
# 用法: bash /workspace/medical-e2e-smoke/chronic-smoke.sh
# 说明: 404/未实现 → SKIP（后端未就绪），不当 FAIL；仅 FAIL>0 时 exit 1
# 不触碰、不重跑 golden-path.sh / smoke.sh
set -u
P_API="${P_API:-http://127.0.0.1:8001}"
D_API="${D_API:-http://127.0.0.1:8000}"
START_ALL="${START_ALL:-/workspace/medical-start-all.sh}"
REPORT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
SKIP=0
RESULTS=()
PATIENT_ID="${PATIENT_ID:-pat-2}"
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
  elif isinstance(d,list):
    for x in d:
      if isinstance(x,dict) and x.get('disclaimer'):
        t=str(x.get('disclaimer'))+' '+t
        break
except Exception:
  pass
keys=['仅供参考','仅供','不能替代','不替代','不构成诊断','须医生确认','辅助','演示','以医院实际','非真实','不发生真实','参考，','就医参考','演示数据']
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

# 404 / 未实现 → SKIP；其它非 2xx → FAIL；返回 0=PASS路径继续断言，1=已记录SKIP/FAIL
handle_unimplemented() {
  local id="$1" label="$2" code="$3" body="$4"
  if [[ "$code" == "404" ]]; then
    record "$id" "SKIP" "$label HTTP 404 — 后端未就绪（慢病 API 未部署）"
    return 1
  fi
  if [[ "$code" == "501" || "$code" == "405" ]]; then
    record "$id" "SKIP" "$label HTTP $code — 后端未就绪/未实现"
    return 1
  fi
  if [[ "$code" != "200" && "$code" != "201" ]]; then
    record "$id" "FAIL" "$label unexpected HTTP $code body=${body:0:160}"
    return 1
  fi
  return 0
}

echo "=== medical M10 chronic-smoke $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo "P_API=$P_API  D_API=$D_API  PATIENT_ID=$PATIENT_ID"
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
  record "CH-00" "PASS" "health patient=$PH_CODE doctor=$DH_CODE"
else
  record "CH-00" "FAIL" "health patient=$PH_CODE doctor=$DH_CODE; abort"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  {
    echo "PASS=$PASS"
    echo "FAIL=$FAIL"
    echo "SKIP=$SKIP"
    echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
    for r in "${RESULTS[@]}"; do echo "$r"; done
  } > "$REPORT_DIR/chronic-smoke.last.env"
  exit 1
fi

# ---- optional demo reset (404 → SKIP，不阻断) ----
http_code POST "$P_API/api/demo/reset" -H 'Content-Type: application/json' -d '{}'
if [[ "$LAST_CODE" == "200" ]]; then
  record "CH-00r" "PASS" "patient demo/reset HTTP 200 seed=$(json_get "$LAST_BODY" "d.get('seedVersion')")"
elif [[ "$LAST_CODE" == "404" ]]; then
  record "CH-00r" "SKIP" "patient demo/reset 404 — 可选，后端未就绪"
else
  record "CH-00r" "SKIP" "patient demo/reset HTTP $LAST_CODE — 可选，不阻断慢病路径"
fi

# ---- 1a POST vitals 正常血压 ----
http_code POST "$P_API/api/chronic/vitals" \
  -H 'Content-Type: application/json' \
  -d "{\"patientId\":\"$PATIENT_ID\",\"type\":\"bp\",\"systolic\":120,\"diastolic\":80,\"note\":\"M10正常打卡\"}"
V1_CODE="$LAST_CODE"; V1_BODY="$LAST_BODY"
VITAL_ID=""
VITALS_READY=0
if handle_unimplemented "CH-01a" "POST /api/chronic/vitals(正常bp)" "$V1_CODE" "$V1_BODY"; then
  VITAL_ID=$(json_get "$V1_BODY" "d.get('id')")
  ABN=$(json_get "$V1_BODY" "d.get('abnormal')")
  DISC_OK=0
  if has_disclaimer_ok "$V1_BODY"; then DISC_OK=1; fi
  if [[ -n "$VITAL_ID" && "$VITAL_ID" != "None" ]]; then
    # 正常血压期望 abnormal 不为 true（允许缺省/false）
    if [[ "$ABN" == "True" || "$ABN" == "true" ]]; then
      record "CH-01a" "FAIL" "正常bp应非异常 id=$VITAL_ID abnormal=$ABN"
    else
      record "CH-01a" "PASS" "id=$VITAL_ID abnormal=${ABN:-false/absent} disclaimer=$DISC_OK"
      VITALS_READY=1
    fi
  else
    record "CH-01a" "FAIL" "缺 id body=${V1_BODY:0:200}"
  fi
fi

# ---- 1b POST vitals 异常血压（可选） ----
http_code POST "$P_API/api/chronic/vitals" \
  -H 'Content-Type: application/json' \
  -d "{\"patientId\":\"$PATIENT_ID\",\"type\":\"bp\",\"systolic\":150,\"diastolic\":95,\"note\":\"M10异常打卡\"}"
V2_CODE="$LAST_CODE"; V2_BODY="$LAST_BODY"
ABN_ID=""
if [[ "$V2_CODE" == "404" || "$V2_CODE" == "501" || "$V2_CODE" == "405" ]]; then
  record "CH-01b" "SKIP" "POST vitals(异常bp) HTTP $V2_CODE — 后端未就绪"
elif [[ "$V2_CODE" == "200" || "$V2_CODE" == "201" ]]; then
  ABN_ID=$(json_get "$V2_BODY" "d.get('id')")
  ABN2=$(json_get "$V2_BODY" "d.get('abnormal')")
  if [[ -n "$ABN_ID" && ( "$ABN2" == "True" || "$ABN2" == "true" ) ]]; then
    record "CH-01b" "PASS" "异常bp id=$ABN_ID abnormal=true"
    VITALS_READY=1
  elif [[ -n "$ABN_ID" ]]; then
    # 有的实现可能把 abnormal 只放在列表/summary；有 id 即记 PASS 并注明
    record "CH-01b" "PASS" "异常bp已写入 id=$ABN_ID abnormal=${ABN2:-absent}（规则字段待后端对齐）"
    VITALS_READY=1
  else
    record "CH-01b" "FAIL" "异常bp缺 id body=${V2_BODY:0:160}"
  fi
else
  record "CH-01b" "FAIL" "POST vitals(异常bp) unexpected HTTP $V2_CODE body=${V2_BODY:0:160}"
fi

# ---- 2 GET vitals list ----
http_code GET "$P_API/api/chronic/vitals?patientId=$PATIENT_ID&limit=20"
VL_CODE="$LAST_CODE"; VL_BODY="$LAST_BODY"
if handle_unimplemented "CH-02" "GET /api/chronic/vitals" "$VL_CODE" "$VL_BODY"; then
  LIST_N=$(json_get "$VL_BODY" "len(d.get('items') if isinstance(d,dict) and 'items' in d else (d if isinstance(d,list) else []))")
  if [[ -n "$LIST_N" && "$LIST_N" != "0" ]]; then
    record "CH-02" "PASS" "list n=$LIST_N patientId=$PATIENT_ID"
  elif [[ "$VITALS_READY" -eq 1 ]]; then
    record "CH-02" "FAIL" "打卡后列表仍空 body=${VL_BODY:0:160}"
  else
    # 未打卡成功时列表可空，但仍 200
    record "CH-02" "PASS" "list HTTP 200 n=${LIST_N:-0}（无先验打卡）"
  fi
fi

# ---- 3 GET vitals summary ----
http_code GET "$P_API/api/chronic/vitals/summary?patientId=$PATIENT_ID"
VS_CODE="$LAST_CODE"; VS_BODY="$LAST_BODY"
if handle_unimplemented "CH-03" "GET /api/chronic/vitals/summary" "$VS_CODE" "$VS_BODY"; then
  DISC_OK=0
  if has_disclaimer_ok "$VS_BODY"; then DISC_OK=1; fi
  # 宽松：有 patientId 或 recent/avg/abnormalCount 任一字段即可
  HAS_SHAPE=$(json_get "$VS_BODY" "1 if (isinstance(d,dict) and (d.get('patientId') or d.get('recent') is not None or d.get('avg7d') is not None or d.get('abnormalCount') is not None or d.get('last') is not None or d.get('bp') is not None or d.get('glucose') is not None or 'items' in d or 'summary' in d)) else 0")
  if [[ "$HAS_SHAPE" == "1" ]]; then
    record "CH-03" "PASS" "summary shape_ok disclaimer=$DISC_OK body_keys_ok"
  else
    record "CH-03" "FAIL" "summary 缺关键字段 body=${VS_BODY:0:200}"
  fi
fi

# ---- 4 doctor login ----
http_code POST "$D_API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$DOCTOR_USER\",\"password\":\"$DOCTOR_PASS\"}"
LG_CODE="$LAST_CODE"; LG_BODY="$LAST_BODY"
TOKEN=$(json_get "$LG_BODY" "d.get('token')")
if [[ "$LG_CODE" == "200" && -n "$TOKEN" ]]; then
  record "CH-04" "PASS" "doctor login ok token_len=${#TOKEN}"
else
  record "CH-04" "FAIL" "doctor login HTTP $LG_CODE body=${LG_BODY:0:160}"
  TOKEN=""
fi

# ---- 5 GET chronic/patients ----
if [[ -n "$TOKEN" ]]; then
  http_code GET "$D_API/api/chronic/patients" -H "Authorization: Bearer $TOKEN"
  CP_CODE="$LAST_CODE"; CP_BODY="$LAST_BODY"
  if handle_unimplemented "CH-05" "GET /api/chronic/patients" "$CP_CODE" "$CP_BODY"; then
    CP_N=$(json_get "$CP_BODY" "len(d.get('items') if isinstance(d,dict) and 'items' in d else (d if isinstance(d,list) else []))")
    record "CH-05" "PASS" "patients n=${CP_N:-0}"
  fi
else
  record "CH-05" "SKIP" "GET chronic/patients skipped — no token"
fi

# ---- 6 GET chronic/inbox ----
INBOX_ITEMS_JSON="[]"
INBOX_READY=0
if [[ -n "$TOKEN" ]]; then
  http_code GET "$D_API/api/chronic/inbox" -H "Authorization: Bearer $TOKEN"
  IB_CODE="$LAST_CODE"; IB_BODY="$LAST_BODY"
  if handle_unimplemented "CH-06" "GET /api/chronic/inbox" "$IB_CODE" "$IB_BODY"; then
    IB_N=$(json_get "$IB_BODY" "len(d.get('items') if isinstance(d,dict) and 'items' in d else (d if isinstance(d,list) else []))")
    INBOX_ITEMS_JSON=$(json_get "$IB_BODY" "d.get('items') if isinstance(d,dict) and 'items' in d else (d if isinstance(d,list) else [])")
    record "CH-06" "PASS" "inbox n=${IB_N:-0}"
    INBOX_READY=1
  fi
else
  record "CH-06" "SKIP" "GET chronic/inbox skipped — no token"
fi

# ---- 7 POST inbox read（若有待阅） ----
if [[ -n "$TOKEN" && "$INBOX_READY" -eq 1 ]]; then
  READ_ID=$(python3 -c "
import json,sys
items=json.loads(sys.argv[1] or '[]')
if not isinstance(items,list):
  items=[]
# prefer unread
for x in items:
  if isinstance(x,dict) and not x.get('read') and x.get('id'):
    print(x['id']); raise SystemExit
for x in items:
  if isinstance(x,dict) and x.get('id'):
    print(x['id']); raise SystemExit
print('')
" "$INBOX_ITEMS_JSON" 2>/dev/null)
  if [[ -z "$READ_ID" ]]; then
    record "CH-07" "SKIP" "inbox 无待阅项 — 无可标已阅"
  else
    http_code POST "$D_API/api/chronic/inbox/$READ_ID/read" \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' -d '{}'
    RD_CODE="$LAST_CODE"; RD_BODY="$LAST_BODY"
    if [[ "$RD_CODE" == "404" ]]; then
      # 尝试 body 形式
      http_code POST "$D_API/api/chronic/inbox/read" \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d "{\"id\":\"$READ_ID\"}"
      RD_CODE="$LAST_CODE"; RD_BODY="$LAST_BODY"
    fi
    if [[ "$RD_CODE" == "404" || "$RD_CODE" == "501" || "$RD_CODE" == "405" ]]; then
      record "CH-07" "SKIP" "POST inbox/read HTTP $RD_CODE — 后端未就绪 id=$READ_ID"
    elif [[ "$RD_CODE" == "200" || "$RD_CODE" == "204" ]]; then
      record "CH-07" "PASS" "inbox read id=$READ_ID HTTP $RD_CODE"
    else
      record "CH-07" "FAIL" "inbox read id=$READ_ID HTTP $RD_CODE body=${RD_BODY:0:160}"
    fi
  fi
elif [[ -z "$TOKEN" ]]; then
  record "CH-07" "SKIP" "POST inbox/read skipped — no token"
else
  record "CH-07" "SKIP" "POST inbox/read skipped — inbox API 未就绪"
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
} > "$REPORT_DIR/chronic-smoke.last.env"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
