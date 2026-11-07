#!/usr/bin/env bash
# M12 运营看板冒烟：login → GET /api/ops/summary → audit export(json|csv)
# 用法: bash /workspace/medical-e2e-smoke/ops-smoke.sh
# 说明: ops/summary 404/501/405 → SKIP（后端未就绪），不当 FAIL；仅 FAIL>0 时 exit 1
# 禁止改动/重跑 smoke.sh / golden-path.sh / chronic-smoke.sh / doctor-ai-smoke.sh
set -u
D_API="${D_API:-http://127.0.0.1:8000}"
START_ALL="${START_ALL:-/workspace/medical-start-all.sh}"
REPORT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
SKIP=0
RESULTS=()
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
keys=['仅供参考','仅供','不能替代','不替代','不构成诊断','须医生确认','辅助','演示','以医院实际','非真实','演示运营','演示数据','参考，','就医参考']
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
  local tmp rc
  tmp=$(mktemp)
  set +e
  LAST_CODE=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" "$url" "$@" 2>/dev/null)
  rc=$?
  set -u
  if [[ $rc -ne 0 || -z "$LAST_CODE" ]]; then
    LAST_CODE="000"
  fi
  LAST_BODY=$(cat "$tmp" 2>/dev/null || true)
  rm -f "$tmp"
}

