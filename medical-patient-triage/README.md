# 导诊台 · 患者端（H5 / PWA · M10 慢病打卡 · M9 黄金路径演示）

看病用户端可点击 Web：症状导诊、智能问诊（AI）、图文/视频医生接诊 Mock、检查检验预约与改约、**药品配送到家**、预约挂号、就诊人 / 健康档案、**慢病打卡（血压/血糖趋势）**、预问诊报告、报告中心、候诊报到、**消息中心（预约/检查/报告/配送）**、院内导航、复诊续方、用药提醒、随访问卷，以及在线缴费、实名绑定、设置须知。支持「添加到主屏幕」安装为 PWA。

## 打开方式

```bash
cd /workspace/medical-patient-triage
python3 -m http.server 8765 --bind 127.0.0.1
```

浏览器访问：**http://127.0.0.1:8765/**

**硬刷新验证**（改版 / 对接后端后务必）：

- macOS：`Cmd + Shift + R`
- Windows / Linux：`Ctrl + Shift + R`
- 或开发者工具 → Network → Disable cache 后刷新

前端静态页在 **8765**，后端 API 在 **8001**（CORS 已开；健康检查 `GET /health`）。**不要用 `file://` 打开**。

演示无需登录。


## M10 慢病打卡 · 演示路径

| 能力 | 怎么点 |
|------|--------|
| **入口** | 首页「慢病打卡」/「我的」→ 慢病打卡 |
| **就诊人** | 页顶下拉切换；联 8001 时用 `pat-1`（演示本人）等种子；离线 Mock 用本地就诊人 |
| **血压** | 填收缩/舒张压 → 提交；≥140/90 标异常 |
| **血糖** | 填数值与单位 → 提交；空腹≥7.0 mmol/L 标异常 |
| **今日已打卡** | 顶栏 pill 显示今日该类型是否已记 |
| **趋势** | 「趋势」Tab：近 7 日均值 / 异常次数 + 折线 |
| **免责** | 「演示数据，非真实慢病管理」 |
| **接口** | 优先 `POST/GET /api/chronic/vitals`、`GET /api/chronic/vitals/summary`（8001）；失败回落 localStorage Mock（含 7 日+1 异常） |

Service Worker：`triage-shell-v11-chronic`。硬刷新后生效。

## M9 黄金路径一键演示

| 能力 | 怎么点 |
|------|--------|
| **演示模式** | 顶栏右侧「演示」开关打开 → 出现步骤条 |
| **步骤条** | ①导诊 → ②预约 → ③AI问诊/预问诊 → ④发起图文接诊 → ⑤看消息；每步「去做」跳转对应页 |
| **勾选** | 进入对应页或点「去做」后自动勾选（`localStorage`：`triage_demo_step_done_v1`） |
| **重置** | 「重置演示数据」→ `POST http://127.0.0.1:8001/api/demo/reset`；失败则清本地 Mock 种子并 toast |
| **免责** | 步骤条内「演示链路，非真实就医」 |

Service Worker：`triage-shell-v11-chronic`（含 M9）。硬刷新后生效。

## 消息中心增强 · 演示路径

| 能力 | 怎么点 |
|------|--------|
| **入口** | 顶栏铃铛 / 底栏「消息」/ 首页「消息中心」 |
| **筛选** | 全部 · 预约 · 检查 · 报告 · 配送 · 系统 |
| **检查** | 筛「检查」→ 预约成功 / 改约通知 → 详情「去我的检查」 |
| **配送** | 筛「配送」→ 待发货 / 运输中 / 已送达 → 「去我的配送」 |
| **报告/预约** | 筛对应 tab → 详情跳转报告中心 / 候诊报到 |
| **未读** | 顶栏铃铛与底栏角标；点开自动标已读 |
| **免责** | 页内「演示消息，非真实推送通道」 |

优先联 `GET /api/messages?type=&unreadOnly=`（`unreadCount`）与 `GET /api/messages/unread-count`；`PATCH /api/messages/{id}/read`。筛选失败则本地 filter；接口不可用则 Mock 种子。

