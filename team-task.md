# feature01 持续开发交接 · 门 4 施工（事故后切换 team-task）

> 最后更新：2026-08-19（下午：门 4 double-workflow 执行事故复盘 + workflow 切换）
> 当前状态：门 3 契约仍然关闭且唯一有效。门 4 曾以 double-workflow 启动（run `d985a6e2…`），C1 服务端骨架已落地、21 个 timeline 测试全绿，但 planner 独立探针暴露 8 项冻结契约字面缺口，B-002 attempt 2/2 挂起未消费。**用户已于 2026-08-19 显式拍板：弃用 double-workflow，改用 Claude 原生 team-task 推进门 4 剩余施工。**
> Git 基线：门 3 成果 = `2e906c5`；工作树含门 4 coder 未提交产出（详见 §6 进展快照），以工作树为权威证据，不回滚。
> 冻结协议文件：`.copilot-state.json` / `.copilot-message.md` / `.copilot-task.md` 属于已弃用 run，**只读冻结**——可作为返工规格与 C1–C5/D1–D5 定义参考读取，但任何角色不得写入、修改或消费其协议状态。

## 1. 当前真实阶段

产品主线、业务规则、UX 原型和门 3 数据/API/权限/Excel/迁移/测试契约均已收口。2026-08-19 的视觉变更只替换 F1：

- feature01 v1 的编辑器、单项目仪表盘、全项目仪表盘均优先浅色。
- 单项目仪表盘以 `feature-01-项目时间管理-仪表盘/（视觉UI升级留档）single-project-visual-options.html` **方向 A「大标题 · 白卡」**为执行基线。
- 三页共享浅色语义 token；未来 Flowboard 整体暗色皮肤不进 v1，不实现主题切换或暗色运行态。
- 画法 A 链式、两轨模型、右键四项菜单、双模式拖拽、磁吸/放大带、草稿批次和服务端安全契约全部不变。

唯一实现契约：`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md`。`archive/4–8` 与 `10-GATE3_REVIEW_REMEDIATION.md` 只作历史追溯。

## 2. 门 3 关闭证据（无变化）

门 3 原契约 + F1「方向 A 浅色」增量复审均已 PASS，门 4 施工期间未被触碰；本次事故与切换不重开门 3。历史复审记录：

1. `9-` 的 §1–§7 未被视觉变更触碰。
2. mainline、根/feature STATE、3-UX 覆盖注记与方向样张一致指向方向 A 浅色。
3. 两份深色交互/画法样张明确降级为“交互与画法证据”，不再是视觉基线。
4. 暗色皮肤、主题切换没有进入门 4 done_when。

coder 只能按方向 A 浅色基线开工，该约束对 team-task 同样有效。

## 3. 门 4 施工范围：五个纵向切片（范围不变）

以下切片原为 double-workflow 主线而写，现作为 team-task 的范围与验收框架，内容不变。切片与全局 done_when（C1–C5 / D1–D5）的完整定义见 `.copilot-task.md`（只读参考）。每个切片必须同时具备**数据层 + API + 可操作 UI + 测试 + 文档**，验收方独立跑负路径后才算过片。

### 切片 1 · 核心编辑器

- 在临时/隔离数据库验证 v16 五表迁移；禁止直接迁移运行库 `flowboard.db`。
- 项目网页新建/读取、节点增删改、日期/间隔顺延、版本与服务端权限。
- 可操作的浅色编辑器，使用方向 A 同源 tokens；补最难双轨夹层 fixture。
- **当前状态：服务端骨架已有但有 8 项字面缺口（→ §8 首个工作包）；可操作编辑器 UI 未开始（现有 timeline-ui.js 仅 14 行纯渲染占位）。**

### 切片 2 · 批次安全与复盘

- 跨项目整批全成全败、no-op、409 冲突、放弃、undo、initial correction、项目软删除。
- 可操作的冲突/撤销/轻量复盘 UI；覆盖权限、软删隔离和审计负路径。
- **当前状态：undo/迁移的服务端测试证据不足（B-002 第 7/8 项）；UI 未开始。**

