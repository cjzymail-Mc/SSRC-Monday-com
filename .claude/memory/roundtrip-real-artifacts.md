---
name: roundtrip-real-artifacts
description: 导入导出/往返验证全程用服务端真实产物+代表性规模数据；拿到真实字节后换手工 fixture 是最危险的假 PASS
type: reference
---

# 真实产物往返验证（08-19 门 4 事故根因 + 09-16 Excel 工作法）

- 往返类验证全程使用服务端返回的真实字节/真实文件：网页真实下载 → 填写 → 预览 → 提交 → 导出 → 再导入 → 再导出比对。**取得真实产物后替换为手工 fixture = 最危险的关键假 PASS**（08-19 门 4：21 个测试全绿但冻结契约 8 项字面缺口，伪造 workbook 覆盖真实字节）。
- 用代表性规模数据（如 97 项目/857 节点）与真实分布画像（先只读查中位数/最大值/跨度，按真实分布造数），不用均匀玩具样本——均匀简化数据测不出真实交互，曾被用户要求返工。
- 明示边界：往返数据相等 ≠ 完整备份恢复（ID/创建者/标签/历史不由导出列承载）。

证据：`mc-plan/（claude-glm复盘-首次施工失败）2026-08-19-feature01-door4-double-workflow-incident-review.md`、`team-progress/B-002-coverage-map.md`、`team-progress/20260916-excel-import-export-assessment.md`、`team-progress/20260916-excel-unified-implementation.md`、`team-progress/20261008-feature02-project-overview.md`。
