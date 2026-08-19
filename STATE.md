# STATE.md — 项目状态 / 变更日志 / 近期决定

> 最后更新：2026-08-19（feature01 F1 视觉增量复审 PASS：方向 A 浅色优先；门 3 重新关闭，待门 4 新 run）
> **与契约的分工**：`feature-00-build-up/PROJECT_MAINLINE.md` = 冻结主线（不可变契约，只在用户调整产品方向时改）；本文件 = 会演进的项目状态。
> **产品**：Flowboard — 面向约 15 人团队的局域网自托管协作看板（monday.com 子集）。
> **权威范围**：现有 `.copilot-task.md`（全局 done_when 1～17）仅属于已完成的第一阶段旧 run；feature01 门 4 当前以 `feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` 为唯一实现契约，新 `.copilot-task.md` 由新 run 启动器生成。第一阶段验收证据索引：`feature-00-build-up/GLOBAL_ACCEPTANCE.md`。

---

## 0. 一句话当前状态

**第一阶段（看板 + 多视图）已完工交付。feature01「项目时间管理 + 仪表盘」F1 视觉增量复审已 PASS：方向 A 浅色优先已并入门 4 唯一实现契约，门 3 重新关闭；数据/API/权限等其余 61 条未重开。尚未动正式代码或数据库，门 4 run 未激活。** feature01 冷启动入口：`feature-01-项目时间管理-仪表盘/STATE.md`。

---

## 1. 变更日志

> 入表标准：只记「改变了项目状态/结构/范围」的事，不记单纯实现细节。
> 反例：单条 bugfix、单次测试通过、跑了一次命令 —— 不入表。

