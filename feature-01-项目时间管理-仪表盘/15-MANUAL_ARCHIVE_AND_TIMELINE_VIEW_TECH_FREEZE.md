# feature01 · 手工归档与时间画布显示增量技术冻结

> 冻结日期：2026-08-25
>
> 状态：静态交互与技术契约已冻结，进入 `ARCHIVE_VIEW_TECH_FROZEN`；正式系统尚未施工或验收。
>
> 权威来源：用户确认归档基线，并拍板 Q1–Q8 = A / A / A / A / A / B / A / A；密集节点选择方案 B；今日左侧白色蒙版为 80%；恢复【全项目仪表盘】全屏按钮。
>
> 适用范围：手工归档、一次性初始化归档、全项目密集节点显示、今日蒙版、全项目全屏入口恢复，以及单项目时间轴横向缩放/拖拽。本文只覆盖这些增量；其余仍分别沿用 `9-GATE3_TECH_FREEZE.md`、`13-TAG_ORDER_TECH_FREEZE.md` 和 `14-PORTFOLIO_CANVAS_TECH_FREEZE.md`。

## 0. 不可变业务基线

1. 归档只能由用户手工触发，未来不得按日期、状态或定时任务自动归档。
2. workspace admin 或项目 `created_by` 可归档；两者也可取消归档。权限必须由服务端执行。
3. 归档是高优先级系统状态，以虚拟系统标签【已归档项目】呈现；它不是删除、软删除、回收站或普通标签。
4. 归档项目从“全部 / 未分类 / 普通标签 / 我的项目 / 项目分组”等活跃入口剔除，只在【全项目仪表盘 → 已归档项目】和首页【已归档】页出现。
5. 首页【已归档】页只列项目名称和【取消归档】动作，不承载时间画布、编辑器、标签修改或删除入口。
6. 归档期间项目内容只读；必须先取消归档才能编辑。
7. 归档不删除普通标签关系或个人顺序；取消归档后恢复原有标签与个人位置。
8. 归档入口位于项目页菜单和全项目行菜单；执行前只出现一次确认弹窗。
9. 归档列表按 `archived_at DESC, name ASC, project_id ASC` 排序；【已归档项目】拥有独立日期范围和独立视角记忆。
10. Q6=B 只批准“首次把全部日期候选归档”的一次性初始化口径，不批准真实库执行，也不改变第 1 条永久规则。

## 1. v18 数据模型

在 v17 `timeline_projects` 上纯增量增加：

```text
archived_at TEXT NULL
archived_by TEXT NULL REFERENCES users(id)
```

并增加只服务于归档查询的索引：

```sql
CREATE INDEX idx_timeline_projects_archive
ON timeline_projects(workspace_id, archived_at DESC, id DESC)
WHERE deleted_at IS NULL AND archived_at IS NOT NULL;
```

- `archived_at IS NULL` 表示活跃；非空表示已归档。`archived_by` 记录实际操作者。
- 归档和取消归档都更新项目 `version` 与 `updated_at`。取消归档将 `archived_at/archived_by` 同时清空；历史由审计保留。
- 不复用 `deleted_at/deleted_by`，不新增名为“已归档项目”的 `timeline_tags` 行，也不创建可改名、可删除或可共享分配的普通标签。
- 已归档项目仍属于“未删除项目”，继续参与 workspace 内活跃名称唯一性校验，不能用相同名称另建项目。
- `SCHEMA_VERSION` 从 17 升到 18；`_migration_v18` 只加列、索引和 migration 记录，**零业务数据回填、零自动归档**。
- v15→v18 必须在隔离副本上按 v16→v17→v18 顺序验证。真实 `flowboard.db` 的迁移与初始化批量归档均须用户另行明确授权。

## 2. 系统标签、普通标签与个人顺序

### 2.1 服务端集合

