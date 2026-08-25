# feature01 Gate 5 UX 重对齐任务（冻结执行合同）

> 冻结日期：2026-08-21
> 冻结来源：用户完成 Gate 5 次轮真实体验反馈后，显式要求冻结一份冷启动自足任务。
> 当前状态：`CP0 PASS（§12）· CP1 完成 · H1 已通过并回填 §13（2026-08-21）· CP2/CP3/CP4 已执行并回填 §14（2026-08-21 深夜）· 返回 WAIT_GATE5_HUMAN`
> 最高产品状态：`WAIT_GATE5_HUMAN`
> 归属：继续属于 feature01，不另开 feature。
> 冷启动规则：新会话先完整阅读本文件；执行本任务不依赖聊天记录。除追溯争议外，不需要先通读 feature01 全部历史稿。

---

## 0. 用户最终拍板速览（本任务不得改写）

### 0.1 次轮反馈问题 1：单项目仪表盘偏离冻结效果

真实项目 `跑鞋研发 2026` 的当前单项目仪表盘，与开工前确认并锁定的仪表盘效果差距过大。后续不能把“已有页面可操作”当作视觉验收通过。

当前视觉外部基线：

- `（视觉UI升级留档）single-project-visual-options.html` 的方向 A「大标题 · 白卡」浅色版。
- `mainline-feature01.md` 与 `9-GATE3_TECH_FREEZE.md` 中已经冻结的浅色语义、六阶段色义、链式时间段、主线/并行双轨、绝对日历和今日线。
- 本轮允许重新组织页面信息层级与布局，但不得借视觉返工推翻既有业务与交互契约。

### 0.2 次轮反馈问题 2：主导航聚焦 feature01

平台当前重心改为 feature01 的项目时间管理。侧边栏最终只保留：

1. `我的工作`
2. `已归档`
3. `回收站`

必须从主导航隐藏：

- 独立的 `仪表盘` 菜单。
- 独立的 `时间管理` 菜单（已被后续反馈覆盖，见 §0.3）。
- 整个 `看板` 区块及其看板列表，例如 `Q3 产品路线图`、`Mc-test`。

“隐藏”严格表示 UI 降级：feature00 的代码、API、数据、schema、权限、路由、测试和历史证据不得删除、改名、软删、迁移或弱化。前端隐藏也不得被冒充为服务端权限控制。

### 0.3 次轮反馈问题 3：`我的工作 = 项目时间管理`

- `我的工作` 成为登录后的默认主页和平台主入口。
- `我的工作` 直接承载现有 feature01 项目时间管理能力，不再保留独立“时间管理”导航项。
- 原 feature00 的“我的工作”页面归档隐藏，不再作为默认主页。
- 新主页展示 timeline 项目，即通过 Excel 导入或网页创建的项目；不得继续用 boards/tasks 旧看板任务充当主页主体。
- 新主页必须能自然进入现有时间表编辑器、单项目仪表盘和全项目仪表盘。
- 主页与仪表盘先从低成本静态 HTML 重新确认；未获用户明确通过，不得接入生产页面。

### 0.4 用户对“共享、实时编辑”的最终澄清

“项目时间管理、共享、实时编辑”只是对现有 feature01 能力的概括：

- 沿用现有注册成员可见、admin 全项目可写、member 仅可写自己创建项目的权限模型。
- 沿用现有草稿批次、版本冲突、409 最新视图、提交与撤销能力。
- 不新增 WebSocket、在线状态、实时光标、逐单元格协同、Google Docs/Sheets 式多人编辑。
- 不新增访客、公开链接、邀请流程、SSO、新角色、项目 ACL 或字段级权限。
- 不重开或改写现有数据模型、API、权限、并发、Excel、审计、迁移契约。

以上澄清已经消除需求歧义，不再为“共享/实时”另开问卷或工作包。

---

## 1. 当前项目事实（冷启动基线）

1. feature01 门 4 已由 CP6 独立终签 PASS：32 条终态为 25 PASS + 7 OUT_OF_SCOPE，零 GAP/CONFLICT。
2. 当前且最高状态为 `WAIT_GATE5_HUMAN`；本任务是 Gate 5 真实体验后的 UX/入口返工，不是新 feature。
3. 门 4 固化 commit：`c5e9820 交付 feature01 门4实现并停在 WAIT_GATE5_HUMAN`。
4. 正式实现已存在：timeline 专表、服务/API、权限、Excel 导入导出、编辑器、单项目仪表盘、全项目仪表盘、复盘与自动化测试。
5. 仓库真实 `flowboard.db` 仍为 schema v15；本任务不得启动或迁移真实库。
6. Gate 5 体验使用 `%TEMP%\flowboard-gate5-trial\flowboard-trial.db`。当前体验数据至少包含用户创建的 `Mc Prj 01`，以及 2026 年 1–12 月、15 节点的 `跑鞋研发 2026` 示例项目；体验数据不是生产 fixture 或正式库内容。
7. 根目录的 `start-gate5-trial.cmd` 与对应 README 说明是本轮后续新增、当前未必已提交；执行者必须先用 `git status --short` 核实，不得假定工作树干净。
8. 工作树还可能包含用户或历史 agent 的无关 `mc-plan/`、`team-progress/`、异常目录及过程文件。它们不属于本任务，不得 reset、checkout、删除、移动、覆盖或顺手提交。

---

## 2. 权威顺序与覆盖关系

本任务内冲突按以下顺序处理：

1. 用户 2026-08-21 及之后的最新明确指令。
2. `mainline-feature01.md` 的产品范围与完成边界。
3. `9-GATE3_TECH_FREEZE.md` 的数据/API/权限/并发/Excel/迁移契约。
4. feature01 `STATE.md` 的当前业务与视觉冻结项。
5. 本文件的执行步骤、允许范围与 done_when。
6. 用户后续明确批准并记录版本的 Gate 5 静态 HTML。
7. 更早的需求草案、问卷、历史样张与 agent 建议。

