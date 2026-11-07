# M11 医生 AI 冒烟报告

- **时间**：2026-10-09 15:22:43 CST
- **脚本**：`/workspace/medical-e2e-smoke/doctor-ai-smoke.sh`
- **环境**：医生 API `http://127.0.0.1:8000` · 账号 `doctor` / `demo123`
- **汇总**：**pass=9 fail=0 skip=0** · exit **0**
- **约束**：未改动、未重跑 `smoke.sh` / `golden-path.sh` / `chronic-smoke.sh`

## 接口状态

| 接口 | HTTP | 结论 |
|------|------|------|
| `GET /health` | 200 | 就绪 |
| `POST /api/auth/login` | 200 | PASS · token_len=52 |
| `POST /api/visits` | 201 | PASS · `v103` |
| `GET /api/templates` | 200 | PASS · n=4 · first=`tpl-general` |
| `POST /api/visits/{id}/apply-template` | 200 | PASS · `tpl-general` |
| `POST /api/visits/{id}/differential` | 200 | PASS · n=5 · disclaimer OK |
| `POST /api/visits/{id}/differential/apply-to-note` | 200 | PASS · target=diagnosis |
| `POST /api/visits/{id}/orders/suggest` | 200 | PASS · exams=8 drugs=7 · source=llm |
| `POST /api/visits/{id}/orders` 批量 | 200 | PASS · orders_n=3（文档形 `{text,source}` 已通） |

## 各步结论

| ID | 结果 | 详情 |
|----|------|------|
| DA-00 就绪 | **PASS** | health doctor=200 |
| DA-01 登录 | **PASS** | token_len=52 |
| DA-02 visit | **PASS** | id=v103 · chief=上腹痛2天伴反酸 |
| DA-03 templates | **PASS** | n=4 · first_id=tpl-general |
| DA-04 apply-template | **PASS** | templateId=tpl-general |
| DA-05 differential | **PASS** | n=5 · names 含急性胃炎/GERD/溃疡 · disclaimer=1 |
| DA-06 apply-to-note | **PASS** | target=diagnosis · 勾选 2 项入病历 |
| DA-07 orders/suggest | **PASS** | exams=8 drugs=7 · source=llm · disclaimer=1 |
| DA-08 orders 批量 | **PASS** | 文档 text+source → 200 · orders_n=3 |

## 失败 / Skip 项

无。首轮探测时 templates / apply-template / apply-to-note 曾为 404；本轮服务重启后已齐，**skip=0**。

## 备注

- 脚本对未齐接口仍按 404/501/405 → **SKIP**；仅 `fail>0` 时 exit 非 0。
- `orders` 批量：若文档形 `{items:[{text,source}]}` 返回 422（缺 `type`），脚本会自动改用 OpenAPI `OrderItem`（`type+text`）再验。本轮文档形已直接 200。
- LLM 长调用后若 API 断连，脚本会尝试 `medical-start-all.sh` 恢复并重建 visit（DA-05r/DA-05v）。

## 复跑

```bash
bash /workspace/medical-e2e-smoke/doctor-ai-smoke.sh
```

产物：`doctor-ai-smoke.last.env` · `doctor-ai-smoke.last.log` · 本报告 · `TEST_CASES.md`（E2E-20 / DOCTOR-AI-*）