- `active`：`deleted_at IS NULL AND archived_at IS NULL`。
- `archived`：`deleted_at IS NULL AND archived_at IS NOT NULL`。
- `mine / all / uncategorized / tag` 在 `13-` 原定义上追加 `archived_at IS NULL`，标签计数也只统计 active。
- 虚拟 `archived` 上下文不接受 `tag_id`，不参与普通标签 CRUD，也不提供个人自定义排序；服务端固定按归档时间倒序。
- 软删除与归档是互斥的用户旅程：归档项目若需进入回收站，必须先取消归档，再按既有 admin 软删除合同执行。

### 2.2 遮蔽而非改写

- 归档/取消归档不写 `timeline_project_tags`，不删除任何普通标签关系。
- 归档项目的 `timeline_order_items` 保留。活跃上下文的排序请求只提交当前可见 active 完整集合；服务端重排时只改写可见槽位，保留归档项目的隐藏槽位与 item，不将其判作“已移出集合”而软删除。
- 取消归档后，项目重新进入所有仍有效的原标签，并回到保留的个人顺序槽位。
- 如果归档期间某普通标签被按既有合同软删除，取消归档不得复活该标签；如果某上下文本身被删除，也不伪造其旧顺序。这不视为违反“保留”规则。

## 3. API、权限、只读与并发

### 3.1 手工归档端点

```text
POST /api/workspaces/{workspace_id}/timeline/projects/{project_id}/archive
POST /api/workspaces/{workspace_id}/timeline/projects/{project_id}/unarchive
```

请求体均为：

```json
{"base_version": 7}
```

成功返回项目最新的 `project_id/name/version/archived_at/archived_by` 与 `read_only`。

- 归档：仅 workspace admin 或该项目 `created_by`；项目必须未删除且当前未归档。
- 取消归档：权限与归档对称；项目必须未删除且当前已归档。
- 条件更新必须同时匹配 workspace、project、`base_version` 和预期归档状态；成功单事务写项目与审计。
- 未登录 401；非成员或不泄漏边界对象沿用既有 403/404；非 admin 且非创建者返回 403 `PROJECT_ARCHIVE_FORBIDDEN`；版本或状态已变化返回 409 `ARCHIVE_STATE_CONFLICT` 并附最新可见项目摘要；请求形状错误返回 422。
- 双击、重放或两个操作者竞争时只能有一次成功；不得重复写审计。

### 3.2 归档只读护栏

- 项目详情 GET 允许 workspace 成员读取归档项目，并返回 `archived_at/archived_by/read_only=true`；普通项目列表默认只返回 active，显式 `archive_state=archived` 才返回归档集合。
- 所有项目内容写路径在服务层统一要求 `archived_at IS NULL`：节点增删改、日期/状态批次、撤销、历史日期更正、标签归属变更及其他会修改既有项目内容的路径均不得只靠前端隐藏。
- admin 和创建者在归档期间也不能编辑；命中时返回 409 `PROJECT_ARCHIVED`。允许的状态写只有取消归档。
- 全项目【已归档项目】可查看只读时间画布；行内不出现节点拖拽、完成状态、编辑、标签、归档或删除动作。项目页若从归档上下文进入，同样只读并只提供【取消归档】。

### 3.3 审计

复用 `audit_log`，至少记录：

```text
timeline.project_archived
timeline.project_unarchived
timeline.archive_bootstrap_completed
```

单项目事件记录 workspace、project、actor、前后 version、`archived_at`；一次性初始化的每个项目仍各有 `timeline.project_archived`，完成事件另记候选数、快照摘要和操作者。归档历史不得因取消归档而删除。

## 4. 一次性初始化归档（Q6=B）

### 4.1 候选定义

以执行预览时服务端 `Asia/Shanghai` 的自然日为【今天】。候选必须同时满足：

1. 当前 workspace、未删除、未归档；
2. 至少有一个未删除节点；
3. 所有未删除节点中的最大 `date` **严格早于今天**。

最后节点等于或晚于今天、以及空项目，均不是候选。节点完成状态不影响候选判定。

### 4.2 只运行一次的受控流程