覆盖说明：

- §0.2/§0.3 只覆盖平台主导航、默认主页和 feature00 的展示优先级，不覆盖 feature00 的底层能力，也不覆盖 feature01 的技术契约。
- 本文件 §0 是用户最新指令的原样固化记录，不代表任务文档自身可以越级修改 mainline；若后续发现实质范围冲突，必须按 §7 停手并由用户拍板。
- “我的工作 + 时间管理”并列的早期反馈已被最终决定 `我的工作 = 时间管理` 覆盖；执行者不得恢复独立“时间管理”菜单。
- 用户最新澄清覆盖任何把“共享/实时编辑”解释为新增协同能力的推断。
- 静态 HTML 是本轮信息架构与视觉确认工具，不能自行覆盖以上文字契约；用户明确批准后，它才成为生产接入的外部视觉参照。

---

## 3. 本任务目标

在不改变 feature01 已有业务能力和后端契约的前提下，完成以下结果：

1. 把平台默认用户旅程从 feature00 看板工作台切换为 feature01 项目时间管理。
2. 把 `我的工作` 重建为 timeline 项目主页，展示 Excel 导入/网页创建的项目。
3. 让用户能从新主页清楚进入时间表编辑器、单项目仪表盘和全项目仪表盘。
4. 让单项目仪表盘重新对齐开工前冻结的方向 A「大标题 · 白卡」视觉与既有时间轴表达。
5. 保留 feature00 全部底层能力和回归，只从主导航与默认主页隐藏。
6. 用真实浏览器和隔离体验数据完成接入验证，再返回 Gate 5 供用户复测。

---

## 4. 明确不做（硬边界）

本任务不得：

- 新建 feature02，或把本任务扩成整个平台重写。
- 删除、改名、迁移、软删或破坏 feature00 的 boards/tasks/groups、API、页面代码、数据、测试和历史文档。
- 修改 schema、timeline 专表、迁移 v16、服务端 API、权限、审计、并发/undo 或 Excel 契约。
- 新增 WebSocket、轮询同步、在线状态、实时光标、协同文档、公开分享、访客或邀请链接。
- 新增工作负载、OKR、工时、预算、资源、审批、自动化、AI、CRM、Webhook、表单、SSO、原生 App、每周看板、md/json 导入、项目改名或恢复。
- 推翻固定六阶段、主线/并行双轨、链式段、绝对日历、今日线、右键四项菜单、双模式拖拽、无默认档、磁吸/放大带或草稿批次。
- 将静态样张写死为第二套业务逻辑、第二套 API client 或第二份 timeline 状态。
- 在静态阶段修改生产 `index.html`、`app.js`、生产 CSS/JS、server 或数据库。
- 写入、迁移、恢复、重建真实 `flowboard.db`。
- 未经用户另行授权执行 commit、push、发布、部署、上线或对外交付。
- 为了通过测试而删除/弱化旧测试、放松权限、伪造数据或把 UI 隐藏冒充服务端授权。

---

## 5. 交付策略与有序检查点

必须严格按 CP0 → CP1 → 人工门 H1 → CP2 → CP3 → CP4 推进。上一检查点未满足，不得提前铺下一检查点。

### CP0 · 现状盘点与允许路径冻结

只读核实并记录：

- 当前登录后默认入口与 `我的工作` 触发链。
- 侧边栏 `仪表盘`、`时间管理`、`已归档`、`回收站` 和 `看板` 区块的 DOM/事件来源。
- feature01 编辑器、单项目仪表盘、全项目仪表盘的生产入口与复用组件。
- feature00 页面在隐藏导航后的代码/路由保留方式。
- 本任务实际需要修改的精确文件 allowlist，以及这些文件是否已存在用户改动。

CP0 只允许读取；不得修改生产文件。若拟改文件与无关脏改动重叠且无法可靠区分归属，立即停手。

### CP1 · 静态 HTML 重新确认

在 `feature-01-项目时间管理-仪表盘/` 内新增一份明确命名的 Gate 5 静态 HTML，集中展示：

1. 完整应用壳和最终侧边栏：`我的工作 / 已归档 / 回收站`。
2. 以 timeline 项目为主体的“我的工作”默认主页。
3. Excel 导入、网页新建项目、进入编辑器、进入单项目/全项目仪表盘的清晰入口。
4. 使用 `跑鞋研发 2026` 等代表性静态数据展示项目列表、当前阶段、临近节点、逾期提示和时间范围。
5. 重新对齐方向 A 的单项目仪表盘首屏，保留六色、链式、双轨、今日线及节点语义。
6. 不出现旧看板列表、旧任务表或独立“仪表盘/时间管理”主菜单。

静态阶段只允许修改：

- 本任务文档（仅补充 CP0 盘点结果和人工批准记录）。
- feature01 目录内本轮新建的静态 HTML。

静态 HTML 只使用本地静态数据，不发 API、不写数据库、不接生产事件处理器。样张以结构、信息层级、操作路径和视觉方向为验收对象，不做无依据的整页像素哈希金标。

### H1 · 静态稿人工冻结门（硬门）

用户必须明确确认以下四项后，才能进入生产接入：

1. 侧边栏与默认入口。
2. “我的工作”主页的信息架构与主要操作路径。
3. 单项目仪表盘的视觉层级与时间轴效果。
4. feature00 只隐藏、不删除的呈现边界。

确认后在本文件记录：静态 HTML 路径、SHA-256、确认日期、用户批准项和仍留 Gate 5 微调项。样张后续若发生结构性修改，必须重新过 H1。

### CP2 · 最小生产接入

H1 通过后才允许：

