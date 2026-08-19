# 门 3 · 单元 ①「领域对象与派生规则」技术方案草案

> 状态：planner 草案 v1（2026-08-18）。**拍板结果（2026-08-18，全项收口，见 `5-GATE3_UNIT1_DECISIONS.md` §0）**：D1=A D2=A D4=A D7=A D8=A **D10=修订为「本周（周一~周日）」窗口**（覆盖推荐 A，配套细则见问卷 §0 第 6 条）D12=B D13=A；P1=A（D3/D5/D6/D9/D11/D14 打包冻结）。**画法拍板（同日）= A 链式**（配套：服务端在链式段之外同派生「阶段区间列表」供重叠分半/展开拆行，服务端单一实现不变，见对照稿拍板区）——单元 ① 完全收口。§0 速览表状态列为出题时快照，以问卷 §0 确认记录为准。**拍板前不编码、不改库的约束继续有效，直至门 3 评审整体通过。**
> 依据：feature01 `STATE.md`（§2/§5/§7）、`mainline-feature01.md`（§2–§6/§8）、`mc-plan/Mc思考03`（§3 缺口 / §5 推进顺序 / §6 待拍板清单）。
> 代码证据均为本次只读勘察核实（文件:行号）；运行库 `flowboard.db` 仅执行了只读 `PRAGMA` 与 `COUNT`，未做任何写操作。
> 主 Claude 抽查复核（2026-08-18）：boards/tasks 无 created_by（database.py:160-171/187-201）、activity 表 board_id NOT NULL + entity_type CHECK（database.py:323-333）、SCHEMA_VERSION=15（database.py:10）——草案 §1.1/§1.2/§1.4 承重论据属实。
> **DDL 修正注记（2026-08-18，单元 ③ F2-④=b 拍板后）**：用户定调「项目名称是唯一标识，不允许同名」——本文 timeline_projects 的 `UNIQUE(workspace_id, name, deleted_at)` 因 SQLite 中 NULL 互不相等、实际不约束活跃行（deleted_at IS NULL），**改为部分唯一索引 `… ON timeline_projects(workspace_id, name) WHERE deleted_at IS NULL` + service 层显式校验 422 NAME_CONFLICT**；唯一性范围=workspace 内活跃项目（软删名称可复用）。详见 `8-GATE3_UNIT3_DECISIONS.md` §0.1 R4；门 3 总固化时并入《技术方案冻结版》。

---

## §0 决策点速览表

