# STATE.md — Flowboard 当前状态

> 跨会话当前快照；完整历史：`team-progress/STATE-archive-20260904-pre-production-rebaseline.md`。
> 更新：2026-09-04

## 默认状态

Flowboard 已在公司局域网正式运行；feature01 已通过真实使用验收并进入第 8 阶段的生产运行与收口。没有自动启动的新 feature，默认只处理用户明确提出的生产反馈。

## 可续接路线

- **生产运行** — `start-flowboard.cmd` 的 8080 健康检查返回 schema v19；2026-09-04 对根 `flowboard.db` 只读核验为 integrity `ok`、外键违规 0，快照为 5 active / 1 archived / 2 soft-deleted 项目、107 节点，最新业务更新为 2026-09-04。下一步是按真实反馈做小批次维护；入口：`README.md`。
- **feature01** — 原 `WAIT_GATE5_HUMAN` 等四个等待态已被人工验收、正式上线及持续使用事实取代；9 月 3 日旗标升级和 9 月 4 日拖拽升级已在 `origin/main` 的 `6e66f7f`。当前只保留用户选中的体验迭代；`AUD-03` 窄屏导航是待拍板可选项，不阻断现有桌面生产。入口：`feature-01-项目时间管理-仪表盘/STATE.md`。

## 恢复边界

- 真实库业务数据是动态快照；继续只读优先，迁移、恢复或 purge 仍须单独授权。开发验证使用 `local-test.cmd` 或临时库。
- `stash@{0}` 是 2026-09-01 同步前保护快照，未获明确指令不得清理；本轮仅更新文档，尚未 commit/push。
- 冻结合同和 `team-progress/` 中旧 `WAIT_*` 文案是里程碑历史，不是当前控制面；当前范围以 `feature-01-项目时间管理-仪表盘/mainline-feature01.md` 为准。