- 初始化不是 schema migration、应用启动逻辑、后台任务、cron 或常驻 API；不得在未来自动重复执行。
- 先只读生成预览快照：workspace、today、候选 `project_id/name/base_version/last_node_date`、总数和摘要哈希。用户已选择“全部日期候选”，因此快照不提供逐项勾选。
- 真正 apply 是单独的显式维护动作，只允许 workspace admin 作为 actor；必须携带该快照并再次验证 workspace、版本、归档状态和候选日期。任一项目漂移则整批 409、零写入，重新预览后再决定。
- apply 在一个事务中归档快照内全部候选、逐项目 version+1 并写审计；成功后写 `timeline.archive_bootstrap_completed`。检测到完成标记时拒绝再次执行。
- 对真实 `flowboard.db` 的 preview 可只读进行；任何 v18 迁移或 apply 均不在本次授权内，必须另行得到用户明确授权并先完成备份/恢复验证。

## 5. UI 与时间画布合同

### 5.1 归档入口与页面

- 项目页菜单与全项目 active 行菜单显示【归档项目】；归档项目不再显示该动作。
- 点击后出现一次确认弹窗，明确“不是删除、将从普通入口隐藏、归档期间只读”；取消零写入，确认后才调用 archive API。
- 全项目标签导航末尾固定显示虚拟【已归档项目】；首页侧边栏【已归档】进入轻量列表，只显示名称与有权限时的【取消归档】。
- 前端根据服务端 `can_archive/can_unarchive` 控制入口可见性，但这只是反馈，不能替代 3.1 的服务端鉴权。

### 5.2 独立范围与视角记忆（Q8=A）

- 【已归档项目】的绝对范围只取当前归档项目节点的最早/最晚日期并各扩 30 天，不复用 active “全部”范围。
- 浏览器视角键扩展为 `workspace × account × context=archived`，独立保存中心日期、缩放天数和纵向位置；切走再返回恢复该视角。
- 归档/取消归档导致集合变化时重新钳制已有中心点；无归档项目时展示空状态，不借用 active 范围制造假数据。

### 5.3 今日蒙版

- 两类仪表盘中，若项目满足 `first_node_date <= today <= last_node_date`，则【今天】左侧整体覆盖 80% 不透明度的白色蒙版；今天右侧维持六阶段原色。
- 蒙版覆盖阶段条、节点和背景，但红色今天线置于蒙版之上；过去/未来项目不加蒙版。今天仍按服务端 `Asia/Shanghai` 日期语义计算。
- 蒙版只是显示层，不改颜色 token、节点数据、状态派生、命中区或权限。

### 5.4 全项目密集节点折叠（方案 B）

- 在同一项目、同一轨道内，按当前缩放把节点日期映射为横向像素；相邻节点中心距小于 18px 时视为重叠，并将连续重叠链折叠成一个 **5px 中性深色实心圆点**（无白圈、描边、光晕或数字）。
- 聚合点是显示替身，不是新节点、服务端数据或可拖拽对象；hover/focus 可列出被折叠节点，编辑前必须滚轮放大。
- 每次缩放、容器尺寸或数据变化后重新计算；当所有相邻中心距均达到 18px 时，立即恢复原白圈节点。相同日期节点无论放大倍数始终聚合。
- 生产界面不暴露“拥挤阈值/圆点方案”调节器；静态稿中的选项只用于效果确认。

### 5.5 缩放、横移与全屏

- 【全项目仪表盘】恢复可见【全屏】按钮；它进入既有应用内全屏，Esc 与【退出全屏】均可退出。筛选/排序/适配/加减缩放按钮仍按 `14-` 的 2026-08-24 覆盖保持隐藏，滚轮缩放继续生效。
- 【单项目仪表盘】增加鼠标滚轮指针锚点缩放和左键空白抓取；只改变时间轴横向中心与缩放，不改变纵向位置，不触发项目/节点写入。
- 单项目最细窗口沿用全项目既有 14 天下限并钳制在项目节点范围±30天；节点和操作控件排除画布抓取。单项目视角持久化不在本增量冻结范围内。

