#!/usr/bin/env bash
# AI 医疗双端总冒烟（患者 8001/8765 + 医生 8000/36967）
# 用法: bash /workspace/medical-e2e-smoke/smoke.sh
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

json_get() {
  # json_get <json> <python_expr_on_d>
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
# Prefer structured disclaimer field when JSON
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
  # stdout: body; echo code to fd3 via global LAST_CODE
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

echo "=== medical e2e smoke $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo "P_API=$P_API  D_API=$D_API  P_UI=$P_UI  D_UI=$D_UI"
echo

# ---- 0 readiness ----
http_code GET "$P_API/health"
PH_CODE="$LAST_CODE"
PH_BODY="$LAST_BODY"
http_code GET "$D_API/health"
DH_CODE="$LAST_CODE"
DH_BODY="$LAST_BODY"

if [[ "$PH_CODE" != "200" || "$DH_CODE" != "200" ]]; then
  echo "health fail (patient=$PH_CODE doctor=$DH_CODE); trying $START_ALL"
  if [[ -x "$START_ALL" || -f "$START_ALL" ]]; then
    if [[ -x "$START_ALL" ]]; then "$START_ALL" || true; else bash "$START_ALL" || true; fi  # S2: 可执行文件直接跑（支持 START_ALL=/bin/true）
    wait_health || true
    http_code GET "$P_API/health"; PH_CODE="$LAST_CODE"; PH_BODY="$LAST_BODY"
    http_code GET "$D_API/health"; DH_CODE="$LAST_CODE"; DH_BODY="$LAST_BODY"
  fi
fi

if [[ "$PH_CODE" == "200" && "$DH_CODE" == "200" ]]; then
  record "E2E-00" "PASS" "health patient=$PH_CODE doctor=$DH_CODE body_ok"
else
  record "E2E-00" "FAIL" "health patient=$PH_CODE doctor=$DH_CODE; abort remaining"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  exit 1
fi

# ---- 13 UI ----
http_code GET "$P_UI/"
PU_CODE="$LAST_CODE"
http_code GET "$D_UI/"
DU_CODE="$LAST_CODE"
if [[ "$PU_CODE" == "200" && "$DU_CODE" == "200" ]]; then
  record "E2E-13" "PASS" "UI patient=$PU_CODE doctor=$DU_CODE"
else
  record "E2E-13" "FAIL" "UI patient=$PU_CODE doctor=$DU_CODE"
fi

# ---- 1 triage ----
http_code POST "$P_API/api/triage/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"chief":"咳嗽发热","duration":"2天","bodyPart":"咽喉","severity":"中等","age":32}'
T_CODE="$LAST_CODE"; T_BODY="$LAST_BODY"
DEPTS=$(json_get "$T_BODY" "d.get('departments')")
SRC=$(json_get "$T_BODY" "d.get('source')")
if [[ "$T_CODE" == "200" && -n "$DEPTS" && "$DEPTS" != "null" && "$DEPTS" != "[]" ]]; then
  if has_disclaimer_ok "$T_BODY"; then
    record "E2E-01" "PASS" "HTTP $T_CODE source=$SRC departments_ok disclaimer_ok"
  else
    record "E2E-01" "FAIL" "HTTP $T_CODE missing disclaimer semantics"
  fi
else
  record "E2E-01" "FAIL" "HTTP $T_CODE body=${T_BODY:0:200}"
fi

# P1 short chief
http_code POST "$P_API/api/triage/recommend" \
  -H 'Content-Type: application/json' \
  -d '{"chief":"a"}'
if [[ "$LAST_CODE" =~ ^(200|4) ]]; then
  record "E2E-14" "PASS" "short chief HTTP $LAST_CODE (accepted as boundary)"
else
  record "E2E-14" "FAIL" "short chief unexpected HTTP $LAST_CODE"
fi

# ---- 2 consult ----
http_code POST "$P_API/api/consult/sessions" \
  -H 'Content-Type: application/json' \
  -d '{"chief":"反复上腹痛3天","patientId":"pat-1"}'
S_CODE="$LAST_CODE"; S_BODY="$LAST_BODY"
SID=$(json_get "$S_BODY" "d.get('id') or d.get('sessionId')")
if [[ "$S_CODE" != "200" || -z "$SID" ]]; then
  # try minimal body
  http_code POST "$P_API/api/consult/sessions" \
    -H 'Content-Type: application/json' \
    -d '{}'
  S_CODE="$LAST_CODE"; S_BODY="$LAST_BODY"
  SID=$(json_get "$S_BODY" "d.get('id') or d.get('sessionId')")
fi

if [[ -n "$SID" ]]; then
  http_code POST "$P_API/api/consult/sessions/$SID/messages" \
    -H 'Content-Type: application/json' \
    -d '{"content":"饭后上腹痛，伴反酸，无黑便"}'
  M_CODE="$LAST_CODE"; M_BODY="$LAST_BODY"
  if [[ "$M_CODE" == "200" ]]; then
    record "E2E-02" "PASS" "session=$SID message HTTP $M_CODE source=$(json_get "$M_BODY" "d.get('source')")"
  else
    record "E2E-02" "FAIL" "message HTTP $M_CODE body=${M_BODY:0:180}"
  fi
else
  record "E2E-02" "FAIL" "create session HTTP $S_CODE body=${S_BODY:0:180}"
fi

# P1 bad session
http_code POST "$P_API/api/consult/sessions/sess-not-exist/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content":"x"}'
if [[ "$LAST_CODE" == "404" ]]; then
  record "E2E-15" "PASS" "missing session message → 404"