| # | 问题 | 选项 | planner 推荐 | 置信度 | 状态 |
|---|------|------|-------------|--------|------|
| D1 | 数据模型落位 | A 复用 boards/tasks 加列 / B 新增专表 | **B 新增专表** | 高 | 【待拍板】 |
| D2 | 「项目」与 board 的映射 | 独立实体 timeline_projects / 一项目=一 board | **独立实体，不与 board 挂钩** | 高 | 【待拍板】（与 D1 联动） |
| D3 | created_by / initial_date 不可变的执行机制 | service 层校验 / DB 触发器双保险 | **service 层 + API 永不暴露该字段 + 测试锁定**，不引入触发器 | 高 | 建议直接冻结 |
| D4 | 「已完成」的持久化载体 | done_at 时间戳 / 0-1 标记列 | **done_at TEXT（UTC 时间戳，内部字段）** | 中 | 【待拍板】（涉及「不新增完成日期列」表述边界） |
| D5 | 审计批次载体 | 扩展现有 activity 表 / 新增 timeline 专表 | **新增专表 + 每批写一行 audit_log 桥接** | 高 | 建议直接冻结（复用 activity 需重建表，约束已证，见 §1.4） |
| D6 | 指标 M1 项目开始日期 | 两轨合并全部节点 min(date)（含已完成/未开始）/ 仅未开始 / 仅主线 | **两轨合并、全部未删除节点取 min(date)** | 高 | 建议直接冻结 |
| D7 | 指标 M2 当前阶段 | 已开始阶段中序最大（跨两轨）/ 最新日期节点的阶段 / 主线轨优先 | **已开始阶段中六阶段序最大，跨两轨**；无已开始节点 → 「未开始」 | 中 | 【待拍板】 |
| D8 | 指标 M3 最近临近节点 | date≥today 且未完成 / 严格 >today；同日取舍 | **date≥today 且状态≠已完成，同日多节点全返回**，排序键 (date, 阶段序, 主线优先, 节点名) | 中 | 【待拍板】 |
| D9 | 指标 M4 逾期未完成节点数 | 两轨合并计 / 分轨计 | **date<today 且状态≠已完成，两轨合并单值** | 高 | 建议直接冻结 |
| D10 | 指标 M5 「7 天内节点」窗口 | 含今天与否 / 是否只算未完成 | **[today, today+6] 共 7 个日历日、只算未完成**（与 M3 同一谓词基） | 中 | 【待拍板】（右端点易歧义） |
| D11 | 派生指标计算方式 | 查询时实时计算 / 落库缓存 | **实时计算 + 专用索引**（约 10 项目 × 数十节点，无缓存必要） | 高 | 建议直接冻结 |
| D12 | Excel 导入状态矛盾语义 | A 拒绝矛盾行 / B 日期优先（仅收「已完成」）/ C 信任三态文本 | **B 日期优先覆盖重算**；C 实质重开已冻结的状态派生模型，不建议 | 高 | 【待拍板】（codex 缺口 2，明确交用户） |
| D13 | 链式 vs 跨式数据契约 | 节点数组主契约+服务端派生区间 / 只给节点 / 只给区间 | **API 恒返回 节点数组+区间数组；区间算法（链式/跨式）留可切换开关**；跨式对已拍板的分半渲染更直接 | 中 | 【待拍板】（等 HTML 对照稿，本单元只锁数据结构） |
| D14 | 「今天」的时区基准 | 服务器 Asia/Shanghai 本地日 / UTC | **Asia/Shanghai 本地日，服务端统一计算** | 高 | 建议直接冻结 |

---

## §1 现状勘察结论（全部经代码核实）

### 1.1 schema 与迁移机制（`flowboard/database.py`）

- 当前 `SCHEMA_VERSION = 15`（database.py:10）；迁移机制 = `PRAGMA user_version` 顺序执行 `_migration_v1`–`_migration_v15`（database.py:68–120），每步单事务、迁移后跑 `foreign_key_check` + `integrity_check`（如 v2：392–397）。
- **迁移前自动备份**：版本升级前 `_backup_database` 生成 `backups/flowboard-pre-vN-时间戳.db` 并先做 integrity_check（database.py:48–65, 82–83）。backups/ 目录现存 v1→v15 共 14 个快照，机制真实运转过。
- 迁移账本表 `schema_migrations(version, name, checksum, applied_at)`（database.py:228–233）。
- 软删除 = `deleted_at`/`deleted_by` + 归档 `archived_at`/`archived_by`，覆盖 boards/groups_/tasks（v1 DDL + v2 加列，database.py:168–169, 184–185, 197–198, 310–318）；回收站保留期 `workspaces.trash_retention_days`（v15，database.py:931–932）。

### 1.2 boards/tasks 无 created_by（纠偏结论复核为真）

- `boards` DDL（database.py:160–171）：workspace_id/name/description/color/access_type/version/deleted_at/deleted_by/created_at——**无 created_by**。`deleted_by`/`archived_by` 是生命周期操作人，语义不是创建者。
- `tasks` DDL（database.py:187–201）：group_id/title/status/priority/due/owner_id/sort_order/version/deleted_at/deleted_by/created_at/updated_at——**无 created_by**。运行库实存 DDL 与源码一致（只读 sqlite_master 核实）。
- 已有 created_by 先例：`task_dependencies`（database.py:604）、`board_templates`（database.py:694）、`import_batches`（database.py:710）、`task_relation_values`（database.py:661）——**加列/建表带 created_by 在本库是既有惯例，不是新发明**。

### 1.3 权限检查现状（`flowboard/service.py`）

