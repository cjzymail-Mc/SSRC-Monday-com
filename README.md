# Flowboard

> 当前状态（2026-09-04）：已在公司局域网正式运行，当前 schema v19；feature01 已完成人工验收和部署，现处于第 8 阶段的生产运行、反馈维护与文档收口。正式入口是 `start-flowboard.cmd`，开发调试使用隔离的 `local-test.cmd`。

## I10 图表与跨看板仪表盘

schema v11 将保存视图扩展为 `chart`，并新增 `dashboards`、`dashboard_sources`、`dashboard_widgets` 与独立的 `dashboard_activity`。数据库只保存版本化配置、显式来源映射和 12 列有界布局，不保存聚合结果或复制任务数据。柱状、折线、饼图、堆叠柱状图以及数字/图表/进度/日历/表格组件全部调用同一个 `flowboard.aggregation` typed aggregation 核；单看板入口是 `POST /api/boards/:id/aggregate`，组件入口是 `POST /api/dashboards/:id/widgets/:widget_id/data`。

每次读取组件都会按当前用户重新检查工作区和来源看板 ACL，并重新执行现有 query AST、生命周期和派生字段读取。来源撤权或私有看板不可见时，该组件返回通用 `WIDGET_SOURCE_UNAVAILABLE`，不回显看板名、字段或历史数值；无关组件仍可显示。跨看板动态字段只能通过 `source_key` 显式映射，不按相同 ID 或名称猜测合并。v1 不缓存结果，因此权限变化即时生效。

聚合支持 count 以及合法 number/rating/数值公式的 sum/avg/min/max；Number 直接对筛选后的全局值计算 KPI（不会错误汇总图表分桶后的 avg/min/max）。日期按 ISO 日、ISO 周或月分桶，标签采用“每个标签成员各计一次”并在响应中声明。单来源最多 2,000 项、单组件合计 5,000 项、每仪表盘 8 个来源/20 个组件、200 buckets/12 series/2,000 cells；add/copy/restore 全部执行活动对象硬上限，超限返回稳定 422 且事务不改变版本或数据。分页期间来源 total 变化或出现无进展页返回 `AGGREGATION_SOURCE_CHANGED`，高基数在累积阶段返回 `AGGREGATION_RESULT_LIMIT`，不会截断后伪装成完整统计。原生 SVG/CSS 图表始终附带文字图例和数据表，不依赖公网 CDN；390px 可从顶部入口浏览仪表盘，编辑者可创建来源/组件、全局筛选、移动/缩放、复制和软删除。

## I9 时间线与 Gantt

schema v10 为任务增加固定排期 `start_date`，并让保存视图支持 `timeline` 与 `gantt`。两种视图共用 `flowboard.schedule` 投影与现有任务查询、动态日期/时间线字段、层级、依赖、权限和版本控制；Gantt 只增加里程碑、可见依赖线和关键路径展示，不维护第二套任务模型。基线固定为 `disabled`，留作后续兼容边界。

排期读取使用 `POST /api/boards/:id/schedule`，严格接收 query 与 presentation；最多物化 500 个可见任务，日期跨度最多 3,660 天。过滤不可见的任务不会通过依赖边泄漏，循环依赖会 fail-closed 停用关键路径并返回诊断。写入使用 `POST /api/tasks/:id/schedule`，同时校验任务/看板版本、CSRF 与写权限；可选择一次性推动全部直接后置任务，但必须提交每个后置任务的版本，否则整笔事务回滚。

桌面端支持日/周/月粒度、今天定位、横向滚动和拖移排期；移动端保留浏览、打开任务及显式“编辑”日期表单，粗指针上禁用易误触的条形拖动。保存视图中的来源与粒度可持久化，URL/default/copy/update 沿用统一视图状态机。

Flowboard 是面向公司内部小团队、局域网部署的协作看板。安全身份、迁移底座、核心生命周期、动态/高级字段、跨看板关系、镜像与计算字段、统一查询/保存视图及表格/Kanban/日历共享视图已经实现。

## I8 模板与 CSV/XLSX 导入导出

