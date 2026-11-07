# M12｜运营看板

目标：演示级运营视角——预约/接诊/配送/续方/随访/慢病异常汇总 + 审计导出入口。

## 范围

### 1. 聚合 API（优先 8000 Bearer）
- `GET /api/ops/summary` →  
  `{ appointmentsToday, waitingConsults, deliveriesActive, refillsPending, followupsUnread, chronicAbnormal, auditsToday?, updatedAt, disclaimer }`
- 可聚合本端 store + 代理 8001（失败则该项 null/0 + `patientApiOk=false`）
- 复用/扩展现有 `workbench/summary` 亦可，但需独立 ops 字段齐全

### 2. 审计导出入口
- 已有 `GET /api/audit/export?format=json|csv`（8000 Bearer / 8001）
- 看板提供「导出 JSON / CSV」按钮（下载或新开）

### 3. UI
- 医生端新 Tab「运营」或独立 `ops` 面板（36967）
- 卡片：今日预约、待接诊、配送中、续方待审、随访待阅、慢病异常
- 点击卡片可跳到已有对应列表（接诊/慢病/随访等）
- 审计导出区 + 免责「演示运营数据，非真实院内部署指标」

### 4. 患者端
- 不做完整运营；可选在 demo 模式显示「本端消息/预约数」占位（非必须）

### 5. 测试
- ops/summary 200 + 关键字段；audit export 抽查；不破既有四类冒烟

## 非目标
真实 BI、多院区、权限分级 RBAC、定时报表邮件。

## 验收
- 医生登录可见运营汇总数字；导出按钮可用
- smoke / golden / chronic / doctor-ai 仍绿

## 分工
- 后端 Python：`/api/ops/summary` + 必要时补代理
- 产品 UI 原型：运营 Tab
- 测试：ops-smoke 小节