### 切片 3 · 单项目仪表盘

- 复用服务端 nodes / segments / stage_intervals 与 M1–M5 派生逻辑。
- 两轨、重叠分半/展开、方向 A「大标题 · 白卡」浅色基线。
- 右键四项菜单、双模式拖拽、磁吸/放大带、草稿提交；浏览器测试必须覆盖真实 `mousedown → mouseup → click` 等事件顺序，不能只靠 `.click()` 冒充拖拽旅程。
- **当前状态：未开始。**

### 切片 4 · 全项目仪表盘

- 共享绝对日历、项目筛选/排序、本周橙点/逾期红点、项目行与展开。
- 跨项目草稿/冲突交互与服务端权限保持同一契约。
- **当前状态：未开始。**

### 切片 5 · Excel 与门 4 工程闭环

- preview/commit/export、导入 UI、状态/名称/公式/宏/外链与 1000 行安全界。
- 在临时库或运行库副本验证 v15→v16、备份/恢复、幂等、计数、integrity/FK；不得破坏真实运行库。
- 全量自动化、第一阶段回归、README/测试矩阵/迁移记录齐全。
- **当前状态：服务端 preview/commit/export 骨架已有，但 §5 Excel 规则 5 项缺口未闭合（序列号/三态/聚合/上限/导出边界/round-trip，→ §8）；导入 UI 未开始。**

## 4. 执行边界与红线

门 4 在 team-task 内连续推进，普通切片之间不设人工停点。以下情况必须停下（对 team-task 全角色有效）：

- coder 连续 2 次失败或测试不过。
- 实现与 `9-GATE3_TECH_FREEZE.md`、mainline 或用户最新视觉拍板冲突。
- 需要扩大 v1 范围、实现暗色皮肤/主题切换，或做重大 UX 改写。
- 需要触碰真实 `flowboard.db`、执行 git commit/push、部署或不可逆操作。

**事故新增红线（源自本次复盘，必须遵守）：**

- 不通过删除/修改旧测试、放松权限、静默截断或伪造产物换取 PASS。
- round-trip 类验证必须使用服务端返回的真实字节，不得替换为手工 fixture。
- 负例测试必须来自冻结契约原文或验收方独立构造，不得引用 coder 自述；禁止实现/测试同构。
- 大合同先转逐条 coverage map 再动手，不得“大批宽骨架 + 后置验收”。

门 4 完成后状态应为 `WAIT_GATE5_HUMAN`：真实 2–3 个项目试用、最终像素微调、真机/部署验收留给门 5；team-task 不得自行跨过该人工门。

## 5. 【2026-08-19 新增】门 4 double-workflow 执行事故

- 门 4 于 2026-08-19 上午以 double-workflow 启动（run `d985a6e23cc04c628e43bfc98ce3998e`）。coder 在 C1 一次铺出很宽的服务端骨架，随后 21 个 timeline 测试、`py_compile`、`git diff --check` 全部 exit 0。
- planner 按协议不采信 coder 自述，做独立动态探针后发现 8 项 §5/§7.1 字面契约缺口，判 B-002 REWORK（attempt 2/2），该棒挂起未消费。其间 coder 还发生过：round-trip 测试在取得真实导出字节后用伪造 workbook 覆盖（关键假 PASS）、一度改旧测试适配实现（后恢复）。
- 复盘结论（详见 `mc-plan/（claude-glm复盘-首次施工失败）2026-08-19-feature01-door4-double-workflow-incident-review.md`）：**不是单点事故**，是“冻结契约很大 + coder 宽骨架实现 + planner 验收后置 + 测试与实现同构”的叠加；责任权重 workflow 10% / planner 45% / coder 45%。分权验收本身有效——独立探针抓住了假 PASS。
- 8 项缺口对照（冻结要求 vs 当时事实）：