Service Worker：`triage-shell-v11-chronic`。

## M7 演示路径（药品配送到家）

| 能力 | 怎么点 |
|------|--------|
| **购药单** | 首页 /「我的」→ 药品配送 → 处方/购药单列表（慢病续方、门诊处方等） |
| **选地址** | 点「去配送」→ 选默认地址或新增（收件人/手机/省市区/详细） |
| **提交配送** | 确认提交 → 进入物流追踪（待发货） |
| **物流推进** | 详情页「模拟物流推进」：待发货 → 运输中 → 已送达 |
| **我的配送** | 首页「我的配送」或配送页入口 → 列表点进看时间轴 |
| **免责** | 各页可见「演示环境，非真实处方流转/非真实物流配送」；不接真实支付 |

与「复诊续方」「用药提醒」入口区分：本流是购药单配送与物流追踪。

## M6 / M5 / M4 / M3 / M2 / M1 摘要

- **M6**：检查检验预约与改约（上限 3 次）
- **M5**：图文/视频医生接诊 Mock
- **M4**：在线缴费 · 实名绑定 · 设置须知与审计
- **M3**：复诊续方 · 用药提醒 · 随访问卷
- **M2**：候诊报到 · 消息中心 · 院内导航
- **M10**：慢病打卡（血压/血糖 · 近 7 日趋势 · 异常提示）
- **M1**：就诊人 · 健康档案 · 预问诊报告 · 报告中心

底栏：首页 · 问诊 · 报告 · 消息 · 我的。

## 安装为 PWA

1. Chrome / Edge 打开 http://127.0.0.1:8765/
2. 菜单 → **安装应用** / **添加到主屏幕**
3. iOS Safari：分享 → **添加到主屏幕**

Service Worker 缓存名：`triage-shell-v11-chronic`（硬刷新后会换新壳）。

## API（优先真实，失败 Mock + localStorage）

`API_BASE = http://127.0.0.1:8001`（见 `js/app.js`）

### 慢病打卡（M10）

- `POST /api/chronic/vitals` `{ patientId, type: bp|glucose, systolic?, diastolic?, glucose?, unit?, measuredAt?, note? }`
- `GET /api/chronic/vitals?patientId=&type=&limit=`
- `GET /api/chronic/vitals/summary?patientId=`
- 种子就诊人：`pat-1` / `pat-2` / `pat-3`；失败则 localStorage Mock

### 消息中心

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/messages` | 列表；可选 `type=`、`unreadOnly=`；响应含 `unreadCount` |
| GET | `/api/messages/unread-count` | 未读数（若已落地） |
| GET | `/api/messages/{id}` | 详情 |
| PATCH | `/api/messages/{id}/read` | 标已读 |

type 映射：`appointment_reminder`→预约，`exam_booking`/`exam_reschedule`→检查，`report_ready`→报告，`delivery_status`→配送，`system`→系统。

### M7 药品配送

优先：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pharmacy/orders` | 处方/购药单列表 |
| GET | `/api/pharmacy/addresses` | 收货地址 |
| POST | `/api/pharmacy/addresses` | 新增地址 |
| GET/POST | `/api/pharmacy/deliveries` | 配送列表 / 提交配送 |
| GET | `/api/pharmacy/deliveries/{id}` | 配送详情 |
| POST | `/api/pharmacy/deliveries/{id}/advance` | 模拟物流推进 |

状态兼容：`pending`/`pending_shipment`（待发货）→ `shipped`/`in_transit`（运输中）→ `delivered`（已送达）。

兼容探测别名：`/api/rx-orders`、`/api/medicine-delivery*`、`/api/drug-delivery*`、`/api/deliveries`。

若 8001 不可用：本机 `pharmacy_orders_v1` / `pharmacy_addresses_v1` / `pharmacy_deliveries_v1` Mock。

### M6 检查检验预约

优先 `/api/lab-exams*` + `/api/lab-exam-bookings*`（改约上限 3）。

### M5 医生接诊