- 按 CP0 的精确 allowlist 修改平台壳、默认路由、侧边栏和必要样式。
- 复用现有 timeline UI、API client、权限与状态管理，把真实 timeline 项目接入新“我的工作”。
- 让登录后默认进入“我的工作”，并能到达编辑器、单项目和全项目仪表盘。
- 从主导航隐藏 feature00 旧入口，同时原代码、路由、数据和测试保持不变。

禁止复制第二套 timeline 业务逻辑；如现有组件不能复用且必须改服务端或技术冻结契约，停手升级用户。

### CP3 · 仪表盘视觉重对齐

- 单项目仪表盘逐项对齐 H1 获批样张与方向 A 基线。
- 全项目仪表盘和编辑器沿用同一浅色语义 token，不另立视觉语言。
- 六阶段颜色、链式段、双轨、今日线、节点状态、重叠/展开与右键四项仍使用现有服务端数据和交互控制器。
- 视觉改动不得改变派生指标、日期语义、批次提交、权限或 API 响应。

### CP4 · 独立回归与 Gate 5 复测交接

必须提供动态证据：

- 登录后默认主页与三个保留菜单的真实浏览器旅程。
- “我的工作”只展示 timeline 项目，不展示 boards/tasks 旧内容。
- Excel 导入或网页新建的项目能出现在主页，并能进入编辑器及单双项目仪表盘。
- admin/member 现有读写权限、409 冲突、草稿提交/放弃/撤销语义不变。
- feature00 主入口已隐藏，但旧数据、API、路由和回归测试未删除或弱化。
- 关键点击、右键菜单和拖拽使用真实 hit-testing 与 `mousedown → mouseup → click` 事件序；不得只用 `.click()` 或直接调 handler 关门。
- Python、Node、真实 Chromium 和 `git diff --check` 按受影响范围及全量门禁通过。
- 所有数据库写入只发生在临时/隔离数据库；真实库保持 v15、指纹不变。

CP4 完成后只允许签注：`Gate 5 UX 重对齐已接入，返回 WAIT_GATE5_HUMAN 等待用户复测`。不得仅凭本任务宣称 Gate 5 PASS、真实迁移完成、已发布或已上线。

---

## 6. 全局 done_when

以下条件必须全部成立：

1. 用户明确批准一份 Gate 5 静态 HTML，批准版本与批准项已留痕。
2. 侧边栏只显示 `我的工作 / 已归档 / 回收站`；无独立“仪表盘”“时间管理”或“看板”区块。
3. 登录后的默认“我的工作”呈现 timeline 项目主页，数据来自现有 feature01 能力。
4. Excel 导入/网页创建项目能在主页出现，并可进入编辑器、单项目仪表盘与全项目仪表盘。
5. 单项目仪表盘能逐项对应方向 A、浅色 token、六色、链式、双轨、绝对日历、今日线和既有节点交互。
6. feature00 不再占据主导航或默认主页；其代码、API、数据、schema、权限、路由、测试和历史证据未删除、改名或弱化。
7. feature01 既有数据、API、权限、并发、Excel、审计、撤销和迁移契约未被重开或改变。
8. 没有新增“共享/实时编辑”产品能力，也没有偷偷纳入任何未来候选。
9. 新增入口测试、真实 Chromium 旅程及 feature00/feature01 回归全部通过，零 skip/删测换 PASS。
10. 真实 `flowboard.db` 未写入、未迁移、未恢复或重建；未执行未授权的 commit/push/发布/部署。
11. 交付状态诚实返回 `WAIT_GATE5_HUMAN`，等待用户在真实体验中复测，不冒充 Gate 5 完成。

---

## 7. 强制停手条件

出现任一情况立即停止并报告，不得硬干：

- H1 静态稿尚未获用户明确通过。
- 用户对默认主页、侧边栏或视觉方向提出新的冲突意见。
- 需要修改 `mainline-feature01.md` 的产品范围或 `9-GATE3_TECH_FREEZE.md` 的技术契约。
- 需要修改 schema、服务端权限、API、并发、Excel、迁移或新增协同能力。
- 需要删除、改名、软删或迁移 feature00 的代码、数据、路由或测试。
- 视觉重排必须破坏既有 feature01 交互契约才能实现。
- 拟改文件与已有无关工作树改动重叠，无法可靠保留用户内容。
- 同一 `failure_key` 连续两次独立实现或验证失败。
- 需要放宽验收标准、删测试或伪造证据才能通过。
- 需要触碰真实库、commit、push、发布、部署、上线或对外交付，但用户尚未单独授权。

---

## 8. 每次交接必须留下的证据

每个 CP 的报告至少包含：

- 当前 CP 与裁定：PASS / REWORK / BLOCKED。
- 精确修改文件列表和未触碰文件声明。
- 对应 done_when 与动态命令/结果。
- 正例、关键负例及数据写入位置。
- `AUTONOMOUS_DECISIONS`：仅限不改变范围的可回滚实现细节。
- `PENDING_HUMAN`：只列真正需要用户体验判断的事项。
- `OPEN_BLOCKERS` 与 `failure_key` 计数。
- 真实库、feature00、技术冻结契约和无关脏工作树的保护情况。

---

## 9. 冷启动最短阅读路径

新执行会话按顺序读取：

1. 本文件（完整读取）。
2. `STATE.md` 顶部当前状态与 §3 视觉/交互基线。
3. `mainline-feature01.md` §1、§4、§5、§6、§7、§9、§10。
4. `9-GATE3_TECH_FREEZE.md` §0、§2、§3、§4、§8、§9、§11。
5. `（视觉UI升级留档）single-project-visual-options.html` 中方向 A。
6. CP0 再按实际入口读取 `index.html`、`app.js`、timeline UI/CSS 和相关测试；不得盲扫后直接改代码。

中央陪审留痕：本任务冻结前已完成 mc-expert 防漂移陪审，结论为高置信 `GO with changes`；调用的是 **Codex custom agent 模拟，非 Claude 原生 mc-expert**。

