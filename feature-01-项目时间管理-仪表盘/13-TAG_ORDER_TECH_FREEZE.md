# feature01 · 标签与个人排序增量技术冻结（v17）

> 冻结日期：2026-08-24  
> 状态：**门 3 技术冻结完成，可进入门 4 纵向切片；不得反向改变 Q1–Q14 产品语义。**  
> 产品真源：`12-PROJECT_TAG_ORDER_REQUIREMENTS.md`。  
> UX 基线：`（标签管理静态稿）三案对照.html` 方案 A“单标签双栏工作台”。  
> 原 v16 技术基线：`9-GATE3_TECH_FREEZE.md`，保持历史原样，本文件只定义 v17 纯增量。  
> 陪审留痕：Codex custom agent 模拟 mc-expert（非 Claude 原生），建议为独立 v17 增量，置信度高。

---

## 0. 技术结论

1. 新增四表，严格分开 workspace 共享标签/归属与用户个人顺序。
2. “全部”“未分类”只做服务端派生，不创建标签行。
3. 标签与归属端点允许任意注册 admin/member 写入；不复用项目内容 `_project_access(write=True)`，也不放松该钩子。
4. 标签删除仅 admin，可恢复地软删除标签及活跃关系；项目本体、节点和其他标签不变。
5. 个人顺序按“用户 × workspace × 上下文”独立保存；同一用户同一上下文以版本锚点处理并发，不同用户互不冲突。
6. 排序提交必须等于服务端当时的完整有效项目集合；集合变化返回 409，旧请求不得把已移出项目重新带回。
7. 自动排序只读零写入；临时筛选/搜索时前端不发排序请求。
8. `_migration_v17` 只建表和索引，零业务数据回填；所有验证使用隔离库，真实 `flowboard.db` 不迁移。

---

## 1. 数据模型

### 1.1 `timeline_tags`（workspace 共享标签目录）

承重字段：

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
workspace_id INTEGER NOT NULL REFERENCES workspaces(id)
name TEXT NOT NULL
version INTEGER NOT NULL DEFAULT 1
created_by TEXT NOT NULL REFERENCES users(id)
deleted_by TEXT NULL REFERENCES users(id)
deleted_at TEXT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

- 标签 ID 稳定；改名只更新 `name/version/updated_at`。
- 活跃标签名称按 workspace 大小写不敏感唯一，使用 `WHERE deleted_at IS NULL` 的部分唯一索引。
- “全部”“未分类”不得写入本表。

### 1.2 `timeline_project_tags`（共享项目多标签归属）

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
workspace_id INTEGER NOT NULL REFERENCES workspaces(id)
project_id INTEGER NOT NULL REFERENCES timeline_projects(id)
tag_id INTEGER NOT NULL REFERENCES timeline_tags(id)
version INTEGER NOT NULL DEFAULT 1
created_by TEXT NOT NULL REFERENCES users(id)
removed_by TEXT NULL REFERENCES users(id)
deleted_at TEXT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

- 服务层在同一事务内验证 workspace、活跃项目、活跃标签一致。
- 一个项目可有多个活跃标签；同一 `project_id + tag_id` 只允许一条活跃关系，使用部分唯一索引。
- 移除只软删除当前活跃关系；重新加入新建活跃关系，旧个人位置不恢复。

