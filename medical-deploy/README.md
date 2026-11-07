# 三分钟起演示 · AI 医疗智能助手（docker compose 四端一键）

> ✅ **已在 box 实机验收**（Docker 29.9.2 + Compose v5.7.0 + buildx v0.38.1，2026-11-03）：三服务 healthy，两个前端端口同源反代 200，compose 环境 5 套冒烟 56/56，见文末。
>
> **演示系统，非真实诊疗**：全部数据为演示/Mock，AI 输出不构成医疗建议，不替代执业医师面诊。

## 1. 前置条件
- Docker Engine 24+ 与 Compose v2（`docker compose version`）；或旧版 `docker-compose`（脚本自动识别）
- **buildx 插件**（`docker buildx version`）：Docker 官方 apt/rpm 包自带；用静态二进制安装时需另装到 `/usr/local/lib/docker/cli-plugins/docker-buildx`。缺 buildx 时 compose 会回退 classic builder（见 §4 说明）
- 宿主机空闲端口：8765、36967、8001、8000（可在 `.env` 改）
- 目录结构保持与 `/workspace` 相同（compose 用相对路径引用兄弟目录）：
  ```
  <root>/medical-deploy/            ← 本目录
  <root>/medical-patient-api/       ← 患者 API 源码（构建上下文）
  <root>/medical-assistant-api/     ← 医生 API 源码（构建上下文）
  <root>/medical-patient-triage/    ← 患者 UI
  <root>/medical-assistant-prototype/ ← 医生 UI
  <root>/medical-guardrails/        ← S2 AI 护栏包（两个 API 镜像的额外构建上下文）
  ```

## 2. 启动
```bash
cd medical-deploy
./deploy.sh up        # 首次自动 cp .env.example .env，构建并后台启动，等健康（最长约 120s）后打印地址
./deploy.sh reset     # 恢复演示种子（两端 POST /api/demo/reset，医生端自动登录拿 Bearer）
./deploy.sh logs [patient-api|doctor-api|web]
./deploy.sh ps
./deploy.sh down      # 停止；./deploy.sh down -v 连数据卷一起删
```
不用脚本：`cp .env.example .env && docker compose up -d --build`。

## 3. 访问地址
| 用途 | 地址 |
|---|---|
| 患者端 UI | http://127.0.0.1:8765/ |
| 医生端 UI | http://127.0.0.1:36967/ （账号 **doctor / demo123**） |
| 患者 API 文档 | http://127.0.0.1:8001/docs |
| 医生 API 文档 | http://127.0.0.1:8000/docs |

**浏览器只经过 web**：UI 镜像内 `config.js` 为 `window.APP_CONFIG = { patientApiBase: '/patient-api', doctorApiBase: '/doctor-api' }`，由 nginx 同源反代到 `patient-api:8001` / `doctor-api:8000`，无跨域。8001/8000 仍发布到宿主机，仅供冒烟脚本和 `/docs` 使用。

## 4. 服务组成
| 服务 | 镜像来源 | 说明 |
|---|---|---|
| `patient-api` | `patient-api/Dockerfile`，上下文 `../medical-patient-api` | python:3.12-slim，uid 10001 非 root，SQLite 在 volume `patient-data:/data` |
| `doctor-api` | `doctor-api/Dockerfile`，上下文 `../medical-assistant-api` | 同上，volume `doctor-data:/data`；`PATIENT_API_BASE=http://patient-api:8001`（服务名）；等 patient-api healthy 才起 |
| `web` | `web/Dockerfile`，上下文 `..`（即 /workspace） | nginx 非 root，8765 患者 UI / 36967 医生 UI + `/patient-api/`、`/doctor-api/` 反代；等两 API healthy 才起 |

- 两个 API 的健康检查用 python `urllib` 请求 `/health`（slim 镜像无 curl）。
- `.dockerignore` 放在两个 API 源码目录（排除 `.venv`、`data`、`__pycache__`、`*.db*`、`tests`、`.git`、`.env`），只影响 docker build，不影响本地运行。
- **web 目录由「产品 UI 原型」维护**（`web/Dockerfile`、`default.conf`、`*.inc`、`config/*.js`、`web/README.md`）。因 web 构建上下文是整个 `/workspace`，依赖 BuildKit 的按 Dockerfile 忽略文件 `web/Dockerfile.dockerignore`（白名单只放两个 UI 目录和 `medical-deploy/web`），避免把其他项目/venv/数据库打进上下文；Compose v2 在装有 buildx 时用 BuildKit。**未装 buildx（compose 打印 `buildx Docker CLI plugin not found: falling back to the classic builder`）或旧版 `docker-compose` v1 时不识别该文件**，整个 `/workspace` 都会作为上下文发送（box 实测 43MB vs 0.7MB），仍能构建，但请装 buildx。