---

## 12. CP0 盘点结果（2026-08-21 · 只读核实 · 裁定 PASS，零生产文件修改）

### 12.1 登录后默认入口与「我的工作」触发链

- 页面加载 `app.js:283` → `restoreSession()`（`app.js:33`）→ `GET /api/session` → `refresh()`（`app.js:65`）→ `GET /api/bootstrap`（可带 `?board=` 深链）→ 主内容渲染 **feature00 看板工作台**（`renderBoard`，`app.js:129`）。
- 侧边栏「我的工作」当前是**纯装饰锚点** `<a class="nav-item active" href="#">`（`index.html:21`），无任何点击处理器；登录后默认主页实际 = bootstrap 返回的首个活跃看板。
- feature01 唯一生产入口：`#timelineBtn`（侧边栏「时间管理」按钮，`index.html:21`）→ `openTimeline()`（`app.js:46`，`mode='home'`）→ `#timelineModal` 全屏浮层（`index.html:36`）→ `#timelineBody` 由 `timeline-ui.js` 的 `FlowboardTimeline.renderWorkspace` 渲染。

### 12.2 侧边栏各菜单 DOM/事件来源（`index.html:21-22` + `app.js:270` 绑定行）

| 菜单 | DOM 来源 | 事件/处理函数 | CP2 处置 |
|---|---|---|---|
| 我的工作 | `a.nav-item.active href="#"` | **无 handler（装饰）** | 改造为 timeline 主页真实默认入口 |
| 仪表盘 | `#dashboardBtn`（另 topbar 移动端 `#mobileDashboardBtn`，`index.html:26`） | `manageDashboards`（`app.js:257`，feature00 跨看板仪表盘） | 从主导航隐藏；**元素与可点击性必须保留**（见 12.6 测试约束） |
| 时间管理 | `#timelineBtn` | `openTimeline`（`app.js:46`） | **该按钮本体改造/重标为「我的工作」并保留 id**（见 12.6）；不再出现独立「时间管理」菜单 |
| 已归档 | `#archivedBtn` | `showArchivedBoards`（`app.js:190`） | 保留 |
| 回收站 | `#trashBtn` | `showTrash`（`app.js:192`） | 保留 |
| 看板区块 | `.side-section`（`#addBoardBtn` + `#boardList`，由 `renderSidebar` `app.js:76-79` 渲染） | `addBoard` / `data-board` 换板 | 整块隐藏；`renderSidebar` 依赖 `#boardList` 节点存在，须保 DOM 仅视觉隐藏或加空值守护 |
| 底部设置 | `a.nav-item`（无 handler） | — | 保留为壳层元素 |

### 12.3 feature01 三屏生产入口与复用组件（全部经 `#timelineModal` + `timeline-ui.js` 单模块）

- **项目列表 home**：`renderWorkspace` 项目卡（`data-timeline-open="editor|single"` 按钮）；**编辑器**：`renderEditor` + `bindEditor`（`app.js:44` 注入 onSubmit/onAdd/onUndo/onCorrect/onReview）；**单项目仪表盘**：`renderSingle` → `renderDashboard` + `bindDashboard`；**全项目仪表盘**：`renderAll`（项目多选筛选 + 4 键排序 + 红橙点 `riskMarkers`）。
- 模式切换：`openTimelineMode`（`app.js:47`）；`#timelineBody` 委托点击 `data-timeline-open` / `data-timeline-mode-target`（`app.js:278`）。
- Excel 导入导出：`renderTransfer` + `#timelineBody` 委托 change/submit（`app.js:276-277`）→ `previewTimelineImport` / `commitTimelineImport` / `exportTimelineWorkspace`；网页新建项目：`form[data-timeline-create]` → `createTimelineProject`（`app.js:48`）。
- 数据源：`GET /api/workspaces/{id}/timeline`（全量视图）、`GET /api/timeline/projects/{id}`（单项目）。
- 共享组件：右键四项菜单 `contextMenu` + `bindContextController`（`timeline-ui.js:23-24`）、`stage_intervals` 重叠分半/展开、绝对日历 + 今日线。

### 12.4 feature00 隐藏后的代码/路由保留方式

- 隐藏 = 纯 UI 层降级：只隐藏导航 DOM；boards/tasks/groups 渲染（`renderBoard/renderTable/renderKanban/renderCalendar/renderSchedule/renderChart`）、全部 API 路由、`?board=` 深链、既有测试一行不动。
- `server.py` `PUBLIC_PATHS` 与所有服务端代码零改动；`flowboard/` 服务包不进 allowlist。
- 服务端权限、schema（真实库 v15）、审计、并发、Excel、迁移契约零触碰。

### 12.5 CP2 精确修改文件 allowlist（H1 通过后才可动工）

1. `index.html` —— 侧边栏三菜单化、主内容区加「我的工作」容器、隐藏看板区块与移动端仪表盘按钮
2. `app.js` —— 登录后默认落「我的工作」timeline 主页；`openTimeline` 目标从浮层改为主内容（或壳内双态）；`renderSidebar` 空值守护
3. `timeline-ui.js` —— `renderWorkspace` home 模式升级为 H1 获批的主页版式
4. `timeline.css` —— 主页 + 仪表盘视觉对齐（CP3 范围）
5. `styles.css` —— 仅当壳层（侧边栏/主区布局）需要配套微调时
6. `tests/`（**只新增不改旧**）—— 新主页/入口 e2e

**脏改重叠检查**：上述 5 个生产文件在 `git status` 中全部干净（基线 `c5e9820`）；当前工作树脏改仅 `README.md`、`mc-plan/`、`team-progress/`、`start-gate5-trial.cmd`（未跟踪）等过程文件，与本 allowlist **零重叠**，无停手情形。

### 12.6 关键测试约束（决定 CP2 隐藏策略，CP0 新发现）

