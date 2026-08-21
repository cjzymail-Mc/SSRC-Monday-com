# B-005 planner report · CP0 coverage map

日期：2026-08-20
角色：planner（独立验证；未改 map、生产、tests、README、治理/冻结/历史文档、真实库或 `.copilot-*`）
裁定：**PASS；允许进入 CP1，不授权越过 CP1。**

## 独立验收

确定性 validator 实测 `exit 0`：D1–D5 与 B-005 CP0–CP6 已精确落到 32 条唯一义务；CP0–CP6 声明各一次，每条映射只有一个 CP/外部去向；四态为 `PASS=3 / GAP-B005=22 / CONFLICT=0 / OUT_OF_SCOPE=7`。22 条 B-005 动态义务均未冒充 `PASS`。

三个继承 PASS 均回读正式终态原件：B-002 wave4 为 PASS，B-003 CP5 明确可关闭，B-004 CP6 明确 PASS/CLOSED。不存在拿历史 REWORK、coder 自述或静态 map 代替终态证据的情况。

Gate 5 排除完整：真实 2–3 项目体验、精确色值/强磁吸/像素微调、§7.3 四段手工冒烟、真机/部署、真实库迁移、commit/push/deploy 及冻结范围外未来能力均未混入门 4自动关闭项。D5 的交付语义落在 B-005 正式报告的 `WAIT_GATE5_HUMAN` 清单；依当前 team-task 隔离裁定，不复用或改写已弃用 `.copilot-*`。

允许修改集也通过独立解析：只含 README 的 CP5 最小收口与 B-005 专属 map/report/verification；不含生产、tests、治理/冻结、真实库、仓库 backups、`.git/` 或 `.copilot-*`。

## 阳性对照与锁盘

- 内存删除 A01：validator 必败，命中 `MISSING_ID`。
- 内存伪造 B-003 证据路径：validator 必败，命中 `EVIDENCE_REFERENCE_MISSING`。
- 真实 map 未被两个 control 修改。
- `flowboard.db` 与 `.copilot-state/task/message` 的 SHA-256、bytes、mtime_ns 前后完全一致；真实库仅作字节 hash/stat。

可复跑验证器与逐项证据：

- `team-progress/verification/B-005-CP0/validate_cp0_map.py`
- `team-progress/verification/B-005-CP0/results.md`

## CP0 终态

无缺口、无 conflict、无 failure key。CP1 只能执行既定的 Gate 3 基线旧测试防篡改审计，不得启动 CP2 全量或改动旧测试。

陪审来源留痕：本施工链中的 `mc-expert` 是 Codex custom 模拟陪审，并非 Claude Code 原生 team-task agent；本 CP0 裁定以 planner 独立文件/命令证据为准，未把该来源表述冒充额外动态验收。
