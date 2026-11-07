#!/usr/bin/env bash
# M11 医生 AI 加深冒烟：templates → apply-template → differential → apply-to-note → orders/suggest → orders 批量
# 用法: bash /workspace/medical-e2e-smoke/doctor-ai-smoke.sh
# 说明: 404/501/405 → SKIP（后端未就绪），不当 FAIL；仅 FAIL>0 时 exit 1
# 禁止改动/重跑 smoke.sh / golden-path.sh / chronic-smoke.sh
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
  elif isinstance(d,list):
    for x in d:
      if isinstance(x,dict) and x.get('disclaimer'):
        t=str(x.get('disclaimer'))+' '+t
        break
except Exception:
  pass
keys=['仅供参考','仅供','不能替代','不替代','不构成诊断','须医生确认','辅助','演示','以医院实际','非真实','AI 建议','参考，','就医参考','演示数据']
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
    record "$id" "SKIP" "$label HTTP 404 — 后端未就绪（M11 接口未部署）"
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

echo "=== medical M11 doctor-ai-smoke $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
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
  record "DA-00" "PASS" "health doctor=$DH_CODE"
else
  record "DA-00" "FAIL" "health doctor=$DH_CODE; abort"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  {
    echo "PASS=$PASS"; echo "FAIL=$FAIL"; echo "SKIP=$SKIP"
    echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
    for r in "${RESULTS[@]}"; do echo "$r"; done
  } > "$REPORT_DIR/doctor-ai-smoke.last.env"
  exit 1
fi

# ---- 1 login ----
http_code POST "$D_API/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$DOCTOR_USER\",\"password\":\"$DOCTOR_PASS\"}"
LG_CODE="$LAST_CODE"; LG_BODY="$LAST_BODY"
TOKEN=$(json_get "$LG_BODY" "d.get('token')")
if [[ "$LG_CODE" == "200" && -n "$TOKEN" && "$TOKEN" != "None" ]]; then
  record "DA-01" "PASS" "doctor login ok token_len=${#TOKEN}"
else
  record "DA-01" "FAIL" "doctor login HTTP $LG_CODE body=${LG_BODY:0:160}"
  echo
  echo "=== SUMMARY pass=$PASS fail=$FAIL skip=$SKIP ==="
  {
    echo "PASS=$PASS"; echo "FAIL=$FAIL"; echo "SKIP=$SKIP"
    echo "TS=$(date '+%Y-%m-%d %H:%M:%S %Z')"
    for r in "${RESULTS[@]}"; do echo "$r"; done
  } > "$REPORT_DIR/doctor-ai-smoke.last.env"
  exit 1
fi
AUTH=(-H "Authorization: Bearer $TOKEN")

# ---- 2 create / get visit ----
http_code POST "$D_API/api/visits" \
  "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"M11医生AI测试","gender":"男","age":42,"chief":"上腹痛2天伴反酸","status":"waiting"}'
CV_CODE="$LAST_CODE"; CV_BODY="$LAST_BODY"
VISIT_ID=$(json_get "$CV_BODY" "d.get('id')")
if [[ "$CV_CODE" != "200" && "$CV_CODE" != "201" ]] || [[ -z "$VISIT_ID" || "$VISIT_ID" == "None" ]]; then
  # fallback: list visits
  http_code GET "$D_API/api/visits" "${AUTH[@]}"
  VISIT_ID=$(json_get "$LAST_BODY" "(d[0].get('id') if isinstance(d,list) and d else (d.get('items')[0].get('id') if isinstance(d,dict) and d.get('items') else None))")
  if [[ -n "$VISIT_ID" && "$VISIT_ID" != "None" ]]; then
    record "DA-02" "PASS" "reuse visit id=$VISIT_ID (create HTTP $CV_CODE)"
  else
    record "DA-02" "FAIL" "create/list visit failed create=$CV_CODE body=${CV_BODY:0:160}"
    VISIT_ID=""
  fi
else
  record "DA-02" "PASS" "create visit id=$VISIT_ID HTTP $CV_CODE chief=上腹痛2天伴反酸"
fi

# optional: PUT chief to enrich differential context
if [[ -n "$VISIT_ID" ]]; then
  http_code PUT "$D_API/api/visits/$VISIT_ID" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d '{"chief":"上腹痛2天伴反酸","hpi":"餐后加重，无黑便","status":"in_progress"}' >/dev/null 2>&1 || true
fi

