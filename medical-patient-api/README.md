# 看病用户端 · 导诊台 API

患者端 FastAPI：症状导诊、多轮问诊、科室/医生/号源 Mock、预约 CRUD。AI 优先走 OpenAI 兼容大模型（`LLM_API_KEY`），失败或未配置时降级规则 Mock（`app/ai_mock.py`），响应带 `source` 与 `disclaimer`。

**免责**：辅助导诊，不替代面诊。急危重症请立即前往急诊或拨打急救电话。

与医生端 `/workspace/medical-assistant-api`（端口 8000）并列；本服务默认 **8001**。


## Guardrails fail-open / LLM judge

- **Fail-open (input → allow)** only when the package is missing/unusable or `check_input` raises/returns garbage. Audit write failures log a warning and **keep** the redflag/refuse decision — they never skip `check_input`.
- Output-check failures keep the prior output (no modify); input checks are unaffected.
- With `GUARDRAILS_LLM` on (default when `LLM_API_KEY` is set), the package LLM judge may **upgrade** a rules-only `allow` (e.g. 「胸闷」 + `caution_cardiac`) to **redflag**. That is product decision A — expected. Set `GUARDRAILS_LLM=0` for rules-only behavior.

## Field naming

JSON 使用 **camelCase**（与前端一致）。

## Setup

```bash
cd /workspace/medical-patient-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## LLM 配置（可选）

密钥只通过环境变量注入，勿写入代码或提交物。

| 变量 | 说明 | 默认 |
|------|------|------|
| `LLM_API_KEY` | OpenAI 兼容 API Key（有则尝试真模型） | 无 |
| `LLM_BASE_URL` | API Base（缺 `/v1` 会补全） | `https://sub.apixu.top/v1` |
| `LLM_MODEL` | 模型名 | `gpt-5.6-sol` |

未设置 `LLM_API_KEY` 时全部 AI 使用 Mock，`source` 为 `mock`。真模型可由「后端 AI」后续接入；钩子在 `app/ai_service.py` + `app/llm.py`。

## Start

```bash
cd /workspace/medical-patient-api
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

- **Base URL**: `http://127.0.0.1:8001`
- **OpenAPI**: `http://127.0.0.1:8001/docs`
- **前端 API 基址**: 指向 `http://127.0.0.1:8001`
- **Health**: `GET /health` → `{ "status": "ok", "llmConfigured": true|false }`（不返回密钥）

## API 列表

| Method | Path | 说明 |
|--------|------|------|
| GET | `/health` | 健康检查 + llmConfigured |
| POST | `/api/triage/recommend` | 症状导诊推荐科室 |
| POST | `/api/consult/sessions` | 新建问诊会话 |
| GET | `/api/consult/sessions/{id}` | 会话详情 |
| POST | `/api/consult/sessions/{id}/messages` | 发送用户消息（非流式 JSON） |
| POST | `/api/consult/sessions/{id}/messages?stream=1` | 同上，SSE：`token` / `final` / `done`（亦可用 `Accept: text/event-stream` 或 body.`stream`） |
| GET | `/api/departments` | 科室列表 |
| GET | `/api/departments/{id}/doctors` | 科室下医生 |
| GET | `/api/doctors/{id}/slots?date=YYYY-MM-DD` | 医生号源 |
| POST | `/api/appointments` | 创建预约 |
| GET | `/api/appointments` | 预约列表（演示） |
| GET | `/api/appointments/{id}` | 预约详情 |
| PATCH | `/api/appointments/{id}` | 更新状态（如 `cancelled`） |
| POST | `/api/previsit/report` | 预问诊报告（医生摘要，可挂 sessionId） |
| GET | `/api/reports` | 检验/检查报告列表（Mock） |
| GET | `/api/reports/{id}` | 报告详情 |
| POST | `/api/reports/interpret` | 报告 AI 解读（text 或 reportId） |
| POST | `/api/consult/sessions/{id}/preconsult-report` | 从会话生成并持久化预问诊报告 |