走 `/api/doctor-consult/...`（别名 `/api/consultations*`）。**不使用** AI 导诊 `/api/consult/sessions`。

### M4 及更早

缴费 `/api/bills`、实名 `/api/identity/binding`、审计 `/api/audit`，以及续方/用药/随访/候诊/消息/导航/就诊人/报告/导诊预约等。

## 免责

辅助导诊，不能替代面诊；急危重症请立即急诊或拨打 120。药品配送为**演示 Mock**，非真实处方流转/非真实物流配送；检查检验预约为演示 Mock；图文/视频接诊为演示 Mock；续方申请不构成处方；在线缴费为模拟支付。

## 部署 / API 地址配置（S1）

- `index.html` 在 `js/app.js` 之前加载 `config.js`，定义 `window.APP_CONFIG = { patientApiBase, doctorApiBase }`。
- **本地开发**：仓库自带 `config.js` 默认 `http://127.0.0.1:8001`，行为与以前一致（`python3 -m http.server 8765`）。
- **compose / nginx**：web 镜像用 `medical-deploy/web/config/patient-config.js` 覆盖为同源 `/patient-api`，由 nginx 反代到 `patient-api:8001`。浏览器不直连 8001。
- Service Worker：`triage-shell-v14-guardrail`（S1 时为 v12-deploy）；`config.js` 网络优先（离线才回退缓存），`/api/`、`/patient-api/`、`/doctor-api/` 及跨域请求一律不缓存。
- 详见 `/workspace/medical-deploy/web/README.md`。

## AI 安全护栏（S2 · 前端）

- **契约**：后端 AI 响应可带 `guardrail: { action: 'redflag'|'refuse'|'allow', category, advice, reason? }`，校验失败回落时可带 `source: 'mock_fallback'`。
- **解析**：`js/app.js` 中唯一入口 `extractGuardrail(resp)`，依次检查 `resp.guardrail` → `resp.data.guardrail` → `resp.message.guardrail` → `resp.reply.guardrail` → `resp.messages` 最后一条 → `resp.triage.guardrail` → `resp.raw.guardrail`。已接入导诊、问诊（`resolveGuardrail` 合并本地）、报告解读。
- **后端枚举（已定）**：
  - redflag：`redflag_cardiac` 心血管急症 / `redflag_stroke` 卒中征象 / `redflag_bleeding` 大出血 / `redflag_suicide` 自伤自杀风险 / `redflag_breathing` 呼吸急症 / `redflag_other` 其他急症
  - refuse：`injection` 提示注入 / `prompt_leak` 提示词泄露 / `role_override` 越权请求 / `prescription_request` 处方请求 / `off_topic` 非医疗话题
  - allow → `category: 'none'`；未知类别按原字符串显示。
- **合并规则（`mergeGuardrail(backend, local)` / `resolveGuardrail(resp, text)`）**：
  - redflag **严格 OR**：后端或本地任一判 redflag 即 redflag；两者都有时用后端的 category/advice；后端 `allow`/`refuse` 不能压掉本地 redflag。
  - 其他情况后端优先；后端完全没给 guardrail 时才用本地 refuse 猜测。