## 6. 验收合同

### 6.1 数据/API

- v17→v18、真实形态 v15→v18 隔离迁移、迁移幂等、失败恢复、FK/integrity、零自动业务回填。
- admin / creator / 其他 member / 非成员 × archive / unarchive 权限矩阵；前端隐藏不能替代负例。
- archived 项目所有内容写端点返回 `PROJECT_ARCHIVED`；取消后恢复写入权限。
- 归档前后普通 tag 行与 order item 数量/内容不变；取消后恢复标签和个人槽位；标签在归档期间被删除的边界正确。
- 同时归档、同时取消、旧 `base_version`、状态重放均验证单成功与零重复审计。
- 一次性候选覆盖 `< today`、`= today`、`> today`、空项目、软删/已归档项目和预览后漂移；真实 apply 必须另行授权。

### 6.2 浏览器

- 两个归档入口均经过一次确认；取消零请求，确认后 active 入口消失、归档两个入口出现、只读态正确，取消归档后原标签/顺序恢复。
- 归档列表按时间倒序，归档视角与 active 视角相互独立并能恢复。
- 80% 今日蒙版、红色今天线层级、右侧原色在两类仪表盘可见。
- 全项目节点在 `<18px` 时变 5px 中性实心点，放大到不重叠时恢复白圈；同日保持聚合。
- 全项目全屏按钮可见且可退出；单项目滚轮锚点缩放、仅横向拖拽、纵向位移为零。

## 7. 明确不做

1. 不做日期驱动、定时或状态驱动的永久自动归档。
2. 不把归档实现成普通标签、删除、回收站或 `deleted_at` 别名。
3. 不在归档期间开放编辑，也不因用户是 admin 放松只读护栏。
4. 不删除或重置普通标签、个人顺序、节点、批次或审计历史。
5. 不在首页【已归档】页加入时间画布、批量编辑、删除或标签管理。
6. 不把静态稿通过、技术冻结或隔离测试表述成正式功能已实现、真实库已迁移或首次批量归档已执行。

## 8. 当前交接边界

- 已更新的确认稿：`（静态确认稿）归档与今日蒙版及单双项目缩放.html`。
- 已回填的问卷：`（施工前问卷）手动归档剩余细节一次性确认.html`，Q1–Q8 = A/A/A/A/A/B/A/A。
- 已按“v18 数据/API与权限 → active/archived 查询与只读 → UI入口与视角 → 一次性预览工具 → 隔离自动验收”完成生产代码施工，当前状态为 `ARCHIVE_VIEW_WAIT_HUMAN`。
- 真实库首次批量归档仍是独立人工门；本契约不构成授权。

## 9. 施工与验证记录（2026-08-25）

- 数据/API：`flowboard/database.py` 增加零回填 v18 migration；`flowboard/timeline.py` 与 `server.py` 落地 archive/unarchive、默认 active/显式 archived 查询、归档只读、系统虚拟标签、标签/个人顺序保留及一次性 bootstrap preview/apply。
- UI：`app.js`、`timeline-ui.js`、`timeline.css` 落地项目页/全项目行菜单、首页轻量归档页、全项目归档只读画布、独立归档视角、80% 今日蒙版、5px 密集点、单项目横向缩放/拖拽与可见全屏入口。
- 隔离自动证据：`tests/test_timeline_archive.py` 5/5、`tests/test_timeline_tags_order.py` 7/7、`tests/timeline_ui.test.js` 全绿；真实 Chromium 专项已操作一次确认归档、active 剔除、归档只读/独立视角、取消归档恢复、蒙版、聚合/放大恢复、单项目仅横向平移与全屏进出，并回归既有全项目筛选、E＋D4＋P1 和风险标记旅程。
- 真实库保护：仅用 SQLite `mode=ro` 复核 `flowboard.db`，结果为 `user_version=15`、`integrity=ok`、`foreign_key_check=0`、`timeline_projects.archived_at` 不存在；SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。未执行 v18 迁移、bootstrap apply、commit、push、发布或部署。