- 写权限链：`_workspace_role`（177–186，挡 viewer）→ `_board_access`（188–202，open 板任何 member 可写、private 板 admin 或列名成员）→ `_group_context`/`_task_context`（204–237 逐级下钻）。**现状无任何创建者校验**——feature01 的「member 仅改 created_by=自己」是全新钩子，需要新的 `_project_access` 类辅助函数（§8）。
- admin 判定模式：`self._workspace_role(...)!="admin"` → 403（如 audit:2776、backups:2795、memberships:2824）。
- 并发：行级乐观版本号 `require_version`（60–63）+ `_conflict` 409（269–272）；`update_task` 版本不符即 409（2171）；批量整批单事务全成全败（`batch_tasks` 2196–2266；`commit_import` 1388–1447）。

### 1.4 审计/活动机制（关键约束）

- `activity` 表带 **`CHECK(entity_type IN ('board','group','task','comment'))` 且 `board_id NOT NULL`**（database.py:322–333；运行库实存 DDL 核实同样成立）。service 层还有第二道锁 `ENTITY_TYPES`（service.py:27, 241–242）。→ **想往 activity 塞 timeline 实体必须重建该表（CHECK 不可 ALTER）且 board_id 无处安放**。
- `_activity` 一次写三表：activity + audit_log（source_key UNIQUE 幂等）+ realtime_events（service.py:240–254）。
- audit_log：workspace 级、含 outcome(success/denied/failure)、admin 专用的查询与 CSV 导出（service.py:2773–2790）。
- **批次审计先例已存在**：`batch_tasks` 用 `batch_key=secrets.token_hex(12)` 写进每条 activity 的 details_json（service.py:2242, 2261）——但这是「同键散条」，不是独立批次表；feature01 需要「一次提交=一个可撤销批次」的强结构。

### 1.5 Excel/导入导出（`flowboard/transfer.py` + service 导入路径）

- 有界解析：MAX_FILE_BYTES=1.5MB、MAX_ROWS=1000、MAX_COLUMNS=100、Excel 公式拒收（transfer.py:8–13, 54）、压缩炸弹防护（69）、CSV 编码 utf-8-sig/gb18030（41–44）。
- 行级报错机制成熟：`commit_import` 校验失败抛错时 details 带 `row`（从 2 起=数据行号）与列名/字段（service.py:1417–1428）。
- 导入批次两段式：`preview_import` 存 `import_batches`（含 created_by、sha256，1346）→ `commit_import` 整批一个事务提交（1388–1447）。feature01 的 Excel 导入可直接沿用此骨架。

### 1.6 tasks 的「列 + 动态字段」双投影（选 B 的重要论据）

tasks 的 status/priority/due/owner 同时落在 tasks 列和 field_definitions/task_field_values，每个写路径都要维护两份（create_task:2140–2148、update_task:2172–2190、commit_import:1433–1442）。把 feature01 节点塞进 tasks 意味着要么给每列造双投影、要么留空穴破坏一致性。

### 1.7 备份机制（`flowboard/operations.py` + `flowboard_ops.py`）

- 完整备份包 = DB 快照 + 附件 + sha256 manifest + 自校验（operations.py:52–78）；恢复 = 离线 CLI、staged 原子替换 + 恢复前安全备份 + 失败回滚（134–167）；保留策略默认留 10（122–131）。
- 运行库现状（只读计数）：user_version=15；4 用户（1 admin + 3 member）、1 workspace、2 boards、2 groups、6 tasks、activity 4 条、audit_log 9 条。**存量数据极小，迁移的真正风险是代码回归面，不是数据体量**。

### 1.8 其他

- `schedule.py` 已有单日里程碑/起止区间的投影与关键路径（schedule.py:20–52），但它是 saved_views 的投影层，不落库、无业务链概念，与 feature01 的「同轨道日期链」不同构，不构成可复用的领域模型。
- server.py 为 http.server 手工路由（server.py:120–321），新端点纯增量，无框架约束。

---

## §2 数据模型落位（D1/D2）

### 方案 A：复用 boards/tasks 加列

