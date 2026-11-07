# M9｜黄金路径一键演示

目标：对外 3–5 分钟讲清「患者→医生→随访→消息」全链路，无需手搓数据。

## 范围
1. **演示种子**（两端 SQLite）
   - 就诊人：演示患者（含过敏/慢病占位）
   - 1 条可预约号源 + 1 条待接诊图文会话占位（可按步骤创建）
   - 消息/随访答卷种子各至少 1 条（路径走完后可见）
2. **重置 API**（演示专用）
   - 患者 `POST /api/demo/reset`（8001）：清演示命名空间数据并重种子；`APP_ENV=prod` 默认拒，除非 `ALLOW_RESET_IN_PROD=1`
   - 医生 `POST /api/demo/reset`（8000，Bearer）：同上；写审计
   - 响应：`{ ok, seedVersion, disclaimer }`；审计记操作者/时间，无敏感明文
3. **患者端 UI（8765）**
   - 顶栏「演示模式」开关 +「重置演示数据」
   - 步骤条：①导诊 ②预约 ③AI问诊/预问诊 ④发起图文接诊 ⑤看消息
   - 每步「去做」跳转对应页；完成后勾选；免责「演示链路，非真实就医」
4. **医生端 UI（36967）**
   - 「演示模式」步骤：①待接诊角标 ②打开预问诊并一键入病历 ③随访提醒已阅
   - 重置按钮调 8000 demo/reset
5. **一键脚本（可选）**
   - `/workspace/medical-e2e-smoke/golden-path.sh`：API 串联跑通并打印步骤结果
6. **冒烟**
   - 增补 E2E-18：demo reset → 关键路径节点 200

## 非目标
真实推送、真实音视频、真实支付/HIS、跨机公网演示账号体系。

## 验收
- 重置后患者端可按步骤条点完；医生端能看到对应预问诊/待接诊并完成入病历与随访已阅
- prod 默认无法 reset；审计有记录
- 原有 18 条冒烟不回归；新增黄金路径脚本 exit 0
- 页面有演示免责

## 分工
- **后端 Python**：8000/8001 `demo/reset` + 种子 + 审计；文档
- **产品 UI 原型**：双端演示模式步骤条与重置
- **测试**：`golden-path.sh` + E2E-18；回归原 smoke

## 路径
- 患者 API `/workspace/medical-patient-api`
- 医生 API `/workspace/medical-assistant-api`
- 患者 UI `/workspace/medical-patient-triage`
- 医生 UI `/workspace/medical-assistant-prototype`
- 启动 `/workspace/medical-start-all.sh`