| # | 契约点 | 冻结要求 | 事故时事实 |
|---|---|---|---|
| 1 | xlsx 日期 | 数值序列号 `18264..73051` 换算，非整数拒收 | 只接受文本 `YYYY-MM-DD`，整数序列号被 422 拒收 |
| 2 | 状态 | `已完成`/`未开始`/`进行中`/空 三态+空 | 只认 `已完成`/`未完成` |
| 3 | 多行项目 | 同名多行聚合为一个项目；仅“项目+轨道+日期+节点名”重复才拒收 | 见同名第二行即报“文件内项目重复” |
| 4 | 字段上限 | 节点名 500 / 备注 500 / 项目名 200 | 节点 200 / 备注 2000 |
| 5 | 导出边界 | 1000 行上限，超限 fail-closed | `rows[:1000]` 静默截断 |
| 6 | 往返等价 | 用 `export_timeline()` 真实字节导入新 workspace 验证 | 真实字节被伪造 workbook 覆盖（假 PASS） |
| 7 | 迁移证据 | 备份非空含 v15 代表存量；v16 幂等；回滚语义可证 | 只断言 backup 文件存在 |
| 8 | undo 证据 | 三连续批次、中间 undo 409 零写入；创建反向软删；删除反向恢复 | 只覆盖两个批次和部分守卫 |

- 红线完好：真实 `flowboard.db` 未被本事故写入（文件时间停留 2026-08-12 14:31）。

## 6. 【2026-08-19 新增】最新进展快照（工作树证据）

以下为 2026-08-19 下午核实的工作树事实，team-task 以此为起点基线：

**已落地（未提交，git 工作树）：**

- `flowboard/timeline.py`（新增，789 行）— timeline 服务核心骨架；sha256 `7d62422d…b95a494`。
- `tests/test_timeline.py`（新增，629 行，21 个测试，当前全绿）；sha256 `f8575c2d…a8af37b`。
- `server.py`（+33）、`flowboard/database.py`（+82）— v16 迁移与 timeline 路由部分接入。
- `README.md` / `app.js` / `index.html` 少量改动。
- 两个哈希与 planner 验收记录完全一致 → **工作树自上次验收后未被改动**，可安全作为 team-task 起点。

**占位/未开工：**

- `timeline-ui.js`（14 行）：纯字符串渲染 UMD（bounds/renderEditor/renderDashboard/renderSingle/renderAll），无拖拽、右键菜单、磁吸、草稿批次、事件接线。
- `timeline.css`（28 行）、`tests/timeline_ui.test.js`（13 行，node 级渲染断言）。
- 离冻结契约的“可操作 UI + 真实浏览器旅程”（B-004）差距很大。

**阻塞状态（沿 B-00x 编号）：**

- B-002：服务核心 §7.1/§5 字面缺口（attempt 2/2 挂起）→ §8 首个工作包。
- B-003：HTTP 路由矩阵未验收。
- B-004：可操作 UI 与真实浏览器旅程未开始。
- B-005：全量回归、文档收口、Gate 5 边界未开始。

## 7. 【2026-08-19 新增】workflow 切换决定与交接

- 用户于 2026-08-19 显式拍板（满足复盘 §6.5“由用户显式拍板切换”的条件）：**弃用当前 double-workflow run，不重开门 3，不回滚已落地服务端骨架（保留并在其上修复），改用 Claude 原生 team-task（planner / mc-expert / coder 三角色小队）推进门 4 剩余施工。**
- `.copilot-*` 三件套只读冻结：不写、不改、不消费其协议状态；`.copilot-message.md` 的 9 项返工规格与 `.copilot-task.md` 的 C1–C5/D1–D5 定义可只读参考。
- `team-progress/` 目录已存在（内含空的 `double-workflow/` 子目录）；team-task 过程产物按 skill 约定落 `team-progress.md`。
- 旧 `temp.md` / `temp - 副本.md` 为历史草稿，不再被消费，保留不删。