### 导诊请求示例

```json
POST /api/triage/recommend
{ "chief": "咳嗽发热", "duration": "2天", "bodyPart": "咽喉", "severity": "中等", "age": 32 }
```

### 预约请求示例

```json
POST /api/appointments
{
  "departmentId": "dept-resp",
  "doctorId": "doc-resp-1",
  "slotId": "slot-…",
  "patientName": "演示患者",
  "phone": "13800000000",
  "chief": "咳嗽发热"
}
```


## 数据持久化（SQLite）

默认将内存实体快照落到 SQLite，**HTTP 契约不变**。

| 变量 | 说明 | 默认 |
|------|------|------|
| `STORE_BACKEND` | `sqlite`（落盘）或 `memory`（纯内存，重启丢失） | `sqlite` |
| `SQLITE_PATH` | 数据库文件路径 | `/workspace/medical-patient-api/data/app.db` |
| `RESET_STORE` | 设为 `1` 时启动清空库并重新种子（**`APP_ENV=prod` 下默认忽略**，需 `ALLOW_RESET_IN_PROD=1`） | 未设置 |
| `APP_ENV` / `PROFILE` | `dev` \| `prod` | `dev` |
| `MASK_SENSITIVE` | 身份等强制脱敏 | `1` |

持久化实体：就诊人/档案、预约、问诊会话、消息、药房（处方单/地址/配送）、检查预约与号源余量、随访回复、审计、候诊队列、预问诊报告、续方、用药提醒、图文接诊会话、账单、实名绑定、检验报告等。科室/医生目录仍为代码常量。

首次空库：写入当前演示种子。之后启动从库加载，不覆盖已有用户数据。

```bash
# 默认 sqlite
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 纯内存（联调可丢数据）
STORE_BACKEND=memory uvicorn app.main:app --host 0.0.0.0 --port 8001

# 清空并重种子
RESET_STORE=1 uvicorn app.main:app --host 0.0.0.0 --port 8001
```


## CORS

允许 `http://localhost:*` 与 `http://127.0.0.1:*`（与医生端相同 `allow_origin_regex`）。

## 数据说明

默认 SQLite 落盘（见「数据持久化」）；`STORE_BACKEND=memory` 时重启清空。无登录鉴权（MVP 原型）。


## AI 问诊增强（2026-10-08）

- 多轮澄清：按缺失槽位提问，避免重复已问信息；信息足够或急危症状时 `status=completed`
- 结构化小结（`triage`）：`chiefComplaint`、`accompanying`、`departments`、`urgency` + `disclaimer`
- 流式可选：`?stream=1` / `Accept: text/event-stream` / body `{"stream":true}` → SSE 事件 `token`（chunk）、`final`（完整响应）、`done`
- **伪流式说明**：问诊需先拿到完整回复做输出护栏，再按 12 字切成 `token` 事件推送（非整段生成前的真 token 流）。`app/llm.py` 已有 `chat_text_stream`，但本轮未接入消息路径，以免未过护栏的内容先发出。
- `source`: `llm` | `mock`；失败降级 Mock

