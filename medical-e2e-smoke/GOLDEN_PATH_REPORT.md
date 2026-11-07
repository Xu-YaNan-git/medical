> **复跑摘要（M10 chronic API 就绪后 · 2026-10-09 15:19:22 CST）**：`golden-path.sh` → **pass=11 fail=0 skip=0** · exit **0**（reset 仍绿）。同步 `chronic-smoke` 10/0/0、`smoke` 18/0/0；详见 `RERUN_M10.md`。

# M9 黄金路径冒烟报告（reset 就绪后复跑）

- **时间**：2026-10-09 15:12:14 CST
- **标注**：demo/reset 就绪后复跑（相对首轮 skip=2）
- **脚本**：`/workspace/medical-e2e-smoke/golden-path.sh`
- **环境**：患者 API `8001` · 医生 API `8000` · UI `8765` / `36967`
- **汇总**：**pass=11 fail=0 skip=0** · exit **0**

## Reset 状态

| 步骤 | 结果 | 说明 |
|------|------|------|
| 患者 `POST 8001/api/demo/reset` | **PASS** | HTTP **200** · `seedVersion=m9-golden-1` |
| 医生 `POST 8000/api/demo/reset`（Bearer） | **PASS** | HTTP **200** · `seedVersion=m9-golden-1` |

首轮因 404 为 SKIP；本轮两端 reset 均已 PASS，**skip=0**。

## 路径节点

| ID | 结果 | 详情 |
|----|------|------|
| GP-00 就绪 | PASS | health patient=200 doctor=200 |
| GP-01a patient reset | PASS | HTTP 200 seed=m9-golden-1 |
| GP-01b doctor login | PASS | token_len=52 |
| GP-01c doctor reset | PASS | HTTP 200 seed=m9-golden-1 |
| GP-02 导诊 | PASS | source=llm · departments_ok · disclaimer_ok |
| GP-03 预约 | PASS | dept-gi / doc-gi-1 / slot-1 → appt-3 |
| GP-04 预问诊 | PASS | previsit/report source=llm |
| GP-05 图文接诊 | PASS | cons-3 create→accept(in_progress)→message |
| GP-06 医生预问诊代理 | PASS | preconsult=200 workbench=200 patientApiOk=True |
| GP-07 随访/消息 | PASS | surveys n=2 · messages n=4 unread=3 |
| GP-08 双端 UI | PASS | 8765/36967 → 200 |

## 失败项

无。

## 顺带回归：原 smoke.sh

- **时间**：2026-10-09 15:12:35 CST
- **汇总**：**pass=18 fail=0 skip=0** · exit **0**（E2E-00..17 与原先一致）

## 交付物

- 脚本：`/workspace/medical-e2e-smoke/golden-path.sh`（逻辑未改）
- 用例：`/workspace/medical-e2e-smoke/TEST_CASES.md`（E2E-18）
- 本报告：`/workspace/medical-e2e-smoke/GOLDEN_PATH_REPORT.md`
- 机器可读：`/workspace/medical-e2e-smoke/golden-path.last.env`
- 原冒烟报告：`/workspace/medical-e2e-smoke/SMOKE_REPORT.md`（顶部已加复跑摘要）

## 复跑

```bash
bash /workspace/medical-e2e-smoke/golden-path.sh
bash /workspace/medical-e2e-smoke/smoke.sh
```

## 备注

- AI 本轮 `source=llm`（导诊/预问诊）
- 脚本未改约定逻辑；reset 200 后 GP-01a/01c 自然由 SKIP → PASS