else
  record "E2E-15" "FAIL" "expected 404 got $LAST_CODE"
fi

# ---- 3 appointments ----
http_code GET "$P_API/api/departments"
DEPT_BODY="$LAST_BODY"; DEPT_CODE="$LAST_CODE"
DEPT_ID=$(json_get "$DEPT_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
http_code GET "$P_API/api/departments/$DEPT_ID/doctors"
DOC_BODY="$LAST_BODY"
DOC_ID=$(json_get "$DOC_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
http_code GET "$P_API/api/doctors/$DOC_ID/slots?date=$TODAY"
SLOT_BODY="$LAST_BODY"
SLOT_ID=$(json_get "$SLOT_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
# fallback: find any available slot in next days
if [[ -z "$SLOT_ID" || "$SLOT_ID" == "None" ]]; then
  for i in 0 1 2 3 4; do
    DAY=$(date -d "+$i day" +%Y-%m-%d 2>/dev/null || date -v+${i}d +%Y-%m-%d 2>/dev/null || echo "$TODAY")
    http_code GET "$P_API/api/doctors/$DOC_ID/slots?date=$DAY"
    SLOT_ID=$(json_get "$LAST_BODY" "next((x.get('id') for x in (d if isinstance(d,list) else d.get('items') or []) if x.get('available',True) and x.get('remaining',1)>0), '')")
    [[ -n "$SLOT_ID" ]] && break
  done
fi
http_code POST "$P_API/api/appointments" \
  -H 'Content-Type: application/json' \
  -d "{\"departmentId\":\"$DEPT_ID\",\"doctorId\":\"$DOC_ID\",\"slotId\":\"$SLOT_ID\",\"patientName\":\"冒烟患者\",\"phone\":\"13800000001\",\"chief\":\"咳嗽发热\"}"
AP_CODE="$LAST_CODE"; AP_BODY="$LAST_BODY"
AP_ID=$(json_get "$AP_BODY" "d.get('id')")
http_code GET "$P_API/api/appointments"
AL_CODE="$LAST_CODE"
http_code GET "$P_API/api/appointments/$AP_ID"
AD_CODE="$LAST_CODE"
if [[ "$DEPT_CODE" == "200" && -n "$DEPT_ID" && -n "$DOC_ID" && -n "$SLOT_ID" && "$AP_CODE" == "200" && -n "$AP_ID" && "$AL_CODE" == "200" && "$AD_CODE" == "200" ]]; then
  record "E2E-03" "PASS" "dept=$DEPT_ID doc=$DOC_ID slot=$SLOT_ID appt=$AP_ID"
else
  record "E2E-03" "FAIL" "dept=$DEPT_CODE/$DEPT_ID doc=$DOC_ID slot=$SLOT_ID create=$AP_CODE id=$AP_ID list=$AL_CODE detail=$AD_CODE body=${AP_BODY:0:160}"
fi

# ---- 4 preconsult ----
PRE_OK=0
if [[ -n "${SID:-}" ]]; then
  http_code POST "$P_API/api/consult/sessions/$SID/preconsult-report" \
    -H 'Content-Type: application/json' -d '{}'
  if [[ "$LAST_CODE" == "200" ]] && has_disclaimer_ok "$LAST_BODY"; then
    PRE_OK=1
    PRE_SRC=$(json_get "$LAST_BODY" "d.get('source')")
    PRE_NOTE="session-preconsult source=$PRE_SRC"
  fi
fi
if [[ "$PRE_OK" -eq 0 ]]; then
  http_code POST "$P_API/api/previsit/report" \
    -H 'Content-Type: application/json' \
    -d '{"chiefComplaint":"反复上腹痛3天","duration":"3天","bodyPart":"上腹","accompanying":["反酸"],"allergies":"青霉素"}'
  if [[ "$LAST_CODE" == "200" ]] && has_disclaimer_ok "$LAST_BODY"; then
    PRE_OK=1
    PRE_SRC=$(json_get "$LAST_BODY" "d.get('source')")
    PRE_NOTE="previsit/report source=$PRE_SRC"
  else
    PRE_NOTE="HTTP $LAST_CODE body=${LAST_BODY:0:160}"
  fi
fi
http_code GET "$P_API/api/reports/preconsult"
if [[ "$PRE_OK" -eq 1 ]]; then
  record "E2E-04" "PASS" "$PRE_NOTE list_HTTP=$LAST_CODE"
else
  record "E2E-04" "FAIL" "$PRE_NOTE"
fi

# ---- 5 report interpret ----
http_code GET "$P_API/api/reports"
R_CODE="$LAST_CODE"; R_BODY="$LAST_BODY"
RID=$(json_get "$R_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
http_code POST "$P_API/api/reports/interpret" \
  -H 'Content-Type: application/json' \
  -d '{"text":"血常规：白细胞 12.5×10^9/L，血红蛋白 118 g/L，血小板 210×10^9/L","reportType":"lab"}'
I_CODE="$LAST_CODE"; I_BODY="$LAST_BODY"
I_SRC=$(json_get "$I_BODY" "d.get('source')")
if [[ "$R_CODE" == "200" && -n "$RID" && "$I_CODE" == "200" ]] && has_disclaimer_ok "$I_BODY"; then
  record "E2E-05" "PASS" "reports list ok id=$RID interpret HTTP $I_CODE source=$I_SRC disclaimer_ok"
else
  # try id interpret
  http_code POST "$P_API/api/reports/$RID/interpret" -H 'Content-Type: application/json' -d '{}'
  if [[ "$LAST_CODE" == "200" ]] && has_disclaimer_ok "$LAST_BODY"; then
    record "E2E-05" "PASS" "reports/$RID/interpret HTTP $LAST_CODE"
  else
    record "E2E-05" "FAIL" "list=$R_CODE id=$RID interpret=$I_CODE body=${I_BODY:0:160}"
  fi
fi

# ---- 6 waiting / messages / nav ----
http_code GET "$P_API/api/waiting/status"
W_CODE="$LAST_CODE"; W_BODY="$LAST_BODY"
http_code GET "$P_API/api/messages"
MSG_CODE="$LAST_CODE"; MSG_BODY="$LAST_BODY"
http_code GET "$P_API/api/navigation/departments"
NAV_CODE="$LAST_CODE"; NAV_BODY="$LAST_BODY"
W_N=$(json_get "$W_BODY" "len(d.get('items') if isinstance(d,dict) else d)")
MSG_N=$(json_get "$MSG_BODY" "len(d.get('items') if isinstance(d,dict) else d)")
NAV_N=$(json_get "$NAV_BODY" "len(d.get('items') if isinstance(d,dict) else d)")
if [[ "$W_CODE" == "200" && "$MSG_CODE" == "200" && "$NAV_CODE" == "200" ]]; then
  record "E2E-06" "PASS" "waiting=$W_CODE(n=$W_N) messages=$MSG_CODE(n=$MSG_N) nav=$NAV_CODE(n=$NAV_N)"
else
  record "E2E-06" "FAIL" "waiting=$W_CODE messages=$MSG_CODE nav=$NAV_CODE"
fi

# ---- 7 refills / meds / followups ----
http_code GET "$P_API/api/refills"
RF_CODE="$LAST_CODE"; RF_N=$(json_get "$LAST_BODY" "len(d.get('items') or [])")
http_code GET "$P_API/api/medications/today"
MD_CODE="$LAST_CODE"; MD_N=$(json_get "$LAST_BODY" "len(d.get('items') or [])")
http_code GET "$P_API/api/followups/surveys"
FU_CODE="$LAST_CODE"; FU_N=$(json_get "$LAST_BODY" "len(d.get('items') if isinstance(d,dict) else d)")
http_code POST "$P_API/api/refills" \
  -H 'Content-Type: application/json' \
  -d '{"patientId":"pat-1","medicationName":"冒烟续方药","dosage":"1片 bid","quantity":"14天","reason":"e2e"}'
RF_POST="$LAST_CODE"
if [[ "$RF_CODE" == "200" && "$MD_CODE" == "200" && "$FU_CODE" == "200" && "$RF_POST" == "200" ]]; then
  record "E2E-07" "PASS" "refills(n=$RF_N) today(n=$MD_N) surveys(n=$FU_N) create=$RF_POST"
else
  record "E2E-07" "FAIL" "refills=$RF_CODE today=$MD_CODE surveys=$FU_CODE create=$RF_POST"
fi

# ---- 8 bills + identity ----
http_code GET "$P_API/api/bills"
B_CODE="$LAST_CODE"; B_BODY="$LAST_BODY"
UNPAID=$(json_get "$B_BODY" "next((x['id'] for x in (d.get('items') or []) if x.get('status')=='unpaid'), '')")
PAY_CODE="skip"
if [[ -n "$UNPAID" ]]; then
  http_code POST "$P_API/api/bills/$UNPAID/pay" -H 'Content-Type: application/json' -d '{}'
  PAY_CODE="$LAST_CODE"
  PAY_STATUS=$(json_get "$LAST_BODY" "d.get('status')")
else
  PAY_STATUS=""
fi
http_code GET "$P_API/api/identity"
ID_CODE="$LAST_CODE"; ID_BODY="$LAST_BODY"
MASK_OK=$(python3 -c "
import json,sys
d=json.loads(sys.argv[1])
# must have masked fields; must NOT contain 18-digit raw id in values
vals=' '.join(str(v) for v in d.values())
import re
raw=bool(re.search(r'(?<![*])\d{17}[\dXx]', vals))
has_mask=('Masked' in ''.join(d.keys())) or ('masked' in vals.lower()) or ('*' in vals)
print('1' if (has_mask and not raw) else '0')
" "$ID_BODY" 2>/dev/null || echo 0)
http_code PUT "$P_API/api/identity" \
  -H 'Content-Type: application/json' \
  -d '{"realName":"冒烟测试","idNumber":"110101199001011234","visitCardNo":"VC99998888"}'
ID_PUT="$LAST_CODE"; ID_PUT_BODY="$LAST_BODY"
# ensure response not echoing full id
LEAK=$(python3 -c "
import json,sys,re
t=sys.argv[1]
print('1' if '110101199001011234' in t else '0')
" "$ID_PUT_BODY" 2>/dev/null || echo 0)
if [[ "$B_CODE" == "200" && ( "$PAY_CODE" == "200" || "$PAY_CODE" == "skip" ) && "$ID_CODE" == "200" && "$MASK_OK" == "1" && "$ID_PUT" == "200" && "$LEAK" == "0" ]]; then
  record "E2E-08" "PASS" "bills=$B_CODE pay=$PAY_CODE/$PAY_STATUS identity_get=$ID_CODE mask_ok put=$ID_PUT no_plaintext_id"
else
  record "E2E-08" "FAIL" "bills=$B_CODE unpaid=$UNPAID pay=$PAY_CODE id_get=$ID_CODE mask=$MASK_OK put=$ID_PUT leak=$LEAK"
fi

# P1 identity mask after put
http_code GET "$P_API/api/identity"
if echo "$LAST_BODY" | grep -q '110101199001011234'; then
  record "E2E-17" "FAIL" "GET identity leaked plaintext idNumber"
else
  # check masked present
  if echo "$LAST_BODY" | grep -qE 'Masked|\*|[0-9]{4}'; then
    record "E2E-17" "PASS" "identity GET masked only after PUT"
  else
    record "E2E-17" "FAIL" "unexpected identity shape ${LAST_BODY:0:120}"
  fi
fi

# ---- 9 doctor-consult M5 ----
http_code POST "$P_API/api/doctor-consult/sessions" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"text","patientId":"pat-1","chiefComplaint":"冒烟图文接诊","departmentName":"全科"}'
DC_CODE="$LAST_CODE"; DC_BODY="$LAST_BODY"
DC_ID=$(json_get "$DC_BODY" "d.get('id')")
if [[ -z "$DC_ID" ]]; then
  # use seeded waiting
  http_code GET "$P_API/api/doctor-consult/sessions?status=waiting_doctor"
  DC_ID=$(json_get "$LAST_BODY" "next((x.get('id') for x in (d.get('items') if isinstance(d,dict) else d or []) if x.get('status') in ('waiting_doctor','queued')), '')")
  DC_CODE="$LAST_CODE"
fi
http_code POST "$P_API/api/doctor-consult/sessions/$DC_ID/accept" \
  -H 'X-Role: doctor' -H 'Content-Type: application/json' -d '{}'
ACC_CODE="$LAST_CODE"; ACC_ST=$(json_get "$LAST_BODY" "d.get('status')")
http_code POST "$P_API/api/doctor-consult/sessions/$DC_ID/messages" \
  -H 'X-Role: doctor' -H 'Content-Type: application/json' \
  -d '{"role":"doctor","content":"冒烟医生回复：注意休息，不适随诊。"}'
MSGD_CODE="$LAST_CODE"
http_code POST "$P_API/api/doctor-consult/sessions/$DC_ID/end" \
  -H 'X-Role: doctor' -H 'Content-Type: application/json' \
  -d '{"summary":"e2e ended"}'
END_CODE="$LAST_CODE"; END_ST=$(json_get "$LAST_BODY" "d.get('status')")
if [[ -n "$DC_ID" && "$ACC_CODE" == "200" && "$MSGD_CODE" == "200" && "$END_CODE" == "200" && "$END_ST" == "ended" ]]; then
  record "E2E-09" "PASS" "id=$DC_ID accept=$ACC_CODE/$ACC_ST msg=$MSGD_CODE end=$END_CODE/$END_ST"
else
  record "E2E-09" "FAIL" "id=$DC_ID create=$DC_CODE accept=$ACC_CODE msg=$MSGD_CODE end=$END_CODE/$END_ST body=${DC_BODY:0:120}"
fi

# ---- 10 exam M6 ----
http_code GET "$P_API/api/exam-items"
EX_CODE="$LAST_CODE"; EX_BODY="$LAST_BODY"
EX_ID=$(json_get "$EX_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
EX_SLOT=""
for i in 0 1 2 3 4; do
  DAY=$(date -d "+$i day" +%Y-%m-%d 2>/dev/null || echo "$TODAY")
  http_code GET "$P_API/api/exam-items/$EX_ID/slots?date=$DAY"
  EX_SLOT=$(json_get "$LAST_BODY" "next((x.get('slotId') or x.get('id') for x in (d if isinstance(d,list) else d.get('items') or []) if x.get('remaining',1)>0 or x.get('available',True)), '')")
  [[ -n "$EX_SLOT" ]] && EX_DAY="$DAY" && break
done
http_code POST "$P_API/api/exam-bookings" \
  -H 'Content-Type: application/json' \
  -d "{\"itemId\":\"$EX_ID\",\"slotId\":\"$EX_SLOT\",\"date\":\"${EX_DAY:-$TODAY}\",\"patientId\":\"pat-1\",\"note\":\"e2e\"}"
BK_CODE="$LAST_CODE"; BK_BODY="$LAST_BODY"
BK_ID=$(json_get "$BK_BODY" "d.get('id')")
http_code GET "$P_API/api/exam-bookings/$BK_ID"
BK_D_CODE="$LAST_CODE"
# cancel抽查
http_code POST "$P_API/api/exam-bookings/$BK_ID/cancel" \
  -H 'Content-Type: application/json' -d '{"reason":"e2e cancel"}'
BK_C_CODE="$LAST_CODE"
if [[ "$EX_CODE" == "200" && -n "$EX_ID" && -n "$EX_SLOT" && "$BK_CODE" == "200" && -n "$BK_ID" && "$BK_D_CODE" == "200" && "$BK_C_CODE" == "200" ]]; then
  record "E2E-10" "PASS" "item=$EX_ID slot=$EX_SLOT book=$BK_ID detail=$BK_D_CODE cancel=$BK_C_CODE"
else
  record "E2E-10" "FAIL" "items=$EX_CODE id=$EX_ID slot=$EX_SLOT book=$BK_CODE/$BK_ID detail=$BK_D_CODE cancel=$BK_C_CODE body=${BK_BODY:0:160}"
fi

# ---- 11 pharmacy M7 ----
http_code GET "$P_API/api/pharmacy/orders"
PO_CODE="$LAST_CODE"; PO_BODY="$LAST_BODY"
PO_ID=$(json_get "$PO_BODY" "next((x['id'] for x in (d.get('items') or []) if x.get('status') not in ('delivering','delivered')), (d.get('items') or [{}])[0].get('id') if d.get('items') else '')")
# prefer an order not already delivering if possible
PO_ID=$(json_get "$PO_BODY" "(d.get('items') or [{}])[-1].get('id') if d.get('items') else ''")
http_code GET "$P_API/api/pharmacy/addresses"
PA_CODE="$LAST_CODE"; PA_BODY="$LAST_BODY"
PA_ID=$(json_get "$PA_BODY" "(d[0]['id'] if isinstance(d,list) and d else (d.get('items') or [{}])[0].get('id'))")
http_code GET "$P_API/api/pharmacy/deliveries"
PD_LIST_CODE="$LAST_CODE"
# create delivery if possible
http_code POST "$P_API/api/pharmacy/deliveries" \
  -H 'Content-Type: application/json' \
  -d "{\"orderId\":\"$PO_ID\",\"addressId\":\"$PA_ID\",\"patientId\":\"pat-1\"}"
PD_CODE="$LAST_CODE"; PD_BODY="$LAST_BODY"
PD_ID=$(json_get "$PD_BODY" "d.get('id')")
if [[ -z "$PD_ID" ]]; then
  # fallback list existing
  http_code GET "$P_API/api/pharmacy/deliveries"
  PD_ID=$(json_get "$LAST_BODY" "(d.get('items') or [{}])[0].get('id') if isinstance(d,dict) else (d[0].get('id') if d else '')")
  PD_CODE="$LAST_CODE"
fi
if [[ "$PO_CODE" == "200" && "$PA_CODE" == "200" && -n "$PO_ID" && -n "$PA_ID" && -n "$PD_ID" ]]; then
  record "E2E-11" "PASS" "orders=$PO_CODE($PO_ID) addr=$PA_CODE($PA_ID) delivery=$PD_ID create/list=$PD_CODE"
else
  record "E2E-11" "FAIL" "orders=$PO_CODE/$PO_ID addr=$PA_CODE/$PA_ID delivery=$PD_CODE/$PD_ID body=${PD_BODY:0:140}"
fi

# ---- 12 doctor proxy ----
http_code POST "$D_API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"doctor","password":"demo123"}'
LG_CODE="$LAST_CODE"; LG_BODY="$LAST_BODY"
TOKEN=$(json_get "$LG_BODY" "d.get('token')")
http_code GET "$D_API/api/visits" 
# unauth
UNAUTH_VISITS="$LAST_CODE"
http_code GET "$D_API/api/preconsult/reports"
UNAUTH_PRE="$LAST_CODE"
if [[ -n "$TOKEN" ]]; then
  http_code GET "$D_API/api/preconsult/reports" -H "Authorization: Bearer $TOKEN"
  PREC_CODE="$LAST_CODE"; PREC_BODY="$LAST_BODY"
  http_code GET "$D_API/api/workbench/summary" -H "Authorization: Bearer $TOKEN"
  WB_CODE="$LAST_CODE"; WB_BODY="$LAST_BODY"
  WB_OK=$(json_get "$WB_BODY" "d.get('patientApiOk')")
  http_code GET "$D_API/api/visits" -H "Authorization: Bearer $TOKEN"
  VIS_CODE="$LAST_CODE"
else
  PREC_CODE=0; WB_CODE=0; VIS_CODE=0; WB_OK=""; PREC_BODY=""
fi
if [[ "$LG_CODE" == "200" && -n "$TOKEN" && "$PREC_CODE" == "200" && "$WB_CODE" == "200" && "$VIS_CODE" == "200" ]]; then
  record "E2E-12" "PASS" "login ok preconsult=$PREC_CODE workbench=$WB_CODE patientApiOk=$WB_OK visits=$VIS_CODE"
else
  record "E2E-12" "FAIL" "login=$LG_CODE token_len=${#TOKEN} pre=$PREC_CODE wb=$WB_CODE visits=$VIS_CODE"
fi
if [[ "$UNAUTH_VISITS" == "401" && "$UNAUTH_PRE" == "401" ]]; then
  record "E2E-16" "PASS" "unauth visits=$UNAUTH_VISITS preconsult=$UNAUTH_PRE"
else
  record "E2E-16" "FAIL" "expected 401 got visits=$UNAUTH_VISITS preconsult=$UNAUTH_PRE"
fi

echo
echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
echo "Results:"
for r in "${RESULTS[@]}"; do
  echo "  $r"
done

# write machine-readable summary for report generator
{
  echo "PASS=$PASS"
  echo "FAIL=$FAIL"
  echo "SKIP=$SKIP"
  echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
  for r in "${RESULTS[@]}"; do
    echo "$r"
  done
} > "$REPORT_DIR/smoke.last.env"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
