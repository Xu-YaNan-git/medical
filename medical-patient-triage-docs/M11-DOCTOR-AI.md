# M11｜医生端 AI 加深

目标：在已有鉴别诊断 / 检查用药建议 / 医嘱草稿之上，补专科模板、鉴别可勾选入病历、建议一键落医嘱。

## 范围

### 1. 专科模板库（8000 + UI）
- `GET /api/templates` → `[{ id, specialty, name, fields: { chiefComplaint?, presentIllness?, ... } }]`
- 内置至少：全科、消化、呼吸、心内（Mock 文案即可）
- `POST /api/visits/{id}/apply-template` `{ templateId, overwrite?: false }` → 空字段优先填充；`overwrite=true` 可覆盖
- 医生 UI：模板下拉/切换；应用前确认是否覆盖

### 2. 鉴别诊断对照表勾选入病历
- 已有 `differential` 列表；UI 每项增加复选框
- `POST /api/visits/{id}/differential/apply-to-note` `{ names: string[], target: "diagnosis"|"assessment" }`  
  → 写入病历「初步诊断/评估」字段（追加，去重）；须医生确认后的显式动作
- 保留原 decision 接口；免责不变

### 3. 检查/用药建议 → 医嘱草稿
- 建议列表项「一键写入医嘱」：`POST /api/visits/{id}/orders` 已有则复用；支持批量 `{ items: [{ text, source }] }`
- UI：检查建议、用药建议旁按钮；写入后右侧医嘱草稿高亮
- 文案带「AI 建议，须医生确认」

### 4. AI 侧（可选增强）
- 生成鉴别/建议时带上当前 `specialty`（来自 visit 或所选模板）
- 无 Key 仍 Mock；强 disclaimer

### 5. 测试
- 增补：templates 列表 → apply-template → differential apply-to-note → orders 批量
- 不破坏 smoke / golden-path / chronic-smoke

## 非目标
真实知识库 RAG、电子签名、正式处方签发、多医院模板同步。

## 验收
- 医生可选专科模板填充病历；勾选鉴别写入诊断区；建议一键进医嘱草稿
- 页面免责仍在；原三类冒烟仍绿

## 分工
- 后端 Python：templates / apply-template / apply-to-note / orders 批量（若缺）
- 后端 AI 功能：specialty 入 prompt；Mock 专科差异
- 产品 UI 原型：模板切换、勾选写入、一键医嘱
- 测试：脚本与用例