## M1 AI · 预问诊报告与报告解读（2026-10-08）

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/previsit/report` | 预问诊报告（医生摘要）：`sessionId` 和/或结构化字段 |
| POST | `/api/reports/interpret` | 检验/检查报告 AI 解读（强 disclaimer） |

### 预问诊报告

从已完成（或可汇总）的 consult session，或显式 JSON 输入，生成给医生看的结构化摘要。

```json
POST /api/previsit/report
{ "sessionId": "sess-1" }
```

或：

```json
{
  "chiefComplaint": "反复上腹痛 3 天",
  "duration": "3天",
  "bodyPart": "上腹",
  "accompanying": ["反酸"],
  "pastHistory": "否认溃疡手术史",
  "allergies": "青霉素",
  "patientNotes": "饭后加重"
}
```

响应字段：`chiefComplaint`、`presentIllness`、`accompanying`、`relevantHistory`、`urgency`、`suggestedDepartments`、`patientNarrative`、`redFlags`、`doctorHints`、`summaryText`、`disclaimer`、`source`（`llm`|`mock`）、`sessionId`、`generatedAt`。

免责：AI 根据患者自述生成，仅供接诊参考，不替代面诊与病历。

### 报告解读

```json
POST /api/reports/interpret
{
  "text": "血常规：白细胞 12.5×10^9/L，血红蛋白 118 g/L，血小板 210×10^9/L",
  "reportType": "lab"
}
```

`reportType` 可选：`lab` | `imaging` | `other`（可省略，规则/模型会推断）。

响应：`interpretation`、`abnormalities[]`（`item`/`finding`/`severity`）、`advice[]`、**强** `disclaimer`、`source`、`reportType`。

明确非诊断、不能替代医生与正式报告。

## M1｜诊前闭环（2026-10-08）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/patients` | 就诊人列表（种子：本人+父母） |
| POST | `/api/patients` | 新建就诊人 `{name,gender,age,relation?}` |
| GET | `/api/patients/{id}` | 详情 |
| PATCH | `/api/patients/{id}` | 更新（亦兼容 PUT） |
| DELETE | `/api/patients/{id}` | 软删除 |
| GET/PUT | `/api/patients/{id}/profile` | 健康档案 `allergies[]/chronicDiseases[]/medications[]/bloodType?/notes?` |
| POST | `/api/consult/sessions` | 可带 `{patientId}` |
| POST | `/api/consult/sessions/{id}/preconsult-report` | 从会话生成并持久化预问诊报告 |
| GET | `/api/reports/preconsult` | 预问诊报告列表 `?patientId=` |
| GET | `/api/reports/preconsult/{id}` | 预问诊详情 |
| POST | `/api/reports/preconsult` | 按 `{sessionId,patientId?}` 生成（别名） |
| GET | `/api/doctor/preconsult` | 医生只读列表 `?patientId=&patientName=` |
| GET | `/api/doctor/preconsult/{id}` | 医生只读详情 |
| GET | `/api/reports` | 报告中心列表（检验/检查 Mock） |
| GET | `/api/reports/{id}` | 报告详情 |
| POST | `/api/reports/{id}/interpret` | AI/Mock 解读 + disclaimer |
| POST | `/api/reports/interpret` | 自由文本解读（AI 钩子） |
| GET | `/api/reports/labs` 等 | `/labs` 兼容别名 |
| POST | `/api/previsit/report` | 预问诊结构化生成（不强制落库，AI 钩子） |

默认 SQLite 持久化就诊人与预问诊报告；`memory` 模式重启后仅保留种子。


## M2｜诊中便利（2026-10-08）

