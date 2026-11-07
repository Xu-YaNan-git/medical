# M12 复跑汇总（ops API 就绪后）

- 时间：2026-10-09 15:27:34 CST
- 触发：`GET /api/ops/summary` 已就绪（200，含 appointmentsToday…patientApiOk=true）

| 脚本 | pass | fail | skip | exit | 备注 |
|------|------|------|------|------|------|
| `ops-smoke.sh` | 8 | 0 | 0 | 0 | summary 原 SKIP→PASS；字段断言未改 |
| `smoke.sh` | 18 | 0 | 0 | 0 | 总冒烟回归 |
| `golden-path.sh` | 11 | 0 | 0 | 0 | M9 黄金路径；seed=m9-golden-1 |
| `chronic-smoke.sh` | 10 | 0 | 0 | 0 | M10 慢病 |
| `doctor-ai-smoke.sh` | 9 | 0 | 0 | 0 | M11 医生 AI |

**合计 pass=56 fail=0 skip=0。失败项：无。**

## 复跑命令
```bash
bash /workspace/medical-e2e-smoke/ops-smoke.sh
bash /workspace/medical-e2e-smoke/smoke.sh
bash /workspace/medical-e2e-smoke/golden-path.sh
bash /workspace/medical-e2e-smoke/chronic-smoke.sh
bash /workspace/medical-e2e-smoke/doctor-ai-smoke.sh
```

报告：`OPS_SMOKE_REPORT.md`（本复跑已覆盖）、`RERUN_M12.md`（本文件）。
