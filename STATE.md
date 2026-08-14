# STATE.md — 项目状态 / 变更日志 / 近期决定

> 最后更新：2026-08-14（feature01 需求调研 Q1–Q22 收口，权限基线落盘）
> **与契约的分工**：`feature-00-build-up/PROJECT_MAINLINE.md` = 冻结主线（不可变契约，只在用户调整产品方向时改）；本文件 = 会演进的项目状态。
> **产品**：Flowboard — 面向约 15 人团队的局域网自托管协作看板（monday.com 子集）。
> **权威范围**：`.copilot-task.md`（全局 done_when 1～17）；验收证据索引：`feature-00-build-up/GLOBAL_ACCEPTANCE.md`。

---

## 0. 一句话当前状态

**第一阶段（看板 + 多视图）已完工交付。feature01「项目时间管理 + 仪表盘」需求调研收口至最后一轮：剩 UX 问卷 Q1–Q8 待用户填答（速览表在问卷 §0），尚未进入技术方案或正式编码。** 当前主线 = 等用户拍板 Q1–Q8 → 回填 → 进阶段门 3（技术方案）；活跃 plan：`mc-plan/Mc思考02-feature01-UX收尾拍板交接.md`。feature01 冷启动入口：`feature-01-项目时间管理-仪表盘/STATE.md`。

---

## 1. 变更日志

> 入表标准：只记「改变了项目状态/结构/范围」的事，不记单纯实现细节。
> 反例：单条 bugfix、单次测试通过、跑了一次命令 —— 不入表。

| 日期 | 变更内容 |
|------|---------|
| 2026-08-14 | feature01 需求调研 Q1–Q22 收口（拖动专题+权限模型+技术契约）；mainline §2/§5/§9 权限基线按用户签字落盘；AGENTS.md 新增 §2 问卷往返模式；PHASE2 草稿加同步注记；剩余 UX 未决项落成 `3-UX_DETAIL_REQUIREMENTS.md` 问卷 **Q1–Q8**（§0 附拍板速览表，待用户填答）；mock 升 **v3.1** 克制加入 Q2/Q5/Q6/Q7 推荐演示（陪审判定不算代签，三条件见 feature01 STATE §6）；新增 Q7/Q8 对照稿 `dual-track-lane-options.html`；交接 plan `mc-plan/Mc思考02`。 |
| 2026-08-12 | 第一阶段全部过程文档归档进 `feature-00-build-up/`；新建 `STATE.md`、`AGENTS.md` 落地治理。 |
| 2026-08-13 | 用户启动 feature01 需求调研；建立冻结主线和静态 mock，当前收敛到单日期、主线/并行双轨独立间隔模型。 |
| 2026-08-03 | 第一阶段完工：planner 最终 PASS，I3～I13 全验收、schema v15、79+5 测试通过、17 项 done_when 满足。见 `feature-00-build-up/第一阶段开发总结.md`。 |
| 2026-08-02 | double-workflow 持续开发启动：temp.md 改为「全项目持续推进总任务」，生成冻结主线 `PROJECT_MAINLINE.md`，收窄本轮范围（排除工作负载/OKR/自动化/表单/Webhook/CRM 等）。 |

---

## 2. 当前 Feature 状态

### feature-00-build-up（第一阶段 · 已完工归档）

- **当前阶段**：已交付（delivery state）。主线 7 条完成边界全部满足，未留 OPEN_BLOCKERS / PENDING_HUMAN。
- **在跑·卡点**：无。无活跃编码。
- **下一步**：方向 1（git commit 固化全部成果）**已完成**——第一阶段全部成果已于 `2832c9b 固化 Flowboard 第一阶段全部成果` 落库。当前剩两个互斥方向，**等用户拍板**（详见 §3 / `mc-plan/Mc思考01-阶段完工-下阶段计划.md`）：
  1. ~~先做一次 git commit 固化全部成果~~ ✅ 已完成（commit 2832c9b）。
  2. 真机主旅程验收（登录→建看板→动态字段→7 视图→评论/提及→CSV 导入→仪表盘→390px）。
  3. 从第三阶段候选池挑方向（优先级：状态自动化+日期提醒 > 工作负载视图 > 表单/Webhook > 项目/OKR 系列）；当前用户已显式启动 **feature01 项目时间管理 + 仪表盘** 调研（见下条），优先于候选池。