候诊/报到、消息中心、院内科室导航。均为 Mock，无 LLM。启动时若无预约会种子 1–2 条 confirmed 预约 + 候诊队列 + 消息。

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/waiting/status?appointmentId=` | 候诊状态；有 id 则按预约返回（无队列且 confirmed 时自动建）；无 id 返回列表 |
| POST | `/api/waiting/status` | 报到 `{appointmentId}`：`not_checked_in`→`waiting`；再 POST 可 Mock 到 `called` |
| GET/POST | `/api/queue` | 同上（兼容别名） |
| GET | `/api/messages` | 消息列表（含种子「预约提醒」「报告已出」等）`{items, unreadCount, disclaimer}` |
| PATCH | `/api/messages/{id}/read` | 标记已读 |
| GET | `/api/messages/{id}` | 消息详情 |
| GET | `/api/navigation/departments` | 科室导航列表（`location`/`tips`） |
| GET | `/api/navigation/{deptId}` | 单科室导航 |
| GET | `/api/departments` | 原科室列表，现附带 `location`/`tips`（兼容） |

候诊状态：`not_checked_in` | `waiting` | `called` | `done`。

消息字段：`id`/`title`/`body`/`type`（`appointment_reminder` | `report_ready` | `system`）/`read`/`createdAt`/`link?`。


## M3｜诊后与用药（2026-10-08）

复诊续方申请、用药提醒、随访问卷。均为内存 Mock，**不真开方**；相关响应带 `disclaimer`。

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/refills` | 续方申请列表 `?patientId=` → `{items, disclaimer}` |
| POST | `/api/refills` | 新建 `{patientId?, medicationName, dosage?, quantity?, reason?, departmentId?}` → `pending` |
| GET | `/api/refills/{id}` | 详情 |
| PATCH | `/api/refills/{id}` | 更新状态 `{status: pending\|approved\|rejected\|cancelled, reviewNote?}` |
| GET | `/api/medications/reminders` | 用药提醒列表 |
| POST | `/api/medications/reminders` | 新建 `{patientId?, drugName, dose, frequency, times[], startDate?, endDate?, enabled?}` |
| PATCH | `/api/medications/reminders/{id}` | 更新字段 / `enabled` / `takenTime`（标记今日该时刻已服） |
| DELETE | `/api/medications/reminders/{id}` | 删除提醒 |
| GET | `/api/medications/today` | 今日待服 `{items:[{reminderId,drugName,dose,time,taken}], disclaimer}` |
| GET | `/api/followups/surveys` | 问卷模板列表（种子：慢病随访、术后随访） |
| POST | `/api/followups/surveys/{id}/submit` | 提交 `{patientId?, answers:{questionId:value}}`；自动计算 `riskLevel`/`riskFlag`/`riskNote` |
| GET | `/api/followups/responses` | 提交历史 `?patientId=`；含 `patientName`/`surveyTitle`/risk 字段 |
| GET | `/api/followups/inbox` | 医生收件箱别名（全部回复，最新在前） |
| GET | `/api/followups/inbox/{id}` | 随访详情别名 |
| GET | `/api/doctor/followups` | 医生只读列表（与预问诊路径风格一致） |
| GET | `/api/doctor/followups/{id}` | 医生只读详情 |

提交/列表项字段：`id, patientId, patientName, surveyId, surveyTitle, submittedAt, createdAt, answers, riskLevel, riskFlag, riskNote, disclaimer`。启动种子 3 条演示回复（高/中/低风险）。风险为规则占位，不构成临床分级。

启动种子：2 条续方（pending/approved）、3 条用药提醒（`/today` 非空）、2 个随访问卷模板。

## M4｜运营与合规增强（2026-10-08）

在线缴费 Mock、实名/就诊卡绑定占位、操作审计。均为内存演示，**不发生真实扣款 / 不对接公安医保实名**。

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/bills` | 账单列表 `?patientId=` → `{items, disclaimer}`（种子含 unpaid+paid） |
| GET | `/api/bills/{id}` | 账单详情 |
| POST | `/api/bills/{id}/pay` | 模拟缴费 `unpaid`→`paid`（已付幂等） |
| GET/PUT | `/api/identity` | 实名/就诊卡（响应仅脱敏：`realNameMasked`/`idCardMasked`/`visitCardLast4`） |
| GET/PUT | `/api/identity/binding` | 同上（前端兼容路径） |
| GET | `/api/audit?limit=` | 审计日志（最新在前，无敏感明文） |

账单字段：`id`/`title`/`amount`/`status`(unpaid\|paid)/`patientId?`/`createdAt`/`paidAt?`/`items?[{name,amount}]`。

PUT `/api/identity` body：`{realName?, idNumber?, visitCardNo?}` — 内存存全文，接口与审计只返回脱敏/后四位。

关键写操作会追加审计：`bill.pay`、`identity.put`、`refill.create/patch`、`appointment.create/cancel`、`patient.create/patch` 等。



## M5｜图文/视频接诊 Mock（2026-10-08）

医生在线接诊（图文/视频状态机占位）。**无真 WebRTC**。勿与 AI 导诊 `/api/consult/sessions` 混用。

### 医生鉴权（演示）

任选其一：

- Header `X-Role: doctor`
- Header `Authorization: Bearer doctor` 或 `Bearer doctor-demo`

接诊医生来自科室目录种子（如 `doc-gp-1` 徐倩、`doc-resp-1` 王强）。

### 主路径（产品 UI）

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/doctor-consult/sessions` | 新建 `{mode:text\|video, patientId?, chiefComplaint?, departmentName?}` → `waiting_doctor`；video 带 `roomId` |
| GET | `/api/doctor-consult/sessions` | 列表 `?role=patient\|doctor&status=&patientId=&mode=` |
| GET | `/api/doctor-consult/sessions/{id}` | 详情（含近期 messages） |
| POST | `/api/doctor-consult/sessions/{id}/accept` | 医生接诊 → `in_progress`（需医生身份） |
| GET | `/api/doctor-consult/sessions/{id}/messages` | 消息列表 |
| POST | `/api/doctor-consult/sessions/{id}/messages` | `{role, content}`；医生消息需已接诊 + 医生身份 |
| POST | `/api/doctor-consult/sessions/{id}/end` | `{summary?}` → `ended`；video 的 `videoState=ended` |

