> **复跑摘要（M10 chronic API 就绪后 · 2026-10-09 15:19:04 CST）**：`smoke.sh` → **pass=18 fail=0 skip=0** · exit **0**。同步 `chronic-smoke` pass=10 skip=0、`golden-path` pass=11 skip=0；详见 `RERUN_M10.md` / `CHRONIC_SMOKE_REPORT.md`。

> **复跑摘要（M9 reset 就绪后 · 2026-10-09 15:12:35 CST）**：`smoke.sh` → **pass=18 fail=0 skip=0** · exit **0**（E2E-00..17 全绿）。同步黄金路径复跑见 `GOLDEN_PATH_REPORT.md`（pass=11 fail=0 skip=0）。

# AI 医疗双端 · 总冒烟收口报告

- **时间**：2026-10-09 10:11:27 CST（以第二次全绿复跑为准）
- **环境**：患者 API `127.0.0.1:8001` · 医生 API `127.0.0.1:8000` · 患者 UI `:8765` · 医生 UI `:36967`
- **账号**：医生 `doctor` / `demo123`；`PATIENT_API_BASE=http://127.0.0.1:8001`
- **脚本**：`bash /workspace/medical-e2e-smoke/smoke.sh`
- **用例**：`/workspace/medical-e2e-smoke/TEST_CASES.md`
- **汇总**：**pass=18 fail=0 skip=0**（exit 0）
- **服务启动**：本轮四端 health/UI 均已 200，**未调用** `medical-start-all.sh`（优先复用在跑进程）

## 模块结论（需求 1–13）

| # | 模块 | 结论 | 关键证据 |
|---|------|------|----------|
| 1 | 导诊 `/api/triage/recommend` | **PASS** | HTTP 200，`source=llm`，departments + disclaimer 语义 OK |
| 2 | 问诊 sessions → messages | **PASS** | 新建 `sess-*`，非流式 messages 200，`source=llm`；不存在会话 → 404（E2E-15） |
| 3 | 预约 departments→doctors→slots→appointments | **PASS** | 例：`dept-gi` / `doc-gi-1` / `slot-1` → `appt-*`；GET list/detail 200 |
| 4 | 预问诊报告 | **PASS** | `POST /api/previsit/report` 200，`source=llm`，disclaimer 含「仅供…参考 / 不能替代」；列表 `/api/reports/preconsult` 200 |
| 5 | 报告解读 | **PASS** | GET `/api/reports`（如 `lab-1`）；`POST /api/reports/interpret` 200，`source=llm`，强 disclaimer OK |
| 6 | 候诊/消息/导航 | **PASS** | waiting n=2；messages n=4；navigation departments n=11 |
| 7 | 续方/用药/随访 | **PASS** | refills / medications/today / followups/surveys 均 200；POST refill 200 |
| 8 | 缴费/身份 | **PASS** | unpaid bill pay → `paid`；identity GET 仅脱敏；PUT 后响应/再 GET **无明文身份证** |
| 9 | 医生接诊 M5 | **PASS** | `doctor-consult` create → `accept`（`X-Role: doctor`）→ message → end=`ended`（例 `cons-*`） |
| 10 | 检查预约 M6 | **PASS** | `exam-cbc` + slot → book `leb-*` → detail 200 → cancel 200 |
| 11 | 药品配送 M7 | **PASS** | orders / addresses / deliveries 抽查 200（例 delivery `del-*`） |
| 12 | 医生预问诊代理 | **PASS** | login 200；`/api/preconsult/reports` 200；`/api/workbench/summary` 200 且 `patientApiOk=True`；visits 200 |
| 13 | 静态前端 | **PASS** | `8765/`=200，`36967/`=200 |

## P1 抽查

| ID | 项 | 结论 |
|----|----|------|
| E2E-14 | 导诊极短 chief | PASS（HTTP 200 降级/接受，已记录） |
| E2E-15 | 问诊不存在 session | PASS → 404 |
| E2E-16 | 医生未认证 visits/preconsult | PASS → 401 |
| E2E-17 | 身份脱敏 | PASS（无明文 idNumber） |

## UI 抽查

- 患者端 `http://127.0.0.1:8765/` → **200**
- 医生端 `http://127.0.0.1:36967/` → **200**

## 医生代理

- `patientApiOk=True`（workbench/summary）
- 预问诊代理 `/api/preconsult/reports` 在 Bearer token 下 **200**（未认证 **401**）

## AI / 免责

- 本轮抽查 AI 路径（导诊/问诊/预问诊/报告解读）`source` 均为 **llm**
- disclaimer 语义抽查通过（「仅供…参考」「不能替代/不构成诊断」等）；**未打印** `LLM_API_KEY`

## 失败项

无。

## 复现 / 复跑

```bash
# 健康检查失败时才会拉起：
# bash /workspace/medical-start-all.sh

bash /workspace/medical-e2e-smoke/smoke.sh
# 期望：SUMMARY pass=18 fail=0；exit 0
```

## 交付路径

| 文件 | 路径 |
|------|------|
| 用例表 | `/workspace/medical-e2e-smoke/TEST_CASES.md` |
| 可跑脚本 | `/workspace/medical-e2e-smoke/smoke.sh` |
| 本报告 | `/workspace/medical-e2e-smoke/SMOKE_REPORT.md` |
| 最近一次机读结果 | `/workspace/medical-e2e-smoke/smoke.last.env` |
| 最近一次日志 | `/workspace/medical-e2e-smoke/smoke.last.log` |
