# B-005 CP0 Coverage Map — 门 4 工程闭环与 Gate 5 边界

日期：2026-08-20
唯一外部真相：`.copilot-task.md` D1–D5（只读历史合同）、`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` §7.1–§7.3/§9.3、`mc-plan/2026-08-19 codex施工计划.md` 切片 5、`team-task.md` B-002→B-005 门禁。
状态词只允许：`PASS` / `GAP-B005` / `CONFLICT` / `OUT_OF_SCOPE`。

> 硬口径：CP0 只建图，不把 B-005 未在当前工作树重跑的动态项写成 `PASS`。B-002/B-003/B-004 已有 planner 正式关门报告，可作为继承 `PASS`；继承不代替 B-005 的全量回归、迁移恢复或终签。`STATIC_ONLY` 不能关闭任何动态行。

## A. CP0–CP6 唯一归属

| CP | 唯一职责 | 关门产物/边界 |
|---|---|---|
| CP0 | coverage map | 本文；planner 独立校验无漏项、状态合法、唯一 CP 归属，并用“删一行/伪造证据路径”阳性对照证明验收器会失败 |
| CP1 | 旧测试防篡改审计 | 以 Gate 3 基线 commit `2e906c5` 中的 12 个 Python + 5 个 Node 测试文件为清单，做 blob/用例清单/删除与 skip 审计；不改测试 |
| CP2 | 全量自动化 | 同一终值工作树跑 Python 全量、Node 全量、`py_compile`、`node --check`、`git diff --check`；一次失败必须保留原始输出 |
| CP3 | 隔离迁移/备份/恢复 | 新临时目录内验证 v15→v16、幂等、计数、FK/integrity、失败回滚、备份 verify/restore/再迁移；严禁写真实库/仓库 `backups/` |
| CP4 | D1–D4 证据矩阵 | 将 CP1–CP3 新证据与 B-002/B-003/B-004 正式关门证据逐项对应，复核范围排除和指纹；不以汇总文字代替原始输出 |
| CP5 | 最小非治理文档 | 只可更新 `README.md` 的 v16 迁移记录/测试矩阵/真实命令，并在 B-005 报告交付 `WAIT_GATE5_HUMAN` 清单；不写 STATE/mainline/AGENTS/CLAUDE/team-task/`.copilot-*` |
| CP6 | planner 终签 | 独立验证全表、复跑代表性关键命令、核对真实库与 `.copilot-*` 指纹；最高终态是 `WAIT_GATE5_HUMAN`，不得写 Done/上线完成 |

## B. D1 · 隔离 v15→v16/备份恢复矩阵

| ID | 冻结要求 | B-005 所需动态证据 | 状态 | 唯一 CP |
|---|---|---|---|---|
| A01 | 真实 v15 形状的隔离 fixture，含 `users/workspaces/boards/groups_/tasks` 代表存量 | 迁移前记录 `user_version=15`、代表行可读且五表动态计数基线；不用空库冒充 | GAP-B005 | CP3 |
| A02 | v15→v16 纯增量迁移 | 五张 timeline 表一次建齐，`PRAGMA user_version=16`，`schema_migrations` 有且仅有一条 version 16 | GAP-B005 | CP3 |
| A03 | 迁移前备份非空且含 v15 代表存量 | 自动 pre-v16 快照可独立打开，`user_version=15`，代表行/计数与迁移前一致；不只断言文件存在 | GAP-B005 | CP3 |
| A04 | v16 重跑幂等 | 第二次 `migrate()` 不新增 version 16 记录、不新增备份、表/索引形状不变 | GAP-B005 | CP3 |
| A05 | 存量计数、FK 与 integrity | 五个存量表迁移前后逐表计数相等；`foreign_key_check=[]`；`integrity_check=ok`；五张新表初始为空 | GAP-B005 | CP3 |
| A06 | 失败回滚与整包恢复 | 注入迁移失败后仍为 v15/无半表；隔离 `flowboard_ops.py backup→verify→restore` 恢复 v15 代表数据，再跑 v16 成功 | GAP-B005 | CP3 |
| A07 | 真实库锁 | 全程只读 stat/hash，终值 hash/size/mtime 与 CP0 相等；不对 `flowboard.db` 调 `migrate`/restore/purge/rebuild | GAP-B005 | CP6 |