## 8. 本次任务（team-task 首个工作包）：B-002 九项最小闭环

把 B-002 拆成 9 个最小可关闭项，**在现有骨架上修复，不重写、不扩大实现面**。每项必须给出：具体测试名 + 动态 PASS 证据 + 验收方独立负例证据；`STATIC_ONLY` 不能关闭任何一项。现有 21 个测试为回归基线，不得删改。

1. **xlsx 序列号**：整数序列号 `18264..73051` 换算日期；分数/越界行级 422；补整数正例与边界拒收负例。
2. **状态三态**：接受 `已完成`/`未开始`/`进行中`/空；仅 `已完成` 持久化 `done_at`，其余按日期重算；非法状态仍 422。
3. **多行项目聚合**：同名多行聚合为一个项目；仅“项目+轨道+日期+节点名”重复才拒收；preview 列实际节点数，commit 报去重项目数与总节点数。
4. **字段上限**：节点名 500 / 备注 500 / 项目名 200；补 500/501、200/201 边界测试。
5. **导出边界**：恰好 1000 行成功导出且产物可再导入；超限 422 `EXPORT_LIMIT`（含 total/max），禁静默截断。
6. **真实字节 round-trip**：用 `export_timeline()` 返回的真实字节导入新 workspace，断言语义等价、`已完成` 保留、非完成态按日期重算、interval 忽略、done_at 允许时间差。
7. **迁移证据**：v15→v16 备份非空且含代表性存量；对 v16 库重跑 migrate 幂等（user_version=16 且仅一条 version 16 迁移记录）；回滚语义可证；全程隔离库。
8. **undo 证据**：三连续批次 fixture，中间批次 undo 返回 409 且零写入；创建反向软删、删除反向恢复的动态断言。
9. **coverage map**：§7.1 第 1–12 组 + §5 Excel 规则逐条映射到具名动态测试。

> **恢复澄清（2026-08-19，承接 `team-progress.md` 自主裁决 #7，不回溯改写原任务）：**
> 第 9 项的“逐条映射”要求覆盖冻结 §7.1/§5 的全部条款，但不把已明确隔离的
> `GAP-非九项` 偷算成 B-002 已实现。B-002 范围内（项 1–8 + 追加项⑩）及 map 中标为
> `PASS` 的条款必须绑定真实存在、可加载运行的具名动态测试；范围外条款必须显式标为
> `GAP-非九项` 并绑定 B-003 候选去向，不能写成 PASS。第 9 项关门还必须有独立验收器：
> 以冻结条款清单为外部真相，校验无漏项、状态合法、范围内测试可加载、范围外去向非空，
> 并用“删除一条映射”和“伪造测试名”两个阳性对照证明验收器会失败。
> 此澄清只消除第 9 项与既有范围隔离裁定的文字冲突；不关闭任何 `GAP-非九项`，
> 不授权提前进入 B-003，也不代表冻结契约全文已完成。

**门禁：B-002 九项全绿前，禁止进入 B-003 / B-004 / B-005**（不铺 HTTP 矩阵、不做 UI、不做全量回归）。B-002 关闭后按 B-003 → B-004 → B-005 顺序推进，切片验收框架见 §3，红线见 §4。

## 9. 下一动作

1. 把本文件复制为 repo 根 `team-task.md`（整篇即可，§8 即“本次任务”）。
2. 运行 `/team-task`，选择驱动模式（A 人工驱动 / B 深度放权）。
3. team 从 §8 首个工作包开工：coder 在现有骨架上逐项修复，planner/mc-expert 用独立负例逐项验收。
4. 全部切片完成、B-005 收口后落 `WAIT_GATE5_HUMAN`，等用户进真实试用与门 5。

## 10. 【2026-08-19 新增】B-003 冻结工作包：HTTP 路由矩阵