- 做法：boards 充当「项目」（加 created_by）；tasks 充当「节点」（加 track/stage/initial_date/done 标记/「kind=timeline」判别列），必要时造合成 group。
- 赌注：
  1. **回归面最大化**。timeline 节点会出现在现有看板/甘特/聚合/仪表盘 widget/搜索/导出的一切查询里（除非每个现有查询都加 kind 过滤——13 个测试文件和全部 read 路径都要动），直接违反「不得破坏第一阶段旧数据/旧功能」红线的精神。
  2. **双投影强加身**（§1.6）：每个节点写路径都要同步 field_definitions/task_field_values，而 feature01 根本用不上看板字段体系。
  3. 权限模型被迫两义：现有 board 写权限（open=member 可写）与 feature01 项目写权限（member 仅 created_by）在同一张表上冲突，判别逻辑散落。
  4. 存量 boards 无 created_by，需要回补语义决策（2 块旧板归谁？）。

### 方案 B：新增专表（推荐）

- 做法（v16 迁移，纯 CREATE TABLE 增量）：

```sql
CREATE TABLE timeline_projects(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(id),   -- 首次创建系统写入，永不可改
  version INTEGER NOT NULL DEFAULT 1,              -- 项目级并发锚点（单元②用）
  deleted_at TEXT, deleted_by TEXT REFERENCES users(id),   -- 沿用软删除惯例
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(workspace_id, name, deleted_at)           -- 同 workspace 活跃项目名唯一（软删除后可重名）
);
CREATE TABLE timeline_nodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES timeline_projects(id),
  track TEXT NOT NULL CHECK(track IN ('main','parallel')),
  stage TEXT NOT NULL CHECK(stage IN ('创意','设计','开发','测试','量产','应用迭代')),
  name TEXT NOT NULL,                              -- 节点名称（二级标签）
  date TEXT NOT NULL,                              -- 当前有效日期 YYYY-MM-DD
  initial_date TEXT NOT NULL,                      -- 首次保存日期，成员不可见不可改
  done_at TEXT,                                    -- 已完成标记：NULL=未手工完成（D4）
  remark TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  deleted_at TEXT, deleted_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX idx_tln_project ON timeline_nodes(project_id, deleted_at, track, date);
```

- **间隔不落库**：已冻结「系统内部间隔始终按日期时间链计算」（mainline §4.1），间隔是 date 链的派生值，读取时按轨道 date 前驱实时算——天然免疫不一致。
- **状态不落库**（除 done_at）：三态中两态是日期派生（§5 总定义）。
- 赌注（B 的代价，如实列出）：新表=新代码路径，boards 侧的看板能力（字段/视图/评论）对项目时间轴全部不可用——但 feature01 的冻结字段清单（8 列）本就不需要它们；管理上「项目」成为与 board 并列的一级实体，导航需要新增入口（产品已在 mock 中如此呈现）。

### 推荐：方案 B，置信度高

理由：字段清单与 tasks 结构不同构（间隔/状态均派生）、双投影是纯负担、回归面从「全库读路径」缩到「零」（纯增量迁移，现有测试套件原样通过即第一阶段回归主体）；权限钩子干净落在新表 created_by 上，不与现有 board 开放写模型互扰。mainline §5「不整体重写、不拆独立系统」与 B 兼容——B 是叠加，不是重写。

**D2 映射定义**：一个项目 = 一行 timeline_projects，与 board 零外键关联。10 个并行项目 = 10 行。不搞「一项目=一 board」，理由如上；未来若要「项目挂看板」是受控变更（加可空列即可），现在不做。

风险与回退：B 的最大风险是「两套实体并存的长期心智成本」——若用户认为项目必须复用 board（例如希望看板与时间轴同屏），则退回 A，代价是接受判别列 + 全读路径过滤的回归成本（建议此时仍保留独立节点表，仅让 board 与 project 建立映射行，混合方案；此为 A/B 之外的折中，仅在用户否决 B 时展开）。

---

## §3 created_by / initial_date 落位（D3/D4）