schema v9 增加工作区级看板/项目模板和导入预览批次。模板保存看板设置、分组、动态字段与选项顺序、共享视图，以及明确选择时的任务样例；实例化会生成独立 ID，重映射内部字段、任务层级、依赖和关系。指向原看板外部资源的关系会以未绑定、停用状态创建，其镜像/公式依赖也会停用，避免副本继续读取原项目。

导入支持 UTF-8（含 BOM）和 GB18030 CSV，以及不含宏、公式、外部链接的真实 OOXML `.xlsx`。多工作表 XLSX 可在预览界面选择非首工作表并重新预览；每列展示服务端类型推断与样例。流程固定为“预览并推断 → 用户字段映射 → 单事务提交”，要求看板写权限、CSRF 和最新看板/批次版本；任一行校验失败会返回来源行号、表头和目标字段类型，且不会产生部分任务。单文件上限 1.5 MB、1000 数据行、100 列、单元格 10000 字符，并限制 ZIP 条目数和解压后体积。

导出复用统一查询入口，可导出当前筛选结果与当前可见动态字段为带 BOM 的 CSV 或真实 `.xlsx`；结果总数最多 1000 行，超过时在物化和编码文件前返回 `EXPORT_LIMIT`。状态、标签和人员使用可读名称，派生字段在导出前预检来源 ACL；所有文本单元格在去除前导控制字符后检测 `= + - @`，命中时加单引号，阻止电子表格公式注入。工具栏中的“模板 / 导入 / 导出”提供桌面和移动端操作入口，其中模板界面支持 board/project 创建、更新、软删除、已删除查看、恢复与实例化。

## I7 高级字段、关系、镜像与计算字段

schema v8 扩展 `timeline/rating/file/email/phone/relation/mirror/formula`。时间线保存经过校验的起止日期；评分上限为 1–10；邮件和电话有长度/格式边界；file 在 I7 只保存安全的名称、大小和媒体类型元数据，不接受路径、二进制或附件 ID，真实上传统一留到 I11。

feature01 时间管理使用 schema v16 新增的五张专表：`timeline_projects`、`timeline_nodes`、`timeline_change_batches`、`timeline_node_changes` 与 `timeline_import_batches`。v17 增加共享标签和用户个人顺序，v18 增加手工归档，v19 将活跃项目名称唯一性升级为大小写不敏感。项目与看板保持零外键，节点间隔与派生指标不落库；所有读写均由服务端派生和授权。接口提供项目新建、读取、重命名、软删除、归档/取消归档、批量编辑、undo、initial correction、轻量复盘、Excel 导出与两段式导入。导入复用安全 XLSX/CSV 解析器，拒绝公式、宏、外链与超限文件，并在 commit 事务内重验同名项目。

跨看板关系用 `task_relation_values` 的单条 canonical 软删除边保存，关系字段声明目标看板与是否展示反向关系。新增关系要求源任务写权限和目标任务当前可见，携带 source task、source board 与 target task version；目标失权、归档或删除后，字段配置会被裁剪，关系、反向关系和镜像统一返回不可用诊断，不泄露目标 ID、标题、数量或活动详情。任务单独复制不复制外部关系；看板复制只重映副本集合内部关系、字段 ID 和公式引用，跨板关系字段复制为停用且未绑定，避免副本意外连回原看板。

镜像和公式均为只读、读时求值，不持久化第二份业务值。公式使用 AST allowlist 解释器，禁止 `eval`、属性访问、下标、任意函数和 SQL；表达式最多 500 字符、80 节点、12 层、每函数 20 参数。`SUM/AVG/MIN/MAX/CONCAT/IF/PROGRESS` 提供数值、文本、条件、汇总与进度最小集合；直接和多跳公式环在保存时拒绝。来源 `UNAVAILABLE` 会传播到镜像和公式，不能被当作空值或零用于推断权限数据。

派生查询采用 SQL 候选 + 权限感知读时求值，最多 2,000 候选和 10,000 个派生 cell，超限明确返回 `QUERY_LIMIT`。关系的有效值只包含 task、group、board 整条祖先链均未归档且未删除的目标；软删除 edge 仍保留，恢复后自动重新显现，失效期间不参与详情、反向关系、筛选或排序。异构公式结果只允许有限数字之间或字符串之间做大小比较；类型不兼容、非有限数字及复合值稳定视为不匹配，排序时复合值按空值处理，不做隐式字符串强转。Kanban 仍只允许状态/人员；日历允许日期或时间线起点，时间线在日历中只读。

