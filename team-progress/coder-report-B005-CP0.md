# B-005 coder report · CP0 coverage map

日期：2026-08-20  
角色：coder（只建图，未写生产代码/测试/README/治理文档）

## 交付

- 新增 `team-progress/B-005-coverage-map.md`，将 `.copilot-task.md` D1–D5、冻结 §7.1–§7.3/§9.3、施工计划切片 5 与 B-002→B-005 门禁收成唯一 map。
- 明确 CP0–CP6 唯一归属：CP0 map；CP1 旧测试审计；CP2 全量自动化；CP3 隔离迁移恢复；CP4 证据矩阵；CP5 最小非治理文档；CP6 planner 终签。
- 仅 B-002/B-003/B-004 以 planner 正式关门证据标继承 `PASS`；所有尚未 B-005 重跑的动态项保持 `GAP-B005`。
- Gate 5 的真实 2–3 项目、像素/色值/强磁吸、15 分钟手工冒烟、真机/部署、真实库迁移、commit/push/deploy 均隔离为 `OUT_OF_SCOPE`，门 4 最高只交 `WAIT_GATE5_HUMAN`。

## 四态统计

32 行：`PASS=3`，`GAP-B005=22`，`CONFLICT=0`，`OUT_OF_SCOPE=7`。

## 基线发现（不冒充动态验收）

- Gate 3 commit `2e906c5` 的旧测试清单为 12 个 Python + 5 个 Node 文件；当前目录为 15 + 6，新增 timeline 文件不能替代旧测试防篡改审计。
- `git status` 对 `tests/test_collaboration.py` / `tests/test_schedule.py` 有 modified 标记，但常规 content diff 为空；已将该异常留给 CP1 用 blob/语义差异判定，CP0 不预判 PASS。
- README 已有四条冻结命令和 v16 五表概述，但迁移段/测试矩阵/`WAIT_GATE5_HUMAN` 仍待 CP5 按动态终值最小补齐。

## 安全与指纹

- `flowboard.db`：SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`，446464 bytes，LastWriteTime `2026-08-12 14:31:25.4654747 +08:00`。
- `.copilot-state.json`：`C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`，2144 bytes。
- `.copilot-task.md`：`34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`，13690 bytes。
- `.copilot-message.md`：`FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`，7317 bytes。

全程只读 hash/stat；未写真实 DB，未修改 `.copilot-*`。

## 后续允许集

仅 `README.md` + `team-progress/` 下 B-005 专属报告/验证证据。任何需求生产代码、`tests/`、治理/冻结/历史文档、真实 DB 或 `.copilot-*` 的修改均必须停下，不在 B-005 顺手处理。

CP0 等待 planner 独立 validator 与签注；本报告不声称 B-005 任何动态项已关闭。