- **落位**：`created_by` 在 timeline_projects（项目级权限锚点，冻结语义是「member 仅可改自己创建的**项目**」，节点表不加 created_by，节点归属由 project 决定）；`initial_date` 在 timeline_nodes。
- **类型**：均为 TEXT；created_by 引用 users(id)；initial_date 为 YYYY-MM-DD，NOT NULL，首次保存时 = date。
- **存量回补**：方案 B 下新表从空开始，**不存在回补问题**（导入建项目时 created_by=导入操作者，复用 import_batches 既有惯例 database.py:710、service.py:1396）。这是 B 相对 A 的一个被低估的优势。
- **不可变执行机制（D3）**：推荐 service 层三重执行——① API 请求体白名单 `reject_unknown` 不含 created_by/initial_date（全库既有惯例，如 service.py:1876）；② UPDATE 语句永不包含这两列（代码评审 + 测试锁定「任何路径改不动」）；③ 例外入口（admin 纠正 initial_date）走独立端点，只改 initial_date 且强制产生 initial_correction 批次（§4）。**不引入 SQLite 触发器**：全库现状零触发器（已核实），触发器会把业务规则藏进 DB 层、增加迁移/恢复排障成本，而本库的权限/版本/审计全部在 service 层，风格一致优于双保险。置信度高。
- **D4 已完成载体**：推荐 `done_at`（UTC 时间戳）。它同时是「已完成」标记和完成时间证据（STATE §2「完成时间由审计/修改历史承载」——done_at 即最轻的承载，且不是用户可见的【完成日期】列，不违反「不单开完成日期列」）。右键菜单【未完成】= 置 NULL。备选 0-1 标记列 + 完全依赖审计表查时间，查询稍省、取证多一跳。置信度中，交拍板（因为触及「完成日期」表述边界，需用户确认 done_at 不被视为新增列）。
- 风险与回退：service 层唯一的弱点是「未来新写路径漏防」——用一条专门测试（尝试经所有端点改 created_by/initial_date 必败）钉死；若 mc-expert 认为不够，补触发器成本很低，可后加。

---

## §4 审计批次表 sketch（D5）

### 结论：新增专表，不复用 activity（置信度高，约束性证据）

activity 的 CHECK 约束 + board_id NOT NULL（§1.4）决定了复用=重建表，收益为零（timeline 无 board 概念、不需要 realtime 推送、不需要看板动态流）。**与现有机制的关系=并存+桥接**：每提交一个批次，向 audit_log 写一行桥接记录（`source_key = "timeline_batch:{id}"`、action_code 如 `timeline.batch_committed`、outcome=success），使 admin 的统一审计查询/CSV（service.py:2773–2790）无需改造即可看到 timeline 操作。不写 activity / realtime_events。

### 表结构草案（字段级）

```sql
CREATE TABLE timeline_change_batches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES timeline_projects(id),
  actor_user_id TEXT NOT NULL REFERENCES users(id),
  change_kind TEXT NOT NULL CHECK(change_kind IN (
      'direct_edit',          -- 直接修改（日期/间隔/名称/阶段/轨道/备注）
      'status_toggle',        -- 状态切换（已完成/未完成）
      'initial_correction',   -- 历史日期修正（admin 例外入口，改 initial_date）
      'undo')),               -- 反向撤销批次
  trigger_source TEXT NOT NULL CHECK(trigger_source IN ('editor','drag','import','undo','admin')),
  project_version_before INTEGER NOT NULL,
  project_version_after  INTEGER NOT NULL,
  undone_batch_id INTEGER REFERENCES timeline_change_batches(id),  -- undo 批次指向被撤销批次
  details_json TEXT NOT NULL DEFAULT '{}',   -- 如 {mode:'顺延', magnet:'standard', file_sha256:...}
  created_at TEXT NOT NULL
);
CREATE TABLE timeline_node_changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES timeline_change_batches(id),
  node_id INTEGER NOT NULL REFERENCES timeline_nodes(id),
  change_role TEXT NOT NULL CHECK(change_role IN ('direct','cascaded')),  -- 直接修改 vs 自动顺延受影响
  field TEXT NOT NULL CHECK(field IN ('date','done_at','initial_date','stage','track','name','remark','created','deleted')),
  old_value TEXT, new_value TEXT          -- created 行 old 为 NULL；间隔变化随 date 前后值可推导，不单独存
);
CREATE INDEX idx_tlcb_project ON timeline_change_batches(project_id, id);
CREATE INDEX idx_tlnc_batch ON timeline_node_changes(batch_id, node_id);
```