| 日期 | 变更内容 |
|------|---------|
| 2026-08-19 | **feature01 F1 视觉覆盖拍板并增量复审 PASS**：用户基于 Flowboard 整体浅色基调，指定 v1 三页优先浅色、单项目仪表盘方向 A「大标题·白卡」当前执行；方向 B 深色转为未来整体暗色皮肤参考，不进 v1。只窄修订 9- §0 F1/§8 及当前状态/样张标识，其余 61 条未重开；三处文档尾差修正后 mc-expert 定向复审 PASS（高置信），门 3 重新关闭，门 4 尚未激活。 |
| 2026-08-18 | **feature01 门 3 最终 PASS 并关闭**：独立增量复审先给 CONDITIONAL PASS，补齐所有项目路径 `require_active=True` 与复盘 undo 计数排除后，mc-expert 最终点检 PASS（高置信）。9- 正式冻结为门 4 唯一实现契约；4/5/6/7/8 已移入 feature01 `archive/`（未删除），引用同步完成，10- 降级为历史记录。未 commit、未激活新 run。 |
| 2026-08-18 | **【历史中间态】门 3 初审修订落盘**：用户拍板 B5c=b；B1–B5/N1–N4/C1–C2 写入 9-，索引核实为 49+13=62。当时尚待增量复审；随后已 PASS 并归档，当前状态以上一行与 §2 为准。 |
| 2026-08-18 | **【初审历史记录；已由上方“修订落盘”推进】门 3 整体评审=有条件退回**：当时发现 B1–B5 + N1–N7，建立 `10-GATE3_REVIEW_REMEDIATION.md`；当时仅 B5c 待用户。其后 B5c=b 已拍板且修订已写入 9-，当前状态以上一行与 §2 为准。 |
| 2026-08-18 | feature01 **门 3 总固化初版**：蒸馏《技术方案冻结版》`9-GATE3_TECH_FREEZE.md`（待用户门 3 整体评审）——当时摘要误记「§0 索引 40 行」，后经 N4 精确核实原始决策为 49 条；其余内容含 v16 五表方案、M1–M5 派生契约、API/权限/Excel/迁移/测试/视觉与 G1–G3 补拍。该初版随后进入整体评审，当前状态以上方“初审修订落盘”记录为准。 |
| 2026-08-18 | feature01 门 3 单元 ③「迁移/Excel/回归/深色范围」收口，**门 3 三单元齐**：单文件问卷 `8-GATE3_UNIT3_DECISIONS.md`（A+B 约定首产物：通俗正文+附录实现规格）→ **mc-expert 陪审先行首跑（AGENTS.md §2 新规）**：14 题中 12 题陪审定稿（planner 全部代码断言独立复核相符），仅 F1/F2-④ 升级人工 → 用户拍板 **F1=b**（feature01 三页整体深色，看板维持亮色，token 层照建可切换）与 **F2-④=b 拒绝同名——项目名称是唯一标识、不允许同名**（未采纳陪审默认落点 a），由此产生联动修订 R1–R5：同名报错有错不许提交、防重复「跳过」规则失效、预览要素修订、**R4 v16 DDL 唯一约束修正**（UNIQUE(workspace_id,name,deleted_at) 因 SQLite NULL 语义不约束活跃行→改部分唯一索引 WHERE deleted_at IS NULL + service 校验 422 NAME_CONFLICT，`4-` 头部加修正注记）、导出往返仅新 workspace 场景。F2-②=b 附用户工作流注（标准模板+agent 预清洗）。陪审贡献三条规格补丁（非整数日期序列号拒收/CSV 报错文案引导/导入提交勿漏 base_version 检查）。下一步：门 3 总固化（蒸馏《技术方案冻结版》+ 4/5/6/7/8 归档 `archive/`）→ 门 3 整体评审。 |
| 2026-08-18 | feature01 门 3 单元 ②「原子批量 API」收口：问卷 `7-GATE3_UNIT2_DECISIONS.md` E1–E8 全部拍板——workspace 级单端点单事务整批全成全败（E1）、逐项目 base_version 任一不符整批 409 零写入+409 带服务端最新视图（E2/E3）、放弃=纯前端丢弃（E3b）、撤销护栏四件套+有写权限即可撤+跨项目 undo_group 等价确认（E4）、_project_access 权限钩子 viewer 挡读挡写（E5）、拖拽全程零网络（E6）、增删改同批+空批 422·全等值 no-op（E7a/b）、**E7c 混合批次缺口拍 a=行级 field 区分不动 D5 结构**、E7d 多锚点钉住+分段平移、E8 意图提交服务端重算（P2 打包）。mainline §8「表复用」「并发冲突技术实现」两项划销。同日治理变更：**AGENTS.md §2 新增 mc-expert 陪审先行规则**（高置信非体验项陪审定稿；无法决定/不确定/重大体验影响→【需人工拍板】，用户显式授权）+ 门 3 文档组织拍板 A+B（见 §3 近期决定）。 |
| 2026-08-18 | feature01 门 3 单元 ①「领域对象与派生规则」拍板收口：技术问卷 `5-GATE3_UNIT1_DECISIONS.md` D1–D14 全部拍板——新增专表 timeline_projects/nodes + 批次审计两表（D1/D2，v16 纯增量）、done_at 载体及「不算新增完成日期列」认定（D4）、当前阶段/临近节点/逾期数/实时计算/时区等派生指标契约冻结（D7/D8/P1）、Excel 状态矛盾=日期优先只认已完成（D12）、API 恒返节点+区段双份且段算法可切换（D13）；**D10 用户修订：全项目橙点窗口由「7 天内」改为「本周（周一~周日）」**（mainline §4.3 与 3-UX §0 记录 5 加覆盖注记）。记录两个未来候选（每周看板、md/json 导入，均不进 v1）。**画法拍板 = A 链式**（对照稿回填降级留档；配套推导：服务端同派生阶段区间列表供重叠分半/展开拆行，服务端单一实现不变）——单元 ① 完全收口，进单元 ②「原子批量 API」。问卷形式按用户指令延伸用于技术拍板。 |
| 2026-08-18 | codex 只读纠偏评估收口（原文 `temp.md`，固化 `mc-plan/Mc思考03`）：确认门 2 已过、范围无漂移、进门 3 节奏正确；抓到 4 缺口——派生指标算法与 Excel 导入状态语义**新增为门 3 议题**（feature01 STATE §7 第 8/9 条），链式 vs 跨式升入首个决策单元，文档漂移当场清理（mainline 泳道术语注记 + 过时圆角表述改冻结 2px + 数字前缀改名后 5 处失效引用修正）。门 3 启动：模式从问卷往返切回 planner↔coder，按 ①领域对象与派生规则 → ②原子批量 API → ③迁移/Excel/回归 顺序推进；单元 ① 草案 v1 已出（feature01 `4-GATE3_UNIT1_TECH_DRAFT.md`，决策点 D1–D14 待拍板）。 |
| 2026-08-18 | feature01 需求侧全部收口：UX 问卷 Q1–Q8 + 交互样张遗留 R1–R3 一次性拍板（含 Q7 改写 PHASE2 §14.6 行模型 → 默认两行 + 展开，mainline §4.2/§4.3/§8 同步改写）；视觉方向 B 深色 + v3.2 色板 + ) 形分界 + 白圈节点（08-17）与右键四项菜单 + 双模式拖拽 + 无默认档（08-18）冻结；新增视觉留档与交互样张两份 HTML；DRAG §0 加覆盖注记（确认 1/13 被取代、确认 2/6 扩展）。过 mainline §6 阶段门 2，下一步阶段门 3（技术方案、数据与 API 契约）。同日 `/mc-update` 建立 `.claude/` 记忆层（写入 2 条：真浏览器事件序测试坑、主线节奏工作风格反馈）。 |
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