## C. D2/D3 · B-002/B-003/B-004 关门证据继承

| ID | 要求 | 正式证据 | 状态 | 唯一 CP |
|---|---|---|---|---|
| B01 | D2 数据/API/权限/审计/并发/undo/软删/correction/复盘/Excel 字面契约 | `team-progress/planner-report-B-002-wave4.md`：§7.1/§5 map 78/78、29/29 测试可加载；`team-progress/planner-report-B003-CP5.md`：11/11 HTTP、8/8 写路由 CSRF 与零写负例（继承证据） | PASS | CP4 |
| B02 | D2 的 B-003 冻结 HTTP 黑盒接线与负路径 | `team-progress/planner-report-B003-CP5.md`：CP0–CP5 关闭，真实库/`.copilot-*` 不变（继承证据） | PASS | CP4 |
| C01 | D3 三个浅色可操作页面与真实 Chromium 交互 | `team-progress/planner-report-B004-CP6.md`：B01–B38 全 PASS，真实 Chromium J1/J2/J3 exit 0，coder E2E 24/24（继承证据） | PASS | CP4 |

## D. D4 · 工程回归、防篡改、文档与范围

| ID | 冻结要求 | B-005 关门证据 | 状态 | 唯一 CP |
|---|---|---|---|---|
| D01 | 旧测试清单完整 | 从 `2e906c5` 枚举 12 Python + 5 Node 旧文件，与当前工作树逐个对应；不允许删文件/删用例/skip/改名逃逸 | GAP-B005 | CP1 |
| D02 | 旧测试防篡改 | 对每个旧测试比对 Git blob/语义 diff；`git status` 当前虽显示 `test_collaboration.py`/`test_schedule.py` 修改，但常规 content diff 为空，CP1 必须区分行尾/工作树标志与内容弱化，不得直接写 PASS | GAP-B005 | CP1 |
| D03 | Python 全量 | 原样运行 README 命令 `python -m unittest discover -s tests -p 'test_*.py' -v`；包含旧回归、timeline service/HTTP/Chromium，零 fail/error/skip | GAP-B005 | CP2 |
| D04 | Node 全量 | 原样运行 `node --test (Get-ChildItem tests -Filter *.test.js | ForEach-Object FullName)`；当前 6 文件全绿 | GAP-B005 | CP2 |
| D05 | Python 语法全量 | 原样运行 `Get-ChildItem -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }`，exit 0 | GAP-B005 | CP2 |
| D06 | JavaScript 语法全量 | 原样运行 `Get-ChildItem -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`，exit 0 | GAP-B005 | CP2 |
| D07 | 补丁空白门 | 全仓 `git diff --check` exit 0；既存 mc-plan 尾空白若仍导致失败，必须如实报 GAP，因不在允许修改集不得顺手改历史文档 | GAP-B005 | CP2 |
| D08 | README 命令与实际一致 | 核对 Python/Node/语法命令和临时 DB/受控沙箱外 Chromium 口径；只做最小修订 | GAP-B005 | CP5 |
| D09 | 测试矩阵 | README 明示旧基线 12 Python + 5 Node 不可改弱，并列出 timeline service/HTTP/Chromium/Node/迁移的当前动态终值 | GAP-B005 | CP5 |
| D10 | v16 迁移记录 | README 的迁移段补齐 v16 五表纯增量、隔离备份/verify/restore 验收、真实库未迁移与 Gate 5 前置；不改冻结文档 | GAP-B005 | CP5 |
| D11 | D1–D4 可追溯证据矩阵 | 每行绑定原始命令输出/独立 probe/正式报告，动态项不只引 coder 自述 | GAP-B005 | CP4 |
| D12 | 排除项无范围蔓延 | 审计 diff/公开路由/UI，确认无暗色运行态、主题切换、每周看板、md/json 导入、改名/恢复、`project_ids` 导出、分页/缓存/未来功能 | GAP-B005 | CP4 |
| D13 | 真实 DB 与弃用编排锁 | 用 CP0 与 CP6 指纹对比证明 `flowboard.db` 及 `.copilot-state/task/message` 不变 | GAP-B005 | CP6 |