### 五类变更的映射方式

冻结语义是「级联顺延记录为**一次操作批次**，区分直接修改与自动影响」（STATE §4）——所以**「直接修改」与「自动顺延」不是两种批次，而是同批内两种行角色**：改 B 日期顺延 C/D → 一个 `direct_edit` 批次，B 的行 change_role=direct、C/D 的行 change_role=cascaded。五类全覆盖：直接修改+自动顺延（direct_edit 批 + 行级 direct/cascaded）、状态切换（status_toggle 批）、历史日期修正（initial_correction 批，仅 admin）、撤销（undo 批 + undone_batch_id 链）。

轻量复盘四问（STATE §4：初始日期/当前日期/净变化天数/直接修改次数）全部可由这两表 + timeline_nodes 直接聚合，无需新冗余列。

风险与回退：批次表无 UNIQUE 幂等键（不像 audit_log）——提交走单事务（单元②）保证原子性即可；undo 只撤「项目最新批次」的护栏在单元② 定，本表结构已留 undone_batch_id。若未来发现 undo 需要多级，加列即可，不动存量。

---

## §5 派生指标契约（D6–D11，codex 纠偏缺口 1）

**前置总定义（一切指标共用）**：

- 节点宇宙 = 该项目全部 `deleted_at IS NULL` 的 timeline_nodes（两轨合并；项目软删除则整体不参与）。
- `today` = 服务器 Asia/Shanghai 本地日（D14）。15 人局域网团队单时区，客户端与服务端一致；全指标服务端计算，前端不得自算「今天」。
- 状态派生（唯一权威定义）：`已完成` = done_at 非空；否则 `date >= today → 未开始`，`date < today → 进行中（隐含逾期）`。

### M1 项目开始日期（D6）——建议直接冻结，置信度高

- 定义：`min(date)` over 节点宇宙。**含已完成、含未开始节点，两轨合并**。理由：项目开始=最早里程碑日期，与状态无关；只算未开始会把已完成的开端节点错误排除。
- 边界：零节点项目 → NULL，全项目仪表盘排序置于最后、显示「—」。

### M2 当前阶段（D7）——【待拍板】，置信度中

- 推荐：`已开始(stage) := ∃节点(date <= today 且属于该阶段)`，当前阶段 = 已开始阶段中**六阶段序最大者**（跨两轨）。
- 边界规则：无任何已开始节点 → 「未开始」（显示于最早节点之前状态）；today 晚于全部节点 → 仍是「已开始阶段序最大」，即项目末期的最后阶段（不会出现「已结束」态，六阶段固定无第七态）。
- 备选与否决理由：按最新日期节点取阶段——同日多节点/双轨交错时结果抖动，不单调；主线轨优先——并行轨领先时（如并行已进测试、主线还在设计）会谎报进度，违背「仪表盘必须真实表达并行」（mainline §4.3）。
- 剩余赌注：「序最大」会让早阶段并行轨的存在被吞掉——这是提示语义（配合行内展开可看到并行），可接受，但请用户确认。

### M3 最近临近节点（D8）——【待拍板】，置信度中

- 推荐：`{节点： date >= today 且 非已完成}` 中 date 最小者；**含今天**（今天到期未完成是最急的）；**同日多节点全部返回**（不隐式丢弃），排序键 `(date, 阶段序, 主线优先, 节点名)`，API 返回列表，UI 可显示「今天 ×N」。
- 边界：集合空（全部完成或全在过去）→ NULL，全项目排序按 M1 兜底。

### M4 逾期未完成节点数（D9）——建议直接冻结，置信度高

- 定义：`count(date < today 且 done_at IS NULL)`，**两轨合并单值**。已冻结状态语义的直接推论（进行中且 date<today 即隐含逾期）；红点阈值 = 该数 ≥ 1。

### M5 7 天内节点（D10）——【已拍板·用户修订】，2026-08-18

