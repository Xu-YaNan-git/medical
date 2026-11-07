#!/usr/bin/env bash
# AI 医疗智能助手 · 演示一键脚本
# 用法: ./deploy.sh up | down | reset | logs [service] | ps
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# 读取 .env 中的端口（不导出、不打印任何密钥）
env_get() {
  local key="$1" def="$2" val=""
  if [[ -f .env ]]; then
    val="$(grep -E "^${key}=" .env | tail -n1 | cut -d= -f2- | tr -d '"'"'"'\r' || true)"
  fi
  printf '%s' "${val:-$def}"
}

PATIENT_API_PORT="$(env_get PATIENT_API_PORT 8001)"
DOCTOR_API_PORT="$(env_get DOCTOR_API_PORT 8000)"
PATIENT_UI_PORT="$(env_get PATIENT_UI_PORT 8765)"
DOCTOR_UI_PORT="$(env_get DOCTOR_UI_PORT 36967)"
PATIENT="http://127.0.0.1:${PATIENT_API_PORT}"
DOCTOR="http://127.0.0.1:${DOCTOR_API_PORT}"

die() { echo "错误: $*" >&2; exit 1; }

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    die "未找到 docker compose / docker-compose，请先安装 Docker Desktop 或 Docker Engine + Compose 插件"
  fi
}

require_docker() {
  command -v docker >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 \
    || die "未找到 docker，请先安装 Docker（https://docs.docker.com/get-docker/）"
}

require_curl() {
  command -v curl >/dev/null 2>&1 || die "需要 curl"
}

# 从 JSON 取字段（python3 优先，退化为 sed）；不依赖 jq
json_field() {
  local field="$1" body="$2"
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$body" | python3 -c "import json,sys
try:
    v=json.load(sys.stdin).get(sys.argv[1], '')
except Exception:
    v=''
print('' if v is None else (str(v).lower() if isinstance(v,bool) else v))" "$field"
  else
    printf '%s' "$body" | sed -n "s/.*\"${field}\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\).*/\1/p" | head -n1
  fi
}

wait_health() {
  local name="$1" url="$2" timeout="${3:-120}" i=0
  printf '等待 %s 健康 (%s) ' "$name" "$url"
  until curl -fsS -o /dev/null --max-time 3 "$url"; do
    i=$((i + 2))
    if (( i >= timeout )); then
      echo " 超时"
      return 1
    fi
    printf '.'
    sleep 2
  done
  echo " OK"
}

# S2：护栏包目录缺失时换成空占位上下文，构建不失败，API 内适配层 fail-open
ensure_guardrails_ctx() {
  if [[ -n "${GUARDRAILS_SRC:-}" ]]; then
    [[ -d "$GUARDRAILS_SRC" ]] || die "GUARDRAILS_SRC=$GUARDRAILS_SRC 不存在"
    return 0
  fi
  if [[ ! -f ../medical-guardrails/pyproject.toml ]]; then
    echo "警告: 未找到 ../medical-guardrails，镜像将不含护栏包（fail-open，不拦截）" >&2
    export GUARDRAILS_SRC=./guardrails-missing
  fi
}

cmd_up() {
  require_docker
  require_curl
  ensure_guardrails_ctx
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "已从 .env.example 生成 .env（LLM_API_KEY 为空 → Mock 模式）"
  fi
  compose up -d --build
  local ok=1
  wait_health "患者 API" "${PATIENT}/health" 120 || ok=0
  wait_health "医生 API" "${DOCTOR}/health" 120 || ok=0
  wait_health "患者 UI" "http://127.0.0.1:${PATIENT_UI_PORT}/" 60 || ok=0
  wait_health "医生 UI" "http://127.0.0.1:${DOCTOR_UI_PORT}/" 60 || ok=0
  echo
  echo "患者端 UI : http://127.0.0.1:${PATIENT_UI_PORT}/"
  echo "医生端 UI : http://127.0.0.1:${DOCTOR_UI_PORT}/   演示账号 doctor / demo123"
  echo "患者 API  : ${PATIENT}/docs"
  echo "医生 API  : ${DOCTOR}/docs"
  echo "演示系统，非真实诊疗。"
  if (( ok == 0 )); then
    echo "部分服务未就绪，查看: ./deploy.sh ps / ./deploy.sh logs" >&2
    exit 1
  fi
}

cmd_down() {
  require_docker
  compose down "$@"
}

cmd_reset() {
  require_curl
  local body token
  echo "重置患者端演示数据 ..."
  body="$(curl -fsS -X POST "${PATIENT}/api/demo/reset")" || die "患者端重置失败（服务未起或 APP_ENV=prod 被拒）"
  echo "  患者端 ok=$(json_field ok "$body") seedVersion=$(json_field seedVersion "$body")"

  echo "登录医生账号 ..."
  body="$(curl -fsS -X POST "${DOCTOR}/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"username":"doctor","password":"demo123"}')" || die "医生登录失败"
  token="$(json_field token "$body")"
  [[ -n "$token" ]] || die "未从登录响应解析到 token"

  echo "重置医生端演示数据 ..."
  body="$(curl -fsS -X POST "${DOCTOR}/api/demo/reset" -H "Authorization: Bearer ${token}")" \
    || die "医生端重置失败（APP_ENV=prod 时需 ALLOW_RESET_IN_PROD=1）"
  echo "  医生端 ok=$(json_field ok "$body") seedVersion=$(json_field seedVersion "$body")"
}

cmd_logs() {
  require_docker
  compose logs -f --tail=200 "$@"
}

cmd_ps() {
  require_docker
  compose ps
}

usage() {
  cat <<USAGE
用法: $0 <命令>
  up            构建并后台启动四端，等待健康后打印访问地址
  down [-v]     停止并移除容器（加 -v 同时删除 SQLite 数据卷）
  reset         调用两端 POST /api/demo/reset 恢复演示种子
  logs [服务]   跟随日志（patient-api | doctor-api | web）
  ps|status     查看容器状态
USAGE
}

case "${1:-}" in
  up) shift; cmd_up "$@" ;;
  down) shift; cmd_down "$@" ;;
  reset) shift; cmd_reset "$@" ;;
  logs) shift; cmd_logs "$@" ;;
  ps|status) shift; cmd_ps "$@" ;;
  -h|--help|help|"") usage ;;
  *) usage; exit 1 ;;
esac