- `tests/test_timeline_e2e.py` 有 **12+ 处**点击 `#timelineBtn`；`tests/test_views_e2e.py:196` 点击 `#dashboardBtn`。`physical_click`（`test_timeline_e2e.py:208-212`）走 `bounding_box()` + 真鼠标序列，`display:none` 元素 `bounding_box()` 返回 null 直接崩；`locator.click()` 同样要求可见。
- **结论**：#timelineBtn / #dashboardBtn 在 CP2 不得删除、不得 `display:none`。可行路径 = ① `#timelineBtn` 保留 id 并重标为「我的工作」入口（元素即原「时间管理」按钮，测试零改动继续通过）；② `#dashboardBtn`（feature00 仪表盘）从主导航移出但降级放置在仍可见可达的位置（如设置区/底部折叠区，具体呈现边界属 H1 第 4 项待用户拍板）；③ `#mobileDashboardBtn`、看板区块无测试引用，可安全视觉隐藏（`#boardList` 保 DOM 节点）。
- 本约束不构成放宽验收：79 个 Python 测试 + 5 个 Node 测试文件仍须原样全绿。

---

## 13. CP1 产物与 H1 人工门记录（2026-08-21 用户批准 · 已关门）

- **静态稿路径（H1 批准版）**：`feature-01-项目时间管理-仪表盘/（Gate5静态稿·终稿）项目工作台全流程.html`（整合终稿：方案A 四屏 + 屏A 替换为案3优化版主页 + 全局更正林晓/4 成员；CP1 首稿 `（Gate5静态稿）我的工作主页与单项目仪表盘.html` 已被其取代，留档不删）。
- **SHA-256**：`d21e4d7fb8f6380828a387db554c0ab61461fa324b4a7287df968cf96ae8fc5d`
- **用户确认日期**：2026-08-21（用户对终稿四屏过目后明确答复「通过」）。
- **批准项（H1 四项，全部通过）**：
  1. **侧边栏与默认入口**：我的工作（登录默认页）/ 全项目仪表盘（独立顶层）/ 项目分组（逐项目直达）/ 已归档 / 回收站 / 底部设置；看板区块整体隐藏不删。
  2. **「我的工作」主页信息架构与操作路径**：IA=方案A 项目工作台（问卷 Q1:1–Q5:1）；主页=案3优化版——KPI 四格（逾期红、可点击下钻联动标签）＋【我的项目】一行一项目整行可点＋【团队项目】一成员一条等宽长条（40px 头像＋负责项目药丸，他人项目 🔒 只读）＋右栏仅「最新动态」随标签联动（我·最近 6 条 / 团队·最近 20 条，时间倒序新在上）。
  3. **单项目仪表盘视觉层级与时间轴效果**：屏B 项目页双页签「仪表盘｜时间轴编辑器」（零跳转真实切换，审计页签预留灰置）；方向A 浅色 token、六阶段色、链式段、主线/并行双轨、绝对日历标尺、今日线、右键四项菜单注记齐备。
  4. **feature00 只隐藏不删除的呈现边界**：屏D 归位「设置→高级·经典功能」；UI 隐藏不删，旧「仪表盘」按钮保留可点击（满足 §12.6 测试约束），权限与 API 契约零改动。
- **附带拍板（2026-08-21，随主页定稿一并收口）**：IA 问卷 Q1–Q5 全按推荐（1/1/1/1/1）；主页=案3优化版（KPI 摘要条+分区标签）；遗留四题按推荐默认——负责人=创建人(created_by)、动态=动作级直陈、动态范围=仅时间管理动作、页名保留「我的工作」。KPI 四格点击下钻联动标签已按拍板在终稿接线。
- **数据口径**：真实＝团队 4 人（林晓 u1 admin · 周然 u2 · 陈默 u3 · 王敏 u4 member）· 两项目 created_by=u1 · audit_log 动态 2 条（今天 09:36/09:40）；「越野跑鞋概念 2027」（周然）及其动态为橙标示意，仅演示只读态/排序/容量，不与真实数据混充。
- **仍留 Gate 5 微调项**：阶段色量产绿对白底对比留真实数据微调（STATE §3）；磁吸「强」档参数留集成验收微调（STATE §3）；CP2 中 `#dashboardBtn` 降级放置的具体位置（设置区/底部折叠区，§12.6 允许路径）以最小可见方案实现，如与用户预期不符再调。
- **过程稿留档（不作生产参照）**：`（Gate5静态稿）我的工作主页与单项目仪表盘.html`、`（IA对照）主页-项目-仪表盘逻辑结构选型.html`、`（Gate5静态稿·方案A）项目工作台全流程.html`、`（Gate5静态稿·主页信息总览）三案对照.html`、`（Gate5静态稿·主页信息总览）案3优化版.html`。
- 注：静态稿若发生结构性修改，须重新过 H1。**H1 已于 2026-08-21 关门，§5 CP2 允许路径解锁。**

## 14. CP2/CP3/CP4 执行与证据（2026-08-21 深夜 · 单会话施工 · /free B 自主流）

### 14.1 裁定与范围

- **CP2 最小生产接入 PASS · CP3 视觉重对齐 PASS · CP4 回归 PASS**；签注：`Gate 5 UX 重对齐已接入，返回 WAIT_GATE5_HUMAN 等待用户复测`（不宣称 Gate 5 PASS）。
- 施工方式：本会话单 session（用户拍板）；mc-expert 陪审前置意见全部消化（review 链于 timeline GET 成功之后、壳迁移先过烟囱门、条件落页列 PENDING_HUMAN 首项等）。

### 14.2 精确修改文件（全部在 §12.5 allowlist 内）