- **拍板结果（覆盖本节原推荐）**：窗口 = **本周（周一 ~ 周日，包含今天的自然周）**，非滚动 7 天窗口。`count(本周一 <= date <= 本周日 且 非已完成)`，**含本周已过去的天**；周基准与 D14 同（Asia/Shanghai）。红点 M4 不变（date<today 且未完成，不限本周）；红橙语义独立可并存（本周内过期的未完成节点两点同亮，显示红左橙右）。用户同时预留未来「每周看板（本周工作提示）」候选，不进 feature01 v1。原推荐 [today, today+6] 滚动窗口**作废**；本节保留出题原文仅供追溯。

### 计算方式（D11）——建议直接冻结，置信度高

**查询时实时计算，不落库缓存**。量级：约 10 项目 × 数十节点 = 数百行，走 `idx_tln_project(project_id, deleted_at, track, date)` 一次扫描即可同时产出全部指标与区间数组；缓存则每个批次提交都要失效重算，纯属负收益。同理**间隔也实时派生**。未来若项目数 ×100 再议缓存，契约不变只变实现。

---

## §6 Excel 导入状态语义（D12，codex 纠偏缺口 2）

前提（已冻结，不可动）：状态只收三态、间隔导入忽略、单一 sheet 首列=项目名称、行级报错给行号（STATE §7 第 4 条）。本决策只补一个洞：**导入文本与日期派生矛盾时怎么办**。矛盾的具体形态：「未开始」文本 + date<today（派生=进行中）；「进行中」文本 + date≥today（派生=未开始）；「已完成」文本与任何日期**都不矛盾**（它是唯一人工态，冻结模型允许任何日期手工完成）。

- **A 拒绝矛盾行（行级报错）**：赌注=旧文件重导几乎必然带过期状态文本（导出后日期被拖动过），用户会被大量无害报错打断；且「未开始/进行中」两态文本在系统内是零信息冗余，为冗余信息报错不成比例。
- **B 日期优先覆盖重算（推荐，置信度高）**：导入时只认「已完成」（写 done_at=导入时刻），「未开始/进行中」文本**仅当参考、落库以日期派生为准**；非三态文本仍然行级报错（守住已冻结的「只收三态」）；状态列为空 → 按日期派生。理由：「已完成」是唯一不能从日期恢复的信息，必须收；其余矛盾按冻结模型日期说了算，与编辑器内行为完全一致（同规则共享，mainline §9）。代价：导入后编辑器显示的状态可能与 Excel 里肉眼看到的不同——需要在导入预览里明示「状态将按日期重算」。
- **C 信任导入文本（三态全收）**：要求持久化「未开始/进行中」的人工覆盖位，否则无处安放——这**实质重开已冻结的状态派生模型**（STATE §2 节点状态 2026-08-14 确认），按纪律不应作为推荐项，仅列出供否决。

风险与回退：B 落地后若用户实际数据里大量存在「日期已过但真没开始」的节点，正确出口是改日期或标已完成，而不是让文本覆盖——维持 B；真需要「过期但未开始」语义时那是冻结模型变更，须用户显式重开，另走流程。

---

## §7 链式 vs 跨式：数据结构影响（D13，画法对照稿另出）

范围声明：本节只锁**查询结果形态与 API 数据结构**，视觉对照按 mainline §8 安排出 HTML 后由用户再定一次，此处不预支视觉决策。

| 维度 | 链式（相邻节点连线成条） | 跨式（阶段首末节点撑开成条） |
|---|---|---|
| 查询形态 | `ORDER BY track, date`（+同日排序键），无聚合 | `GROUP BY (track, stage)` 取 min(date)；末端正点=本阶段最后节点日期（或延伸到下一阶段首节点日，取决于对照稿定案） |
| 返回结构 | 节点数组/轨，前端自算段 | 区间数组/轨（每阶段一条） |
| 段归属 | 段的颜色由左端节点阶段决定；阶段交错（设计节点夹在两个开发节点之间）时忠实呈现夹层 | 阶段区间由 min/max 撑开，交错日期表现为**两阶段区间重叠** |
| 与已拍板「重叠段上下分半 + 展开按钮按阶段拆行」的关系 | 前端必须先把相邻段合并回「阶段区间」才能判断重叠、分半、拆行——等于客户端再实现一遍跨式 | 重叠区间是查询的直接产物，分半判定（区间相交）与展开（每阶段一行）零转换 |
| 对派生指标的影响 | 无（M1–M5 均只依赖节点级 date/done_at/阶段） | 无 |

