# M10 复跑汇总（chronic API 就绪后）

- **时间**：2026-10-09 15:18–15:19 CST
- **触发**：`/api/chronic/*` 已就绪（vitals / summary / patients / inbox 手测 200）

| 脚本 | pass | fail | skip | exit | 备注 |
|------|------|------|------|------|------|
| `chronic-smoke.sh` | **10** | 0 | **0** | 0 | 原 SKIP 全变 PASS；见 `CHRONIC_SMOKE_REPORT.md` |
| `smoke.sh` | **18** | 0 | 0 | 0 | 原 18 条未回归破坏；见 `SMOKE_REPORT.md` 顶部摘要 |
| `golden-path.sh` | **11** | 0 | **0** | 0 | reset 仍绿；见 `GOLDEN_PATH_REPORT.md` 顶部摘要 |

## 失败项

无。

## 复跑命令

```bash
bash /workspace/medical-e2e-smoke/chronic-smoke.sh
bash /workspace/medical-e2e-smoke/smoke.sh
bash /workspace/medical-e2e-smoke/golden-path.sh
```