### feature-01-项目时间管理-仪表盘（门 3 已重新关闭，待门 4 新 run）

- **当前阶段**：需求、UX 与门 3 技术方案已收口；F1 浅色覆盖增量复审 PASS，门 3 已重新关闭，9- 仍为唯一实现契约，过程稿已归档；未动正式代码或数据库。
- **当前模型**：固定六阶段；一行一个节点；一个日期字段；主线/并行两轨各自计算一列间隔、各自顺延；状态三态（未开始/进行中/已完成）；仪表盘行模型 = 每项目默认主线/并行两行 + 展开按钮拆重叠阶段（未展开仅重叠段上下分半）；拖拽 = 节点右键四项菜单双模式（拖拽/拖拽顺延/已完成/未完成）、无默认档、草稿批次统一提交；视觉 = **方向 A 浅色（大标题·白卡）+ v3.2 亮色六色 + ) 形分界 + 白圈节点**，三页共享浅色语义 token，暗色皮肤不进 v1；权限 = workspace admin 全改 / member 仅改自己创建的项目，查看对所有注册成员开放；项目入口 = admin/member 网页新建、仅 admin 软删、v1 不改名。**门 3 冻结**：数据模型 = 新增五张专表（timeline_projects/nodes + 批次审计两表 + timeline_import_batches，间隔/状态不落库实时派生）；已完成载体 = 内部 done_at；派生指标契约（当前阶段=已动工阶段序最大跨两轨、临近节点=今天起最早未完成同日全返、逾期数两轨合并、**橙点=本周（周一~周日）内有未完成节点**、指标服务端实时计算、今天=Asia/Shanghai）；Excel 导入状态矛盾 = 日期优先只认「已完成」；API 恒返 nodes+segments+stage_intervals 三份，段算法可切换。
- **下一步**：取得用户基于最新浅色契约的 commit 与门 4 planner↔coder 新 run 明确启动；启动前 `.copilot-state.json` 保持旧 run `done/seq=58`，不编码。未来候选（不进 v1，升级须拍板）：每周看板、md/json 导入、项目改名/恢复入口、Flowboard 整体暗色皮肤。
- **冷启动入口**：`feature-01-项目时间管理-仪表盘/STATE.md`。

---

## 3. 近期决定

- **2026-08-19 ｜ feature01 视觉改为方向 A 浅色优先（用户覆盖拍板）｜** v1 三页均以浅色 token 开发，单项目以「大标题·白卡」为基线；方向 B 仅作未来整体暗色皮肤参考，不实现主题切换。
- **2026-08-18 ｜ feature01 门 3 技术文档组织（A+B 叠加，用户拍板）｜** 单元 ③ 起不再单出 DRAFT；门 3 最终 PASS 后已蒸馏 `9-GATE3_TECH_FREEZE.md` 为门 4 唯一实现契约，4/5/6/7/8 过程稿已移入 `feature-01-项目时间管理-仪表盘/archive/` 降级留档（未删除），10- 为历史修订记录。
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
| `.claude/` | 记忆层 | `auto-memory/` 用户偏好（每会话加载）+ `memory/` 技术细节（按需读），各自 MEMORY.md 索引；由 `/mc-update` 流程维护 |
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
