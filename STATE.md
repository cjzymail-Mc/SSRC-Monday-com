# STATE.md — 项目状态 / 变更日志 / 近期决定

> 最后更新：2026-08-12
> **与契约的分工**：`feature-00-build-up/PROJECT_MAINLINE.md` = 冻结主线（不可变契约，只在用户调整产品方向时改）；本文件 = 会演进的项目状态。
> **产品**：Flowboard — 面向约 15 人团队的局域网自托管协作看板（monday.com 子集）。
> **权威范围**：`.copilot-task.md`（全局 done_when 1～17）；验收证据索引：`feature-00-build-up/GLOBAL_ACCEPTANCE.md`。

---

## 0. 一句话当前状态

**第一阶段（看板 + 多视图主线）已 100% 完工并通过 planner 独立验收**（schema v15 / 79 Python + 5 Node 测试全 PASS / 17 项 done_when 全 PASS）。代码与运行库在仓库根目录；**第一阶段的过程文档已统一归档进 `feature-00-build-up/`**。当前停在**交付态**，等待用户拍板下一步（commit / 真机验收 / 从第三阶段候选池挑方向），不自动开新编码。

---

## 1. 变更日志

> 入表标准：只记「改变了项目状态/结构/范围」的事，不记单纯实现细节。
> 反例：单条 bugfix、单次测试通过、跑了一次命令 —— 不入表。

| 日期 | 变更内容 |
|------|---------|
| 2026-08-12 | 第一阶段全部过程文档归档进 `feature-00-build-up/`；新建 `STATE.md`、`AGENTS.md` 落地治理。 |
| 2026-08-03 | 第一阶段完工：planner 最终 PASS，I3～I13 全验收、schema v15、79+5 测试通过、17 项 done_when 满足。见 `feature-00-build-up/第一阶段开发总结.md`。 |
| 2026-08-02 | double-workflow 持续开发启动：temp.md 改为「全项目持续推进总任务」，生成冻结主线 `PROJECT_MAINLINE.md`，收窄本轮范围（排除工作负载/OKR/自动化/表单/Webhook/CRM 等）。 |

---

## 2. 当前 Feature 状态

### feature-00-build-up（第一阶段 · 已完工归档）

- **当前阶段**：已交付（delivery state）。主线 7 条完成边界全部满足，未留 OPEN_BLOCKERS / PENDING_HUMAN。
- **在跑·卡点**：无。无活跃编码。
- **下一步**：三个互斥方向，**等用户拍板**（详见 §3 / `mc-plan/Mc思考01-阶段完工-下阶段计划.md`）：
  1. 先做一次 git commit 固化全部成果（0 commit，强烈建议，最高 ROI）。
  2. 真机主旅程验收（登录→建看板→动态字段→7 视图→评论/提及→CSV 导入→仪表盘→390px）。
  3. 从第三阶段候选池挑方向（优先级：状态自动化+日期提醒 > 工作负载视图 > 表单/Webhook > 项目/OKR 系列）。
- **关键文件指针**：
  - 代码（根目录）：`server.py`、`flowboard/`（database/service/query/aggregation/schedule/transfer/advanced/operations）、`app.js`、`view-*.js`、`schedule-ui.js`、`dashboard-ui.js`、`index.html`、`styles.css` 等。
  - 运维：`flowboard_ops.py` + `feature-00-build-up/WINDOWS_OPERATIONS.md`。
  - 测试：`tests/`（12 Python + 5 Node）。
  - 运行库：`flowboard.db`（schema v15 / user_version=15 / integrity ok / FK clean）。
  - 第一阶段文档：全部在 `feature-00-build-up/`（见 §4 目录索引）。
- **状态边界**：第三阶段候选池（C06 工作负载 / E 项目管理 / G 自动化 / F 表单 / H Webhook）**是候选，不是已批准计划**——planner 不得擅自把候选升级成任务，需用户依据真实使用反馈拍板（冻结主线 §7 纠偏第 4 问）。

---

## 3. 近期决定

- **2026-08-12 ｜ 第一阶段过程文档归档进 `feature-00-build-up/` ｜** 保持根目录干净，代码与运行库留在根；归档不改变任何实现或验收结论。
- **2026-08-03 ｜ 第一阶段交付态，不自动开第三阶段 ｜** 详见 `mc-plan/Mc思考01-阶段完工-下阶段计划.md`：候选池需用户拍板，不在无真实反馈前启动。
- **2026-08-02 ｜ 本轮范围冻结收窄 ｜** 排除工作负载/OKR/自动化/表单/Webhook/CRM/Dev/Service/AI/Workdocs/SSO/原生 App 等进入「未来按需升级」，见 `feature-00-build-up/PROJECT_MAINLINE.md` §4。

---

## 4. 顶级目录索引（含归档说明）

| 路径 | 角色 | 说明 |
|------|------|------|
| `feature-00-build-up/` | **第一阶段过程文档归档** | 冻结主线 / 架构 / 验收 / subplan / Windows 运维 / 总结（只读冻结档，勿改实现细节） |
| `flowboard/` | 业务服务（Python） | database / service / query / aggregation / schedule / transfer / advanced / operations / security |
| `tests/` | 测试 | 12 `test_*.py` + 5 `*.test.js`（含 9 个真实 Chromium E2E） |
| `backups/` | 迁移与运维备份 | `flowboard-pre-vN-*` 历史快照，勿手删 |
| `mc-plan/` | 规划产物 | 阶段决策记录（如阶段完工与下阶段计划） |
| `flowboard.db` | 运行库 | schema v15；**只读操作可直接做，禁止对运行库 purge/restore/重建** |
| `server.py` / `app.js` / `*.css` / `index.html` / `*-ui.js` | 启动适配层 + 原生 Web 前端 | 渐进式模块化单体，原生 Web，无框架 |
| `flowboard_ops.py` | Windows 运维 CLI | backup/list/verify/retention/restore；恢复仅离线 CLI |
| `temp.md` / `.copilot-*` | double-session 交接 | 持续任务与 planner/coder 接力状态（见 AGENTS.md） |

---

## 5. 文档优先级（冲突时）

1. 用户最新明确指令
2. `feature-00-build-up/PROJECT_MAINLINE.md` 的产品范围与主线边界（冻结）
3. `temp.md` 的当前持续任务与检查点
4. `feature-00-build-up/subplan01.md` 的阶段计划
5. `feature-00-build-up/MONDAY_FEATURE_MAP.md` 的模块定义
6. 架构与实施文档（`PHASE1_ARCHITECTURE.md` 等）

> 与 `PROJECT_MAINLINE.md` §8 一致；本状态文件不在优先级链内。
