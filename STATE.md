# STATE.md — Flowboard 当前状态

> 跨会话当前快照；完整历史：`team-progress/STATE-archive-20260904-pre-production-rebaseline.md`。
> 更新：2026-09-07

## 默认状态

Flowboard 已在公司局域网正式运行；feature01 已通过真实使用验收并进入第 8 阶段的生产运行与收口。没有自动启动的新 feature，默认只处理用户明确提出的生产反馈。

## 可续接路线

- **Git skills** — 支持未提交修复中途同步、主动处理冲突，并按影响走快速路径/复用 PASS；常规提交两次 fetch，Git 工具测试与产品回归分离。23+6 项隔离专项通过。当前入口与证据：`team-progress/skill-fast-path-20260907.md`；此前冲突试做：`team-progress/skill-sync-wip-20260907.md`。
- **生产运行** — `start-flowboard.cmd` 的 8080 健康检查返回 schema v19；2026-09-04 对根 `flowboard.db` 只读核验为 integrity `ok`、外键违规 0，快照为 5 active / 1 archived / 2 soft-deleted 项目、107 节点，最新业务更新为 2026-09-04。下一步是按真实反馈做小批次维护；入口：`README.md`。
- **feature01** — 原 `WAIT_GATE5_HUMAN` 等四个等待态已被人工验收、正式上线及持续使用事实取代；9 月 3 日旗标升级和 9 月 4 日拖拽升级已在 `origin/main` 的 `6e66f7f`。当前只保留用户选中的体验迭代；`AUD-03` 窄屏导航是待拍板可选项，不阻断现有桌面生产。入口：`feature-01-项目时间管理-仪表盘/STATE.md`。

## 恢复边界

- 真实库业务数据是动态快照；继续只读优先，迁移、恢复或 purge 仍须单独授权。开发验证使用 `local-test.cmd` 或临时库。
- 2026-09-01 同步前保护快照保留，未获明确指令不得清理；本次 skill 改造未改动该快照，后续使用 stash 时按 OID/消息识别，避免依赖会变化的数字序号。
- 冻结合同和 `team-progress/` 中旧 `WAIT_*` 文案是里程碑历史，不是当前控制面；当前范围以 `feature-01-项目时间管理-仪表盘/mainline-feature01.md` 为准。