## I6 子任务与依赖

schema v7 为普通任务增加同看板父子关系与兄弟顺序，并用独立的有向依赖边保存前置关系。层级最多 3 层；服务端拒绝自身父级、祖先回挂、跨看板父级、跨看板依赖、重复依赖和完整多跳环。层级重排携带 task/board version，依赖新增/删除携带关系两端 task version 与 dependency version，stale 写入返回 409。

任务进度不落第二份数据：读取时同时计算活跃直接子任务与递归后代的完成数、总数和百分比；无子任务时百分比为 `null`。父任务 status 仍可单独编辑，不会静默覆盖子任务。依赖前置任务未完成时返回 `blocked/blocked_by`，前置归档或删除后边保留但暂不阻塞，恢复后重新生效。父任务存在活跃子任务时禁止归档/删除，须先处理或解除子任务，避免隐藏的任务级孤儿。

日期联动只有建边时的显式 `due_policy`：默认 `none`；`push_successor_once` 最多把本次后置任务推迟到前置日期，永不提前、永不递归。前置无合法日期或后置是 legacy 非 ISO 日期时明确 no-op，不猜测覆盖；结果和前后值进入活动审计。

任务详情可新增、排序、重挂或解除子任务，新增/删除依赖并选择日期策略。table 以缩进显示层级，table/Kanban/calendar 都显示递归进度和阻塞摘要；查询仍返回所有匹配任务，父任务未命中时子任务只以 `↳` 标识，不补入未匹配父任务、不重复数据。

## I5 共享基础视图

三种视图使用同一服务端查询结果。schema v5 的 `saved_views.presentation_json` 保存表格列宽/冻结前缀、Kanban 状态或人员分组字段、日历日期字段；schema v6 的 `tasks.board_order` 保存跨分组的稳定卡片顺序。表格列宽可拖动并立即保存；Kanban 通过单个带 task/board version 的原子命令同时更新分组字段与顺序，日历拖动使用带版本任务 PATCH；只读成员不能拖动。日历月份仅保存在 URL `month=YYYY-MM`，合法但不在当前 42 格范围内的日期单列为“其他月份”，不会混入无日期区。

失效字段、损坏 JSON 或错误类型会将保存视图整体标记为 blocked。升级 v5/v6 前会自动生成对应的 `backups/flowboard-pre-vN-*.db`，源码回滚时需同时恢复该备份。

## 启动

正式使用时直接双击仓库根目录的 `start-flowboard.cmd`，或在 PowerShell 中执行：

```powershell
.\start-flowboard.cmd
```

启动器使用仓库根目录的真实 `flowboard.db`、`flowboard-attachments` 和 `backups`，监听局域网端口 `8080`。同事使用期间需保持启动窗口运行；按 `Ctrl+C` 可停止服务。

### 本地开发调试

开发和修复 Bug 时不要使用正式库，改为执行：

```powershell
.\local-test.cmd
```

它只监听 `http://127.0.0.1:8081`，并在被 Git 忽略的 `local-test-data/` 中创建独立数据库、附件和备份。首次运行会自动建立少量虚构数据。每位开发者都使用 `test / test` 登录，该账号只在各自电脑的本地假库中拥有管理员权限，与正式系统账号及权限无关；因此普通成员也能完整修改项目和调试。`u2 / localtest`（成员）与 `u3 / localtest`（只读成员）仅用于检查权限行为。

开发数据可自由修改。需要重新开始时，先关闭本地测试服务，再删除整个 `local-test-data/` 目录并重新执行 `local-test.cmd`。正式入口 `start-flowboard.cmd` 和真实 `flowboard.db` 不用于开发调试。

## I11 评论协作、提及、附件与订阅

