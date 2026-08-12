# Flowboard 第一阶段架构与迭代计划

## I9 统一排期投影

Timeline 与 Gantt 使用同一个只读投影边界：任务查询先完成 ACL、筛选和排序，再由 `flowboard/schedule.py` 从固定 `start_date`/`due` 或一个活动的 date/timeline 动态字段生成区间。投影最多接收 500 项、跨度最多 3,660 天；非法日期进入未排期区，不猜测或修复数据。依赖仅在投影后的可见节点间返回，因此筛选和权限边界不会被边信息绕过。

写路径仍落在任务及动态字段的权威存储中。排期变更要求 task version 与 board version；直接后置推动是单层、显式、全版本匹配的原子操作，不递归传播。关键路径是可见 DAG 上的确定性计算；循环时返回诊断并停用。Gantt baseline 目前只有 `disabled` 配置值，避免在没有版本化基线模型前制造伪数据。

## I5 共享表格、Kanban 与日历（schema v5/v6）

- `saved_views.presentation_json` 按 `view_type` 严格校验：table 保存列宽和冻结前缀，kanban 保存 active status/person 字段，calendar 保存 active date 字段。
- 三种 renderer 只消费统一查询返回的同一组任务对象；不保存查询结果副本。schema v6 的 `tasks.board_order` 是 Kanban 顺序的唯一持久化真相。
- 编辑和拖动复用 `PATCH /api/tasks/{id}`、CSRF、任务 version、类型校验与服务端权限。冲突后重新加载。
- 日历固定生成 6×7 月网格；legacy 日期与空值进入无日期区，合法但超出网格的日期进入“其他月份”。月份属于 URL 本地状态。

## I7 高级字段与派生求值（schema v8）

- `field_definitions` 继续是字段注册的唯一真相，新增 timeline/rating/file/email/phone/relation/mirror/formula；输入值复用类型化值表，派生结果不落库。
- `task_relation_values` 用单条带 version、软删除信息和双向索引的 canonical edge 表示跨看板关系；反向结果由同一条边按当前权限解析。
- 镜像与公式通过统一读时路径解析；受限 AST 只开放确定的算术、比较、布尔、条件和聚合函数，并限制表达式长度、节点、深度、参数及结果范围。
- 派生查询先用 SQLite 取得有界候选，再按当前用户权限求值、筛选、排序和分页；不可访问来源传播 `UNAVAILABLE`，共享视图不继承创建者权限。
- v7→v8 先用 SQLite backup API 备份，重建扩展类型约束的字段注册表并建立关系索引，随后执行外键、完整性和恢复副本检查。

## I6 子任务与依赖（schema v7）

- `tasks.parent_id/subtask_order` 采用邻接表；子任务仍是普通 task，共用动态字段、query、version、activity、`sort_order` 和 `board_order`。层级最多 3 层，复杂祖先/深度规则由同一事务中的服务层校验。
- `task_dependencies` 保存同看板有向边并软删除；递归 CTE 检测完整多跳环。进度、blocked 和关系摘要均读时计算，不复制为事实列。
- 根任务继续按 group/task order；`subtask_order` 只用于兄弟子任务，层级 mutation 使用 task + board version 防止并发覆盖，且不改 Kanban `board_order`。
- 日期联动只有显式、默认关闭的单跳 `none | push_successor_once`；不递归，不提前，不覆盖 legacy 日期，活动记录策略与结果。
- 父任务有活跃子任务时禁止归档/删除；任务复制默认脱离层级/依赖，分组和看板复制只复制副本范围内部的父子与依赖关系。
- 轮询在拖动或缩放期间暂停，交互结束后重新取得服务端事实。

## 结论

现有原型采用渐进重构，不归零重写。保留 SQLite、原生 Web 前端和现有任务数据；Python 服务拆为启动适配层、数据库迁移、安全模块与业务服务。首个迭代只建立安全身份和可迁移数据底座，动态字段与多视图在后续迭代共享同一业务模型。

## 现状审计与差距

| 范围 | 现状 | 第一阶段缺口 |
|---|---|---|
| 身份与权限 | 前端可任意设置 `X-User-Id` | 登录、会话、CSRF、工作区角色、看板访问控制 |
| 数据迁移 | 请求时运行 `CREATE TABLE IF NOT EXISTS` | 有版本、备份、校验和回滚边界的显式迁移 |
| 看板模型 | 单工作区假设；CRUD 不完整 | 工作区关系、开放/私有看板、完整生命周期 |
| 分组/任务 | 固定字段、部分新增/更新 | 完整 CRUD、排序、移动、软删除、并发版本 |
| 动态字段 | 不存在 | 字段定义、选项、类型化值、统一验证 |
| 视图 | 只有固定表格 | 保存视图、Kanban、日历，共享查询与修改语义 |
| 协作与运行 | 评论基础接口、5 秒轮询 | 活动展示、备份恢复、审计和后续实时同步 |