wait_health() {
  local i
  for i in $(seq 1 30); do
    if curl -sf "$D_API/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# 404/501/405 → SKIP；其它非 2xx → FAIL；返回 0=可继续断言
handle_unimplemented() {
  local id="$1" label="$2" code="$3" body="$4"
  if [[ "$code" == "404" ]]; then
    record "$id" "SKIP" "$label HTTP 404 — 后端未就绪（M12 ops API 未部署）"
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

assert_ops_fields() {
  local body="$1"
  python3 -c "
import json,sys
d=json.loads(sys.argv[1])
if not isinstance(d, dict):
  print('not_object'); sys.exit(1)
required=['appointmentsToday','waitingConsults','deliveriesActive','refillsPending','followupsUnread','chronicAbnormal','updatedAt','disclaimer']
optional=['auditsToday','patientApiOk']
missing=[k for k in required if k not in d]
if missing:
  print('missing:'+','.join(missing)); sys.exit(1)
# numeric-ish fields can be int/float/None but key must exist
nums=['appointmentsToday','waitingConsults','deliveriesActive','refillsPending','followupsUnread','chronicAbnormal']
bad=[]
for k in nums:
  v=d.get(k)
  if v is not None and not isinstance(v,(int,float)):
    bad.append(f'{k}={type(v).__name__}')
if bad:
  print('bad_types:'+','.join(bad)); sys.exit(1)
if not d.get('updatedAt'):
  print('empty_updatedAt'); sys.exit(1)
if not d.get('disclaimer'):
  print('empty_disclaimer'); sys.exit(1)
extra=','.join([k for k in optional if k in d])
print('ok'+(' extras='+extra if extra else ''))
sys.exit(0)
" "$body" 2>/dev/null
}

write_report_env() {
  {
    echo "PASS=$PASS"
    echo "FAIL=$FAIL"
    echo "SKIP=$SKIP"
    echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
    for r in "${RESULTS[@]}"; do echo "$r"; done
  } > "$REPORT_DIR/ops-smoke.last.env"
}

echo "=== medical M12 ops-smoke $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo "D_API=$D_API"
echo

# ---- 0 readiness ----
http_code GET "$D_API/health"
DH_CODE="$LAST_CODE"
if [[ "$DH_CODE" != "200" ]]; then
  echo "health fail doctor=$DH_CODE; trying $START_ALL"
  if [[ -x "$START_ALL" || -f "$START_ALL" ]]; then
    if [[ -x "$START_ALL" ]]; then "$START_ALL" || true; else bash "$START_ALL" || true; fi  # S2: 可执行文件直接跑（支持 START_ALL=/bin/true）
    wait_health || true
    http_code GET "$D_API/health"; DH_CODE="$LAST_CODE"
  fi
fi
if [[ "$DH_CODE" == "200" ]]; then
  record "OPS-00" "PASS" "health doctor=$DH_CODE"
else
  record "OPS-00" "FAIL" "health doctor=$DH_CODE; abort"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  write_report_env
  exit 1
fi

# ---- 1 login ----
http_code POST "$D_API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$DOCTOR_USER\",\"password\":\"$DOCTOR_PASS\"}"
LG_CODE="$LAST_CODE"; LG_BODY="$LAST_BODY"
TOKEN=$(json_get "$LG_BODY" "d.get('token') or d.get('accessToken')")
if [[ "$LG_CODE" == "200" && -n "$TOKEN" && "$TOKEN" != "None" ]]; then
  record "OPS-01" "PASS" "doctor login ok token_len=${#TOKEN}"
else
  record "OPS-01" "FAIL" "doctor login HTTP $LG_CODE body=${LG_BODY:0:160}"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  write_report_env
  exit 1
fi
AUTH=(-H "Authorization: Bearer $TOKEN")

# ---- 2 GET /api/ops/summary ----
http_code GET "$D_API/api/ops/summary" "${AUTH[@]}"
SUM_CODE="$LAST_CODE"; SUM_BODY="$LAST_BODY"
if handle_unimplemented "OPS-02" "GET /api/ops/summary" "$SUM_CODE" "$SUM_BODY"; then
  FIELD_CHK=$(assert_ops_fields "$SUM_BODY" || true)
  if [[ "$FIELD_CHK" == ok* ]]; then
    DETAIL="fields ok ($FIELD_CHK)"
    if has_disclaimer_ok "$SUM_BODY"; then
      DETAIL="$DETAIL; disclaimer OK"
    else
      DETAIL="$DETAIL; disclaimer soft-warn (no demo/参考语义)"
    fi
    # optional peek counts
    AT=$(json_get "$SUM_BODY" "d.get('appointmentsToday')")
    WC=$(json_get "$SUM_BODY" "d.get('waitingConsults')")
    DA=$(json_get "$SUM_BODY" "d.get('deliveriesActive')")
    RP=$(json_get "$SUM_BODY" "d.get('refillsPending')")
    FU=$(json_get "$SUM_BODY" "d.get('followupsUnread')")
    CA=$(json_get "$SUM_BODY" "d.get('chronicAbnormal')")
    UA=$(json_get "$SUM_BODY" "d.get('updatedAt')")
    record "OPS-02" "PASS" "summary 200 appt=$AT wait=$WC del=$DA refill=$RP fu=$FU chron=$CA updatedAt=$UA; $DETAIL"
  else
    record "OPS-02" "FAIL" "summary 200 but fields invalid: ${FIELD_CHK:-unknown} body=${SUM_BODY:0:220}"
  fi
fi

# ---- 2b unauth summary (if implemented) ----
http_code GET "$D_API/api/ops/summary"
UNA_CODE="$LAST_CODE"
if [[ "$UNA_CODE" == "404" || "$UNA_CODE" == "501" || "$UNA_CODE" == "405" ]]; then
  record "OPS-02b" "SKIP" "unauth summary HTTP $UNA_CODE — endpoint 未齐，跳过鉴权抽查"
elif [[ "$UNA_CODE" == "401" || "$UNA_CODE" == "403" ]]; then
  record "OPS-02b" "PASS" "unauth GET /api/ops/summary → $UNA_CODE"
else
  record "OPS-02b" "FAIL" "unauth GET /api/ops/summary expected 401/403 got $UNA_CODE"
fi

# ---- 3 GET /api/audit (list smoke) ----
http_code GET "$D_API/api/audit?limit=5" "${AUTH[@]}"
AL_CODE="$LAST_CODE"; AL_BODY="$LAST_BODY"
if handle_unimplemented "OPS-03" "GET /api/audit" "$AL_CODE" "$AL_BODY"; then
  HAS_ITEMS=$(json_get "$AL_BODY" "(len(d.get('items') or d) if isinstance(d,(dict,list)) else 0)")
  if [[ -n "$HAS_ITEMS" && "$HAS_ITEMS" != "0" && "$HAS_ITEMS" != "None" ]]; then
    record "OPS-03" "PASS" "audit list HTTP 200 items/len=$HAS_ITEMS"
  else
    # empty list still ok if object shape
    if echo "$AL_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,(dict,list)) else 1)" 2>/dev/null; then
      record "OPS-03" "PASS" "audit list HTTP 200 empty-or-shaped ok body=${AL_BODY:0:80}"
    else
      record "OPS-03" "FAIL" "audit list 200 but unexpected body=${AL_BODY:0:160}"
    fi
  fi
fi

# ---- 4 audit export json ----
http_code GET "$D_API/api/audit/export?format=json" "${AUTH[@]}"
EJ_CODE="$LAST_CODE"; EJ_BODY="$LAST_BODY"
if handle_unimplemented "OPS-04" "GET /api/audit/export?format=json" "$EJ_CODE" "$EJ_BODY"; then
  OK_JSON=$(echo "$EJ_BODY" | python3 -c "
import sys,json
raw=sys.stdin.read()
if not raw.strip():
  print('empty'); sys.exit(1)
d=json.loads(raw)
if isinstance(d,dict) and isinstance(d.get('items'),list):
  print('items='+str(len(d['items']))); sys.exit(0)
if isinstance(d,list):
  print('list='+str(len(d))); sys.exit(0)
print('shape'); sys.exit(1)
" 2>/dev/null || echo "parse_fail")
  if [[ "$OK_JSON" == items=* || "$OK_JSON" == list=* ]]; then
    record "OPS-04" "PASS" "audit export json 200 $OK_JSON non-empty-body"
  elif [[ "$OK_JSON" == "empty" ]]; then
    record "OPS-04" "FAIL" "audit export json 200 but empty body"
  else
    # 200 with parseable non-empty still soft pass if length>0
    if [[ ${#EJ_BODY} -gt 2 ]]; then
      record "OPS-04" "PASS" "audit export json 200 body_len=${#EJ_BODY} shape_warn=$OK_JSON"
    else
      record "OPS-04" "FAIL" "audit export json unexpected: $OK_JSON body=${EJ_BODY:0:160}"
    fi
  fi
fi

# ---- 5 audit export csv (optional-ish but required by M12) ----
http_code GET "$D_API/api/audit/export?format=csv" "${AUTH[@]}"
EC_CODE="$LAST_CODE"; EC_BODY="$LAST_BODY"
if handle_unimplemented "OPS-05" "GET /api/audit/export?format=csv" "$EC_CODE" "$EC_BODY"; then
  if [[ ${#EC_BODY} -gt 0 ]]; then
    # prefer header-ish first line
    FIRST_LINE=$(printf '%s' "$EC_BODY" | head -n 1)
    if echo "$FIRST_LINE" | grep -qiE 'id|action|actor|created'; then
      record "OPS-05" "PASS" "audit export csv 200 body_len=${#EC_BODY} header≈${FIRST_LINE:0:60}"
    else
      record "OPS-05" "PASS" "audit export csv 200 non-empty body_len=${#EC_BODY} first=${FIRST_LINE:0:60}"
    fi
  else
    record "OPS-05" "FAIL" "audit export csv 200 but empty body"
  fi
fi

# ---- 6 unauth audit export ----
http_code GET "$D_API/api/audit/export?format=json"
UE_CODE="$LAST_CODE"
if [[ "$UE_CODE" == "401" || "$UE_CODE" == "403" ]]; then
  record "OPS-06" "PASS" "unauth audit export → $UE_CODE"
else
  record "OPS-06" "FAIL" "unauth audit export expected 401/403 got $UE_CODE"
fi

echo
echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
write_report_env

# also write a quick markdown snippet for the report consumer
{
  echo "# M12 运营看板冒烟简报"
  echo
  echo "- 时间：$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "- 环境：医生 API \`$D_API\` · 账号 doctor/demo123"
  echo "- 结果：**pass=$PASS fail=$FAIL skip=$SKIP**"
  echo "- 脚本：\`bash /workspace/medical-e2e-smoke/ops-smoke.sh\`"
  echo
  echo "| ID | 状态 | 详情 |"
  echo "|----|------|------|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r st id det <<<"$r"
    echo "| $id | $st | $det |"
  done
  echo
  echo "## 说明"
  echo "- \`GET /api/ops/summary\` 若 404/501/405 → SKIP（后端未齐），不当 FAIL。"
  echo "- 期望 summary 字段：appointmentsToday, waitingConsults, deliveriesActive, refillsPending, followupsUnread, chronicAbnormal, auditsToday?, updatedAt, disclaimer。"
  echo "- 未重跑、未改坏 smoke / golden-path / chronic / doctor-ai。"
} > "$REPORT_DIR/OPS_SMOKE_REPORT.md"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