**推荐契约（与最终画法解耦）**：API 恒返回两份——`nodes[]`（编辑器与详情的唯一事实源）+ `segments[]`（服务端按「当前选定的段算法」派生的区间数组）。链式/跨式=服务端一个可切换的段算法开关，切换只改 segments 内容不改 API 形状，两类仪表盘共享同一段派生实现（满足 mainline §9「共享同一份数据和业务规则」）。**就分半渲染的友好度而言，跨式（区间数组）更直接**；链式的优势（交错日期的忠实夹层呈现）是否值得用户牺牲一点实现直白性，留给 HTML 对照稿验证。置信度中。

---

## §8 单元 ②/③ 的接口预留

本单元一旦拍板即**锁定**：

1. 表结构三件套（timeline_projects / timeline_nodes / timeline_change_batches + node_changes）及 v16 纯增量迁移形态——单元② 的 API 与单元③ 的迁移/回归都以此为地基；字段在 v16 一次建齐（含 done_at/initial_date/version/trigger_source），**避免二次迁移**。
2. 权限锚点：created_by 只在项目级、`_project_access(conn, user, project_id, write=)` 辅助函数形态（admin 全改 / member 仅 created_by=自己 / viewer 挡写，与 _board_access 188–202 同构不同表）。
3. 派生指标与段派生的**唯一实现位置 = 服务端**（前端只消费），单元② 的批量提交后返回值可直接复用同一派生器产出最新视图。
4. 并发锚点：timeline_projects.version 每批 +1（批次表已存 before/after），undo 护栏「仅可撤项目最新批次」的数据基础在本表。

本单元**留口不锁**：批量 API 端点形状/整批全成全败与 409 语义、撤销的交互细节（单元②）；迁移执行 runbook、Excel 解析器列映射细则、深色主题范围、第一阶段回归清单的最终形态（单元③）；链式/跨式最终画法（HTML 对照稿）；磁吸强档参数（集成验收）。

---

## §9 不改变的事实（已冻结，本草案一律当输入，未重开）

- 权限模型：admin 全项目可写、member 仅 created_by=自己、查看全员开放、未登录不可见；created_by 系统首写后永不可改（含 admin）；initial_date 纠正仅 workspace admin；导入项目 created_by=导入者；服务端执行。
- 业务模型：六阶段固定不可增删改序；一行=单日里程碑；双轨独立日期链与顺延规则（日期优先、只顺延本轨后续、删除只重算间隔、保存后一次撤销）；单【日期】列，无计划/实际双列；排序切换不改数据。
- 状态三态及派生语义（日期≥今天=未开始 / <今天未手工完成=进行中隐含逾期 / 手工完成=已完成）；不单开用户可见【完成日期】列；不强制修改原因。
- 行模型与视觉基线：默认主线/并行两行+展开按钮、仅重叠段上下分半；方向 B 深色、v3.2 色板、) 形分界、白圈节点、2px 小圆角、右键四项菜单、无默认档拖拽、磁吸标准档、±10 天×8 放大带。
- 轻量复盘边界：无 baseline/定期快照/复杂 BI；复盘=按单/多项目筛选看初始日期、当前日期、净变化、直接修改次数、修改历史。
- Excel 边界：只作导入导出；单一 sheet 首列项目名称、间隔导入忽略、状态只收三态、行级报错给行号。
- 工程红线：迁移前备份且可恢复、不破坏第一阶段数据、软删除优先、每检查点五件套；mainline §5 不做清单全部维持。
- 流程红线：门 3 期间不编码、不碰主程序与运行库；冻结决策的任何变更须用户显式拍板。

---

**planner 附注（低置信度项申报）**：D7（当前阶段取法）、D8（同日多节点全返回）、D10（7 天窗口右端）、D13（段契约与链式/跨式倾向）置信度为中——其中 D7 涉及「序最大吞掉并行轨领先信息」的产品判断，建议交 mc-expert 陪审或用户拍板；其余高置信度项可随草案一并过，但均已在 §0 标注状态，不构成既成事实。
