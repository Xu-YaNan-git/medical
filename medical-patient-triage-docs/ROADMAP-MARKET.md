# 市面对齐 · 医疗产品下一期路线图

对照互联网医院患者端常见能力（导诊、预约、图文问诊、预问诊、报告查询/解读、复诊续方、缴费、档案、随访等），结合已交付能力排期。

## 已具备
- 医生端：鉴别诊断 / 检查用药建议 / 病历生成、Web 原型、真实 LLM
- 患者端：症状导诊、加强 AI 问诊（结构化小结+流式）、预约 Mock、H5/PWA

## 下一期（按优先级连续开发）

### M1｜诊前闭环（立刻开工）
1. 就诊人管理（添加/切换家人）
2. 简易健康档案（过敏史、慢病、用药）
3. AI 预问诊报告：问诊结束后生成可给医生看的摘要；医生端可打开查看
4. 报告中心 Mock：检验/检查列表 + AI 报告解读

### M2｜诊中便利
5. 候诊/报到状态页（Mock）
6. 消息中心（预约提醒、报告已出）
7. 院内导航占位（科室位置文案）

### M3｜诊后与用药
8. 复诊续方申请入口（表单+状态，不真开方）
9. 用药提醒
10. 随访问卷

### M4｜运营与合规增强
11. 在线缴费 Mock
12. 实名/就诊卡绑定占位
13. 操作审计与更强免责分层

不做（本路线图外）：真实 HIS/支付/电子处方合规签发、视频问诊 SDK、医保结算。

### M5｜在线接诊 Mock（已完成）
- 图文/视频问诊会话（视频仅状态机+占位画面）
- 患者排队与聊天；医生待接诊/回复/结束

### M6｜检查检验预约与改约（已完成）
- 项目列表（检验/检查）→ 选日期时段 → 预约成功
- 我的检查：改约（上限 3 次）/ 取消
- 特殊检查注意事项文案；演示免责「非真实院内预约/HIS」
- 患者端优先联 `/api/lab-exams*` + `/api/lab-exam-bookings*`，失败 Mock

### M7｜药品配送到家 Mock（已完成）
- 处方/购药单列表 → 选地址 → 提交配送
- 物流状态：待发货 → 运输中 → 已送达（时间轴 + 模拟推进）
- 我的配送列表与详情；演示免责「非真实处方流转/非真实物流配送」
- 患者端优先联 `/api/pharmacy/orders|addresses|deliveries`（含 advance），失败 Mock

### M8｜医生端工作台增强（已完成）
- 待接诊/在线接诊并入主工作台（列表 tabs + 角标 + 迷你队列）
- 打开就诊时展示预问诊报告（8001 `/api/doctor/preconsult`，失败 Mock）
- 一键采纳主诉/现病史进病历字段（空字段优先，可强制覆盖）
- 接诊会话快捷入口；保留 M5 全屏接诊页

### 慢病随访闭环（医生端·已完成）
- 医生工作台增加「随访提醒」列表（待处理答卷角标）
- 答卷摘要：逐题问答 + 风险占位/摘要；「标为已阅」
- 联调优先 `8000 /api/followups/inbox`，其次 `8001 /api/doctor/followups` / `responses`，失败 Mock

### 消息推送增强（患者端·已完成）
- 消息中心统一：预约提醒、检查预约/改约、报告已出、配送状态变更
- tabs：全部 / 预约 / 检查 / 报告 / 配送 / 系统；类型规范化映射
- 联调 `8001 GET /api/messages?type=&unreadOnly=` + `unreadCount` / `unread-count`；失败本地 filter + Mock
- 详情「去查看」跳转预约/我的检查/报告/我的配送；铃铛与底栏未读角标
- SW `triage-shell-v9-msg`；页内免责「演示消息，非真实推送通道」


### M9｜黄金路径一键演示（已完成）
> **M9 UI（2026-10-09）**：患者端 8765 / 医生端 36967 已上「演示模式」步骤条 + 重置按钮；重置优先真实 `POST /api/demo/reset`（8001 无鉴权 / 8000 Bearer），未就绪则 Mock 清本地种子。SW `triage-shell-v10-demo`。

- 预设演示账号与种子数据：患者「演示患者」、医生 doctor/demo123
- 一键重置演示数据（非 prod，或需 ALLOW_RESET_IN_PROD）
- 患者端「演示模式」引导条：导诊→预约→预问诊→图文接诊→消息
- 医生端「演示模式」：待接诊→打开预问诊→一键入病历→随访提醒已阅
- 脚本化步骤列表 + 进度；可选自动推进 Mock 状态（配送/候诊）
- 冒烟扩展：黄金路径 API 串联用例