schema v13 将评论升级为两级线程，编辑使用 version 乐观并发并保留 `comment_versions` 历史；删除为软删除，正文不再通过普通任务详情返回，已有回复仍保留。提及只接受当前工作区有效用户或最小 `all` 目标。每个任务/用户只有一条订阅记录：创建者、评论者和直接被提及者仅在无记录时自动关注；用户手动取消后保持 `opted_out`，评论或再次提及不会偷偷恢复，只有显式订阅才能恢复。所有评论、提及、订阅和附件变更同时写入现有活动流和 `collaboration_events` 事务 outbox，事件载荷只含必要标识，不在本迭代发送通知。

schema v15 增加任务长描述、工作区回收站保留期与删除时间索引。批量更新、分配、移动、归档和删除使用逐项乐观版本校验和单一事务，任何一项 ACL、版本或结构校验失败都不会产生部分变更或事件。到期永久清理使用预览哈希、精确确认和 pre-purge 校验备份，且保留审计记录。完整 Windows 部署、备份、保留与离线恢复步骤见 [WINDOWS_OPERATIONS.md](feature-00-build-up/WINDOWS_OPERATIONS.md)。

附件使用严格有界的 JSON/base64 上传（单文件 1 MB、每任务 20 个），仅允许内容签名、扩展名与声明 MIME 一致的 PNG/JPEG/GIF/TXT/PDF；SVG、HTML 和不匹配内容会被拒绝。二进制存入 `FLOWBOARD_ATTACHMENT_DIR` 指定的私有目录（默认数据库同目录的 `flowboard-attachments`），不进入静态文件路由；下载和安全预览都会重新执行任务 ACL，并返回 `private, no-store`、`nosniff` 与沙箱 CSP。TXT 和安全图片可内联预览，PDF 只下载。元数据软删除，blob 保留以支持恢复/取证，管理员可在备份完成后按已删除元数据做离线清理。

viewer 可以读取其有权访问任务的评论、附件元数据和订阅状态，但不能评论、上传、编辑或删除。评论作者可编辑/删除自己的评论；工作区管理员可删除他人评论和附件。

## I12 通知、全局搜索、实时同步与审计

schema v14 增加无敏感正文快照的通知、确定性事件消费游标、append-only 审计和轻量实时事件。通知投影复用 I11 `collaboration_events` 与统一活动 action，采用 `(recipient,event_key)` 唯一键保证幂等；提及、订阅任务变化和显式可测试的到期扫描均在读取时按需 drain。通知列表、未读数、单条/批量已读都会重新执行当前任务 ACL，权限撤销或资源删除后不返回内容或计数。

全局搜索直接查询统一 SQLite 数据，覆盖看板、任务、评论、附件文件名和成员；空查询返回空集，查询最长 100 个 Unicode 字符，结果按精确度、类型和 ID 稳定排序，并在服务端排除私有、软删除和失效父资源。实时层使用 SSE + 持久数据库游标，浏览器断线后按游标恢复；`limit` 是每次读取的原始事件扫描上限，响应游标只推进到本次实际扫描的最后一条，ACL 隐藏批次可返回空事件但仍推进游标。连接失败时保留 5 秒 JSON/全量轮询降级。presence 仅是适合小团队的进程内在线连接计数，服务重启会清空。实时消息只携带 action 与资源定位，不替代 version/409 或授权 API。

工作区管理员可查询和导出结构化审计；登录、退出、权限变化、删除及关键业务 mutation 均使用稳定 action code。审计不记录密码、session、CSRF、附件内容或评论正文；CSV 对 `= + - @ TAB CR` 公式前缀加单引号。普通 member/viewer 在服务端得到 403，前端隐藏仅是辅助体验。

需要 Python 3.10+，无第三方依赖。

首次迁移前设置所有已有成员的初始密码；示例仅供本地开发：

```powershell
$env:FLOWBOARD_INITIAL_PASSWORD = '请替换为强密码'
python server.py
```

打开 `http://localhost:8080`。迁移自旧原型时，用户名沿用成员 ID（`u1`、`u2` 等）。首位成员是管理员，其余成员默认是普通成员。若首次迁移时没有设置环境变量，兼容默认密码为 `flowboard`，登录后应尽快通过后续账号管理能力替换；不要用该默认值正式部署。

可选环境变量：

