# medical-deploy/web · 静态 UI + 反代（nginx）

一个镜像同时提供两个前端：

| 端口 | 内容 | 根目录 |
|---|---|---|
| 8765 | 患者端 `medical-patient-triage` | `/usr/share/nginx/html/patient` |
| 36967 | 医生端 `medical-assistant-prototype` | `/usr/share/nginx/html/doctor` |

两个 server 都带同源反代（浏览器只访问 web，不直连 API）：

- `/patient-api/*` → `http://patient-api:8001/*`
- `/doctor-api/*` → `http://doctor-api:8000/*`

例：`/patient-api/api/demo/reset` → `patient-api:8001/api/demo/reset`；`/doctor-api/health` → `doctor-api:8000/health`。

## 文件

- `Dockerfile` — 基于 `nginxinc/nginx-unprivileged:1.27-alpine`（非 root，UID 101），**构建上下文为 `/workspace`**
- `Dockerfile.dockerignore` — BuildKit 按 Dockerfile 名读取；白名单只放两个 UI 目录和本目录，并排除 `.venv`、`__pycache__`、`node_modules`、`data`、`*.db`
- `default.conf` — 两个 server，SPA 回退 `try_files $uri $uri/ /index.html`；`sw.js`、`config.js` 返回 `Cache-Control: no-cache`
- `api-proxy.inc` / `proxy-common.inc` — 反代 location 与公共头（`proxy_buffering off`、读超时 300s，对 SSE/流式友好；`client_max_body_size 20m`）
- `config/patient-config.js`、`config/doctor-config.js` — 构建时覆盖各 UI 的 `config.js`：
  ```js
  window.APP_CONFIG = { patientApiBase: '/patient-api', doctorApiBase: '/doctor-api' };
  ```

### 为什么用 `resolver 127.0.0.11` + 变量

`proxy_pass` 用变量时 nginx 在请求时才解析，API 容器还没起时 nginx 也能启动（不会出现 `host not found in upstream`）。用变量后 proxy_pass 不再自动替换 URI 前缀，所以用 `rewrite ^/patient-api/(.*)$ /$1 break;` 去掉前缀（查询串会自动保留）。

## compose 片段（compose 文件位于 `/workspace/medical-deploy/`）

```yaml
web:
  build: { context: .., dockerfile: medical-deploy/web/Dockerfile }
  ports: ["8765:8765", "36967:36967"]
  depends_on:
    patient-api: { condition: service_healthy }
    doctor-api: { condition: service_healthy }
```

服务名必须是 `patient-api` / `doctor-api`（nginx 反代写死这两个名字）。

## 改 API 地址而不重建

挂载覆盖即可（`config.js` 是 no-cache，SW 网络优先，刷新即生效）：

```yaml
  volumes:
    - ./my-patient-config.js:/usr/share/nginx/html/patient/config.js:ro
    - ./my-doctor-config.js:/usr/share/nginx/html/doctor/config.js:ro
```

## 本地开发（不用 Docker）

不变：两个 UI 目录自带的 `config.js` 默认 `http://127.0.0.1:8001` / `http://127.0.0.1:8000`，用 `python3 -m http.server 8765` / `36967` 起即可。

## 手动构建 / 校验

```bash
cd /workspace
docker build -f medical-deploy/web/Dockerfile -t medical-web .
docker run --rm medical-web nginx -t
```