> 前置：B-002 已按 wave-2→wave-3 REWORK→CP3a→wave-4→最终陪审 GO 正式关闭。
> 本包只关闭冻结 API 的 HTTP 黑盒接线及可经 HTTP 观察的遗留契约，不进入 UI/B-004，
> 不执行 B-005 全量回归、文档总收口或 Gate 5 交接。

### 10.1 十一个冻结端点（不得增减）

1. `GET /api/workspaces/{id}/timeline`
2. `GET /api/timeline/projects/{id}`
3. `GET /api/workspaces/{id}/timeline/review`
4. `POST /api/workspaces/{id}/timeline/projects`
5. `DELETE /api/workspaces/{id}/timeline/projects/{project_id}`
6. `POST /api/workspaces/{id}/timeline/batches`
7. `POST /api/workspaces/{id}/timeline/batches/undo`
8. `POST /api/workspaces/{id}/timeline/batches/initial-correction`
9. `POST /api/workspaces/{id}/timeline/imports/preview`
10. `POST /api/workspaces/{id}/timeline/imports/commit`
11. `POST /api/workspaces/{id}/timeline/export`

每个端点必须以真实 HTTP 请求证明 method/path/status、认证/CSRF、权限、请求/响应形状和 service
调用一致；service 直调测试只能作底座，不能替代路由验收。导出严格为 POST→200 `base64+sha256`
JSON，workspace 全量导出；不接受 GET、单项目导出或 `project_ids` 扩展。

### 10.2 有序检查点

- **CP0 · coverage map**：以冻结 §3–§5 为外部真相，逐路由登记 method/path/status、请求/响应、权限、
  service 调用与具名 HTTP 测试。11/11 无漏项；独立验收器的“删除一条路由/伪造测试名”阳性对照必须失败。
- **CP1 · 读取与项目生命周期（1–5）**：补单项目 GET、DELETE 路径/索引、review 完整响应；每路由具备
  HTTP 正例与本路由关键 401/403/404/409/428 负例。
- **CP2 · 批次写入（6–8）**：修正批次/undo/initial-correction 接线；HTTP 证明 CSRF、版本、权限、
  软删和零写入护栏。
- **CP3 · 导入（9–10）**：完成 preview→commit HTTP 旅程；关闭 D-4 同名全行错误清单、D-5 多 sheet/CSV
  提示和 D-7 xlsx 数值单元格类型判定；共享 transfer 层只跑定向回归。
- **CP4 · 导出（11）**：严格 POST、返回 base64+sha256 JSON；真实字节可解码/解析/再导入；关闭 D-6
  项目→轨道→日期→节点名自然序→id。
- **CP5 · 独立关门**：planner 对同一冻结盘面复跑 11/11 路由矩阵、全部写路由 CSRF、代表性权限/
  原子性负例；逐 CP 四态签注，`STATIC_ONLY` 不得关门。

每个 CP 必须“实现 + HTTP 正例 + 验收方独立负例”同批关闭后才进入下一 CP，禁止先铺完再统一验收。

### 10.3 B-002 §D 遗留项归属

- **并入 B-003**：D-4、D-5、D-6、D-7；以及 D-2 中可经 HTTP 黑盒验证的 created_by、
  correction 不钳制/不级联与 no-op、越界 node、软删 correction/undo 404、member 撤 initial-correction 403、
  M3/M5/红橙指标、重叠 row_index、interval 3650/3651、缺版本 428、timeline 入口认证/权限安全界。
- **明确后置且不得假记 PASS**：部分唯一索引兜底直触属于 backend/data follow-up；UI/真实浏览器事件序/
  视觉交互留 B-004；全量历史回归、文档总收口、Gate 5 交接留 B-005。
- **禁止扩展**：不新增 PATCH 改名/恢复、单项目导出、export `project_ids`、分页、缓存或其他未来能力。

### 10.4 B-003 关门条件

CP0–CP5 全部 PASS；真实 `flowboard.db` 未被写入；`.copilot-*` 保持只读冻结；无同一 failure_key 两次独立
失败。关门后才允许进入 B-004。