### 4.1 AI 护栏包（S2）
- 两个 API 的 compose `build` 增加 `additional_contexts: { guardrails: ${GUARDRAILS_SRC:-../medical-guardrails} }`，Dockerfile 中 `COPY --from=guardrails . /opt/medical-guardrails` 后 **非 editable** `pip install /opt/medical-guardrails`（带上依赖 `jsonschema`），构建时打印 `guardrails 0.1.0` 自检。
- 选这个方案而不是把上下文改成 `..`：API 的构建上下文仍是各自源码目录，原有 `.dockerignore` 不变，护栏包作为独立的小上下文，不会把整个 `/workspace` 打进去，也不需要再维护一份按 Dockerfile 的忽略文件。
- **需要 BuildKit / Compose ≥ 2.17**（`additional_contexts` 与 `COPY --from=<上下文名>`）。classic builder 不支持（会把 `guardrails` 当镜像名去拉取而失败），请装 buildx（见 §1）。
- **护栏目录缺失**：`./deploy.sh up` 检测到 `../medical-guardrails/pyproject.toml` 不存在时会打印警告，并把 `GUARDRAILS_SRC` 指向空占位目录 `guardrails-missing/`。Dockerfile 发现没有 `pyproject.toml` 就跳过安装，镜像照常构建。API 内的适配层 `app/guardrails.py` 对导入失败或运行异常一律 **fail-open**（放行，不拦截），`/health` 返回 `guardrails.packageLoaded=false`。直接用 `docker compose` 且目录缺失时，需手动 `GUARDRAILS_SRC=./guardrails-missing docker compose up -d --build`。
- 开关：`GUARDRAILS_ENABLED=1`（默认，`.env` 可设 0 关闭）。命中统计：患者端 `GET /api/guardrails/stats`，医生端 `GET /api/ops/summary` 的 `guardrailHits`（两端合计 `{total, byCategory, byAction, bySide}`，来源为已脱敏的审计记录 `guardrail.redflag` / `guardrail.refuse`，不含原文）。
- 本机 venv 开发：`.venv/bin/pip install -r requirements-guardrails.txt`（内容为 `-e /workspace/medical-guardrails`）。