### 1.3 `timeline_order_contexts`（用户个人顺序版本锚点）

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
workspace_id INTEGER NOT NULL REFERENCES workspaces(id)
user_id TEXT NOT NULL REFERENCES users(id)
context_type TEXT NOT NULL CHECK(context_type IN ('mine','all','uncategorized','tag'))
tag_id INTEGER NULL REFERENCES timeline_tags(id)
version INTEGER NOT NULL DEFAULT 1
deleted_at TEXT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
CHECK(
  (context_type='tag' AND tag_id IS NOT NULL) OR
  (context_type IN ('mine','all','uncategorized') AND tag_id IS NULL)
)
```

- `mine/all/uncategorized` 使用 `tag_id IS NULL` 的部分唯一索引。
- `tag` 使用包含 `tag_id` 的独立部分唯一索引，避免 SQLite `NULL` 唯一性失效。
- 删除标签时软删除其活跃 `tag` contexts；其他 contexts 不变。

### 1.4 `timeline_order_items`（个人完整序列）

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
context_id INTEGER NOT NULL REFERENCES timeline_order_contexts(id)
project_id INTEGER NOT NULL REFERENCES timeline_projects(id)
position INTEGER NOT NULL CHECK(position >= 0)
deleted_at TEXT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

- 一个 context 的活跃项目与 position 均唯一，使用两个部分唯一索引。
- 每次 PUT 在同一事务内软删除该 context 旧 items，再插入完整新序列并递增 context version。
- 规模约 25 项，不使用稀疏 rank、浮点分数、trigger 或缓存。

---

## 2. 服务端派生集合

所有集合只包含当前 workspace 的活跃 `timeline_projects`：

- `mine`：`created_by = 当前用户 id`。
- `all`：全部活跃项目。
- `uncategorized`：不存在任何活跃 `timeline_project_tags` 的项目。
- `tag`：存在指定活跃 tag 关系的项目。

读取个人顺序时：

1. 取 context 活跃 items 中仍属于当前集合的项目；
2. 保留其已存顺序；
3. 未出现的新/重加项目按稳定默认顺序追加末尾（`timeline_projects.id ASC`）；
4. 返回 `order_version`（context 不存在时为 0）与完整 `project_ids`。

---

## 3. API 契约

### 3.1 标签目录

```text
GET    /api/workspaces/{workspace_id}/timeline/tags
POST   /api/workspaces/{workspace_id}/timeline/tags
PATCH  /api/workspaces/{workspace_id}/timeline/tags/{tag_id}
DELETE /api/workspaces/{workspace_id}/timeline/tags/{tag_id}
```

- POST：`{name}`。
- PATCH：`{name, base_version}`。
- DELETE：`{base_version}`，仅 admin。
- GET 返回虚拟入口、普通标签、活跃项目计数和版本；普通成员看不到删除按钮不等于授权，DELETE 仍服务端拒绝。

### 3.2 标签归属与方案 A 双栏

```text
GET    /api/workspaces/{workspace_id}/timeline/tags/{tag_id}/projects
PUT    /api/workspaces/{workspace_id}/timeline/tags/{tag_id}/projects/{project_id}
DELETE /api/workspaces/{workspace_id}/timeline/tags/{tag_id}/projects/{project_id}
```

- GET 返回 `included[] / excluded[]`，项目条目只需 `project_id/name`。
- PUT/DELETE 请求携带 `{base_tag_version}`；一次拖拽一次事务。
- 成功返回最新标签视图；409 返回最新标签视图，前端回滚拖拽并刷新。
- PUT 已存在、DELETE 已不存在作为等值 no-op 返回当前视图，不重复写审计。

### 3.3 用户个人顺序

```text
GET /api/workspaces/{workspace_id}/timeline/order?context_type=...&tag_id=...
PUT /api/workspaces/{workspace_id}/timeline/order
```

PUT：

```json
{
  "context_type": "mine|all|uncategorized|tag",
  "tag_id": null,
  "base_order_version": 0,
  "project_ids": [3, 1, 7]
}
```

- `project_ids` 必须无重复且与服务端当前完整集合完全相等。
- 版本不符返回 `ORDER_VERSION_CONFLICT` 409 + 最新顺序。
- 集合不符返回 `ORDER_SCOPE_CHANGED` 409 + 最新集合/顺序。
- 自动排序与临时筛选只在前端显示，不调用 PUT。

### 3.4 校验与错误

- 所有请求体严格白名单；未知字段 422。
- 名称 trim 后 1–80 字符；同 workspace 活跃重名 409 `TAG_NAME_CONFLICT`。
- 未登录 401；非 workspace 成员/跨 workspace/软删对象 403 或 404，沿用现有不泄漏对象边界。
- 标签/顺序并发冲突均返回服务端最新可见视图，不要求客户端猜测合并。

---

## 4. 权限、并发与审计

### 4.1 权限

- 读取：workspace 内注册 admin/member。
- 创建/改名标签、添加/移除任意活跃项目标签：workspace 内注册 admin/member。
- 删除标签：admin only。
- 标签归属写入只验证 workspace 成员、项目/标签活跃与同 workspace；禁止因此放松项目内容写权限。
- `mine` 排序只允许当前用户自己的 context；所有排序 context 的 `user_id` 均取会话，不接受客户端传入。

### 4.2 并发

- 标签改名、删除、归属增删共享标签 `version` 锚点，使用 `BEGIN IMMEDIATE` + 条件更新。
- 同一用户同一 context 排序共享 context version；不同用户、不同 context 互不冲突。
- 归属变化与排序提交竞争时，排序端事务内重算集合；旧集合不得覆盖新归属。

### 4.3 审计

复用 `audit_log`：

```text
timeline.tag_created
timeline.tag_renamed
timeline.tag_deleted
timeline.tag_project_added
timeline.tag_project_removed
timeline.personal_order_changed
```

- 标签/归属审计记录 workspace、actor、tag、project（如适用）、前后版本。
- 个人顺序审计只记录 actor、context、版本、项目数，不进入主页团队“最新动态”，避免噪声。
- 删除标签单事务软删标签、活跃关系和对应 tag contexts；不删除项目本体。

---

## 5. v17 迁移与恢复

- `SCHEMA_VERSION` 从 16 升到 17；新增 `_migration_v17`，不修改 v16 DDL/checksum。
- v17 只创建四表、索引和 `schema_migrations(version=17, checksum='flowboard-schema-v17')`，不回填业务数据。
- 迁移前沿用现有自动完整备份；迁移后执行 `PRAGMA foreign_key_check` 与 `integrity_check`。
- 必测 v16→v17、真实形态 v15→v17、幂等、存量计数不变、失败恢复。
- v15→v17 为 v16/v17 两次迁移事务；若 v16 已提交而 v17 失败，必须停服并从迁移前完整备份恢复，不能宣称整链单事务。
- 真实 `flowboard.db` 迁移仍须用户另行授权，本轮只操作临时隔离库。

---

## 6. 前端交互契约

- 新增侧边栏 `#timelineTagsBtn` 顶级入口；不改已有入口 id。
- 【标签】页使用方案 A：标签目录 + 当前标签“未加入/已加入”双栏；项目条目只显示名称，横向跨栏改变共享归属，栏内不排序。
- 页面常显“影响全团队”；共享归属写成功后才落位，失败/409 回滚并刷新最新视图；提供一次即时反向撤销。
- 标签删除不使用拖拽，只在 admin 明确菜单/按钮中二次确认。
- 【我的项目】和全项目大图只在“自定义顺序 + 无临时筛选/搜索”时提供纵向拖拽；此拖拽只调用个人 order API。
- 原生 drop 生命周期中不得同步替换正在拖拽的 DOM；drop 先收集意图，dragend 后宏任务或等价稳定收尾再渲染。