`index.html` 原有中文发生乱码，本迭代已恢复 UTF-8 文案。数据库中的非规范日期（如“今天”）和原值不猜测转换，留到动态字段迁移制定明确规则。

## 数据关系

- `users` 通过 `workspace_memberships` 加入 `workspaces`，角色为 `admin/member/viewer`。
- `boards` 属于工作区；开放看板对工作区成员可见，私有看板还要求管理员或 `board_memberships`。
- `groups_` 属于看板，`tasks` 属于分组，`comments` 与 `activity` 归属任务。
- 可变业务实体带 `version` 做乐观并发，删除列统一为 `deleted_at/deleted_by`。
- 后续动态字段采用 `field_definitions`、`field_options` 与按类型约束的 `task_field_values`；旧状态、优先级、负责人、日期将在该迭代迁移，不继续增加固定任务字段。
- `saved_views` 后续只保存视图类型、筛选、排序和显示配置，不复制任务数据。

## API 与安全边界

- API 错误统一为 `{"error":{"code":"...","message":"...","details":...}}`。
- 登录产生 HttpOnly、SameSite=Lax 会话 Cookie；写操作同时验证 CSRF token。
- 所有读写先在服务端核验工作区角色和看板访问权，客户端隐藏按钮不构成授权。
- 任务更新必须提交 `version`；版本过期返回 `409 VERSION_CONFLICT`。
- 当前标准库 HTTP 层只是可替换适配器。正式局域网部署应在反向代理后启用 HTTPS；后续可换 Waitress 等生产服务而不改业务服务。
- 静态文件的 GET/HEAD 路由共享默认拒绝清单，只允许当前 UI 所需资源；数据库、备份、源码、测试和点文件永不从仓库根目录透出或被 HEAD 枚举。

## 迁移与恢复

首次启动先执行 `integrity_check`，再用 SQLite backup API 写入 `backups/`，之后在事务内迁移并核对旧表行数。每个连接启用外键、5 秒 busy timeout；数据库切换 WAL。禁止用直接复制正在运行的 WAL 数据库作为备份。

恢复验证：停止服务，将迁移前备份通过 SQLite backup API 恢复到独立路径，运行 `PRAGMA integrity_check` 并核对核心表计数；确认后再替换运行库。

## 可验收迭代

1. **安全身份与迁移底座（已验收）**：兼容迁移、备份、登录/退出、三角色、开放/私有看板访问、统一错误、CSRF、任务版本冲突，保持现有任务和评论可用。
2. **核心生命周期（已完成并通过独立验收）**：看板、分组、任务的创建、编辑、复制、移动、归档、软删除和恢复；服务端记录结构化活动。
3. **动态字段（REWORK attempt 1，整改后待复验）**：schema v3 字段定义、选项、八类类型化值、非规范日期隔离、统一 task version 和动态表格列；旧固定字段暂作回滚投影。

## schema v3 动态字段语义

- `tasks.title` 保持核心标题；每个看板初始化 status、priority、owner、due 四个系统字段。
- `field_definitions` 与 `field_options` 管理定义、排序、停用、软删除和版本；字段类型创建后不可变。
- `task_field_values` 使用类型列保存单值，标签使用独立关联表；清空值删除值行。
- 所有字段写入沿用 `tasks.version`，同一事务完成类型/权限校验、动态值、旧回滚投影、version 和结构化活动。
- 非 ISO 的旧日期不猜测转换，逐字保存在 `legacy_task_field_values`；用户修正后转入类型化日期。
- v2→v3 迁移前生成 SQLite backup，迁移不增加任务 version；重复启动不重复建字段或备份。
4. **查询与保存视图**：多条件筛选、排序和个人/看板保存视图。
5. **共享基础视图**：表格、Kanban、日历基于同一查询和命令模型，拖动使用版本检查。
6. **协作收口**：批量操作、详情活动、回收站、备份保留与恢复演练。

## schema v2 生命周期语义

- 看板、分组和任务以 `archived_at/archived_by` 与 `deleted_at/deleted_by` 表示正交的归档和删除状态；父实体变更不批量篡改子实体自身状态。
- 活跃查询要求实体及祖先均未归档、未删除。恢复子实体时若父实体已删除，返回 `409 PARENT_DELETED`；先恢复父实体后方可恢复子实体。
- 分组和任务使用连续整数排序。客户端提交目标索引及实体/容器版本，服务端在一个 `BEGIN IMMEDIATE` 事务中重排并写活动。
- 复制只复制有效的基础实体，不复制评论或历史活动；副本根实体产生 `.copied` 活动。
- 活动表保存 `board_id/task_id/entity_type/entity_id/action_code/details_json/user_id/created_at`，UI 根据稳定 action code 映射文案。

## 生命周期 API

