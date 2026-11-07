# syntax=docker/dockerfile:1
# 医生端诊疗辅助 API（medical-assistant-api） —— 构建上下文为源码目录（见 docker-compose.yml: context）
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# S2 护栏包：来自 compose additional_contexts「guardrails」（默认 ../medical-guardrails），
# 非 editable 安装到 site-packages（连同依赖 jsonschema）。目录缺失时 deploy.sh 会换成
# 空占位目录 guardrails-missing/，此处跳过安装，API 内的适配层 fail-open（/health 中
# guardrails.packageLoaded=false），服务照常可用但不做护栏拦截。
COPY --from=guardrails . /opt/medical-guardrails
RUN if [ -f /opt/medical-guardrails/pyproject.toml ]; then \
      pip install /opt/medical-guardrails \
      && python -c "import guardrails, jsonschema, importlib.metadata as m; d = m.packages_distributions().get('guardrails'); assert d == ['medical-guardrails'], d; print('guardrails', guardrails.__version__, d)"; \
    else \
      echo "WARN: medical-guardrails 未提供，护栏 fail-open（不拦截）" >&2; \
    fi \
 && if pip show guardrails-ai >/dev/null 2>&1; then echo "ERROR: PyPI guardrails-ai 与本地 guardrails 包重名" >&2; exit 1; fi \
 && rm -rf /opt/medical-guardrails/build /opt/medical-guardrails/*.egg-info

COPY app/ ./app/

# 非 root 运行；SQLite 落在 /data（compose 挂命名 volume）
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app \
 && mkdir -p /data \
 && chown -R app:app /data

# 注意：LLM_API_KEY 等密钥只通过运行时环境变量注入，镜像内不写入
ENV STORE_BACKEND=sqlite \
    SQLITE_PATH=/data/app.db \
    APP_ENV=demo \
    MASK_SENSITIVE=1

VOLUME ["/data"]
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