- **关键文件指针**：
  - 代码（根目录）：`server.py`、`flowboard/`（database/service/query/aggregation/schedule/transfer/advanced/operations）、`app.js`、`view-*.js`、`schedule-ui.js`、`dashboard-ui.js`、`index.html`、`styles.css` 等。
  - 运维：`flowboard_ops.py` + `feature-00-build-up/WINDOWS_OPERATIONS.md`。
  - 测试：`tests/`（12 Python + 5 Node）。
  - 运行库：`flowboard.db`（schema v15 / user_version=15 / integrity ok / FK clean）。
  - 第一阶段文档：全部在 `feature-00-build-up/`（见 §4 目录索引）。
- **状态边界**：第三阶段候选池（C06 工作负载 / E 项目管理 / G 自动化 / F 表单 / H Webhook）**是候选，不是已批准计划**——planner 不得擅自把候选升级成任务，需用户依据真实使用反馈拍板（冻结主线 §7 纠偏第 4 问）。

### feature-01-项目时间管理-仪表盘（需求与 UX 调研）

- **当前阶段**：产品主线已建立；拖动专题与权限模型已收口（2026-08-14，DRAG 问卷 Q1–Q22）；静态原型继续收敛；未动正式代码或数据库。
- **当前模型**：固定六阶段；一行一个节点；一个日期字段；主线/并行两轨各自计算一列间隔、各自顺延；状态三态（未开始/进行中/已完成）；权限=workspace admin 全改 / member 仅改自己创建的项目，查看对所有注册成员开放。
- **下一步**：用户填答 `3-UX_DETAIL_REQUIREMENTS.md` 问卷 Q1–Q8（轨道控件、同日排序、六阶段色值、仪表盘筛选排序、Excel 契约、双轨 mock 验收、默认两行+展开、重叠渲染；速览表在问卷 §0）；收口后进技术方案。交接与实施步骤见 `mc-plan/Mc思考02-feature01-UX收尾拍板交接.md`。
- **冷启动入口**：`feature-01-项目时间管理-仪表盘/STATE.md`。

---

## 3. 近期决定

- **2026-08-14 ｜ feature01 需求文档命名加数字前缀（1-/2-/3-）｜** 用户手动重命名以理顺阅读顺序（先追溯草稿 → 已收口问卷 → 当前活跃问卷）；后续新增需求文档沿用「数字前缀 + 大写英文名」命名。是否升入 AGENTS.md §5 落点规约表，待用户对齐（治理文件不代改）。
- **2026-08-12 ｜ 第一阶段过程文档归档进 `feature-00-build-up/` ｜** 保持根目录干净，代码与运行库留在根；归档不改变任何实现或验收结论。
- **2026-08-03 ｜ 第一阶段交付态，不自动开第三阶段 ｜** 详见 `mc-plan/Mc思考01-阶段完工-下阶段计划.md`：候选池需用户拍板，不在无真实反馈前启动。
- **2026-08-02 ｜ 本轮范围冻结收窄 ｜** 排除工作负载/OKR/自动化/表单/Webhook/CRM/Dev/Service/AI/Workdocs/SSO/原生 App 等进入「未来按需升级」，见 `feature-00-build-up/PROJECT_MAINLINE.md` §4。

---

## 4. 顶级目录索引（含归档说明）

| 路径 | 角色 | 说明 |
|------|------|------|
| `feature-00-build-up/` | **第一阶段过程文档归档** | 冻结主线 / 架构 / 验收 / subplan / Windows 运维 / 总结（只读冻结档，勿改实现细节） |
| `feature-01-项目时间管理-仪表盘/` | **feature01 需求与原型** | 冷启动状态 / 冻结主线 / 需求草稿 / 静态 mock；当前不含正式实现 |
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
2. 当前 feature 的冻结主线：feature00 用 `feature-00-build-up/PROJECT_MAINLINE.md`；feature01 用 `feature-01-项目时间管理-仪表盘/mainline-feature01.md`
3. `temp.md` 的当前持续任务与检查点
4. `feature-00-build-up/subplan01.md` 的阶段计划
5. `feature-00-build-up/MONDAY_FEATURE_MAP.md` 的模块定义
6. 架构与实施文档（`PHASE1_ARCHITECTURE.md` 等）

> 与 `PROJECT_MAINLINE.md` §8 一致；本状态文件不在优先级链内。
