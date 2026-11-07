# AI 医疗双端：S1 / S2 源码导入

这是演示项目，非真实诊疗系统；请勿用于真实患者医疗决策。保留 main 原有 README。

## 目录
- `medical-patient-api/`：患者 API（8001）
- `medical-assistant-api/`：医生 API（8000）
- `medical-patient-triage/`：患者前端（8765）
- `medical-assistant-prototype/`：医生前端（36967）
- `medical-deploy/`：Compose、Dockerfile、nginx 同源反代
- `medical-guardrails/`：护栏包 0.2.0
- `medical-e2e-smoke/`：六组冒烟及测试说明
- `medical-patient-triage-docs/`：需求及演示流程
- `medical-start-all.sh`：原 box 本机启动脚本，ROOT 固定为 /workspace；其他路径请调整 ROOT。Compose 不依赖此脚本。

## Compose 运行
需要 Docker Engine、Compose >=2.17 和 BuildKit。构建上下文均为相对路径，保留本仓库目录布局。

上传接口不保证 shell 可执行位，首次拉取后运行：

```bash
chmod +x medical-start-all.sh medical-deploy/deploy.sh medical-e2e-smoke/*.sh
cd medical-deploy
cp .env.example .env
# 在当前 shell 安全注入 LLM_API_KEY；不要提交真实密钥，也不要写入源码/镜像。
./deploy.sh up
./deploy.sh ps
./deploy.sh reset
```

患者 UI http://localhost:8765，医生 UI http://localhost:36967。
`LLM_API_KEY` 仅在运行时通过环境变量传入 API；默认模型 `gpt-5.6-sol`，上游不可用时允许 Mock。

## 冒烟
先在 medical-deploy 执行 reset，再在仓库根目录执行：

```bash
cd medical-e2e-smoke
for script in smoke.sh golden-path.sh chronic-smoke.sh doctor-ai-smoke.sh ops-smoke.sh guardrail-smoke.sh; do
  START_ALL=/bin/true P_API=http://127.0.0.1:8001 D_API=http://127.0.0.1:8000 P_UI=http://127.0.0.1:8765 D_UI=http://127.0.0.1:36967 bash "$script"
done
```

此前 S2 box 验收：三服务 healthy、护栏 0.2.0 `packageLoaded=true`、69/69；胸口剧痛 redflag，心情很差睡不着 caution。此次导入未重新执行部署/冒烟。

## 排除与限制
- 不含 .env、密钥、虚拟环境、依赖缓存、数据库、运行数据、日志、.last.env、备份和构建产物。
- 保守排除含 sk 风格测试凭据的两个护栏测试文件（test_r2.py、test_llm_judge_r4.py）及含非空 API key 示例的 medical-assistant-api/README.md；剩余测试不等同完整原测试集。
- 文本上传接口未包含患者 PWA 的三个 PNG 图标，manifest 引用仍保留，图标请求可能 404；不影响 API / HTML 主流程。
- box 特有：dockerd 手动启动、iptables FORWARD 规则非持久化，重启需重新配置，不代表其他主机必需操作。
- 反代 /docs 的 openapi.json 根路径问题仍待处理。
- 演示账号及 token 验证简化逻辑仅供本机演示，公开部署前必须加固认证、访问控制与敏感信息处理。
- 收尾使用 `cd medical-deploy && ./deploy.sh down` 保留命名卷；不要误用会删除卷的命令。