- 生产 5 件：`index.html`（侧边栏方案A + #boardWorkspace 包裹 + #timelineView 内联容器 + #timelineModal 空壳保留 + #loadState 迁 topbar）；`app.js`（openTimeline/openTimelineMode/closeTimeline 主内容化、落页探测 landTimelineHome、loadTimeline 在飞去重、review 链式拉取、setHomeTab 标签联动、点击委托扩展 kpi/tab/member-open）；`timeline-ui.js`（renderWorkspace home 分支重写为终稿屏A版式、bindContextController 菜单贴底上翻/右缘钳制、renderSingle 增量补屏B KPI 摘要行与图例条）；`timeline.css`（主页版式+图例/摘要样式+`.tl-section[hidden]` 修正）；`styles.css`（`.legacy-hidden`+`.nav-button`）。
- 测试只增：`tests/test_gate5_home_e2e.py`（新增 6 用例；独立 harness，不继承父类避免整套双跑）。
- **未触碰**：`server.py`、`flowboard/` 全目录（schema/API/权限/Excel/迁移契约零改动）；既有全部测试文件零修改、零删除、零 skip。

### 14.3 行为与正负例（对应 §6 done_when）

- 正例：有项目且可写 → 登录默认落「我的工作」主页；KPI 四格下钻联动标签、成员长条药丸进单项目仪表盘、右栏动态我·6/团队·20 联动（test_gate5_home_kpi…）；Excel 导入/网页新建/编辑器/撤销全链路原样可用（既有 24 个 timeline e2e 零改动全绿）；单项目仪表盘补齐屏B头部 KPI 摘要行与图例条（CP3，纯增量，Node 字符串断言全保留）。
- 关键负例：无 timeline 项目 → 登录停留经典看板（既有 `.task-row` 类等待语义不变）；viewer 不探测、无 403 噪音、手动进入被服务端拒（test_gate5_viewer…）；URL 带 `?board/?view/?month` → 不落页（恢复意图优先）；删除最后一个项目 → 主页稳定空态零 JS 错误。
- 数据写入位置：全部测试库在 %TEMP% `tempfile.TemporaryDirectory`；真实 `flowboard.db` 以只读连接核实 `PRAGMA user_version=15` 未变。

### 14.4 回归与门禁（主跑，本会话直接执行）

- Python：`python -m unittest discover -s tests` → **`Ran 148 tests in 364.529s` / `OK`**（既有 142 + 新增 6，既有用例零修改）。
- Node：6 个 `tests/*.test.js` 全 OK（含锁字符串断言的 `timeline_ui.test.js`）。
- `git diff --check`：仅 `mc-plan/Mc思考01….md` 2 处尾随空格（早前会话遗留的已修改文档，非 Gate5 产物，原样保留）；Gate5 五件生产文件零告警。
- 过程中定位并修复的三处真缺陷：①全项目视图右键菜单向下展开被挤出 1280×800 视口、真鼠标静默 miss（贴底上翻+右缘钳制）；②落页隐藏 #boardWorkspace 造成 #loadState 可见性竞态（迁 topbar 常显）；③落页探测与手动打开的双重渲染竞态（openTimeline 幂等短路 + loadTimeline 在飞去重 + 探测复用同一拉取）。

### 14.5 AUTONOMOUS_DECISIONS（不改范围、可回滚的实现细节）

1. 条件落页：可写/admin 且已有 timeline 项目才默认落主页，否则停留经典看板（§6 #3/#6 的落地形态，关联 PENDING_HUMAN 首项）。
2. 右键菜单贴底向上翻转、贴右缘左移钳制。
3. `#loadState` 自看板工具栏迁至 topbar（常显，消除可见性竞态）。
4. 「我的工作」已可见时点 #timelineBtn 幂等短路不重取（刷新走其他入口）。
5. 成员长条药丸用独立钩子 `data-timeline-member-open`（保证 `data-timeline-open`+`data-project-id` 全 DOM 唯一，physical_click 严格模式安全）。
6. 主页保留工具栏四模式按钮与新建项目表单（既有测试钩子要求；终稿屏A未含，作为弱化工具条呈现）。
7. 成员长条不显示角色标签（bootstrap members 无 role 字段）。
8. 动态「今日/昨日」计数按 UTC 日期近似（服务端 created_at 为 UTC isoformat，演示级精度，未改服务端）。

### 14.6 PENDING_HUMAN（真正需要用户体验判断）

1. **条件落页 vs 无条件落页**：当前无项目时停留经典看板（保住空团队引导与既有回归语义）；若期望「无项目也强制落我的工作（空态引导页）」，需改测试契约再动。
2. `#dashboardBtn` 降级位置现为侧边栏底部「经典仪表盘」（§13 预告的最小可见方案）；是否符合预期。
3. 主页工具条（四模式按钮+新建表单+Excel 导入导出区）在终稿屏A中不存在，现以弱化形式保留在主页顶部；是否需要在 CP 后续轮次把它收进「更多」或项目页内。

### 14.7 CP4 独立复核（子代理 · 2026-08-21 深夜 · 四项全过）

- **① Python**：子代理独立复跑 `python -m unittest discover -s tests` → `Ran 148 tests in 334.311s` / `OK`（退出码 0；首跑判定行被 server 日志挤出管道尾，按预案完整落盘重跑取证，两次时长一致）。
- **② Node**：6 个 `tests/*.test.js` 逐文件 6/6 OK。
- **③ 改动面**：已跟踪修改全部在允许清单内（Gate5 五件生产文件 + README/STATE/mc-plan 文档）；**`server.py` 零改动、`flowboard/` 目录 12 个 .py 零改动**（scoped 双重核对为空）；untracked 超清单项（team-progress/ 等）均为会话起始前已存在的早前产物。
- **④ 真实库**：sqlite3 只读连接 `PRAGMA user_version` → **15**，未写库。
- 结论：四项全部通过，无红线项。

### 14.8 OPEN_BLOCKERS

- 无（failure_key 计数 0）；三处过程失败均已定位修复并回归（14.4）。

### 14.9 保护情况声明