---

## 7. 门 4 纵向切片

### V1 · 标签目录与 v17 基础

四表迁移 + 标签 CRUD/API + 标签页外壳/目录 + 权限、唯一性、软删、审计、迁移测试。

### V2 · 共享项目归属与方案 A 工作台

归属 API + 标签版本并发 + 双栏真实横向拖拽 + 多标签/未分类 + 权限例外、真实事件序和跨 workspace 测试。

### V3 · 个人顺序与【我的项目】

order context/items + GET/PUT + created_by 集合 + 主页项目行纵向拖拽 + 每用户隔离、刷新持久化、版本冲突测试。

### V4 · 全项目仪表盘整合

全部/未分类/普通标签导航 + 各 context 个人顺序 + 自定义默认 + 四自动排序只读 + 筛选禁拖 + 移除再加入末尾测试。

### V5 · 独立关门验收

迁移/恢复、权限矩阵、并发竞态、审计、真实浏览器拖拽、原 Python/Node 全量回归与文档交接；不新增功能。

---

## 8. 关门红线

1. 不写真实 `flowboard.db`，不 commit/push/发布/部署。
2. 不删除、弱化旧测试；原回归必须原样通过。
3. 不把标签权限例外扩展到项目内容。
4. 不把团队共享归属与个人顺序合并成一张表、一个端点或一种拖拽反馈。
5. 不让自动排序、筛选或搜索覆盖个人顺序。
6. 不物理删除项目、标签审计或通过同名标签恢复旧偏好。

---

## 9. 门 4 实施与自动验收结果（2026-08-24）

- V1–V4 已落地：schema v17 四表、共享标签目录/归属、方案 A 双栏管理页、【我的项目】个人序、全项目“全部/未分类/普通标签”各上下文个人序，以及自定义/四种自动排序共存。
- 服务端权限、软删除、版本冲突、审计、CSRF、跨用户隔离、移除再加入末尾和 v16→v17 幂等迁移均有自动测试；所有迁移测试只使用临时隔离库。
- Chromium 真拖拽覆盖共享标签归属、【我的项目】排序、全项目排序、刷新持久化、用户隔离、拖拽事件序和时间轴节点不得误触排序。
- 最终全量 `python -m unittest discover -s tests -p "test_*.py"`：157/157，退出码 0；6 个 Node 测试文件全部通过；Python 编译检查通过。
- 真实 `flowboard.db` 只读核验仍为 schema v15，SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`；未执行真实迁移、commit、push、发布或部署。
- v17 增量状态转为 `TAG_INCREMENT_WAIT_HUMAN`；该状态不改变原 v16 `WAIT_GATE5_HUMAN`，也不代表人工体验或上线已通过。
