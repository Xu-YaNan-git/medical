# AI 医疗智能助手 · 医生端 Demo

单文件前端（`index.html`）对接本地后端 API（`http://127.0.0.1:8000`）。**在线接诊 / 预问诊** 优先对接患者同源 API `http://127.0.0.1:8001`（`PATIENT_API_BASE`），失败则 Mock。

## 架构

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端静态页 | `http://127.0.0.1:36967/` | 需用 HTTP 打开（见下） |
| 诊疗辅助 API | `http://127.0.0.1:8000` | FastAPI；登录 / 就诊 / 鉴别诊断 / 病历 |
| 患者同源 API | `http://127.0.0.1:8001` | `/api/doctor-consult/*`、`/api/doctor/preconsult*`、随访兜底 |
| 随访收件箱 | `8000 /api/followups/inbox` | 医生端优先（Bearer）；失败再试 8001 |

**请勿用 `file://` 直接打开**。

## 启动前端静态服务

```bash
cd /workspace/medical-assistant-prototype
python3 -m http.server 36967 --bind 127.0.0.1
```

打开：**http://127.0.0.1:36967/**

修改后请 **强制刷新**（Ctrl/Cmd+Shift+R）。

## 演示账号

`doctor` / `demo123`

## M8｜工作台增强

登录后主页为「医生工作台」：

1. **Tabs**：就诊列表 | 在线接诊（待接诊角标） | 随访提醒（待办角标） | **慢病（异常待阅角标）**
2. **待接诊摘要条**：最多 3 条，点「进入会话」
3. **打开就诊** → 中间栏顶部 **预问诊报告**（`GET 8001/api/doctor/preconsult`，空则 Mock 样例）
4. **一键采纳**：主诉 / 现病史摘要 / 全部采纳 → 写入左侧病历；已填字段默认跳过，可勾选「强制覆盖」
5. **工作台顶栏**「在线接诊」角标 + 患者行下迷你待接诊列表
6. 独立全屏接诊页仍保留（列表「打开全屏接诊页」）



## M9｜黄金路径一键演示

登录后工作台顶区：

1. 打开「演示模式」→ 出现步骤条（免责：演示链路，非真实就医）
2. ① **待接诊角标** → 跳转「在线接诊」tab，查看角标与队列
3. ② **打开预问诊并一键入病历** → 打开首条就诊工作台，预问诊「采纳」后勾选完成
4. ③ **随访提醒已阅** → 跳转随访 tab，答卷「标为已阅」
5. **重置演示数据** → `POST http://127.0.0.1:8000/api/demo/reset`（Bearer，账号 doctor/demo123）；失败则清本地 Mock（随访已阅 / 接诊种子）并 toast

修改后请 **强制刷新**（Ctrl/Cmd+Shift+R）。


## M10｜慢病管理加深

登录后工作台第四 tab **慢病**（顶栏 / 工作台亦有「慢病」入口与异常角标）：

1. **患者列表**：`GET /api/chronic/patients`（Bearer）；失败用 Mock（王秀英等）
2. **点开趋势**：`GET /api/chronic/patients/{id}/vitals`（或 8001 vitals 兜底）→ 血压/血糖近 7 日折线
3. **异常待阅**：`GET /api/chronic/inbox`；「标已阅」→ `POST /api/chronic/inbox/{alert_id}/read`（已验 200）；失败写本地已阅
4. **角标**：待阅数；若 `GET /api/workbench/summary` 含 `chronicAbnormal` 则同步
5. **免责**：演示数据，非真实慢病管理

与「随访提醒」并列，不替换。修改后请 **强制刷新**。

## M11｜医生端 AI 加深

打开任一就诊工作台后：

1. **专科模板**：左栏「专科模板」下拉（全科/消化/呼吸/心内）→「应用模板」  
   - 优先 `GET /api/templates` + `POST /api/visits/{id}/apply-template`（`overwrite`）  
   - 空字段优先填充；将覆盖已填字段时会确认  
   - 接口失败则用内置 Mock 模板写入本页
2. **鉴别 → 病历诊断**：生成鉴别后勾选条目 →「写入病历诊断」（目标：初步诊断/评估）  
   - `POST /api/visits/{id}/differential/apply-to-note` `{ names, target }`，追加去重  
   - 失败则本地写入「初步诊断 / 评估」框
3. **建议 → 医嘱**：检查/用药建议旁「一键写入医嘱」  
   - `POST /api/visits/{id}/orders`（支持 `{ items: [...] }` 批量）  
   - 写入后医嘱草稿高亮；toast「AI 建议，须医生确认」
4. 生成鉴别/建议时若已选模板，会附带 `specialty`（后端可忽略）

免责文案保持不变。修改后请 **强制刷新**。

## M12｜运营看板

登录后工作台第五 tab **运营**（顶栏 / 列表区亦有「运营」入口）：

1. **汇总卡片**：今日预约、待接诊、配送中、续方待审、随访待阅、慢病异常  
   - 优先 `GET /api/ops/summary`（Bearer）；404 时用 `workbench/summary` + Mock 数字兜底