Session 字段：`id, mode, status(queued\|waiting_doctor\|in_progress\|ended), patientName, doctorName, queuePosition, createdAt, acceptedAt, endedAt, summary, videoState(idle\|connecting\|connected\|ended), roomId?, disclaimer`。

种子：`cons-1` 图文 waiting、`cons-2` 视频 waiting（含 roomId）。

### 兼容别名（需求整理）

| Method | Path | 说明 |
|--------|------|------|
| POST/GET | `/api/consultations` | 同会话；body 可用 `type`；列表 status=`queued` 匹配 waiting |
| GET | `/api/consultations/{id}` | 详情 |
| POST | `/api/consultations/{id}/messages` | 发消息 |
| GET | `/api/consultations/{id}/messages` | 消息 |
| POST | `/api/consultations/{id}/end` | 结束 |
| GET | `/api/doctor/consultations?status=queued` | 医生队列（需医生身份） |
| POST | `/api/doctor/consultations/{id}/claim` | 接诊 |
| POST | `/api/doctor/consultations/{id}/reply` | `{content}` 医生回复 |
| POST | `/api/doctor/consultations/{id}/end` | 结束 |

写操作追加审计：`consultation.create/claim/message/end`。

## M6｜检查检验预约（2026-10-08）

检查/检验项目目录、号源与预约（**独立于**门诊挂号 `/api/appointments` 与医生号源）。内存 Mock；改约最多 3 次。

免责：演示预约，以医院实际开单与告知为准。

### 目录与号源

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/lab-exams` | 项目列表（亦 `/api/exams`、`/api/exams/catalog`）`?category=lab\|imaging\|other` |
| GET | `/api/lab-exams/{id}` | 详情（含完整 `prepNotes` / `注意事项`） |
| GET | `/api/lab-exams/{id}/slots?date=` | 号源 `{id,examId,date,time,remaining,available}`（别名 `/api/exams/{id}/slots`） |

种子 8 项：血常规、肝肾功能、腹部超声、胸部CT、心电图、胃镜、尿常规、甲状腺功能；今日起约 5 天号源。

### 预约

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/lab-exam-bookings` | `{examId, slotId, patientId?, patientName?}` → `confirmed` |
| GET | `/api/lab-exam-bookings` | 列表 `?patientId=` → `{items, disclaimer}` |
| GET | `/api/lab-exam-bookings/{id}` | 详情（含 `prepNotes`/`注意事项`、`rescheduleCount`） |
| PATCH | `/api/lab-exam-bookings/{id}` | 改约 `{slotId}` 或 `{date,time}`；第 4 次 → `400 reschedule_limit`；或 `{status:"cancelled"}` |
| POST | `/api/lab-exam-bookings/{id}/cancel` | 取消 |

别名：`/api/exam-appointments` 等同 bookings。

