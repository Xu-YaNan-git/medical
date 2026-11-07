# AI 医疗智能助手 · 医生端 API 测试用例

- **Base**: `http://127.0.0.1:8000`
- **Auth**: `Authorization: Bearer <token>`（登录后获取）
- **字段**: JSON camelCase
- **免责声明期望文案（含关键语义即可）**: `辅助决策，不替代执业医师。AI 结果仅供参考，须医生确认。`
- **优先级**: P0 = 必测主路径/鉴权/阻断性异常；P1 = 边界与扩展异常

## P0 — 功能主路径

| ID | 模块 | 前置 | 步骤 | 期望 | 类型 |
|----|------|------|------|------|------|
| P0-01 | Health | 服务已起 | `GET /health` | 200；`status=ok`；含 `llmConfigured` bool；**不**返回任何 API Key | 功能 |
| P0-02 | Login 成功 | 无 | `POST /api/auth/login` body `{"username":"doctor","password":"demo123"}` | 200；`token` 非空；`displayName` 为张医生 | 功能 |
| P0-03 | 就诊列表 | 已登录 | `GET /api/visits` + Bearer | 200；返回数组 | 功能 |
| P0-04 | 新建就诊 | 已登录 | `POST /api/visits` body `{name,gender,age,chief,status}` | 201；返回含 `id` 的 VisitDetail | 功能 |
| P0-05 | 更新字段 | 已有 visitId | `PUT /api/visits/{id}` 更新 `chief/hpi/allergy/status` 等 | 200；字段已更新 | 功能 |
| P0-06 | parse-text | 已有 visitId | `POST .../parse-text` `{"rawText":"..."}` | 200；含 chart 建议字段；含 `disclaimer`；含 `source`=`llm`\|`mock` | 功能 |
| P0-07 | differential | 主诉或 rawText 已填 | `POST .../differential` | 200；`items` 长度 3–5（或至少 ≥1）；含 `disclaimer`；`source` 可观测 | 功能 |
| P0-08 | accept/reject | 已生成鉴别项 | `POST .../differential/decision` `{"itemId","decision":"accept\|reject"}` | 200；对应项 `decision` 更新；含 `disclaimer` | 功能 |
| P0-09 | orders/suggest | 已有 visit | `POST .../orders/suggest` | 200；含 `exams`/`drugs`/`disclaimer`；`source` 可观测 | 功能 |
| P0-10 | 写入 orders | 已有建议或手工项 | `POST .../orders` 用 `items` 或 `type`+`text` | 200；VisitDetail.`orders` 含新项 | 功能 |
| P0-11 | note generate | 已有 visit | `POST .../note/generate` | 200；`sections`/`fullText`/`disclaimer`；`source` 可观测 | 功能 |
| P0-12 | note polish | 已有 note 或传 content | `POST .../note/polish` `{"style":"concise","content":"..."}` | 200；`text` 非空；含 `disclaimer` | 功能 |
| P0-13 | export.md | 已有 visit | `GET .../export.md` | 200；`Content-Type` 含 `text/markdown`；正文非空 | 功能 |
| P0-14 | Happy-path 串联 | 服务可用 | 登录→建诊→更新→parse→鉴别→决策→医嘱建议→写入→病历生成→润色→导出 | 全链路无 5xx；AI 允许 mock | 功能 |

## P0 — 鉴权 / 异常

| ID | 模块 | 前置 | 步骤 | 期望 | 类型 |
|----|------|------|------|------|------|
| P0-A1 | 错误密码 | 无 | login `doctor` + 错误密码 | 401；`error=invalid_credentials` | 异常 |
| P0-A2 | 无 token | 无 | `GET /api/visits` 不带 Authorization | 401；`error=unauthorized` | 异常 |
| P0-A3 | 无效 token | 无 | Bearer `invalid-token` 访问 visits | 401；`error=unauthorized` | 异常 |
| P0-A4 | 缺失字段 login | 无 | login 缺 `password` | 422；`error=validation_error` | 异常 |
| P0-A5 | parse-text 空文 | 已登录+visit | `rawText=""` 或仅空白 | 400；`error=bad_request` | 异常 |
| P0-A6 | 不存在 visit | 已登录 | `GET /api/visits/not-exist-id` | 404；`error=not_found` | 异常 |
| P0-A7 | 鉴别决策无项 | 新建 visit 未生成鉴别 | decision accept | 400；提示先生成鉴别诊断 | 异常 |
| P0-A8 | 写 orders 缺参 | 已登录+visit | `POST .../orders` `{}` | 400；提示提供 items 或 type+text | 异常 |

## P1 — 边界 / 扩展

| ID | 模块 | 前置 | 步骤 | 期望 | 类型 |
|----|------|------|------|------|------|
| P1-01 | 免责声明抽查 | AI 接口任一成功 | 检查 parse/differential/orders/note 的 `disclaimer` | 含「辅助决策」「不替代」「仅供参考」「医生确认」语义 | 边界 |
| P1-02 | differential 无主诉 | 新建 visit，chief 为空/待填写且无 rawText | `POST .../differential` | 400；请先填写主诉或粘贴病情 | 边界 |
| P1-03 | decision 未知 itemId | 已有鉴别列表 | decision 用假 id | 404；`not_found` | 边界 |
| P1-04 | decision 非法枚举 | 已有 itemId | `decision="maybe"` | 422 validation_error | 边界 |
| P1-05 | polish 非法 style | 已登录 | `style="casual"` | 422 | 边界 |
| P1-06 | 过敏冲突提示 | allergy 含青霉素类；写入相关药品 | orders suggest/write | 相关药品可出现 `conflict=true` 与 `warn`（若 mock/llm 覆盖） | 边界 |
| P1-07 | 默认建诊 | 已登录 | `POST /api/visits` `{}` | 201；默认 name/gender/age/chief/status | 边界 |
| P1-08 | AI source 观测 | 主流程 AI 调用 | 记录各 AI 响应 `source` | 仅为 `llm` 或 `mock`；报告中如实记录 | 功能 |
| P1-09 | export 鉴权 | 无 token | `GET .../export.md` | 401 | 异常 |
| P1-10 | camelCase | 任意成功响应 | 检查关键字段名 | 使用 camelCase（如 `displayName`、`rawText`、`fullText`） | 边界 |

## 冒烟覆盖映射

| 冒烟脚本 | 覆盖用例 |
|----------|----------|
| `test_health` | P0-01 |
| `test_login_ok` | P0-02 |
| `test_login_wrong_password` | P0-A1 |
| `test_login_missing_field` | P0-A4 |
| `test_visits_no_token` | P0-A2 |
| `test_visits_invalid_token` | P0-A3 |
| `test_happy_path_smoke` | P0-03~P0-14, P1-01, P1-08 |
| `test_parse_empty_raw_text` | P0-A5 |
| `test_visit_not_found` | P0-A6 |
| `test_differential_without_chief` | P1-02 |
| `test_orders_missing_body` | P0-A8 |
| `test_decision_before_differential` | P0-A7 |