- 真实库 v15 未写入/未迁移/未恢复/未重建；feature00 代码/API/数据/路由/测试未删未改未弱化（#boardList/#addBoardBtn 留 DOM 仅 UI 隐藏，#dashboardBtn 降级至底部「经典仪表盘」可见可点，#timelineBtn 保 id 改文案）；门 3 技术冻结契约未重开；未 commit/push/发布/部署（提交授权留用户）；无关脏工作树（team-progress/、mc-plan/ 等早前未跟踪产物）原样未动。

---

## 15. Gate 5 人工复测反馈修复（2026-08-22）

### 15.1 触发与根因

- 用户对生产页截图反馈：单项目仪表盘的整体效果、操作手感及拖拽效果与 H1 已确认静态终稿差距明显，并直接授权修复。
- 对照 `（Gate5静态稿·终稿）项目工作台全流程.html` 屏 B 与 `（交互样张）node-drag-magnetism.html` 后确认三类根因：节点长文案常驻导致重叠；阶段条与节点纵向中心未共线且未完整复用服务端 `segments[]`；仪表盘右键菜单只有动作标记，没有真实拖拽控制器。
- 按核心文件改动门禁先行完成 mc-expert 中央 KB 陪审；结论为 HIGH 置信度，建议用跨页共享的项目草稿状态、绝对日历映射与既有 batch API 收口，未要求改服务端或 schema。

### 15.2 已修复行为

- 单项目页恢复终稿层级：项目内页签、紧凑标题/KPI、月份标尺、双轨链式阶段段、今日线、图例与卡片底部操作区；项目页不再常驻展示全局新建/Excel 大工具区。
- 节点命中区继续保持 28×28；节点长文案改为 hover/focus 浮层，阶段条与节点中心精确对齐，跨区间连线按服务端 `segments[]` 绘制。
- 右键节点一次授权后可真实水平拖动：绝对日期换算、按 1 天吸附；顺延仅影响同轨后续节点；拖动时显示 21 天放大镜、旧/新日期、位移及边界。
- 松手只写入前端草稿并保留原位置空心标记，不立即请求服务端；再次未授权拖动无效；点击「更新日期」才通过既有 batch API 一次提交。支持撤销本次移动、放弃草稿及 Esc 取消当前拖动。
- 单项目仪表盘与时间轴编辑器共用同一份项目草稿，页签切换不丢失未提交改动；全项目仪表盘也读取对应项目草稿预览。

### 15.3 修改面与验收证据

- 生产：`app.js`、`timeline-ui.js`、`timeline.css`；测试新增：`tests/test_gate5_home_e2e.py` 的真实鼠标视觉/拖拽用例。`server.py`、`flowboard/`、schema、权限与 API 路由均未修改。
- Node：6 个测试文件全部通过（`timeline_ui.test.js` 24 项断言通过）。
- Chromium：Gate 5 主页/仪表盘/编辑器专项组 **10/10 OK**；新增用例覆盖节点/阶段条中心误差 ≤1.5px、长文案默认隐藏、右键一次授权、21 天放大镜、拖动期间零 POST、松手草稿化、二次未授权拖动无效、单次 batch 提交。
- Python：`python -m unittest discover -s tests` 全量执行退出码 0；discover 共 **149** 项。
- 真实 `flowboard.db` 仅以只读 URI 核实 `PRAGMA user_version=15`；未迁移、未写库。范围内 `git diff --check` 无空白错误（仅换行风格提示）。

### 15.4 当前状态

- 修复与自动验收完成，状态仍为 **`WAIT_GATE5_HUMAN`**：等待用户对本次视觉与真实拖拽手感复测，不自动宣称 Gate 5 PASS。
- 未 commit、未 push、未发布、未部署；用户与其他会话留下的无关脏改保持原样。

---

## 16. Gate 5 第二轮人工反馈修复（2026-08-23）

### 16.1 触发与根因

- 用户截图指出：节点右键时原生 `title`、自定义 hover 浮层和右键菜单三层同时出现；同时生产主页与 H1 批准终稿屏 A 差距仍大，要求一并直接修复。
- 浮层根因是同一节点同时保留浏览器原生 `title` 与自定义提示，右键菜单打开后又未关闭 hover 提示。主页根因是为兼容旧测试而常驻保留四模式工具栏和空闲 Excel 大卡，且主页自身缺少 H1 的标题/KPI/紧凑项目行/成员长条/三列动态层级。

### 16.2 已修复行为

- 节点只保留 `aria-label` + 自定义 hover/focus 浮层，移除原生 `title`；右键菜单打开时节点进入瞬态 `is-context-open`，浮层立即隐藏，菜单动作、外点与 Esc 均经统一 `closeMenu()` 清理，三层重叠不再成立。
- 主页按 H1 屏 A 重排为：页面标题与日期、四格 KPI、我的项目紧凑行、团队成员身份区+横向项目药丸、右栏头像/动作/时间三列动态；旧四模式工具栏与空闲 Excel 大卡从主页移除。
- 导入、导出、新建保留为标题区低强调且唯一的真实入口；仅当导入/导出流程处于 busy/preview/error/committed/exportReady 状态时显示 transfer 状态卡，活动卡不复制第二套 starter selector。
- 项目编辑/删除动作改为 hover/focus 渐显；动作区始终可命中以避免与整行主按钮形成浏览器 hit-test 循环，无 hover 设备直接显示动作。进入主页后重新同步 chrome，面包屑不再残留旧看板名。
- `start-gate5-trial.cmd` 仍从仓库根启动同一 `server.py` 并直接服务当前前端资源，环境变量与隔离库路径均未变化，故本轮**无需修改启动器 cmd**。

### 16.3 修改面与验收证据