2. **点击卡片**：预约→就诊列表；待接诊→在线接诊；随访→随访提醒；慢病异常→慢病；配送/续方为演示占位提示
3. **审计导出**：导出 JSON / CSV → `GET /api/audit/export?format=json|csv`（Bearer，本机下载）
4. **免责**：演示运营数据，非真实院内部署指标

修改后请 **强制刷新**。

## 慢病随访闭环

登录后工作台第三 tab **随访提醒**（顶栏/工作台亦有入口与待办角标）：

1. 列表：患者名、问卷标题、提交时间、待处理/已阅；高风险有「风险关注」标记
2. 点进看答卷摘要（逐题问答 + 风险/摘要文案）
3. 「标为已阅」：优先尝试 PATCH；无接口则本地记住（localStorage）
4. 数据优先级：`8000 GET /api/followups/inbox`（Bearer）→ `8001 /api/doctor/followups` → `8001 /api/followups/responses` → 内置 Mock
5. 免责：演示随访，不构成诊疗结论

## 在线接诊（M5）

待接诊 → 接诊 → 回复 → 结束小结。视频为占位状态机。数据优先 `8001`，失败 `localStorage` seed。

## 建议点击路径（辅助诊疗）

登录 → 见待接诊角标 → 打开「李秀英」等就诊 → 预问诊「全部采纳」→ 生成鉴别诊断 → 医嘱/病历 → 或从工作台进接诊会话

页面顶部固定声明：**辅助决策，不替代执业医师**。

## 部署 / API 地址配置（S1）

- 主脚本前加载 `config.js`：`window.APP_CONFIG = { patientApiBase, doctorApiBase }`；`API` ← `doctorApiBase`，`PATIENT_API_BASE` ← `patientApiBase`（自动去掉末尾 `/`）。
- **本地开发**：自带 `config.js` 默认 `http://127.0.0.1:8000` / `http://127.0.0.1:8001`，行为不变。
- **compose / nginx**：web 镜像用 `medical-deploy/web/config/doctor-config.js` 覆盖为同源 `/doctor-api`、`/patient-api`。
- 本端无 Service Worker。详见 `/workspace/medical-deploy/web/README.md`。

## AI 安全护栏（S2 · 前端）

- 所有 AI 输出（预问诊报告、鉴别诊断、医嘱草稿、病历预览）统一标注 pill「AI 建议，需医生确认」。
- `extractGuardrail(resp)` 解析 `resp.guardrail` / `data` / `message` / `reply` / `messages` 末条 / `triage` / `raw`。接诊记录与预问诊用 `resolveGuardrail` / `mergeGuardrail` 与本地关键词（主诉/现病史/原文）合并；鉴别诊断/医嘱建议/病历生成只看后端。
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
- **redflag**：工作台顶部红色警示条「⚠ 护栏提示：可能存在急症风险（中文类别）— advice」（advice 加粗；缺失时兜底，`redflag_suicide` 兜底含 12356），可「关闭」（同一接诊同一提示关闭后不再弹）。
- **refuse**：对应面板内小号中性提示「护栏：该请求已被拒绝（中文类别）— advice」；`source: 'mock_fallback'` 时提示已回落 Mock。
- **预览**：`http://127.0.0.1:36967/?guardrailDemo=redflag`（模拟后端 redflag_cardiac + advice）/ `psych`（后端 allow + 本地 redflag_suicide）/ `refuse`（本地 injection）。未登录时渲染本地 Mock 接诊（不跳登录页、跳过后端调用）。

### S2 v15 · 护栏联调真实后端
- 医生端 redflag「只提示不拦截」：`guardrail.action === 'redflag'` 或 `guardrail.redflag` 标志（true 或 `{category, advice}`）→ 顶部护栏条；鉴别诊断/检查/用药/病历照常渲染。
- 后端 `aiNotice`（string 或 `{text|message|notice|label, detail|tooltip}`）覆盖对应区块「AI 建议，需医生确认」标签文字与 tooltip（来自后端时实线描边），不额外插第二条。
- refuse 面板提示使用 advice → reason；`guardrail.caution` 在面板提示中显示「⚠ 护栏提醒」。
- 运营看板新增「🛡 护栏拦截」卡：读取 `/api/ops/summary.guardrailHits {total, byCategory, byAction, bySide}`（类别中文名来自共享映射）；字段缺失显示 —/暂无数据；仅当 8000 不可达时使用 Mock 数字并标注「Mock · 后端不可达」。

## S2 v16 — guardrails 0.2.0 对齐
- 预问诊面板改用 8000 `GET /api/visits/{id}/preconsult`（Bearer）：已关联显示真实报告（标签「已关联 · pcr-…」）；404 → 「未关联预问诊」+ 报告选择器（`GET /api/preconsult/reports`），`PUT /api/visits/{id} {preconsultReportId}` 关联后重载；失败仅 toast，不再 Mock 成功（Mock 样例仅护栏预览未登录时）。
- AI 端点（differential / orders/suggest / note/generate / note/polish / parse-text）60s 超时；按钮「AI 思考中…」并禁用防重复提交。
- 本地红旗规则增加否定语境识别（「无黑便呕血」不再误报大出血）；API 基址仍只来自 config.js（APP_CONFIG）。