## 5. 配置（`.env`）
| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_API_KEY` | 空 | **空 = 规则 Mock，可完整演示**；填入则走 OpenAI 兼容真模型 |
| `LLM_BASE_URL` / `LLM_MODEL` | 空 / `gpt-5.6-sol` | BASE_URL 空则用代码默认值；模型默认 gpt-5.6-sol（API 与护栏二次判定共用）|
| `APP_ENV` | `demo` | 仅 `prod`/`production` 视为生产（禁止演示重置）；`demo` 等同 dev |
| `MASK_SENSITIVE` | `1` | 强制脱敏 |
| `STORE_BACKEND` | `sqlite` | `memory` 则重启清空 |
| `ALLOW_RESET_IN_PROD` | 空 | `APP_ENV=prod` 时允许 `/api/demo/reset` |
| `GUARDRAILS_ENABLED` | `1` | AI 护栏开关；包缺失/异常时自动 fail-open |
| `GUARDRAILS_LLM` | 不设 | 护栏 LLM 二次判定（包 0.2.0+；不设且有 `LLM_API_KEY` 时开启）；冒烟/回归设 `0` 保证结果稳定 |
| `GUARDRAILS_SRC` | `../medical-guardrails` | 护栏包构建上下文目录（缺失时 deploy.sh 自动换成 `guardrails-missing/`） |
| `CORS_ORIGIN_REGEX` | 空 | **可选**。空 = 仅 localhost/127.0.0.1；只有浏览器绕过 web 直连 8001/8000 时才需要 |
| `PATIENT_API_PORT` / `DOCTOR_API_PORT` / `PATIENT_UI_PORT` / `DOCTOR_UI_PORT` | 8001/8000/8765/36967 | 宿主机端口 |

密钥只经 `.env` → compose 插值 → API 容器运行时环境变量；不写入镜像，web 容器拿不到，`deploy.sh` 不打印。`.env` 勿提交。`SQLITE_PATH` 在 compose 中固定为 `/data/app.db`。

## 6. 数据持久化与重置
- 两端 SQLite 分别在命名卷 `medical-demo_patient-data` / `medical-demo_doctor-data`；`docker compose restart` / `down` 后再 `up` 数据仍在。
- 恢复演示态：`./deploy.sh reset`（seedVersion `m9-golden-1`）。
- 彻底清空：`./deploy.sh down -v`（或 `docker compose down -v`），下次启动自动重新种子。

## 7. 冒烟脚本指向 compose
`/workspace/medical-e2e-smoke/*.sh` 读取的是 `P_API` / `D_API` / `P_UI` / `D_UI`（不是 `PATIENT_API_BASE` / `DOCTOR_API_BASE`），默认值已是 127.0.0.1 的 8001/8000/8765/36967，端口未改时可直接跑。健康失败时脚本会调用 `START_ALL`（本机 venv 启动脚本），compose 环境下建议禁用：
```bash
START_ALL=/bin/true P_API=http://127.0.0.1:8001 D_API=http://127.0.0.1:8000 \
P_UI=http://127.0.0.1:8765 D_UI=http://127.0.0.1:36967 bash ../medical-e2e-smoke/smoke.sh
# 同理：golden-path.sh  chronic-smoke.sh  doctor-ai-smoke.sh  ops-smoke.sh
```
注意：compose 与本机 `medical-start-all.sh` 使用相同端口，**不要同时运行**（或改 `.env` 端口）。

## 8. 局域网 / 远程访问
UI 走同源反代，其他机器直接打开 `http://<宿主机IP>:8765/`、`:36967/` 即可，无需改 CORS。只有从别的主机在浏览器里直连 8001/8000 时才设 `CORS_ORIGIN_REGEX`，例如：
`CORS_ORIGIN_REGEX=https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?`。不提供 HTTPS，勿暴露公网。

## 9. 常见问题
- **端口被占用**：改 `.env` 中 `*_PORT`，或先停本机 `medical-start-all.sh` 起的进程。
- **health 一直不过**：`./deploy.sh logs doctor-api`；doctor-api 依赖 patient-api healthy，先看 patient-api。`docker compose ps` 看 `health` 列。
- **UI 能开但接口报错**：确认 web 日志里反代到 `patient-api:8001` / `doctor-api:8000` 成功；浏览器强刷（Service Worker 缓存旧 `config.js`）。
- **反代 504 / web 日志 `upstream timed out ... while connecting to upstream`**（容器之间互不通、宿主机直连 8001/8000 却正常）：宿主机防火墙拦了网桥转发。常见于同时存在 iptables-legacy 与 iptables-nft、legacy 表 `FORWARD` 策略为 DROP（`sudo iptables-legacy -S FORWARD` 可见 `-P FORWARD DROP`）。处理：`sudo iptables-legacy -P FORWARD ACCEPT`（nft 侧 Docker 规则仍生效），或在 DOCKER-USER 放行 `br-+` 网桥。
- **想重来**：`./deploy.sh down -v && ./deploy.sh up`。
- **配了 Key 不生效**：改 `.env` 后需 `docker compose up -d`（重建容器）；`/health` 返回 `llmConfigured:true` 即生效。

## 10. 验证记录（box，2026-11-03 实机）
- 环境：Debian 13，无 systemd；Docker 29.9.2 静态二进制（download.docker.com/linux/static）+ Compose 插件 v5.7.0 + buildx v0.38.1；dockerd 手动后台启动（`dockerd --group docker`，日志 /var/log/dockerd.log）。
- `docker compose config` 通过；`nginx -t`（web 镜像内）通过；`./deploy.sh up` 约 12s 完成，patient-api / doctor-api / web 均 healthy。
- 8765、36967 两个端口上 `/patient-api/health`、`/doctor-api/health`、`/`、`/config.js` 均 200；doctor-api 容器内经服务名访问 `patient-api:8001/health` 200；`./deploy.sh reset` 两端 ok（seed `m9-golden-1`）。
- 冒烟（START_ALL=/bin/true，先 reset）：smoke 18/18、golden-path 11/11、chronic-smoke 10/10、doctor-ai-smoke 9/9、ops-smoke 8/8，合计 **56/56**。
- 两端 OpenAPI 全部无参 GET（直连 + 经反代，共 152 次）响应体无 127.0.0.1/localhost 绝对链接；上游 3xx Location 经 `proxy_redirect` 改写为同源 `/patient-api/…`、`/doctor-api/…`。
- 镜像体积（docker images，磁盘/压缩内容）：patient-api 269MB/59.7MB，doctor-api 271MB/60.1MB，web 75.7MB/21.3MB。
- 已知限制：经反代访问 `/patient-api/docs` 时 Swagger 仍请求根路径 `/openapi.json`（未设 root_path），API 文档请直接用 8001/8000 的 `/docs`。

## 11. S2 护栏改动验证状态（2026-11-03）
- `docker compose config` 通过（含 `additional_contexts`，以及 `GUARDRAILS_SRC=./guardrails-missing` 的占位分支）；`deploy.sh` 通过 `bash -n`。
- **镜像未重建验证**：当前会话用户无 `/var/run/docker.sock` 权限（permission denied），没有执行 `./deploy.sh up`。有权限的环境请执行 `./deploy.sh up`，然后确认两端 `/health` 中 `guardrails.packageLoaded=true`、`version=0.1.0`。
- 本机 venv 进程已验证：护栏生效，5 套冒烟见 S2 报告。


## GitHub 文本导入说明

首次拉取后请设置脚本执行权限（上传接口不保证执行位）：

```bash
# 在仓库根目录执行
chmod +x medical-start-all.sh medical-deploy/deploy.sh medical-e2e-smoke/*.sh
```

本次源码导入范围、安全排除、S2 结果与已知限制见根目录 `IMPORT-NOTES.md`。根 main 分支原有 README 未改动。