## 11. 【2026-08-20 新增】B-004 冻结工作包：可操作 UI 与真实浏览器旅程

> 前置：B-003 已由 CP0–CP5 正式关闭，11/11 HTTP 路由与 8/8 写路由 CSRF 均有独立动态证据。
> 本包只关闭冻结 feature01 的生产 UI 接线和真实浏览器交互，不重做 B-003 路由层，不执行 B-005 全量历史回归、文档总收口或 Gate 5 人工验收。

### 11.1 有序检查点

- **CP0 · coverage map**：逐条映射冻结 §3–§5、§7、§8.3 到生产入口、具名浏览器测试和唯一 CP；验收器必须能以“删映射”和“伪造测试名”阳性对照失败。
- **CP1 · 入口与项目生命周期**：登录后真实点击进入三种页面模式；真实读取、新建与 admin 软删；刷新持久化；admin/member/viewer 服务端权限矩阵。
- **CP2 · 本地草稿编辑器**：右键四项、每次重选 single/cascade、钳制/级联、标准磁吸与放大带、状态+日期混合草稿、排序、放弃与离开拦截。拖拽期间网络请求必须为零。
- **CP3 · 提交/冲突/撤销/纠正/复盘**：一次真实 batch POST，payload 带 `mode/magnet/zoom_band`；409 使用服务端最新视图且零写入；刷新持久化；真实 undo；initial correction 的 admin-only 边界。
- **CP4 · 单项目/全项目仪表盘**：共享绝对日历、两轨、重叠分半与展开、阶段区间、今日线、红橙提示、筛选排序，并复用同一右键菜单控制器。
- **CP5 · Excel UI**：真实文件 preview→commit、行级错误、多 sheet/CSV 提示；导出必须使用服务端真实 base64/sha256 字节并在新 workspace 重新上传导入。
- **CP6 · 独立关门**：planner 在新隔离库复跑三条完整旅程：编辑→放弃/提交/刷新/撤销；单/全仪表盘交互；导入→导出→再导入。

每个实现 CP 必须同批交付生产接线、真实 Chromium 正例、独立负例和可观察状态证据；上一 CP 未签注不得进入下一 CP。

### 11.2 浏览器证据硬门

- 关键点击、右键菜单和拖拽必须通过真实浏览器 hit-testing；点击链记录并断言 `mousedown→mouseup→click`。必须有一个“在 mousedown 隐藏目标会吞 click”的 canary 阳性对照。
- `element.click()`、直接调用 handler、只派发单个合成 click、固定向已隐藏目标手工派三事件，均不得作为关门证据。
- DOM 字符串、CSS token、截图、纯函数 Node 单测只作补充；mock fetch、service 直调、孤立 `set_content()` 组件不得替代从生产 `index.html/app.js` 入口发出的真实 HTTP。
- 失败路径须观察网络请求、响应与隔离库前后状态；拖拽零网络、4xx 零写入等阴性结论必须先做探针阳性对照。
- 视觉像素验收属于 Gate 5 人工试用；B-004 只关闭结构、可操作性与冻结交互语义。

### 11.3 文件与范围边界

- `timeline-ui.js` 承载纯状态、渲染与交互控制器；`app.js` 仅做生产 DOM/API 薄接线，禁止借机全局前端重构。
- Node 快测保留为计算层；新增真实浏览器 E2E 文件用于关门。测试只用临时数据库和随机端口，不写真实 `flowboard.db`。
- 禁止新增冻结范围外的改名/恢复、分页、缓存、工作负载、OKR、自动化或其它候选功能。
- 本拆分经 mc-expert 陪审，高置信；留痕为 **Codex custom agent 模拟，非 Claude 原生 mc-expert**。

### 11.4 B-004 关门条件

CP0–CP6 全部 PASS；真实 `flowboard.db` 与 `.copilot-*` 指纹不变；无同一 failure_key 两次独立失败。关门后才允许进入 B-005。