- `GET|POST /api/workspaces/{wid}/boards`；`GET /api/workspaces/{wid}/trash`
- `GET|PATCH|DELETE /api/boards/{id}`；`POST /api/boards/{id}/{copy|archive|unarchive|restore}`
- `POST /api/boards/{id}/groups`；`GET /api/boards/{id}/{activity|archived}`
- `GET|PATCH|DELETE /api/groups/{id}`；`POST /api/groups/{id}/{copy|move|archive|unarchive|restore}`
- `POST /api/groups/{id}/tasks`
- `GET|PATCH|DELETE /api/tasks/{id}`；`POST /api/tasks/{id}/{copy|move|archive|unarchive|restore}`
- `POST /api/tasks/{id}/comments`；`GET /api/tasks/{id}/activity`

所有 mutation 都要求会话、CSRF 和适用的 `version`；移动另外要求源/目标容器版本。

## schema v11 与 typed aggregation 边界

- `saved_views.view_type` 增加 `chart`；presentation 使用严格 version 1 tagged spec，不另建图表数据表。
- dashboard 只持久化工作区作用域、显式 `source_key → board/query`、widget config 和有界网格布局；跨看板活动写独立 `dashboard_activity`，不伪挂到任一看板。
- `FlowboardService` 先按当前用户逐来源执行 `_board_access`，再复用 `query_tasks`；`flowboard.aggregation` 只接收有界 typed rows，负责所有 chart/number/progress 聚合。
- 聚合结果不缓存、不持久化。撤权、归档、删除和字段停用会在下一次读取立即 fail closed；错误不包含不可见来源的名称或旧值。
- Number 走同一 typed metric 校验但直接计算全局标量；分页对 total 变化/空页稳定失败，高基数 series/cell 在写入累积状态前检查。来源与组件的活动对象上限统一覆盖 add/copy/restore，失败事务不推进任何 version。
- 单看板 chart 与 dashboard chart 共用 AggregationSpec 和渲染数据形状；浏览器只画服务端 categories/series/scalar/rows，不下载全量敏感任务后自行汇总。

## schema v13 协作与附件边界

- 评论、版本历史、提及、订阅和附件元数据均在 SQLite；附件 blob 位于静态根之外的私有目录，任何读取都重新执行任务 ACL。
- `task_subscriptions` 以 `(task_id,user_id)` 唯一，状态只有 `following/opted_out`。自动关注只创建缺失记录，不覆盖用户的手动取消；显式订阅/取消才改变既有状态并推进订阅 version。
- 评论、提及、订阅和附件 mutation 在同一事务写业务数据、活动与最小化 `collaboration_events` outbox；失败和 stale 写入三者均不变化。

## schema v14 通知、搜索、实时与审计边界

实时 JSON poll 与 SSE 共用同一 raw-scan 游标契约：`limit` 限制每次按 ID 升序扫描的原始事件数，游标仅推进到本批最后扫描事件；ACL 过滤后的空批次也会提交进度，避免隐藏事件密集时重扫、跳跃或阻塞后续可见事件。

- `notifications` 只保存资源定位和 kind，不保存任务标题、评论正文或附件文件名快照；生成、读取、计数和已读 mutation 均重新检查当前 ACL。
- `event_consumers` 在同一短事务内推进 outbox/activity 游标；显式 `process_notifications_once(now=...)` 让到期提醒、重放与失败回滚可确定测试，不引入任务平台。
- 全局搜索直接读取统一业务表，服务层统一过滤 private/soft-delete/失效父级；不复制索引模型。
- `realtime_events` 提供持久游标，SSE 是首选传输，JSON/5 秒刷新为断线降级。每批投递重新授权，消息不覆盖 version/409 语义；presence 是进程内 best-effort。
- `audit_log` 是 append-only 安全投影，业务活动在同一事务镜像；登录/退出和权限变化显式记录。查询/CSV 仅 workspace admin，details 白名单化且 CSV 防公式注入。
- 安全预览仅开放验证后的文本与图片，使用 inline disposition、私有禁缓存、`nosniff` 和 sandbox CSP；PDF 与其他类型保持下载。
- HTTP 攻击矩阵覆盖 CSRF、角色/私有看板 ACL、路径与 MIME 欺骗、失败原子性；真实 Chromium 覆盖两用户桌面协作与 390px 移动端上传/删除。

## 当前全局验收

第一阶段已推进到 schema v15。完整累计套件、I3～I13/schema 映射、17 项 done_when、权限矩阵、双用户桌面与 390px 旅程、legacy 迁移和隔离备份恢复证据统一记录在 `GLOBAL_ACCEPTANCE.md`。部署及离线恢复命令以 `WINDOWS_OPERATIONS.md` 和 `flowboard_ops.py --help` 为准。

schema v15 增加任务描述、工作区保留期及删除索引；批量操作使用单事务逐项 ACL/version 校验。永久清理采用 preview/hash/精确确认、pre-purge 校验备份和 blob 隔离。运维备份包含 SQLite 快照、附件和 checksum manifest；恢复仅允许离线 CLI，并按 DB/附件各自交换状态回滚，失败矩阵覆盖 stage、DB、附件和最终验证边界。
