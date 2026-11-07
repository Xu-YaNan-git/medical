# M10｜慢病管理加深

目标：在已有健康档案「慢病标签」之上，补血压/血糖打卡、趋势与医生侧待阅，异常可 Mock 生成随访任务。

## 范围

### 1. 患者 API（8001）
- `POST /api/chronic/vitals` `{ patientId, type: bp|glucose, systolic?, diastolic?, glucose?, unit?, measuredAt?, note? }` → 记录 id
- `GET /api/chronic/vitals?patientId=&type=&limit=` → 列表（新→旧）
- `GET /api/chronic/vitals/summary?patientId=` → 近 7/30 日均值、最近值、异常次数占位
- 异常规则（演示）：收缩压≥140 或舒张压≥90，或空腹血糖≥7.0 → `abnormal=true`；可选自动 `POST` 一条随访待办/消息（Mock）
- 审计：vital.create；脱敏无多余 PII
- 免责字段 disclaimer

### 2. 医生 API（8000）
- `GET /api/chronic/patients`（Bearer）→ 有慢病标签或近期 vitals 的患者摘要列表
- `GET /api/chronic/patients/{patientId}/vitals` 或代理 8001 summary+list
- `GET /api/chronic/inbox` → 异常打卡待阅；`POST .../read` 标已阅
- workbench/summary 可增加 `chronicAbnormal` 角标数字（可选）

### 3. 患者 UI（8765）
- 「慢病打卡」页：选就诊人、血压/血糖表单、今日已打卡、近 7 日简易折线（canvas/SVG）
- 异常提示 + 免责「演示数据，非真实慢病管理」
- 底栏或健康入口可进

### 4. 医生 UI（36967）
- 「慢病」Tab/面板：患者列表 + 点开看趋势摘要 + 异常待阅标已阅
- 与随访提醒可并列，不替换

### 5. 种子 / demo reset
- M9 `demo/reset` 可附带 5–7 条 vitals 历史（含 1 条异常）便于演示

### 6. 测试
- 增补冒烟或 `chronic-smoke` 小节：打卡→列表→summary→医生 inbox
- 不破坏 golden-path / 原 18 条

## 非目标
真实设备同步、诊疗方案引擎、医保慢病认定、推送通道。

## 验收
- 患者可打卡并见趋势；异常有标识且医生 inbox 可见
- 免责展示；原 smoke + golden-path 仍绿
- README 两端补慢病说明

## 分工
- 后端 Python：8000/8001 API + 种子 + 审计
- 产品 UI 原型：双端页面
- 测试：用例与脚本