### M10｜慢病管理加深（已完成）
> **M10 UI（2026-10-09）**：患者端 8765「慢病打卡」（就诊人、血压/血糖、今日已打卡、近 7 日 sparkline、异常提示）；医生端 36967「慢病」Tab（患者列表、趋势摘要、异常待阅标已阅）。优先联 8001 `/api/chronic/vitals*` 与 8000 `/api/chronic/patients|inbox`；未就绪 Mock。SW `triage-shell-v11-chronic`。
- 患者：血压/血糖打卡、趋势简易图、异常演示规则（≥140/90 或空腹血糖≥7.0）
- 医生：慢病患者列表、趋势简报、异常 inbox 标已阅（可与随访并列）
- 免责：演示数据，非真实慢病管理平台
- 后端：8000/8001 `/api/chronic/*` + demo reset 附 vitals 种子（进行中）

### M11｜医生端 AI 加深（已完成 · UI 已交付）
> **M11 UI（2026-10-09）**：医生端 36967 就诊工作台 — 专科模板下拉+应用（确认覆盖）、鉴别勾选「写入病历诊断」、检查/用药「一键写入医嘱」；优先联 8000 `/api/templates`、`apply-template`、`differential/apply-to-note`、`orders` 批量，失败 Mock。
- 专科模板库（全科/消化/呼吸/心内可切换）
- 鉴别诊断对照表可勾选写入病历
- 检查/用药建议一键落医嘱草稿
- 免责分层保持

### M12｜运营看板（已完成）
> **M12 UI（2026-10-09）**：医生端 36967 新 Tab「运营」— 六张汇总卡片（点击跳已有列表）+ 审计导出 JSON/CSV；优先 `GET /api/ops/summary`，未就绪则 workbench/summary + Mock；审计 `GET /api/audit/export?format=json|csv` 已验 200。免责：演示运营数据，非真实院内部署指标。
- 预约量/待接诊/配送/续方/随访待阅/慢病异常汇总
- 审计导出入口可视化（接现有 audit API）
- 演示级运营页（挂医生端 Tab）

不做：真实 HIS/支付/WebRTC/电子处方签发/医保。
## 收口（2026-10-09）
M9–M12 + SQL 并行轨均已完成。冒烟合计：smoke18 + golden11 + chronic10 + doctor-ai9 + ops8 = 56。

## S1 部署打包 · 前端（2026-11-03）
双端 `config.js`（`window.APP_CONFIG`）可配 API 地址，默认仍 127.0.0.1:8001/8000；`medical-deploy/web/` 提供 nginx 非 root 镜像（8765/36967，同源反代 `/patient-api/`、`/doctor-api/`）；患者端 SW → `triage-shell-v12-deploy`。

## S2 AI 安全护栏 · 前端（2026-11-03）
双端解析 `guardrail{action,category,advice}`（`extractGuardrail`，后端优先、本地关键词 Mock 兜底）：患者端 redflag 急症弹卡（120 / 心理类 12356）+ 锁问诊、refuse 琥珀提示、AI 回复固定免责页脚，SW → `triage-shell-v14-guardrail`；医生端 AI 输出统一「AI 建议，需医生确认」+ 工作台 redflag 警示条；预览 `?guardrailDemo=redflag|psych|refuse`。
v14：对齐后端枚举（redflag_* / injection·prompt_leak·role_override·prescription_request·off_topic / none），redflag 严格 OR 合并（后端 allow 不压本地 redflag），12356 仅 redflag_suicide，后端 advice 优先显示。
- [x] S2 v15（2026-11-03）：护栏联调真实 8000/8001 后端（顶层 guardrail、advice|reason、caution 琥珀提示、医生端 redflag 只提示不拦截 + aiNotice 标签、运营看板「护栏拦截」卡读 guardrailHits）；患者 SW `triage-shell-v15-guardrail-live`。
- [x] S2 v16（2026-11-03）：对齐 guardrails 0.2.0 冻结契约（caution_category 中文标签 + 12356、nextSteps 列表、refuse 优先 advice、问诊 SSE 流式、AI 超时 60s +「AI 思考中…」、医生端预问诊未关联/关联选择器）；患者 SW `triage-shell-v16-guardrail-020`。