- 生产：`app.js`、`timeline-ui.js`、`timeline.css`；测试：`tests/timeline_ui.test.js`、`tests/test_gate5_home_e2e.py`。未改 `server.py`、`flowboard/`、schema、权限与 API。
- H1 唯一批准版 SHA-256 仍为 `d21e4d7fb8f6380828a387db554c0ab61461fa324b4a7287df968cf96ae8fc5d`；本轮对照屏 A 后重排，未改静态稿。
- Chromium 专项：`test_timeline_e2e.py` **24/24 OK**；`test_gate5_home_e2e.py` **7/7 OK**。后者包含 hover 阳性对照、无原生 title、真实右键后菜单可见且 hover 浮层隐藏、物理菜单点击清理状态，以及真实拖拽/草稿/提交链。
- Node：6 个 `tests/*.test.js` 文件全部通过；语法检查与范围内 `git diff --check` 通过（仅 Git LF→CRLF 提示）。
- 全量 Python：一次非缓冲执行因长服务日志截断了失败摘要且退出码 1，未伪称通过；随后使用缓冲模式完整复跑 `python -m unittest discover -s tests -b` → **`Ran 149 tests in 297.055s` / `OK`**。专项 31 个浏览器用例另行独立全绿。
- 核心文件改动前的 custom agent mc-expert 模拟陪审给出 HIGH 置信路线；连续失败后的追加 follow-up 因 `PROJECT_MEMORY` 交接未满足 profile 合同被拒，未将其冒充有效 KB 结论。最终点击层根因由真实 Chromium `getBoundingClientRect()` + `elementFromPoint()` 命中探针定位，并由原失败用例及全量回归验证。

### 16.4 当前状态与保护声明

- 当前仍为 **`WAIT_GATE5_HUMAN`**，等待用户刷新真实页面复测主页视觉、右键浮层与拖拽手感；自动测试不代替人工 Gate 5 终签。
- 所有测试均使用 `%TEMP%` 隔离库；真实 `flowboard.db` 未迁移、未写入、未恢复、未重建。未 commit、未 push、未发布、未部署；无关脏工作树保持原样。

---

## 17. Gate 5 第三轮人工纠偏：时间表编辑器偏航修复（2026-08-23）

### 17.1 用户纠偏与权威依据

- 用户以 `mockup.html` 截图明确指出：所需始终是“时间表编辑器”，从未要求“时间轴编辑器”，并要求再次检查其他偏航后一并修复。
- 复核三项权威证据结论一致：`mainline-feature01.md` 要求类 Excel 网页编辑；`mockup.html` 画面一是一行一个节点的表格；`9-GATE3_TECH_FREEZE.md` 将节点表定义为编辑源数据。生产画布编辑器属于实现偏航，不是新需求。
- 本节是对 §13/§15 中错误“时间轴编辑器”措辞与对应生产实现的后续纠正；仪表盘的时间轴展示和真实拖拽仍属已确认范围，不受影响。

### 17.2 修复内容

1. **表格主体**：项目内编辑页恢复为类 Excel 时间表，固定列为 `# / 项目阶段 / 轨道 / 项目节点 / 日期 / 时间间隔（天） / 状态 / 备注 / 操作`；间隔列可显隐，首节点显示 `—`。
2. **完整编辑闭环**：原生 input/select 逐格编辑；支持按日期/六阶段排序、行内新增/删除、状态完成切换、草稿计数、放弃、单批保存、撤销和轻量复盘。新增行直接落本地 create 草稿，不再串行弹四个 prompt。
3. **移除错误机械**：编辑页不再包含 `.timeline-canvas`、`.timeline-node`、缩放带、右键菜单或拖拽绑定；右键四项菜单和拖拽仅用于仪表盘。
4. **数据意图**：日期、间隔、阶段、轨道、节点名、状态、备注均进入既有 batch；轨道改变会清掉不可组合的间隔意图；编辑器提交 `trigger_source=editor`、仪表盘提交 `trigger_source=drag`。
5. **权限纠偏**：member 仅编辑自己创建的项目，查看他人项目时整表禁用且无新增/保存；管理员全可编辑。`initial-correction` 入口只向管理员渲染，避免向普通成员暴露必然失败的操作。
6. **文案与导入边界**：项目页签和反馈统一为“时间表编辑器/项目时间表”；导入入口明确只新建项目，不再使用可能暗示覆盖已有项目的“导入更新”。

### 17.3 验收证据

- JS 语法：`node --check timeline-ui.js`、`node --check app.js` 通过。
- Node：6 个 `tests/*.test.js` 全绿；其中时间管理单测 36 项，新增覆盖表格固定列、旧画布不存在、只读态、字段意图、轨道/间隔互斥、临时行与审计来源。
- Chromium：`test_timeline_e2e.py` **24/24 OK（103.645s）**；`test_gate5_home_e2e.py` **7/7 OK（26.126s）**。真实鼠标用例覆盖表内编辑、排序、增删、单批提交、撤销、409 最新表回刷、项目级只读和管理员入口。
- Python 全量：最终 `python -m unittest discover -s tests -b` → **`Ran 149 tests in 331.368s` / `OK`**。首轮全量唯一失败是 viewer 403 用例在异步 response 回调入队前读取数组；服务 stdout 已记录 403，改用 `expect_response` 消除竞态后目标场景及全量均通过。

### 17.4 当前状态与保护声明

- 本轮未改 `server.py`、`flowboard/`、schema、权限规则或 API 路由；所有浏览器测试使用临时隔离库，真实 `flowboard.db` 未迁移、未写入、未恢复、未重建。
- `start-gate5-trial.cmd` 从仓库根直接启动 `server.py`，静态资源由当前 `index.html` 引用，无复制或构建缓存步骤，故**启动器无需更新**；浏览器需 `Ctrl+F5` 清除旧前端缓存。
- 最高状态仍为 **`WAIT_GATE5_HUMAN`**，等待用户复测时间表编辑手感、主页与仪表盘；未 commit、未 push、未发布、未部署。