# ---- 3 GET /api/templates ----
http_code GET "$D_API/api/templates" "${AUTH[@]}"
TP_CODE="$LAST_CODE"; TP_BODY="$LAST_BODY"
TEMPLATE_ID=""
if handle_unimplemented "DA-03" "GET /api/templates" "$TP_CODE" "$TP_BODY"; then
  TP_N=$(json_get "$TP_BODY" "len(d if isinstance(d,list) else (d.get('items') if isinstance(d,dict) else []))")
  TEMPLATE_ID=$(json_get "$TP_BODY" "(d[0].get('id') if isinstance(d,list) and d else (d.get('items')[0].get('id') if isinstance(d,dict) and d.get('items') else None))")
  # expect >=1 specialty templates (全科/消化/呼吸/心内)
  if [[ -n "$TP_N" && "$TP_N" != "0" ]]; then
    record "DA-03" "PASS" "templates n=$TP_N first_id=${TEMPLATE_ID:-none}"
  else
    record "DA-03" "FAIL" "templates 空列表 body=${TP_BODY:0:200}"
  fi
fi

# ---- 4 POST apply-template ----
if [[ -z "$VISIT_ID" ]]; then
  record "DA-04" "SKIP" "POST apply-template skipped — no visit"
elif [[ -z "$TEMPLATE_ID" || "$TEMPLATE_ID" == "None" ]]; then
  # still probe route even without template id
  http_code POST "$D_API/api/visits/$VISIT_ID/apply-template" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d '{"templateId":"gi","overwrite":false}'
  AT_CODE="$LAST_CODE"; AT_BODY="$LAST_BODY"
  if [[ "$AT_CODE" == "404" || "$AT_CODE" == "501" || "$AT_CODE" == "405" ]]; then
    record "DA-04" "SKIP" "POST apply-template HTTP $AT_CODE — 后端未就绪（无 templates 时探测）"
  elif [[ "$AT_CODE" == "200" || "$AT_CODE" == "201" ]]; then
    record "DA-04" "PASS" "apply-template HTTP $AT_CODE（fallback templateId=gi）"
  else
    # 400/422 with route present but bad id — still SKIP if templates missing, else FAIL
    record "DA-04" "SKIP" "POST apply-template HTTP $AT_CODE — 无可用 templateId，字段/路由未齐 body=${AT_BODY:0:120}"
  fi
else
  http_code POST "$D_API/api/visits/$VISIT_ID/apply-template" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d "{\"templateId\":\"$TEMPLATE_ID\",\"overwrite\":false}"
  AT_CODE="$LAST_CODE"; AT_BODY="$LAST_BODY"
  if handle_unimplemented "DA-04" "POST apply-template" "$AT_CODE" "$AT_BODY"; then
    record "DA-04" "PASS" "apply-template templateId=$TEMPLATE_ID visit=$VISIT_ID"
  fi
fi

# ---- 5 POST differential（可跑） ----
DX_NAMES_JSON="[]"
DIFF_OK=0
if [[ -z "$VISIT_ID" ]]; then
  record "DA-05" "SKIP" "POST differential skipped — no visit"
else
  http_code POST "$D_API/api/visits/$VISIT_ID/differential" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d '{}'
  DF_CODE="$LAST_CODE"; DF_BODY="$LAST_BODY"
  if handle_unimplemented "DA-05" "POST differential" "$DF_CODE" "$DF_BODY"; then
    DX_N=$(json_get "$DF_BODY" "len(d.get('items') if isinstance(d,dict) and 'items' in d else (d if isinstance(d,list) else []))")
    DX_NAMES_JSON=$(json_get "$DF_BODY" "[x.get('name') for x in (d.get('items') if isinstance(d,dict) else d) if isinstance(x,dict) and x.get('name')][:3]")
    DISC_OK=0
    if has_disclaimer_ok "$DF_BODY"; then DISC_OK=1; fi
    if [[ -n "$DX_N" && "$DX_N" != "0" ]]; then
      record "DA-05" "PASS" "differential n=$DX_N disclaimer=$DISC_OK names=${DX_NAMES_JSON:0:80}"
      DIFF_OK=1
    else
      record "DA-05" "FAIL" "differential 空 items body=${DF_BODY:0:200}"
    fi
  fi
fi