- **12356** 仅在 `category === 'redflag_suicide'` 时显示。
- **advice**：后端 advice 优先且突出显示（已含 120/12356 指引）；缺失才用兜底文案，不重复同一句。
- **本地 Mock 关键词**：胸痛→redflag_cardiac；口角歪斜/半身无力/说话不清→redflag_stroke；大出血/吐血/呕血→redflag_bleeding；想死/自杀/自残/不想活/轻生→redflag_suicide；呼吸困难→redflag_breathing；昏迷/抽搐→redflag_other；开处方/开药/剂量/吃几片→prescription_request；忽略之前的指令→injection；系统提示词→prompt_leak；你现在是→role_override。
- 合并逻辑两端为同一份 core（`/* --- S2 guardrail core ... end core --- */`），单测：`node /workspace/s2-tools/test-merge.mjs`。
- **redflag**：红色急症弹卡（点遮罩不关闭）、标题「请立即就医」（自杀类为「请立即寻求帮助」）+ advice + `tel:120`（`redflag_suicide` 另加 `tel:12356`）。问诊输入框锁定并显示「当前问诊已暂停，请优先就医」+「重新开始新问诊」；「我知道了」仅关闭弹卡，新会话前保持锁定。
- **refuse**：琥珀色温和提示（标题带中文类别），输入框不锁。
- **免责页脚**：每条 AI 回复固定附「AI 生成内容仅供参考，不能替代医生诊断；如有不适请及时就医。」（不重复追加）。
- **预览**（走真实合并函数）：`?guardrailDemo=redflag`（模拟后端 redflag_cardiac + advice）/ `?guardrailDemo=psych`（后端 allow + 本地 redflag_suicide → 严格 OR）/ `?guardrailDemo=refuse`（无后端 → 本地 prescription_request）。控制台 `__guardrailDemo('psych')`。
- Service Worker：`triage-shell-v14-guardrail`（`APP_VERSION = 'v14-s2-guardrail'`）；`config.js` 仍网络优先。

### S2 v15 · 护栏联调真实后端（`triage-shell-v15-guardrail-live`，APP_VERSION `v15-s2-guardrail-live`）
- 后端 `guardrail` 在响应顶层：`{action, category, advice | reason}`；展示优先 advice → reason（去掉「（命中「…」）」内部说明）→ 前端兜底文案。
- `source: 'guardrail'` 显示为「安全护栏」；refuse 时 `departments: []` 显示「本次请求未生成科室建议…」，等级徽标为「🛡 安全护栏」；redflag 时不再叠加通用急诊横幅（锁定条已提示）。
- 新增可选 `guardrail.caution`（string 或 `{text|advice|message}`）：导诊结果 / 问诊回复 / 报告解读下方琥珀小提示，不弹窗、不锁输入。预览：`?guardrailDemo=caution`。
- 后端回复/disclaimer 已含「以上内容由 AI 生成，仅供参考」时不再追加前端默认免责（导诊结果直接展示后端文案）。
- redflag 时问诊气泡里与弹窗 advice 重复的那句会被收起为「（就医指引见弹窗）」。
- 问诊接口无流式（`POST /api/consult/sessions/{id}/messages` 一次性返回），无需解析流式末事件。
- 共享护栏核心同步脚本：`python3 /workspace/s2-tools/sync-core.py`；单测：`node /workspace/s2-tools/test-merge.mjs`。

## S2 v16 — guardrails 0.2.0 对齐（SW `triage-shell-v16-guardrail-020`，APP_VERSION `v16-s2-guardrail-020`）
- **caution**（仅 action=allow）：读取 `guardrail.caution`（文本）+ `guardrail.caution_category`；琥珀提示显示中文标签（情绪/孕期/儿科/低血糖/心脏相关/其他），附 `tel:120`；`caution_mood` 额外 `tel:12356`。
- 本地规则：单纯「胸闷」不再 redflag（仅无后端 guardrail 时本地猜 caution_cardiac）；「胸闷压榨/压榨样/胸痛」仍 redflag_cardiac；否定语境（无…呕血、否认胸痛）不命中。
- refuse：优先 `advice`（患者向），`reason` 为内部文案不展示。
- redflag：`nextSteps` 以有序列表展示在导诊结果与红旗弹窗（advice 下方）；移除 v15 的 dedupeRedflagReply / advice≠narrative 去重。
- 问诊流式：`POST /api/consult/sessions/{id}/messages?stream=true`（SSE token/final/done/error），fetch + ReadableStream 解析，逐段渲染，`final` 中 guardrail 生效；异常/不支持回落非流式。SW 不拦截 /api/。
- 真实 LLM（~10–20s）：AI 端点超时 60s（其余 15s）；导诊/解读/预问诊遮罩「AI 思考中…」；问诊气泡「AI 思考中…」+ 发送按钮禁用防重复提交。
- 后端问诊回复不再做「急诊」关键词扫描（LLM 安全话术会误触发顶部急诊横幅），以 guardrail 为准；仅本地 Mock 扫描。
