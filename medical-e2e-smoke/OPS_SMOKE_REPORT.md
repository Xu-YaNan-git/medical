# M12 运营看板冒烟简报

- 时间：2026-11-03 23:54:52 CST
- 环境：医生 API `http://127.0.0.1:8000` · 账号 doctor/demo123
- 结果：**pass=8 fail=0 skip=0**
- 脚本：`bash /workspace/medical-e2e-smoke/ops-smoke.sh`

| ID | 状态 | 详情 |
|----|------|------|
| OPS-00 | PASS | health doctor=200 |
| OPS-01 | PASS | doctor login ok token_len=52 |
| OPS-02 | PASS | summary 200 appt=2 wait=2 del=1 refill=1 fu=3 chron=1 updatedAt=2026-11-03 23:54:51; fields ok (ok extras=auditsToday,patientApiOk); disclaimer OK |
| OPS-02b | PASS | unauth GET /api/ops/summary → 401 |
| OPS-03 | PASS | audit list HTTP 200 items/len=5 |
| OPS-04 | PASS | audit export json 200 items=10 non-empty-body |
| OPS-05 | PASS | audit export csv 200 body_len=832 header≈﻿id,action,resourceType,resourceId,actor,detail,createdAt |
| OPS-06 | PASS | unauth audit export → 401 |

## 说明
- `GET /api/ops/summary` 若 404/501/405 → SKIP（后端未齐），不当 FAIL。
- 期望 summary 字段：appointmentsToday, waitingConsults, deliveriesActive, refillsPending, followupsUnread, chronicAbnormal, auditsToday?, updatedAt, disclaimer。
- 未重跑、未改坏 smoke / golden-path / chronic / doctor-ai。