- `FLOWBOARD_HOST`：监听地址，默认 `0.0.0.0`。
- `FLOWBOARD_PORT`：端口，默认 `8080`。
- `FLOWBOARD_DB`：SQLite 文件路径，默认仓库根目录 `flowboard.db`。
- `FLOWBOARD_ATTACHMENT_DIR`：私有附件 blob 目录，必须与静态资源目录隔离并纳入备份。
- `FLOWBOARD_BACKUP_DIR`：校验备份包目录，必须与附件源目录分离。
- `FLOWBOARD_SECURE_COOKIE=1`：HTTPS 部署时启用 Secure Cookie。

当前部署边界是公司可信局域网内的本机服务；HTTPS 反向代理不是默认上线条件。若未来服务跨越不受信任网络或用户明确要求 HTTPS，再增加反向代理并启用 `FLOWBOARD_SECURE_COOKIE=1`。

HTTP 静态服务的 GET 与 HEAD 均采用同一份默认拒绝清单：只公开入口 HTML、明确列入 `server.py::PUBLIC_PATHS` 的 CSS/JS 资源（含 dashboard、schedule、I12、I13 资源）和 `/api/health` 的最小 JSON。数据库、备份、源码、测试、点文件及其他仓库文件不会被 Web 路由下载或枚举；新增前端资源时必须显式加入公开清单并补测试。

## 迁移、备份与恢复

首次启动或升级会先运行 SQLite `integrity_check`，再使用 SQLite backup API 在 `backups/` 生成对应目标版本的迁移前备份，然后执行版本化迁移。schema v3 增加字段系统，v4 增加保存视图，v5 增加 presentation，v6 增加 Kanban board order，v7 增加任务邻接层级与依赖边，v8 增加高级字段类型和跨看板关系边，v9 增加模板快照和导入预览批次，v12 增加评论协作与私有附件元数据，v13 将订阅归一为每任务/用户一条 sticky 状态记录，v14 增加通知、实时游标和安全审计，v15 增加任务描述及回收站保留策略，v16 增加 feature01 五张 timeline 专表，v17 增加标签/个人顺序，v18 增加手工归档，v19 增加活跃项目名称大小写不敏感唯一约束。v16 DDL 使用逐条执行，避免 `executescript` 隐式提交破坏失败回滚；运行库使用 WAL；服务运行时不要用文件复制替代一致性备份；恢复时数据库与附件目录必须取同一备份时间点。

门 4 已在隔离目录验证 v15→v16 迁移、幂等、故障回滚和备份恢复；其后真实库经授权于 2026-08-25 迁移至 v18、2026-08-28 迁移至 v19。2026-09-04 只读复核：`user_version=19`、`integrity_check=ok`、外键违规 0；当前业务数据快照为 5 active / 1 archived / 2 soft-deleted 时间项目和 107 个节点。该计数会随生产使用变化，不是固定验收常量。

恢复演练应在停止服务后进行：先把备份通过 SQLite backup API 恢复到独立路径，运行 `PRAGMA integrity_check` 并核对任务数和关键字段，确认无误后再替换运行库。架构与分迭代说明见 [PHASE1_ARCHITECTURE.md](feature-00-build-up/PHASE1_ARCHITECTURE.md)。

## 测试