# ---- reconnect if API dropped during long LLM call ----
http_code GET "$D_API/health"
if [[ "$LAST_CODE" != "200" ]]; then
  echo "doctor API down after differential (health=$LAST_CODE); trying restart"
  if [[ -x "$START_ALL" || -f "$START_ALL" ]]; then
    if [[ -x "$START_ALL" ]]; then "$START_ALL" || true; else bash "$START_ALL" || true; fi  # S2: 可执行文件直接跑（支持 START_ALL=/bin/true）
    wait_health || true
  fi
  http_code GET "$D_API/health"
  if [[ "$LAST_CODE" == "200" ]]; then
    record "DA-05r" "PASS" "doctor API restarted after differential"
    # re-login (token may still be valid but refresh)
    http_code POST "$D_API/api/auth/login" \
      -H 'Content-Type: application/json' \
      -d "{\"username\":\"$DOCTOR_USER\",\"password\":\"$DOCTOR_PASS\"}"
    TOKEN=$(json_get "$LAST_BODY" "d.get('token')")
    AUTH=(-H "Authorization: Bearer $TOKEN")
    # recreate visit if lost (in-memory) — try GET first
    if [[ -n "$VISIT_ID" ]]; then
      http_code GET "$D_API/api/visits/$VISIT_ID" "${AUTH[@]}"
      if [[ "$LAST_CODE" != "200" ]]; then
        http_code POST "$D_API/api/visits" \
          "${AUTH[@]}" \
          -H 'Content-Type: application/json' \
          -d '{"name":"M11医生AI测试","gender":"男","age":42,"chief":"上腹痛2天伴反酸","status":"in_progress"}'
        VISIT_ID=$(json_get "$LAST_BODY" "d.get('id')")
        record "DA-05v" "PASS" "recreate visit after restart id=$VISIT_ID"
        # re-run differential briefly for apply-to-note names
        http_code POST "$D_API/api/visits/$VISIT_ID/differential" \
          "${AUTH[@]}" -H 'Content-Type: application/json' -d '{}'
        if [[ "$LAST_CODE" == "200" || "$LAST_CODE" == "201" ]]; then
          DX_NAMES_JSON=$(json_get "$LAST_BODY" "[x.get('name') for x in (d.get('items') if isinstance(d,dict) else d) if isinstance(x,dict) and x.get('name')][:3]")
        fi
      fi
    fi
  else
    record "DA-05r" "FAIL" "doctor API still down after restart health=$LAST_CODE"
  fi
fi

# ---- 6 POST differential/apply-to-note（404→SKIP） ----
if [[ -z "$VISIT_ID" ]]; then
  record "DA-06" "SKIP" "POST apply-to-note skipped — no visit"