写操作审计：`lab_exam_booking.create` / `reschedule` / `cancel`。

### 产品 UI 合同别名

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/exam-items` | 同 catalog；字段含 `durationMin`/`prepNotes`/`price` |
| GET | `/api/exam-items/{id}/slots?date=` | 号源含 `slotId,startTime,endTime,remaining`（兼 `id`/`time`） |
| POST | `/api/exam-bookings` | `{itemId,slotId,date?,patientId?,note?}` → status=`booked` |
| GET | `/api/exam-bookings` | `?patientId=` |
| GET | `/api/exam-bookings/{id}` | 详情含 `itemId/itemName/slotLabel/rescheduleCount/maxReschedule` |
| POST | `/api/exam-bookings/{id}/reschedule` | `{slotId,date?}`；最多 3 次 |
| POST | `/api/exam-bookings/{id}/cancel` | `{reason?}` |

UI status：`confirmed`→`booked`；有改约记录→`rescheduled`；取消→`cancelled`。原 `/api/lab-exams*` 路径保留。


## M7｜药品配送 Mock（2026-10-08）

可配送处方/购药单、收货地址 CRUD、配送单状态机。**非真实处方与物流履约**。

免责：演示配送，非真实处方与物流履约。

### 处方/购药单

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/pharmacy/orders` | 可配送处方单列表 `?patientId=` → `{items, disclaimer}` |
| GET | `/api/pharmacy/orders/{id}` | 详情 |
| GET | `/api/rx-orders` | 同上（别名） |

种子：氨氯地平续方、感冒药购药单、胃黏膜保护剂；字段 `id,title,items[{name,spec,qty}],status,createdAt,patientId?`。

### 地址

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/pharmacy/addresses` | 地址列表 `?patientId=` |
| POST | `/api/pharmacy/addresses` | `{name,phone,province?,city?,district?,detail,isDefault?,patientId?}` |
| GET | `/api/pharmacy/addresses/{id}` | 详情 |
| PUT/PATCH | `/api/pharmacy/addresses/{id}` | 更新；`isDefault=true` 时取消同患者其他默认 |
| DELETE | `/api/pharmacy/addresses/{id}` | 删除（若删默认则提升另一条） |

种子 2 条地址，仅 1 条 `isDefault`。

### 配送

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/pharmacy/deliveries` | `{orderId,addressId,patientId?}` → `pending` / `uiStatus=pending_shipment` |
| GET | `/api/pharmacy/deliveries` | 列表 `?patientId=` |
| GET | `/api/pharmacy/deliveries/{id}` | 详情含 `trackingEvents` |
| POST | `/api/pharmacy/deliveries/{id}/advance` | 推进：`pending→shipped→delivered`；可选 body `{status}` 或 `{uiStatus}`（兼 `pending_shipment`/`in_transit`） |
| POST | `/api/pharmacy/deliveries/{id}/cancel` | 取消（已送达不可取消） |

状态双字段：`status`=`pending|shipped|delivered|cancelled`；`uiStatus`=`pending_shipment|in_transit|delivered|cancelled`。首次推进到 `shipped` 生成 `trackingNo` 并追加物流事件。

配送字段：`id,orderId,orderTitle,status,uiStatus,addressSnapshot,trackingNo,trackingEvents[{at,status,desc}],patientId?,createdAt,updatedAt,disclaimer`。

写操作审计：`pharmacy.address.create/update/delete`、`pharmacy.delivery.create/advance/cancel`。

启动种子：≥2 购药单、≥1 地址、1 条 pending 配送（`del-1` → `rx-1`）。


## 慢病管理 / M10