日常修复先运行与改动相关的专项测试；已有可信 PASS 且相关内容未变化时，提交阶段复用结果。以下是产品全量回归入口，按风险或明确要求运行，不是每次同步/提交的默认步骤。

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
node --test (Get-ChildItem tests -Filter *.test.js | ForEach-Object FullName)
git diff --check
```

测试在临时数据库副本和临时端口上运行，不修改仓库中的运行库。Windows sandbox 若禁止 Chromium/Node 子进程，应在受控的沙箱外运行相同完整套件，不能跳过断言。最终验收索引见 `GLOBAL_ACCEPTANCE.md`。

提交阶段若需要包含语法和运行数据核验的完整检查，可在修复已提交到本地分支、工作区干净时使用 `.agents/skills/commit-push-pr/scripts/run-flowboard-checks.ps1`；它只枚举 Git 跟踪源码，Python 在单个进程中检查且不写入源码目录。上面的产品套件可直接用于尚未提交的修复。单个 Python 专项可用 `python -m unittest discover -s tests -p 'test_name.py' -v -f`，前端专项可用 `node --test tests/timeline_ui.test.js` 等对应文件。

Git 协作工具的隔离测试单独运行；仅在修改相关 skill/脚本或明确要求时使用，不随上面的产品测试自动执行：

```powershell
python -m unittest discover -s tests/skill_checks -p 'test_*.py' -v -f
```

`tests/skill_checks/` 不作为 Python package（不添加 `__init__.py`），以保持两个 unittest discovery 入口独立。Git 工具测试只使用临时本地仓库。

feature01 门 4 终值测试矩阵（2026-08-20）：

- Gate 3 旧基线：12 个 Python + 5 个 Node 文件全部保留，旧 Python 测试方法 79/79，零 skip；经用户授权，仅把 8 个旧 Python 文件中“当前 schema/备份前缀”的过期 v15 预期改为 `SCHEMA_VERSION`，历史 v15 checksum、旧库版本、数据/FK/integrity/权限断言未弱化。
- Python 全量（含真实 Chromium）：142/142，`OK`；timeline 分栏为 service 29、HTTP 10、Chromium 24。
- Node：6/6 测试文件通过；JavaScript 语法检查通过。
- v15→v16 隔离迁移/备份/恢复验证器 exit 0；修改迁移事务后，timeline service 29/29 回归通过。
- Python 语法检查和字面全仓 `git diff --check` 均 exit 0。

## feature01 生产运行状态

feature01 的原 `WAIT_GATE5_HUMAN`、`TAG_INCREMENT_WAIT_HUMAN`、`PORTFOLIO_CANVAS_WAIT_HUMAN` 和 `ARCHIVE_VIEW_WAIT_HUMAN` 均为上线前历史状态。真实数据人工验收、正式启动入口、真实库部署和局域网使用已经完成，当前阶段为 `PRODUCTION_RUNNING / STAGE8_CLOSEOUT`。

- 正式服务自 2026-08-31 起运行；PR #1/#2 已合入，2026-09-04 本地 `main` 与 `origin/main` 同步在 `6e66f7f`。
- 9 月 3 日完成聚焦节点旗标升级，9 月 4 日完成旗标直拖与拖拽选中反馈升级；本次文档重基线复跑 `node tests/timeline_ui.test.js` PASS，关联 Chromium 2/2 PASS。
- `AUD-03` 窄屏导航和纯键盘打开项目右键菜单仍是可选体验/可访问性改进，不阻断当前桌面端生产。新功能或范围升级仍须用户另行拍板。

## 核心生命周期运维复查清单

1. 使用 `u1` 登录，创建看板并验证名称、描述、颜色和访问类型编辑；刷新确认颜色持久化，再验证复制、归档、恢复和软删除。
2. 在看板中新增分组，验证重命名、复制、上下排序、归档和删除菜单。
3. 新增任务，在详情中编辑标题和基础字段并刷新确认持久化，再验证评论、复制、跨组移动、拖拽、归档和删除。
4. 从“已归档”和“回收站”恢复项目，并确认父级已删除时子级恢复会给出明确错误。
5. 使用只读成员登录，确认写操作控件隐藏，且直接调用写 API 仍返回 403。
6. 检查活动时间线；在两个浏览器窗口并发编辑同一对象，确认旧版本写入返回版本冲突。

## 当前边界

Flowboard 已进入局域网生产运行和反馈维护。统一查询 AST 支持 AND/OR、按字段类型限定的筛选、多字段真类型排序、稳定兜底排序及严格 422；保存视图支持个人/共享、默认优先级、复制、更新和软删除，无效保存配置会阻止执行而不会扩大结果。前端筛选、排序和视图调用同一服务端查询入口，I12 全局搜索覆盖五类实体。旧 `status/priority/owner/due` 仍作为事务内同步的回滚投影。表格、Kanban、月历、SSE 实时同步及轮询降级已实现；I13 已加入原子批量操作、保留期清理与可校验的数据库加附件备份/离线恢复工具。当前默认工作不是扩产品范围，而是根据真实使用反馈做小批次修复并维持数据可恢复性。