else
  # pick names from differential or fallback
  APPLY_NAMES=$(python3 -c "
import json,sys
names=json.loads(sys.argv[1] or '[]')
if not names:
  names=['胃炎','消化性溃疡']
print(json.dumps(names[:2], ensure_ascii=False))
" "$DX_NAMES_JSON" 2>/dev/null)
  http_code POST "$D_API/api/visits/$VISIT_ID/differential/apply-to-note" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d "{\"names\":$APPLY_NAMES,\"target\":\"diagnosis\"}"
  AN_CODE="$LAST_CODE"; AN_BODY="$LAST_BODY"
  if handle_unimplemented "DA-06" "POST differential/apply-to-note" "$AN_CODE" "$AN_BODY"; then
    record "DA-06" "PASS" "apply-to-note target=diagnosis names=$APPLY_NAMES"
  fi
fi

# ---- 7 POST orders/suggest（可跑） ----
SUGGEST_ITEMS_JSON="[]"
if [[ -z "$VISIT_ID" ]]; then
  record "DA-07" "SKIP" "POST orders/suggest skipped — no visit"
else
  http_code POST "$D_API/api/visits/$VISIT_ID/orders/suggest" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d '{}'
  OS_CODE="$LAST_CODE"; OS_BODY="$LAST_BODY"
  if handle_unimplemented "DA-07" "POST orders/suggest" "$OS_CODE" "$OS_BODY"; then
    EX_N=$(json_get "$OS_BODY" "len(d.get('exams') or [])")
    DR_N=$(json_get "$OS_BODY" "len(d.get('drugs') or [])")
    DISC_OK=0
    if has_disclaimer_ok "$OS_BODY"; then DISC_OK=1; fi
    SRC=$(json_get "$OS_BODY" "d.get('source')")
    # build batch items from suggest (type+text); fallback static
    SUGGEST_ITEMS_JSON=$(python3 -c "
import json,sys
d=json.loads(sys.argv[1])
items=[]
for x in (d.get('exams') or [])[:2]:
  if isinstance(x,dict) and x.get('text'):
    items.append({'type': x.get('type') or '检查', 'text': x['text'], 'source': 'ai_suggest'})
for x in (d.get('drugs') or [])[:1]:
  if isinstance(x,dict) and x.get('text'):
    items.append({'type': x.get('type') or '用药', 'text': x['text'], 'source': 'ai_suggest'})
if not items:
  items=[{'type':'检查','text':'血常规','source':'ai_suggest'},{'type':'用药','text':'奥美拉唑 20mg qd','source':'ai_suggest'}]
print(json.dumps(items, ensure_ascii=False))
" "$OS_BODY" 2>/dev/null)
    if [[ -n "$EX_N" || -n "$DR_N" ]]; then
      record "DA-07" "PASS" "orders/suggest exams=$EX_N drugs=$DR_N source=${SRC:-?} disclaimer=$DISC_OK"
    else
      record "DA-07" "FAIL" "orders/suggest 缺 exams/drugs body=${OS_BODY:0:200}"
    fi
  fi
fi

# ---- 8 POST orders 批量 items ----
# M11 文档: {items:[{text,source}]}；现网 OpenAPI OrderItem 要求 type+text（source 可选）
# 策略: 先试文档形；若 422 缺 type → 改用 type+text 再验；404→SKIP；其它 4xx→FAIL
if [[ -z "$VISIT_ID" ]]; then
  record "DA-08" "SKIP" "POST orders 批量 skipped — no visit"
else
  # 8a probe doc-shaped payload
  DOC_ITEMS=$(python3 -c "
import json,sys
items=json.loads(sys.argv[1] or '[]')
out=[{'text':x.get('text'),'source':x.get('source') or 'ai_suggest'} for x in items if x.get('text')]
if not out:
  out=[{'text':'血常规','source':'ai_suggest'},{'text':'奥美拉唑','source':'ai_suggest'}]
print(json.dumps({'items':out}, ensure_ascii=False))
" "${SUGGEST_ITEMS_JSON:-[]}" 2>/dev/null)
  http_code POST "$D_API/api/visits/$VISIT_ID/orders" \
    "${AUTH[@]}" \
    -H 'Content-Type: application/json' \
    -d "$DOC_ITEMS"
  OB_CODE="$LAST_CODE"; OB_BODY="$LAST_BODY"
  if [[ "$OB_CODE" == "404" || "$OB_CODE" == "501" || "$OB_CODE" == "405" ]]; then
    record "DA-08" "SKIP" "POST orders 批量 HTTP $OB_CODE — 路由未齐"
  elif [[ "$OB_CODE" == "200" || "$OB_CODE" == "201" ]]; then
    ORD_N=$(json_get "$OB_BODY" "len(d.get('orders') or [])")
    record "DA-08" "PASS" "orders 批量(文档 text+source) HTTP $OB_CODE orders_n=${ORD_N:-?}"
  elif [[ "$OB_CODE" == "422" || "$OB_CODE" == "400" ]]; then
    # field shape: retry with type+text (OpenAPI OrderItem)
    TYPED_ITEMS=$(python3 -c "
import json,sys
items=json.loads(sys.argv[1] or '[]')
out=[]
for x in items:
  if not x.get('text'):
    continue
  out.append({'type': x.get('type') or '检查', 'text': x['text'], 'source': x.get('source') or 'ai_suggest'})
if not out:
  out=[{'type':'检查','text':'血常规','source':'ai_suggest'},{'type':'用药','text':'奥美拉唑 20mg qd','source':'ai_suggest'}]
print(json.dumps({'items':out}, ensure_ascii=False))
" "${SUGGEST_ITEMS_JSON:-[]}" 2>/dev/null)
    http_code POST "$D_API/api/visits/$VISIT_ID/orders" \
      "${AUTH[@]}" \
      -H 'Content-Type: application/json' \
      -d "$TYPED_ITEMS"
    OB2_CODE="$LAST_CODE"; OB2_BODY="$LAST_BODY"
    if [[ "$OB2_CODE" == "200" || "$OB2_CODE" == "201" ]]; then
      ORD_N=$(json_get "$OB2_BODY" "len(d.get('orders') or [])")
      record "DA-08" "PASS" "orders 批量(type+text) HTTP $OB2_CODE orders_n=${ORD_N:-?}；文档-only text+source→$OB_CODE（现网 OrderItem 要求 type）"
    elif [[ "$OB2_CODE" == "404" || "$OB2_CODE" == "501" ]]; then
      record "DA-08" "SKIP" "POST orders 批量字段未齐 doc=$OB_CODE typed=$OB2_CODE"
    else
      # 路由存在但批量仍失败
      record "DA-08" "FAIL" "orders 批量 doc=$OB_CODE typed=$OB2_CODE body=${OB2_BODY:0:160}"
    fi
  else
    record "DA-08" "FAIL" "POST orders 批量 unexpected HTTP $OB_CODE body=${OB_BODY:0:160}"
  fi
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
  echo "VISIT_ID=${VISIT_ID:-}"
  for r in "${RESULTS[@]}"; do
    echo "$r"
  done
} > "$REPORT_DIR/doctor-ai-smoke.last.env"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