## E. D5 · 唯一自动终态

| ID | 要求 | 关门证据 | 状态 | 唯一 CP |
|---|---|---|---|---|
| E01 | 门 4 只交 `WAIT_GATE5_HUMAN` | B-005 终报告明确“自动门禁已收口，未完成门 5/上线”；不修改已弃用 `.copilot-*` 伪造 state | GAP-B005 | CP5 |
| E02 | 人工清单完整且不冒充 blocker 清零 | 列出真实 2–3 项目试用、精确色值/强磁吸/像素项、15 分钟手工冒烟、真机/部署、真实库正式迁移、commit/push/发布与上线决策 | GAP-B005 | CP5 |

## F. Gate 5 / 外部变更范围隔离

| ID | 保留项 | 处理 | 状态 | 唯一去向 |
|---|---|---|---|---|
| F01 | 真实 2–3 个项目试用 | 需用户真实数据与体验判断，B-005 不执行 | OUT_OF_SCOPE | Gate 5 |
| F02 | v3.2 六阶段精确色值、强磁吸参数、条形/节点/字号/行高/留白/响应式像素微调 | 冻结 §9.3 明确留集成验收 | OUT_OF_SCOPE | Gate 5 |
| F03 | §7.3 约 15 分钟手工冒烟 | 开板拖卡/刷新、甘特切视图、widgets 出数、普通成员登录权限，只列清单不伪造记录 | OUT_OF_SCOPE | Gate 5 |
| F04 | 真机/部署验收 | 涉及外部环境与上线决策，不属门 4 自动收口 | OUT_OF_SCOPE | Gate 5 |
| F05 | 真实 `flowboard.db` 迁移演练/正式迁移 | B-005 只验隔离库；真实库操作必须另行人工拍板 | OUT_OF_SCOPE | Gate 5 |
| F06 | git commit/push、deploy/发布/对外交付 | 本回合无授权，不执行 | OUT_OF_SCOPE | 用户显式授权 |
| F07 | 冻结范围外未来能力 | 工作负载/OKR/工时/预算/资源/审批/自动化/AI/CRM/Webhook/表单/SSO/原生 App 等不入 B-005 | OUT_OF_SCOPE | 新立项+用户拍板 |

## G. 允许修改集与停手条件

B-005 后续唯一允许修改集：

- `README.md`（仅 CP5 最小的测试矩阵、v16 迁移记录、`WAIT_GATE5_HUMAN` 边界）。
- `team-progress/B-005-coverage-map.md`、`team-progress/coder-report-B005-CP*.md`、`team-progress/planner-report-B005-CP*.md`、`team-progress/verification/B-005-CP*/`（只存验收器/原始输出/隔离临时证据，不得藏生产补丁）。

明确禁止修改：任何生产代码、`tests/`、`team-task.md`、`STATE.md`、mainline/门 3 冻结文档、`AGENTS.md`、`CLAUDE.md`、`.copilot-*`、真实 `flowboard.db`、仓库 `backups/`、`.git/`。若 CP1–CP6 发现必须改除 README/本组 B-005 证据外的任何文件，立即保留 failure key 并停下，不自行扩大允许集。

## H. CP0 只读指纹盘

| 对象 | SHA-256 | bytes | LastWriteTime (Asia/Shanghai) |
|---|---|---:|---|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` | 446464 | `2026-08-12 14:31:25.4654747 +08:00` |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` | 2144 | `2026-08-19 14:00:55.4931559 +08:00` |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` | 13690 | `2026-08-19 09:48:23.4936218 +08:00` |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` | 7317 | `2026-08-19 13:57:38.6945649 +08:00` |

本 CP 只做只读 hash/stat，未打开或写入真实库，未修改 `.copilot-*`。

## I. CP0 状态统计（coder 自检，等待 planner 签注）

- 条款行：32。
- `PASS=3`（全为 B-002/B-003/B-004 正式关门继承）。
- `GAP-B005=22`（所有 B-005 动态重跑/文档/终态项）。
- `CONFLICT=0`。
- `OUT_OF_SCOPE=7`（全为 Gate 5/外部授权/未来能力）。

CP0 未运行 B-005 全量测试、未做迁移恢复、未写 README，因此不授权越过 planner CP0 独立验收。
