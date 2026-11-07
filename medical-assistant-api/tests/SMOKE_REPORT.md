# 冒烟测试报告 · AI 医疗智能助手（医生端 API）

| 项 | 值 |
|----|----|
| 时间 | 2026-10-02 17:22 CST（Asia/Shanghai） |
| Base | `http://127.0.0.1:8000` |
| 环境 | `/workspace/medical-assistant-api`，venv 内 `pytest` + `httpx` |
| Health | `status=ok`，`llmConfigured=true`（**未**打印任何 API Key） |
| 命令 | `cd /workspace/medical-assistant-api && source .venv/bin/activate && pytest tests/test_smoke.py -v` |
| **pytest 退出码** | **0** |
| 摘要 | **12 passed in 48.16s** |

## 结果一览

| 用例 | 结果 | 说明 |
|------|------|------|
| `test_health` | PASS | readiness + llmConfigured；响应无密钥痕迹 |
| `test_login_ok` | PASS | doctor/demo123 → token + displayName=张医生 |
| `test_login_wrong_password` | PASS | 401 `invalid_credentials` |
| `test_login_missing_field` | PASS | 422 `validation_error` |
| `test_visits_no_token` | PASS | 401 `unauthorized` |
| `test_visits_invalid_token` | PASS | 401 `unauthorized` |
| `test_happy_path_smoke` | PASS | 登录→列表/新建→更新→parse→鉴别→accept/reject→医嘱建议→写入→病历生成/润色→export.md |
| `test_parse_empty_raw_text` | PASS | 400 `bad_request` |
| `test_visit_not_found` | PASS | 404 `not_found` |
| `test_differential_without_chief` | PASS | 400 `bad_request` |
| `test_orders_missing_body` | PASS | 400 `bad_request` |
| `test_decision_before_differential` | PASS | 400 `bad_request` |

**失败项**: 无。

## 主流程 Repro

```bash
cd /workspace/medical-assistant-api
source .venv/bin/activate
# 若 8000 未监听：uvicorn app.main:app --host 0.0.0.0 --port 8000
pytest tests/test_smoke.py -v
# 或仅主流程：
pytest tests/test_smoke.py::test_happy_path_smoke -v
```

手动串联（与脚本一致）：

1. `POST /api/auth/login` → Bearer token  
2. `POST /api/visits` 建诊 → `PUT` 更新 chart  
3. `POST .../parse-text` → `POST .../differential` → `POST .../differential/decision`  
4. `POST .../orders/suggest` → `POST .../orders`  
5. `POST .../note/generate` → `POST .../note/polish`  
6. `GET .../export.md`

## 免责声明抽查

期望文案：`辅助决策，不替代执业医师。AI 结果仅供参考，须医生确认。`

| 接口 | disclaimer | 关键词检查 |
|------|------------|------------|
| parse-text | 与期望一致 | OK |
| differential | 与期望一致 | OK |
| orders/suggest | 与期望一致 | OK |
| note/generate | 与期望一致 | OK |
| note/polish | 与期望一致 | OK |

关键词：辅助决策 / 不替代 / 仅供参考 / 医生确认 — **全部命中**。

## AI source 观察（llm | mock）

抽查会话（visitId=`v108`，与冒烟同时段）：

| 接口 | source |
|------|--------|
| parse-text | **llm** |
| differential | **llm** |
| orders/suggest | **llm** |
| note/generate | **llm** |
| note/polish | **llm** |

说明：当前环境 `llmConfigured=true`，本轮 AI 段均走真实 LLM（未降级 mock）。冒烟脚本对 `source` 仅断言为 `llm` 或 `mock`，两种均可接受。

## 交付物路径

| 交付 | 路径 |
|------|------|
| 用例表 | `/workspace/medical-assistant-api/tests/TEST_CASES.md` |
| 冒烟脚本 | `/workspace/medical-assistant-api/tests/test_smoke.py` |
| 本报告 | `/workspace/medical-assistant-api/tests/SMOKE_REPORT.md` |

## 结论

主 happy-path 全链路可跑通；鉴权失败、错误密码、无/无效 token、缺失字段与业务 bad_request/not_found 异常用例均按预期返回。免责声明文案符合要求；AI 本轮 source 均为 `llm`。未打印、未写入任何 API Key。
