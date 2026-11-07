# 步骤 1｜部署打包（docker-compose 四端一键）

## 背景
M1–M12 演示功能已齐，但只能在当前机器靠 `medical-start-all.sh` 起；环境一丢（如 venv 丢失）就起不来，换机器演示成本高。

## 目标
任意一台装了 Docker 的机器，`docker compose up -d` 一条命令起齐四端，带演示种子，可直接演示。

## 需求
### P0
1. **镜像**
   - 患者 API（8001）、医生 API（8000）各一个 Dockerfile（python:3.12-slim 或同级，非 root 运行）
   - 两个静态 UI 合进一个 nginx 镜像（8765 / 36967 两个 server，或同端口不同路径——以前端不改代码为准）
2. **compose**：`/workspace/medical-deploy/docker-compose.yml`
   - 服务：patient-api、doctor-api、web（nginx）
   - 医生 API 通过服务名访问患者 API（`PATIENT_API_BASE=http://patient-api:8001`）
   - SQLite 数据挂 volume，重启不丢
   - healthcheck：两个 API `/health`
   - 前端访问 API 的地址可配（浏览器侧要能打到 8001/8000；若前端写死 127.0.0.1，提供 nginx 反代 `/patient-api/`、`/doctor-api/` 或注入 config.js）
3. **配置**：`.env.example`
   - `LLM_API_KEY`（可空，空则 Mock）、`LLM_BASE_URL`、`LLM_MODEL`
   - `APP_ENV`（默认 demo）、`MASK_SENSITIVE=1`、`STORE_BACKEND=sqlite`
   - Key 只走环境变量，不进镜像、不进日志
4. **一键脚本**：`deploy.sh up|down|reset|logs`
   - `reset` 调两端 `POST /api/demo/reset`
5. **README**：一页「三分钟起演示」——前置条件、命令、访问地址、演示账号、常见问题

### P1
6. 冒烟脚本支持指向 compose 环境（`PATIENT_API_BASE` / `DOCTOR_API_BASE` 环境变量），在 compose 里跑通 5 套冒烟
7. 镜像体积尽量小；`.dockerignore` 排除 .venv、data、__pycache__

## 非目标
K8s / Helm、HTTPS 证书、公网域名、CI/CD 流水线、多副本。

## 成功指标
- 新机器 `docker compose up -d` 后 2 分钟内四端可用
- compose 环境下 5 套冒烟合计 56/56
- 不配 Key 也能完整演示（Mock）

## 待确认
- 本机（box）是否有 Docker；没有则先交付文件 + 本地语法校验（`docker compose config` 不可用时用 yamllint），在有 Docker 的机器上验收
- 前端访问 API 的方式（反代 vs config.js）由 UI 和 Python 对齐后定

## 分工
- 后端 Python：两个 API Dockerfile、compose、.env.example、deploy.sh、README
- 产品 UI 原型：前端 API 地址可配置（若需），nginx 配置
- 测试：冒烟脚本参数化 + compose 环境验收
