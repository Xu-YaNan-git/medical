# M10 慢病冒烟报告（API 就绪后复跑）

- **标注**：**API 就绪后复跑**（相对首轮 pass=3 / skip=7）
- **时间**：2026-10-09 15:18:09 CST
- **脚本**：`/workspace/medical-e2e-smoke/chronic-smoke.sh`
- **环境**：患者 API `8001` · 医生 API `8000` · `PATIENT_ID=pat-2`
- **汇总**：**pass=10 fail=0 skip=0** · exit **0**
- **脚本改动**：本轮无（断言已匹配真实响应；未改 smoke/golden）

## 接口状态（复跑）

| 接口 | HTTP | 结论 |
|------|------|------|
| `GET 8001/health` · `GET 8000/health` | 200 | 就绪 |
| `POST 8001/api/demo/reset` | 200 · `seedVersion=m9-golden-1` | PASS |
| `POST 8001/api/chronic/vitals` | 200 | PASS（正常/异常 bp） |
| `GET 8001/api/chronic/vitals` | 200 | PASS · list n=3 |
| `GET 8001/api/chronic/vitals/summary` | 200 | PASS · `last7` / `abnormalCount` / disclaimer |
| `POST 8000/api/auth/login` | 200 | PASS |
| `GET 8000/api/chronic/patients` | 200 | PASS · n=3 |
| `GET 8000/api/chronic/inbox` | 200 | PASS · items + unreadCount |
| `POST 8000/api/chronic/inbox/{id}/read` | 200 | PASS · 例 `calert-2` |

## 各步结论

| ID | 结果 | 详情 |
|----|------|------|
| CH-00 就绪 | **PASS** | health patient=200 doctor=200 |
| CH-00r demo/reset | **PASS** | seed=m9-golden-1 |
| CH-01a POST vitals 正常 bp | **PASS** | id=vital-8 · abnormal=false · disclaimer OK |
| CH-01b POST vitals 异常 bp | **PASS** | id=vital-9 · abnormal=true（≥140/90） |
| CH-02 GET vitals list | **PASS** | n=3 · patientId=pat-2 |
| CH-03 GET vitals/summary | **PASS** | shape_ok · last7/abnormalCount · disclaimer |
| CH-04 医生登录 | **PASS** | token_len=52 |
| CH-05 GET chronic/patients | **PASS** | n=3 |
| CH-06 GET chronic/inbox | **PASS** | n=2（items + unreadCount） |
| CH-07 POST inbox/read | **PASS** | id=calert-2 HTTP 200 |

## 失败项

无。首轮 7 条 SKIP 本轮均已变 PASS，**skip=0**。

## 字段抽查（真实响应）

- vitals：`id` / `abnormal` / `disclaimer`（「演示数据，非真实慢病管理…」）
- summary：`patientId` · `last7` · `last30` · `latest` · `abnormalCount`
- inbox：`items[]` · `unreadCount` · `patientApiOk`

## 顺带回归

见同目录 `RERUN_M10.md`：`smoke.sh` 18/18 · `golden-path.sh` 11/0/0。

## 复跑

```bash
bash /workspace/medical-e2e-smoke/chronic-smoke.sh
```