血压 / 血糖打卡、趋势摘要与异常提醒（演示规则）。

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/chronic/vitals` | 打卡 `{patientId,type:bp\|glucose,systolic?,diastolic?,glucose?,unit?,measuredAt?,note?}` → 含 `abnormal`/`disclaimer`；异常写消息 `chronic_alert` + 医生 inbox |
| GET | `/api/chronic/vitals?patientId=&type=&limit=` | 列表（新→旧） |
| GET | `/api/chronic/vitals/summary?patientId=` | 近 7/30 日均值、最近值、`abnormalCount`（30 日窗口） |
| GET | `/api/doctor/chronic/inbox` | 异常 vitals 未阅（供 8000 代理） |
| POST | `/api/doctor/chronic/inbox/{id}/read` | 标已阅 |
| GET | `/api/doctor/chronic/patients` | 有慢病标签或近期 vitals 的患者 |
| GET | `/api/doctor/chronic/patients/{id}/vitals` | 列表 + summary |
| GET | `/api/doctor/chronic/patients/{id}/summary` | summary |

异常规则（演示）：收缩压≥140 或舒张压≥90，或血糖≥7.0 mmol/L。审计 `vital.create` / `chronic_alert.read`（detail 脱敏）。`POST /api/demo/reset` 会种子 5–7 条 vitals（含 ≥1 异常）。

**免责**：演示数据，非真实慢病管理。

## 演示重置 / M9

黄金路径一键演示：清空可变演示数据并重种子（就诊人含过敏/慢病、号源、消息、随访答卷、待接诊图文等）。

| Method | Path | Auth | 说明 |
|--------|------|------|------|
| POST | `/api/demo/reset` | 无（MVP） | `{ok, seedVersion, disclaimer}`；写审计 `demo.reset` |

- `seedVersion`：`m9-golden-1`
- `disclaimer`：`演示重置，非真实就医数据。`
- **生产门禁**：`APP_ENV=prod` 或 `PROFILE=prod` 时默认 **403**；仅当 `ALLOW_RESET_IN_PROD=1` 才允许（与启动时 `RESET_STORE` 无关）
- 审计 detail 无敏感明文

```bash
curl -s -X POST http://127.0.0.1:8001/api/demo/reset
# prod 拒：
APP_ENV=prod python -c "from app.settings import allow_demo_reset; print(allow_demo_reset())"  # False
```

## 合规与免责

本仓库为**演示 / 原型系统**，不替代面诊与诊疗；**无真实 HIS、支付、公安/医保实名对接**。AI 导诊、预问诊报告、报告解读等均带 `disclaimer`，仅供参考。

### 审计导出（无敏感明文）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/audit?limit=` | 审计列表（最新在前） |
| GET | `/api/audit/export?format=json\|csv` | 导出；CSV 表头 `id,action,resourceType,resourceId,actor,detail,createdAt`；JSON `{items,exportedAt,disclaimer}` |

写入审计与导出前会对 `detail` 做脱敏（11 位手机号、15/18 位证件号模式替换为掩码）。接口与导出**不含**手机号/证件号全文。

### 敏感字段策略

| 变量 | 说明 | 默认 |
|------|------|------|
| `MASK_SENSITIVE` | `1` 强制身份等响应脱敏 | `1`（开启） |
| `ALLOW_FULL_SENSITIVE` | **危险**：非 prod 下关闭强制脱敏，身份接口可附带明文 | 未设置 |
| `APP_ENV` / `PROFILE` | `dev` \| `prod` | `dev` |

实现见 `app/privacy.py`（`mask_phone` / `mask_id_card` / `mask_name` / `redact_for_log`）与 `app/settings.py`。日志与 `append_audit` 的 detail 均应走脱敏。

### 生产 profile（`APP_ENV=prod` 或 `PROFILE=prod`）

- 默认仍使用 `STORE_BACKEND=sqlite` 落盘
- **忽略** `RESET_STORE=1`，除非同时设置 `ALLOW_RESET_IN_PROD=1`
- 建议启动：

```bash
cd /workspace/medical-patient-api && source .venv/bin/activate
export APP_ENV=prod
export STORE_BACKEND=sqlite
# 勿设 RESET_STORE；确需清空才加 ALLOW_RESET_IN_PROD=1
uvicorn app.main:app --host 0.0.0.0 --port 8001
```
