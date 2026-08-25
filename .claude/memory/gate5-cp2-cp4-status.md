---
name: gate5-cp2-cp4-status
description: feature01 停在 WAIT_GATE5_HUMAN——门4已独立签字，两轮 Gate5 真实用户反馈修复完毕（08-23），等用户复测；工作树未 commit/push 勿误判
type: project
---

# Gate5 收口状态钩子（2026-08-23 刷新；首版 2026-08-21）

- **当前状态 = `WAIT_GATE5_HUMAN`**：门4施工独立签字后，又经两轮真实用户 Gate5 反馈修复——第一轮：单项目时间线视觉层级 + 物理拖拽行为；第二轮：三层节点叠撞 + 主页 H1 屏A层级。**修复 ≠ Gate5 PASS**，下一步仍是用户人工复测（判断项见任务书 §14.6 PENDING_HUMAN 三条）。
- 最新验证证据（08-23）：149/149 buffered Python、24/24 timeline Chromium、7/7 Gate5 主页/拖拽 Chromium、6 个 Node 测试文件全过；已批 H1 静态稿 SHA-256 `d21e4d7fb8f6380828a387db554c0ab61461fa324b4a7287df968cf96ae8fc5d` 未变。
- 运营边界未动：真实 `flowboard.db` 保持 schema v15、未被浏览器测试写入；无 commit/push/发布/部署/真实库迁移——**新会话勿把工作树改动误判为已提交**。
- 沿革：08-21 CP2（生产接入）/CP3（视觉重对齐）/CP4（独立回归）单会话收口、两轮回归全绿为首版内容；「主跑+独立复跑」让 UI 真缺陷全部浮出 = done_when 阳性对照实例。
- **本条寿命**：Gate5 用户复测拍板后即过时，届时删除或归档，勿再刷新。
- 证据与改动清单：`feature-01-项目时间管理-仪表盘/STATE.md` §0.5 + `11-GATE5_UX_REALIGNMENT_TASK.md` §14。
