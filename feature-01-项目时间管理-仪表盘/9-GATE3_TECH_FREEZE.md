# feature01 · 门 3《技术方案冻结版》（总固化产物）

> 建立日期：2026-08-18（门 3 三单元全部收口当日蒸馏）
> 状态：**门 3 整体评审 PASS（2026-08-18）；F1 视觉条款 2026-08-19 窄修订增量复审 PASS（高置信），门 3 已重新关闭**。初审 5 阻断 + 7 同步修正已全量吸收；B1–B5b/N2 经 mc-expert 陪审，B5c 由用户拍板=b（网页新建 + admin 软删 + v1 不改名）；补齐软删项目 `require_active=True` 与复盘 undo 计数排除后最终 PASS。2026-08-19 仅替换 F1/§8 视觉基线，其余 61 条未重开。本文是**门 4 唯一实现契约**；门 4 编码仍须用户显式启动新 run。
>
> **依据文件**（全部只读；本稿只蒸馏已拍板内容，零新决策）：
> 1. `archive/5-GATE3_UNIT1_DECISIONS.md` §0 —— 单元 ① D1–D14（含 D10 用户修订）+ P1 打包 + 画法 A 链式 + 两个未来候选
> 2. `archive/7-GATE3_UNIT2_DECISIONS.md` §0 —— 单元 ② E1–E8（含 P2 七项打包）
> 3. `archive/8-GATE3_UNIT3_DECISIONS.md` §0/§0.1 —— 单元 ③ F1–F5+P3（12 题陪审定稿 + F1/F2-④ 用户拍板）+ 联动修订 R1–R5 + 附录 B1–B5 实现规格
> 4. `archive/4-GATE3_UNIT1_TECH_DRAFT.md` —— v16 DDL 细节（其头部「DDL 修正注记」= R4，已并入本稿 §1）
> 5. `archive/6-GATE3_UNIT2_TECH_DRAFT.md` —— API 契约细节（请求/响应体、错误码、`_project_access` 代码形态）
> 6. `STATE.md`（§2 业务模型、§5 权限红线）、`mainline-feature01.md`（§4 交付范围、§9 完成边界）
>
> **纪律声明**：
> - 本文件 = 门 4 的唯一实现契约。过程稿 4/5/6/7/8 已移入 `archive/`；如有冲突，**以本文为准**——尤其 archive/8- §0.1 联动修订 R1–R5 优先于更早单元表述，D10 本周窗口优先于「7 天」旧表述。本文索引中的 `4-`/`5-`/`6-`/`7-`/`8-` 短写均指 `archive/` 内同名文件。
> - 本文每个条款均可回指上述文件或 `10-GATE3_REVIEW_REMEDIATION.md` 的拍板/陪审记录；初审修订项以本文吸收后的条款为实现权威。
> - 门 3 整体评审通过后，4/5/6/7/8 过程稿已移入 `archive/` 子目录降级留档（不删）——见 STATE §6 文档组织约定（2026-08-18 A+B 拍板）。
> - 陪审定稿项用户保留事后一句话推翻权（AGENTS.md §2）；冻结条款的任何变更须用户显式拍板。

---

## §0 拍板总索引（原始 49 条 + 评审修订 13 条 = 62 条）

| 编号 | 一句话结论 | 定稿来源 | 出处 |
|---|---|---|---|
| D1 | 数据模型=**新增专表**（timeline_projects/nodes + 批次审计表，v16 纯增量迁移）；间隔/状态不落库、实时派生 | 用户拍板 | 5- §0-1 |
| D2 | 项目=**独立实体**，与 board 零外键；未来挂钩走受控变更（加列） | 用户拍板 | 5- §0-2 |
| D3 | created_by/initial_date 不可变=**service 层三重锁**（请求体白名单不含 / UPDATE 永不含 / 专项测试锁定），**不用触发器** | 用户拍板（P1 打包） | 5- §0-9/P1-1 |
| D4 | 已完成载体=**done_at 内部时间戳**；认定不违反「不单开完成日期列」（界面永不出现完成日期列/输入框，仅复盘页间接可见） | 用户拍板 | 5- §0-3 |
| D5 | 审计=**批次专表** + direct/cascaded **行角色** + audit_log 桥接（不走 activity/realtime） | 用户拍板（P1 打包） | 5- §0-9/P1-2 |
| D6 | 项目开始日期=**两轨全部节点 min(date)**（含已完成）；零节点→NULL、排末显示「—」 | 用户拍板（P1 打包） | 5- §0-9/P1-3 |
| D7 | 当前阶段=**已动工阶段中六阶段序最大者（跨两轨）**；无→「未开始」；知情接受序最大吞掉早阶段并行尾巴（泳道展开仍可见） | 用户拍板 | 5- §0-4 |
| D8 | 临近节点=**date≥今天且未完成中最早者；同日多节点全返回**，排序键 (日期, 阶段序, 主线优先, 节点名)；空→按项目开始日期兜底 | 用户拍板 | 5- §0-5 |
| D9 | 逾期数=**date<today 且未完成，两轨合并单值**；红点阈值 ≥1 | 用户拍板（P1 打包） | 5- §0-9/P1-4 |
| D10 | 橙点窗口=**本周（周一~周日，含今天所在自然周）内有未完成节点，含本周已过去的天**；红点不变；红橙独立可并存、红左橙右（用户修订，覆盖「7 天内」表述） | 用户拍板（修订） | 5- §0-6 |
| D11 | 指标+间隔**实时计算不落库**，服务端唯一实现 | 用户拍板（P1 打包） | 5- §0-9/P1-5 |
| D12 | Excel 导入状态矛盾=**日期优先，只认「已完成」**；非三态文本仍行级报错；预览明示「状态将按日期重算」 | 用户拍板 | 5- §0-7 |
| D13 | 原始拍板为 API 恒返 **nodes[] + segments[]**；B4 安全补全后恒返第三份 `stage_intervals[]`，链式/跨式仍只切换 segments 算法 | 用户拍板 + mc-expert B4 补全 | 5- §0-8；10- B4 |
| D14 | **今天=服务器 Asia/Shanghai 本地日**，全指标服务端算，前端不自算 | 用户拍板（P1 打包） | 5- §0-9/P1-6 |
| 画法 | **A 链式**（相邻节点连线成条、段色=左端节点阶段、忠实呈现交错）+ 服务端同派生「**阶段区间列表**」供重叠分半/展开拆行（单一实现不变） | 用户拍板（对照稿） | 4- 头部注记；STATE §6 |
| E1 | 批次端点=**workspace 级单端点单事务**（1..N 项目变更组一次提交、整批全成全败；返回体含各项目最新完整视图） | 用户拍板 | 7- §0-1 |
| E2 | **逐项目 base_version**，任一不符→整批 409 零写入 | 用户拍板（P2 打包） | 7- §0-6 |
| E3 | 409 返回体带**冲突项目服务端最新完整视图**（并排确认用） | 用户拍板（P2 打包） | 7- §0-6 |
| E3b | 放弃更改=**纯前端丢弃**，零请求零批次零审计 | 用户拍板（P2 打包） | 7- §0-6 |
| E4 | 撤销**护栏四件套**（仅可撤各项目最新批次 / undo 亦为批次 / 不做 redo / 无服务端时限）+ 通常有写权限即可撤；**目标含 initial_correction 时须 admin（B1 安全修订）**；跨项目撤销=每项目一行 undo 批次+同一 **undo_group** | 用户拍板 + mc-expert 安全修订 | 7- §0-2；10- B1 |
| E5 | **_project_access**：读=admin+member（viewer 挡读挡写）；写=admin 或 created_by=自己；403 模糊化 `PROJECT_FORBIDDEN` | 用户拍板（P2 打包） | 7- §0-6 |
| E6 | 拖拽**全程零网络**，唯一点【更新日期】POST；details 记 {mode, magnet} | 用户拍板（P2 打包） | 7- §0-6 |
| E7a | **增删改同批**（create/remove/set 混排；删除=软删不动他日期） | 用户拍板（P2 打包） | 7- §0-6 |
| E7b | 空变更数组→**422**；全部等值→**200 静默 no-op**（不建批、version 不动） | 用户拍板 | 7- §0-3 |
| E7c | 混合批次**不动表结构**：批次记主类型、行级 field 区分、批次补 details_json.kinds | 用户拍板 | 7- §0-4 |
| E7d | 同批多锚点=**钉住+分段平移**（非 direct 跟随最近上游 direct 位移；direct 绝对优先） | 用户拍板 | 7- §0-5 |
| E8 | 提交**「意图」非「结果」**（顺延由服务端重算，防漂移防伪造） | 用户拍板（P2 打包） | 7- §0-6 |
| F1 | **2026-08-19 用户覆盖拍板**：feature01 v1 三页优先浅色；单项目仪表盘以视觉样张**方向 A（大标题·白卡）**为当前执行基线，编辑器/全项目仪表盘沿用同一浅色 token 语言；未来整体暗色皮肤仅作候选，不实现主题切换或暗色运行态 | 用户拍板（覆盖 2026-08-18 F1=b） | 本文 §8/§11；3-UX §0 覆盖注记 |
| F2-① | **固定 8 列列序 + 表头精确校验**（文件级报错，文案附标准表头） | mc-expert 陪审定稿 | 8- §0.1 |
| F2-② | 文本 YYYY-MM-DD + **xlsx 日期序列号换算（1950–2100）**；附非整数拒收/CSV 文案两条补丁 | mc-expert 陪审定稿 | 8- §0.1 |
| F2-③ | 枚举/必填/限长细则照本文 §5；限长报错同走行级 422 带 row/header | mc-expert 陪审定稿 | 8- §0.1 |
| F2-④ | 同名既有项目=**b 拒绝**（项目名称是唯一标识，不允许同名） | 用户拍板（未采纳陪审默认 a） | 8- §0.1 |
| F2-⑤ | 文件内重复=行级报错（保留不变）；库内「跳过+汇总」子项随 R2 失效 | mc-expert 陪审定稿 + R2 修订 | 8- §0.1 |
| F2-⑥ | 沿用现有导入安全界（1.5MB / 1000 行 / 10k 字符 / 公式宏外链拒收） | mc-expert 陪审定稿 | 8- §0.1 |
| F2-⑦ | 预览两段式 + 提交事务内再验；导入只创建新项目，提交资格由批次状态机控制，内容由事务内名称唯一复查+行级重校验控制（N2 修订） | mc-expert 陪审定稿 + N2 修订 | 8- §0.1；10- N2 |
| F2-⑧ | 导出规则：8 列同格式 / 间隔=计算值 / 状态=派生三态 / 行序项目→轨道→日期→节点名自然序→id / 上限 1000 闭环 | mc-expert 陪审定稿 + B3 稳定序补全 | 8- §0.1；10- B3 |
| F2-⑨ | 导入预览载体=**timeline_import_batches v16 同构新表**（preview_json+sha256，previewed/committed 状态机） | mc-expert 陪审定稿 | 8- §0.1 |
| F3 | 迁移 runbook 执行序确认；**F3-i CLI 备份强制=是**；**F3-ii 五表一次建齐=是** | mc-expert 陪审定稿 | 8- §0.1 |
| F4 | 回归三件套（自动化原样全跑 + 15 分钟手工冒烟 + 12 组新增测试）；冒烟结果留一行文字记录 | mc-expert 陪审定稿 | 8- §0.1 |
| F5 | GET 两端点 + 全量返回前端筛排**不分页** + server_today；**不加缓存层** | mc-expert 陪审定稿 | 8- §0.1 |
| P3 | 上述八项确认型打包冻结（F2-①③⑥⑦⑧ / F3 主体+i+ii / F4 / F5），无例外拆出 | mc-expert 陪审定稿 | 8- §0.1 |
| R1 | 同名报错形态：该同名项目的行**全部报错（带行号）、有错不许提交、不做部分导入**；改名或删行后重传 | 联动修订（随 F2-④=b 生效） | 8- §0.1 R1 |
| R2 | 库内重复「跳过+预览汇总」**失效**（前提追加模式已被否决）；文件内重复行级报错保留 | 联动修订 | 8- §0.1 R2 |
| R3 | 预览要素修订版：①新建 N 个项目（列名）②「状态将按日期重算，仅『已完成』保留」醒目提示 ③行级错误清单（含同名报错），有错不许提交；提交事务内重放 preview_json 并再验名称唯一与行级规则 | 联动修订 + N2 | 8- §0.1 R3；10- N2 |
| R4 | timeline_projects 唯一约束=**部分唯一索引** `WHERE deleted_at IS NULL` + service 层显式校验 422 `NAME_CONFLICT`；唯一范围=workspace 内**活跃**项目（软删名称可复用） | 联动修订 | 8- §0.1 R4；4- 头部注记 |
| R5 | 往返注记：同名即拒后「导出→导回同一 workspace」被 R1 拦截；往返等价仅发生在全新 workspace / 项目已删除场景 | 联动修订 | 8- §0.1 R5 |
| G1 | 导出端点=**workspace 级全量导出**（`POST /api/workspaces/{id}/timeline/export`，一次导出全部活跃项目；单项目导出不进 v1，未来走 project_ids 扩展） | mc-expert 陪审定稿（冻结版蒸馏缺口补拍） | 8- §0.1 补拍 |
| G2 | 导入端点=`timeline/imports/preview` 与 `.../imports/commit`，均 201（子路径沿用看板导入惯例 server.py:210-211） | mc-expert 陪审定稿（补拍） | 8- §0.1 补拍 |
| G3 | undo batch_id 查无此批=**404 `TIMELINE_BATCH_NOT_FOUND`**（存在但非最新仍 409 `UNDO_TARGET_STALE`；对齐 commit_import 409/404 分界） | mc-expert 陪审定稿（补拍） | 8- §0.1 补拍 |

### §0.1 门 3 整体评审修订索引（13 条）

| 编号 | 一句话结论 | 定稿来源 | 出处 |
|---|---|---|---|
| B1 | undo 目标批次为 `initial_correction` 时，整次撤销要求 workspace admin；否则 403 `ADMIN_REQUIRED`、零写入 | mc-expert 陪审定稿 | 10- §3 B1 |
| B2 | 项目访问绑定路径 workspace；项目不存在/跨 workspace/无权统一 403；变更行 node 无效或越界统一 422 | mc-expert 陪审定稿 | 10- §3 B2 |
| B3 | batch 补齐 interval_days/done_at/服务端钳制；链序=`track,date,节点名自然序,id`，邻居取前置事务快照 | mc-expert 陪审 + 既有用户冻结项纠偏 | 10- §3 B3 |
| B4 | 视图显式增加 `stage_intervals[]`，元素含 node_ids 与确定性 row_index；三类响应同形 | mc-expert 陪审定稿 | 10- §3 B4 |
| B5a | admin initial_date 多节点纠正独立端点；自由历法日期、不钳制不级联、产生 initial_correction 批次 | mc-expert 陪审定稿 | 10- §3 B5a |
| B5b | 轻量复盘独立 GET；项目/节点汇总完整，历史批次每项目最近 50 条 + has_more | mc-expert 陪审定稿 | 10- §3 B5b |
| B5c | 网页端 admin/member 可新建项目；仅 admin 可软删；v1 不改名 | **用户拍板=b** | 10- §1/§3 B5c |
| C1 | initial_date 编辑器不展示，但复盘页对 admin/member 可见 | mc-expert 陪审定稿 | 10- C1 |
| C2 | 顶层 project 访问失败→403；操作对象 batch 查无→404；行内 node 无效/越界→422 | mc-expert 陪审定稿 | 10- C2 |
| N1 | `timeline_import_batches` 补完整 DDL | 机械修订 | 10- N1 |
| N2 | 导入删除无对象的 base_version/sha256 比对语义，改由状态机资格检查+事务内重校验 | mc-expert 陪审定稿 | 10- N2 |
| N3 | 迁移冒烟使用迁移前动态计数基线，不写死运行库数量 | 机械修订 | 10- N3 |
| N4 | §0 精确清点：原始决策 49 条，本次评审修订 13 条，共 62 条 | 机械修订 | 本节 |

---

## §1 数据模型（v16 五表，纯 CREATE TABLE 增量）

依据：D1/D2/D3/D4/D5（5- §0）、R4（8- §0.1）、F2-⑨、F3-ii（8- §0.1）、4- §2/§4 DDL（R4 修正后）。**原则：间隔不落库（date 链派生值，读取时按轨道 date 前驱实时算）；状态不落库（除 done_at，两态由日期派生）；一切派生只在服务端计算（D11）。**

### 1.1 timeline_projects（项目）

```sql
CREATE TABLE timeline_projects(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(id),   -- 首次创建系统写入，永不可改（D3）
  version INTEGER NOT NULL DEFAULT 1,              -- 项目级并发锚点（E2 base_version 比对对象，每批 +1）
  deleted_at TEXT, deleted_by TEXT REFERENCES users(id),   -- 软删除惯例
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
-- R4 修正：原 UNIQUE(workspace_id, name, deleted_at) 因 SQLite NULL 互不相等、
-- 实际不约束活跃行，改为部分唯一索引：
CREATE UNIQUE INDEX idx_timeline_projects_active_name
  ON timeline_projects(workspace_id, name) WHERE deleted_at IS NULL;
```

- **唯一性范围=workspace 内活跃项目**（软删项目的名称可复用）；service 创建/导入路径**同时显式校验**、报 422 `NAME_CONFLICT`（索引为兜底双保险）。
- 项目与 board **零外键**（D2）；10 个并行项目 = 10 行。
- 项目可由网页新建或 Excel 导入创建；两条路径均写入 `created_by=当前操作者` 且永不可改。仅 workspace admin 可软删项目；v1 无改名、恢复接口（B5c=b）。

### 1.2 timeline_nodes（节点）

```sql
CREATE TABLE timeline_nodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES timeline_projects(id),
  track TEXT NOT NULL CHECK(track IN ('main','parallel')),
  stage TEXT NOT NULL CHECK(stage IN ('创意','设计','开发','测试','量产','应用迭代')),
  name TEXT NOT NULL,                              -- 节点名称（二级标签）
  date TEXT NOT NULL,                              -- 当前有效日期 YYYY-MM-DD
  initial_date TEXT NOT NULL,                      -- 编辑器不展示；复盘页 admin/member 可见；仅 admin 可纠正（D3/C1）
  done_at TEXT,                                    -- 已完成标记：NULL=未手工完成（D4，UTC 时间戳）
  remark TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  deleted_at TEXT, deleted_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX idx_tln_project ON timeline_nodes(project_id, deleted_at, track, date);
```

- created_by **只在项目级**（节点归属由 project 决定，节点表不加）；initial_date 只在节点级。
- 新表从空开始，**不存在存量回补问题**；导入建项目时 created_by=导入操作者（复用 import_batches 惯例 database.py:710、service.py:1396）。

### 1.3 timeline_change_batches（批次）

```sql
CREATE TABLE timeline_change_batches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES timeline_projects(id),
  actor_user_id TEXT NOT NULL REFERENCES users(id),
  change_kind TEXT NOT NULL CHECK(change_kind IN (
      'direct_edit',          -- 直接修改（日期/间隔/名称/阶段/轨道/备注）——混合批次的主类型（E7c）
      'status_toggle',        -- 纯状态切换批次
      'initial_correction',   -- 历史日期修正（admin 例外入口，改 initial_date，独立端点）
      'undo')),               -- 反向撤销批次
  trigger_source TEXT NOT NULL CHECK(trigger_source IN ('editor','drag','import','undo','admin')),
  project_version_before INTEGER NOT NULL,
  project_version_after  INTEGER NOT NULL,
  undone_batch_id INTEGER REFERENCES timeline_change_batches(id),  -- undo 批次指向被撤批次
  details_json TEXT NOT NULL DEFAULT '{}',   -- {mode, magnet, zoom_band, historical_correction,
                                              --  file_sha256, undo_group, kinds:[...]}（E4/E6/E7c）
  created_at TEXT NOT NULL
);
CREATE INDEX idx_tlcb_project ON timeline_change_batches(project_id, id);
```

- **每项目一批一行**；跨项目一次请求 = N 行批次（项目间无任何联动计算，双轨规则都在项目内）。
- undo 的 `undo_group` token 与混合批次的 `kinds` 标签均落 details_json，**无新列**（E4/E7c 拍板不动 D5 结构）。
- 每提交一批向 audit_log 写一行桥接（`source_key="timeline_batch:{id}"`、action_code 如 `timeline.batch_committed`、outcome=success），admin 统一审计查询/CSV（service.py:2773-2790）零改造可见；**不写 activity / realtime_events**（activity 的 CHECK(entity_type IN ('board','group','task','comment')) + board_id NOT NULL 决定复用=重建表，database.py:323-333）。

### 1.4 timeline_node_changes（行级变更）

```sql
CREATE TABLE timeline_node_changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES timeline_change_batches(id),
  node_id INTEGER NOT NULL REFERENCES timeline_nodes(id),
  change_role TEXT NOT NULL CHECK(change_role IN ('direct','cascaded')),  -- 直接修改 vs 自动顺延受影响
  field TEXT NOT NULL CHECK(field IN ('date','done_at','initial_date','stage','track','name','remark','created','deleted')),
  old_value TEXT, new_value TEXT          -- created 行 old 为 NULL；间隔变化随 date 前后值可推导，不单独存
);
CREATE INDEX idx_tlnc_batch ON timeline_node_changes(batch_id, node_id);
```

- 「直接修改」与「自动顺延」= **同批内两种行角色**（改 B 顺延 C/D → 一个 direct_edit 批，B=direct、C/D=cascaded）。五类变更全覆盖：直接修改+自动顺延（direct_edit 批 + 行角色）、状态切换（status_toggle 批 / 混合批走行级 field='done_at'）、历史日期修正（initial_correction 批，仅 admin）、撤销（undo 批 + undone_batch_id 链）。
- 轻量复盘四问（初始日期 / 当前日期 / 净变化天数 / 直接修改次数）全部由本表+timeline_change_batches+timeline_nodes 直接聚合，无需新冗余列。

### 1.5 timeline_import_batches（导入预览载体，F2-⑨）

```sql
CREATE TABLE timeline_import_batches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  filename TEXT NOT NULL,
  file_format TEXT NOT NULL CHECK(file_format IN ('csv','xlsx')),
  content_sha256 TEXT NOT NULL,                    -- 原上传内容审计指纹；commit 不重收文件、不作二次比对
  preview_json TEXT NOT NULL,                      -- 已通过 preview 全量校验的规范化行数据
  status TEXT NOT NULL DEFAULT 'previewed' CHECK(status IN ('previewed','committed')),
  version INTEGER NOT NULL DEFAULT 1,              -- 状态迁移内部并发锚点，不由客户端提交 base_version
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  committed_at TEXT
);
CREATE INDEX idx_timeline_import_batches_workspace
  ON timeline_import_batches(workspace_id, created_by, status, id);
```

- 本表与现有 `import_batches` 同构，但**去掉 board_id、改为 workspace_id**；`content_sha256` 仅用于来源审计。commit 不重收文件，因此不存在可比较的第二份 sha256，也不要求导入项目 `base_version`（导入只创建新项目）。
- commit 资格由 `(id, workspace_id, created_by, status='previewed')` 状态机与事务内条件更新控制；内容合法性由 `BEGIN IMMEDIATE` 事务内重放 `preview_json`、复查活跃项目名称唯一性与全部行级规则控制。
- preview_json 体积上界受 12MB 解压上限约束（与现有看板导入同暴露面，不动）；**previewed 批次无过期清理**（同旧表现状，留维护注记）。commit 时每个新项目产生 `trigger_source='import'` 的 timeline 批次，与手工编辑在审计层同构。

### 1.6 v16 建表形态

- 五表一次建齐（F3-ii），纯 CREATE TABLE 零数据变换、不碰任何旧表旧数据（D1「加盖一页」）；字段一次到位（含 done_at/initial_date/version/trigger_source），避免二次迁移。执行序见 §6。

---

## §2 派生指标与视图契约（M1–M5 + nodes[]/segments[]/stage_intervals[]）

依据：D6–D14（5- §0）、画法 A（4- 头部注记）、4- §5。

### 2.1 前置总定义（一切指标共用）

- **节点宇宙** = 该项目全部 `deleted_at IS NULL` 的 timeline_nodes（两轨合并；项目软删除则整体不参与）。
- **today** = 服务器 **Asia/Shanghai 本地日**（D14）；全指标服务端计算，前端不得自算「今天」。
- **状态派生（唯一权威定义）**：`已完成` = done_at 非空；否则 `date >= today → 未开始`、`date < today → 进行中（隐含逾期）`。
- **轨内典范链序**（B3，遵守 UX Q3）：`date ASC → 节点名称自然序 ASC → id ASC`；自然序按数字片段数值比较（`B2 < B10`），id 仅作同名最终兜底。间隔、前驱/后邻、链式 segments、导出同日行序均使用此链序；track 之间永不互算。

### 2.2 M1–M5

| 指标 | 冻结定义 | 边界 |
|---|---|---|
| M1 项目开始日期 | `min(date)` over 节点宇宙，**含已完成、两轨合并** | 零节点项目 → NULL，全项目排序置末、显示「—」 |
| M2 当前阶段 | `已开始(stage) := ∃节点(date <= today 且属该阶段)`；当前阶段=已开始阶段中**六阶段序最大者（跨两轨）** | 无已开始节点→「未开始」；today 晚于全部节点仍取序最大（无第七态）。知情接受：早阶段并行尾巴在一格提示中被序最大吞掉（泳道展开仍可见） |
| M3 最近临近节点 | `{date >= today 且非已完成}` 中 date 最小者；**同日多节点全部返回**；排序键 `(date, 阶段序, 主线优先, 节点名)` | 集合空（全完成/全过去）→ NULL，全项目排序按 M1 兜底；UI 可显示「今天 ×N」 |
| M4 逾期未完成节点数 | `count(date < today 且 done_at IS NULL)`，**两轨合并单值** | 红点阈值 = 该数 ≥ 1；不限本周 |
| M5 本周窗口（D10 修订版） | `count(本周一 <= date <= 本周日 且 非已完成)`，**含本周已过去的天**（周一到昨天没做完的也是本周工作）；周基准 Asia/Shanghai | 橙点=本周内有未完成节点；红橙语义独立**可并存**（本周内过期的未完成节点两点同亮），显示**红左橙右** |

- 原推荐 [today, today+6] 滚动窗口**作废**（D10 用户修订，覆盖 mainline §4.3 与 UX §0 记录 5 的「7 天内」表述）。

### 2.3 计算方式（D11）

**查询时实时计算，不落库缓存**。量级约 10 项目 × 数十节点 = 数百行，走 `idx_tln_project(project_id, deleted_at, track, date)` 扫描后按 §2.1 典范链序稳定排序，一次产出全部指标与段数组；间隔同理**实时派生**（每轨按典范链序前驱算，首节点为空；同日相邻间隔=0）。缓存=每批提交都要失效重算，纯负收益；未来项目数 ×100 再议缓存，契约不变只变实现。

### 2.4 视图契约（D13 + 画法 A）

- API 恒返 **三份**：`nodes[]`（编辑器与详情的唯一事实源）+ `segments[]`（链式段）+ `stage_intervals[]`（阶段合并游程）；段算法=服务端**可切换开关**，切换只改 segments 内容不改 API 形状。
- `nodes[]` 元素至少为 `{id, project_id, track, stage, name, date, initial_date, interval_days, status, remark}`；`interval_days` 为该轨相对前驱的实时计算值（首节点 `null`），`status` 为三态派生值。initial_date 在编辑器 UX 不展示，但复盘页可见（C1）。
- **画法 A 链式（已拍板）**：`segments[]` 元素 `{track, start_node_id, end_node_id, start_date, end_date, stage}`；段=典范链序中相邻节点连线成条，段色=**左端节点阶段**，忠实呈现交错夹层。
- `stage_intervals[]` 元素 `{track, stage, start_date, end_date, row_index, node_ids}`，表示同轨同阶段的合并游程，供重叠分半/展开拆行和悬浮/点击穿透使用。`row_index` 在同轨内按 `(start_date, 首节点id)` 排序后贪心分配最低可用行号，结果确定；`node_ids` 按典范链序排列。
- 读写**共用同一服务端派生器**（D11/D13）：E1 返回体的 view、GET 端点、409 冲突视图全部同源；两个仪表盘永远共享同一段计算，不分叉。
- 每个读响应带 `server_today`（D14 落位）。

---

## §3 API 契约

依据：E1–E8（7- §0）、6- §2–§9 细节、F5 + B4（8- §0.1/附录）、F2-⑦ 补丁、R4。路由=server.py 手工 if 链纯增量（对齐 server.py:150-155/:163-164/:203 惯例）；401/CSRF 由路由层统一处理（current_user server.py:107-111 → service.authenticate 401 `AUTH_REQUIRED`/`SESSION_INVALID`，service.py:135-149；dispatch 内全部非登录路由先调 server.py:142），timeline 端点零额外代码自动获得。

### 3.1 POST /api/workspaces/{id}/timeline/batches（批次提交，E1）

**请求体**（意图提交，E8——前端只说「改了什么」，顺延重算由服务端做）：

```json
{
  "requests": [
    {
      "project_id": 3,
      "base_version": 7,
      "trigger_source": "drag",
      "details": {"mode": "cascade", "magnet": "standard"},
      "changes": [
        {"node_id": 41, "set": {"date": "2026-09-02"}},
        {"node_id": 44, "set": {"interval_days": 12}},
        {"node_id": 42, "set": {"done_at": true}},
        {"node_id": 41, "set": {"stage": "测试", "track": "main", "name": "B2", "remark": "..."}},
        {"create": {"track": "main", "stage": "开发", "name": "B3", "date": "2026-09-10", "remark": ""}},
        {"node_id": 43, "remove": true}
      ]
    }
  ]
}
```

规则要点（全部已拍板）：

- **单请求单事务**：BEGIN IMMEDIATE 写锁串行化写者（database.py:25-33），1..N 项目变更组整批全成全败（DRAG 确认 4/5 的一字不差兑现）。
- **同 node_id 可多行**：最终值语义（确认 3 的服务端版）——按序应用、以最后为准；服务端合并后再算级联。
- **变更行归属**：每个 `node_id` 必须以 `WHERE id=? AND project_id=?` 读取/写入；不存在、已删除或属于别的项目统一 422 行级错误（带 node_id）。路径 workspace 与 project 绑定见 §4.1。
- `interval_days` 是 change 行 `set` 的合法意图字段：仅接受整数 `0..3650`，只可用于已存在节点；create 行携带、节点无前驱、或与 `track` 同批修改导致上下文不确定均 422。服务端按**事务开始时该轨典范链序的前驱日期 + N 天**换算目标 date；与 `date` 并存时**date 优先**并覆盖重算间隔（STATE §2 冻结规则）。
- `done_at` 输入只接受布尔：`true` → 服务器当前 UTC ISO 时间戳，`false` → NULL，其他类型 422；等值判定按布尔语义（true 等价于现值非 NULL）。create 行可选 `done_at` 布尔，省略即 NULL。
- create 行首次落库时由服务端强制写 `initial_date=date`；请求不得提供 initial_date。导入创建节点同理取导入行 date，之后只有 §3.3 admin 端点可纠正。
- **白名单**：`reject_unknown` 不含 created_by/initial_date（D3 三重锁第①重，惯例 service.py:78-81/1876）。
- **防呆上限**：`requests` ≤ 20 项目、每项目 `changes` ≤ 200 行（batch_tasks 限 100 同类做法，service.py:2200）；超限 422。
- **并发锚点（E2）**：事务内逐项目比对 `timeline_projects.version != base_version`，比对在**任何写入之前**（先全检后全写，仿 service.py:2226-2230）；再以条件 UPDATE `SET version=version+1 WHERE id=? AND version=?` + `_conflict`（rowcount!=1 即 409，service.py:269-272/1443 模式）双保险。缺 base_version → **428 VERSION_REQUIRED**（service.py:60-63）。
- **服务端钳制（B3；2026-08-31 拖拽覆盖）**：以前置事务快照中的典范链序固定每个 direct 节点的前驱/后邻，再解析本批 date/interval 意图。`trigger_source='drag'` 时 direct 日期下界为同轨前驱 + **1 天**，无后邻上界；`details.mode='single'` 只在后续节点不足 1 天时递归做最小碰撞顺延，`cascade` 则将同轨后续节点整体平移。非拖拽来源继续沿用既有编辑器间隔语义（同日相邻间隔可为 0）；编辑器来源缺省 mode=`cascade`。非法 mode 422。钳制后即服务端真值，不另报错；若等于现值按 E7b 剔除。不得用合并终态反推邻居，以免循环定义。
- **行角色生成（E7d）**：完成 direct 日期解析与钳制后，direct 节点钉死新日期。`cascade` 的非 direct 节点跟随**最近上游 direct 的位移**整体平移（锚点间相对间隔保持）；拖拽 `single` 只把违反 1 天下界的后续节点递归推迟到刚好满足，并将这些自动影响记为 `cascaded`。direct 与级联重叠时 **direct 绝对优先**（级联跳过该行、从它重新分段）。最终按典范链序返回；非拖拽来源仍允许同日相邻间隔=0。
- **权限/活跃态**：事务内对每个涉及项目逐一 `_project_access(workspace_id=路径id, write=True, require_active=True)`；任一 403/404 整批拒绝（全成全败对权限与软删隔离同样成立）。
- **空批/等值（E7b）**：changes 空数组/缺省 → 422（对齐 service.py:2156/2213 惯例）；逐行比对后全部与现状等值 → **200 静默 no-op**：等值行剔除、不建批次、version 不动、返回当前视图 + `"no_op": true`（复盘「直接修改次数」不被空转批次污染）；部分等值→正常建批，等值行不产生 node_changes 行。
- **混合批次（E7c=a）**：批次级 change_kind 记主类型（含日期修改=direct_edit，纯切状态=status_toggle）；类型区分由行级 field 承载（date 行=改日期、done_at 行=标完成）；批次补 `details_json.kinds`（如 `["direct_edit","status_toggle"]`）便于筛选。
- **拖拽批次（E6）**：`trigger_source='drag'`，details_json 记 `{"mode": "single"|"cascade", "magnet": "standard"|"strong", "zoom_band": "±10d×8"}`；编辑器来源 `trigger_source='editor'`。
- **拖动已完成节点**（DRAG 确认 10/Q6）：仍是改当前 `date`，direct_edit 批 + details 标 `{"historical_correction": true}` 供前端标【历史日期修正】。⚠️ 概念区分：与 `initial_correction`（admin 独立端点改 **initial_date**，D3 第③重）是两个概念，实现以字段为准（date vs initial_date）。
- **删除=软删**（deleted_at/deleted_by），不动其他日期、只重算该轨合并间隔（E7a；STATE §2）。

**200 返回体**：

```json
{"results": [{"project_id": 3, "batch_id": 118, "version": 8,
  "view": {"nodes": [...], "segments": [...], "stage_intervals": [...], "metrics": {...}}}]}
```

view 由服务端唯一派生器产出（D11/D13），前端提交后整视图刷新、零客户端重算；no-op 情形返回当前视图。

**409 返回体（VERSION_CONFLICT，E3）**：

```json
{"error": {"code": "VERSION_CONFLICT", "message": "批量提交存在版本冲突，整批未写入",
  "details": {"conflicts": [
     {"project_id": 3, "submitted_version": 7, "server_version": 9,
      "view": {"nodes": [...], "segments": [...], "stage_intervals": [...], "metrics": {...}}}]}}}
```

只含**冲突项目**的视图（未冲突项目零写入、草稿全保留）；前端并排「我的草稿 vs 服务端最新」。放弃更改=纯前端丢弃（E3b）。

### 3.2 POST /api/workspaces/{id}/timeline/batches/undo（撤销，E4）

- 请求体 `{"batch_ids": [118, 119]}`（前端原样送回提交响应里的 batch_id 集合）。
- **护栏四件套**：① 每个 batch_id 必须是其所属项目 `MAX(id)` 批次，任一不满足 → **整个 undo 409 `UNDO_TARGET_STALE` 零写入**（专属 409 code 有先例 service.py:2240）；② undo 本身也是批次（change_kind='undo'、undone_batch_id 指向被撤批次、trigger_source='undo'、version 照常 +1——被撤批次不再是最新由 undo 批自身占据，天然封死重复撤销）；③ 逐行生成反向变更（old/new 互换；'created' 反向=软删该节点、'deleted' 反向=恢复 deleted_at=NULL），**原批次原样保留**；④ **不做 redo**（undo 批不可再撤）。
- **无服务端时限**：撤销入口消失由前端控制（页面刷新/新编辑开始），与「无倒计时」拍板一致。
- **谁可撤**：通常有项目写权限即可（不限原操作者）；但只要本次任一目标批次 `change_kind='initial_correction'`，操作者必须是 workspace admin，否则整个 undo 403 `ADMIN_REQUIRED`、零写入。admin 可撤该纠正批；其他护栏不变（B1）。
- undo 在读取目标批次后，对其所属每个项目调用 `_project_access(workspace_id=路径id, write=True, require_active=True)`；软删项目返回 404 `PROJECT_NOT_ACTIVE`，不得产生反向批次。
- **跨项目等价处理（已确认）**：一次 undo 请求 = 每项目一行 undo 批次 + 同一 `details_json.undo_group` token，审计按一次操作一组呈现（与 DRAG 确认 17「一条反向批次」语义等价的字面↔结构转换）。

### 3.3 POST /api/workspaces/{id}/timeline/batches/initial-correction（B5a）

请求体：

```json
{"project_id": 3, "base_version": 8,
 "corrections": [
   {"node_id": 41, "initial_date": "2026-08-01"},
   {"node_id": 42, "initial_date": "2026-08-05"}
 ]}
```

- 仅 workspace admin 可调用；非 admin 403 `ADMIN_REQUIRED`。`corrections` 为 1..200 项，同一 node_id 重复、字段多缺、非法历法日期均 422。
- 所有 node 必须未删除且属于请求 project；行内 node 无效/跨项目统一 422。事务内先以 `_project_access(workspace_id=路径id, write=True, require_active=True)` 做路径 workspace、admin、活跃态与 base_version 全检，再写入，任一失败零写入。
- initial_date 是历史记录字段，**只做真实 YYYY-MM-DD 历法校验，不参与典范日期链，不钳制、不级联、不改变当前 date**。逐行等值全部命中时按 E7b 返回 200 no-op。
- 非等值纠正组成同一 `initial_correction` 批次（trigger_source=`admin`，每行 field=`initial_date`/role=`direct`），项目 version +1；响应与 3.1 单项目 result 同形，含完整 view。该批次的 undo 受 §3.2 admin 门槛保护。

### 3.4 GET 视图端点（F5，B4 形状）

```text
GET /api/workspaces/{id}/timeline
→ 200 {"projects":[{project_id, name, created_by, version,
      metrics:{start_date, current_stage, upcoming:[...], overdue_count, this_week_count},
      nodes:[...], segments:[...], stage_intervals:[...]}],
    "server_today":"2026-08-18"}          # D14：前端不自算今天
权限：workspace membership；viewer 403（Q18-B 挡读）；默认全部活跃项目（deleted_at IS NULL），无分页

GET /api/timeline/projects/{id}
→ 200 同单项目视图形状（nodes/segments/stage_intervals/metrics/version）
权限：_project_access(workspace_id=NULL, write=False, require_active=True)；由项目反查 membership，软删返回 404
```

- 视图结构=3.1 返回体的 view（`nodes[]+segments[]+stage_intervals[]+metrics`），元素 schema 见 §2.4；**读写共用同一服务端派生器**，不加缓存层。
- 筛选/排序=初版**全量返回、前端筛排**（约 10 项目×几十节点≈数十 KB，局域网无压力；筛选下拉本身需要全量项目名单）；`project_ids` 可选参数留未来扩展、契约向后兼容；**不分页**（该量级分页是负收益）。

### 3.5 GET /api/workspaces/{id}/timeline/review（轻量复盘，B5b）

- 查询参数 `project_ids=1,2` 可选；缺省返回全部活跃项目。权限与 workspace timeline GET 相同：admin/member 可读，viewer 403；不带 base_version。
- 200：`{"projects":[...],"server_today":"2026-08-18"}`。每个项目元素为：
  - `{project_id, name, version, summary:{direct_edit_total}, nodes:[...], batches:[...], has_more}`；项目与节点汇总**完整返回、不分页**。
  - `nodes[]` 元素 `{node_id,name,track,stage,initial_date,date,delta_days,direct_edit_count}`；`delta_days=date-initial_date`。直接修改次数只计 `timeline_change_batches.change_kind='direct_edit' AND timeline_node_changes.change_role='direct' AND field='date'`，不计级联、状态、initial_correction、undo 或 no-op；summary 为节点计数之和。
  - `batches[]` 仅历史明细截断为该项目最近 **50** 批（id DESC）；元素 `{batch_id,change_kind,trigger_source,actor:{id,name},created_at,change_rows:[{node_id,node_name,change_role,field,old_value,new_value}]}`。存在更早批次时 `has_more=true`；v1 不做续载游标。

### 3.6 项目生命周期端点（B5c=b）

- `POST /api/workspaces/{id}/timeline/projects`，请求体仅 `{"name":"项目名称"}`：admin/member 可新建，viewer 403；名称 trim 后 1..200 字，workspace 内活跃项目同名 422 `NAME_CONFLICT`。服务端写 `created_by=当前操作者`、version=1，返回 201 `{project_id,name,created_by,version}`。空项目立即出现在编辑器/仪表盘，后续节点走 3.1 create 行。
- `DELETE /api/workspaces/{id}/timeline/projects/{project_id}`，请求体 `{"base_version":7}`：**仅 workspace admin**，非 admin 403 `ADMIN_REQUIRED`；先调用 `_project_access(workspace_id=路径id, write=True, require_active=True)`，再以条件 UPDATE 写 `deleted_at/deleted_by`、version+1，版本不符 409。返回 200 `{project_id,version,deleted_at}`；节点与批次保留、不级联硬删；重复删除返回 404 `PROJECT_NOT_ACTIVE`。
- 两条路径均写 `audit_log`（`timeline.project_created` / `timeline.project_deleted`）。v1 **没有 PATCH 改名、没有恢复端点**；名称录错由 admin 软删后按原名或新名重建，软删名称可复用。

### 3.7 Excel 导入两段式 + 导出（F2-⑦/⑧/⑨，R1–R5，N2）

- **preview**：`POST /api/workspaces/{id}/timeline/imports/preview`，请求 `{filename,content_base64}`；admin/member 可用，viewer 403。解析+全量校验成功后存 `timeline_import_batches`（preview_json、content_sha256、created_by=导入者、status=previewed），返回 201 `{batch_id,format,row_count,projects:[...],warnings:[...]}`。
- **commit**：`POST /api/workspaces/{id}/timeline/imports/commit`，请求仅 `{"batch_id":123}`，返回 201。`BEGIN IMMEDIATE` 事务内先按 id/workspace/created_by 查批次：查无 404、已 committed 409；随后重放 preview_json，复查全部行规则与 workspace 内活跃项目名称唯一性，任一失效 422 零写入；最后条件更新状态为 committed。**不提交 project base_version，也不比较 sha256**——导入只创建新项目，commit 不重收文件，二者均无可比较对象。
- commit 为每个新项目建项目/节点及 `trigger_source='import'` timeline 批次，与手工编辑在审计层同构；状态机在资格检查层防重复提交，事务写锁+名称唯一索引封住 preview→commit 竞态。
- **预览要素（R3 修订版）**：① 将新建 N 个项目（列名）；② 「**状态将按日期重算，仅『已完成』保留**」醒目提示；③ 行级错误清单（含同名项目报错），**有错不许提交**。
- **导出**：8 列单 sheet；间隔=实时派生计算值（每轨首节点空）；状态=当前派生三态；行序=项目→轨道→日期→节点名自然序→id；行上限 1000（与导入闭环，导出物必可再导入）；`make_csv`/`make_xlsx`+`safe_cell` 防公式注入现成（transfer.py:125-159）。往返既定差异：导出→再导入后「已完成」保留但打勾时刻变为导入时刻（原时刻只在审计里）；R5：同名即拒使「导出→导回同一 workspace」被 R1 拦截，往返等价仅发生在全新 workspace/项目已删除场景。
- **导出端点（G1：workspace 级全量）**：`POST /api/workspaces/{id}/timeline/export` → 200 base64+sha256（形态对齐 export_board 的 POST→200，server.py:212；服务端复用 service.py:1460-1512 先例）；一次导出该 workspace **全部活跃项目**。权限=workspace membership（viewer 403）。单项目导出不进 v1，未来走 `project_ids` 可选参数扩展。

### 3.8 错误码全集（C2 分层）

分层总则：顶层 project 不存在、跨 workspace 或无权访问统一 403 `PROJECT_FORBIDDEN`；undo/import batch 等**操作对象 ID**查无为 404 专属 code；变更行内 node 无效、已删除或跨项目为 422 行级错误。

| 状态 | code | 场景 |
|---|---|---|
| 401 | `AUTH_REQUIRED` / `SESSION_INVALID` | 路由层统一（含写方法 CSRF），timeline 零额外代码 |
| 403 | `PROJECT_FORBIDDEN` | 顶层 project 不存在/跨路径 workspace/无权；viewer 挡读挡写/member 写他人项目；统一模糊文案「资源不存在或不可访问」 |
| 403 | `ADMIN_REQUIRED` | 非 admin 调 initial-correction、项目软删，或撤销含 initial_correction 的批次；整请求零写入 |
| 404 | `PROJECT_NOT_ACTIVE` | 已通过归属/权限检查的项目命中软删状态 |
| 404 | `TIMELINE_BATCH_NOT_FOUND` | undo 请求中 batch_id 查无；权限模糊化检查在前，任一 404 整批零写入 |
| 404 | `TIMELINE_IMPORT_BATCH_NOT_FOUND` | commit 的 batch_id 在当前 workspace/当前操作者下查无 |
| 409 | `VERSION_CONFLICT` | batch/correction/delete 的 base_version 不符，整批零写入；batch 冲突 details 带项目完整视图 |
| 409 | `UNDO_TARGET_STALE` | undo 目标非项目最新批次 / undo 批不可再撤，整批零写入 |
| 409 | `TIMELINE_IMPORT_ALREADY_COMMITTED` | 导入批次状态已 committed 或条件状态迁移失败 |
| 422 | `NAME_CONFLICT` | service 层网页创建/导入显式校验同名活跃项目（R4，与部分唯一索引双保险） |
| 422 | （行级校验） | details 带 `row`/`header` 或 `node_id`；含 node 无效/越界、空数组、超限、非法枚举/日期/类型/限长、同名项目全部行、文件内重复 |
| 422 | `IMPORT_HEADERS_MISMATCH`（文件级） | 表头 strip 后与 8 列标准列名不完全一致，整文件拒绝、文案附标准表头 |
| 428 | `VERSION_REQUIRED` | batch/correction/delete 请求缺 base_version（沿用 require_version，service.py:60-63） |

---

## §4 权限模型

依据：E5（7- §0-6）、D3（5- §0-9）、DRAG Q18-B / Q20–Q22、STATE §5、mainline §2。

### 4.1 `_project_access` 形态（仿 `_board_access` 同构不同表，service.py:188-202）

```python
def _project_access(self, conn, user_id, project_id, *, workspace_id=None,
                    write=False, require_active=False):
    row = conn.execute(
        """SELECT p.*, wm.role FROM timeline_projects p
           JOIN workspace_memberships wm ON wm.workspace_id=p.workspace_id AND wm.user_id=?
           WHERE p.id=? AND (? IS NULL OR p.workspace_id=?)""",
        (user_id, project_id, workspace_id, workspace_id)).fetchone()
    if not row or row["role"] == "viewer":          # Q18-B：viewer 连看都不行（挡读挡写）
        raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
    if write and row["role"] != "admin" and row["created_by"] != user_id:
        raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
    if require_active and row["deleted_at"]:
        raise ApiError(404, "PROJECT_NOT_ACTIVE", "项目当前不可用")
    return row
```

### 4.2 语义要点

- **读** = admin+member（STATE §5「查看对所有注册成员开放」）；**viewer 挡读挡写**（DRAG Q18 选 B）。⚠️ 与 `_workspace_role` 现行为不同（那里读不挡 viewer，service.py:184 只挡写）——本钩子语义**收紧**，依据即 Q18-B 拍板，非笔误。
- **写** = admin 全改；member 仅 `created_by=自己`。
- workspace 路径端点**必须传 workspace_id**；因此项目不存在、跨路径 workspace、无 membership/viewer、member 写他人项目均自然落同一 403 `PROJECT_FORBIDDEN`，不泄露存在性。无 workspace 路径的单项目 GET 传 NULL，但 membership JOIN 仍挡未授权访问。
- **节点归属**：所有变更行在项目授权后再以 `id + project_id + deleted_at IS NULL` 查 node；查无/跨项目/已删除均 422 行级，禁止仅按 node_id 更新。
- **服务端执行**：batch/undo/initial-correction/单项目 GET/项目 DELETE 对每个涉及项目均显式 `require_active=True`；项目软删另加 admin 门槛。网页创建/Excel 导入尚无既有项目可校验，改为 workspace membership 后显式拒绝 viewer。任一权限或活跃态失败整请求零写入。

### 4.3 created_by / initial_date 三重锁（D3）

① 通用 batch 请求体白名单 `reject_unknown` 不含 created_by/initial_date；② 通用 UPDATE 语句**永不包含**这两列（代码评审+测试锁定「任何通用路径改不动」）；③ 唯一例外为 §3.3 admin initial-correction 端点，只改 initial_date 且强制产生 `initial_correction` 批次。initial_date 在编辑器不展示，但在全员可见的复盘语境返回（C1）。**不引入 SQLite 触发器**（全库现状零触发器，权限/版本/审计全部在 service 层，风格一致优于双保险）。

### 4.4 创建、删除、导入与契约

- 网页新建与 Excel 导入项目的 created_by 均为**当前操作者**（DRAG Q22/B5c，第一版不做指定创建者）；admin/member 可创建、viewer 403。仅 admin 可软删；v1 不改名。
- 权限技术契约（DRAG Q20–Q22 冻结）：created_by 首次创建系统写入后**任何人（含 admin）不可修改**；initial_date 例外纠正权仅限 workspace admin；权限必须服务端执行。

---

## §5 Excel 解析器规则（B2 表 · R1–R5 修订后版本）

依据：Q6 大框架、D12=B、F2-①–⑨（8- §0.1）、R1/R2/R3/R5。列序=项目名称｜阶段｜轨道｜节点｜日期｜间隔｜状态｜备注。

### 5.1 文件级校验（任一命中=整文件拒绝，不进预览）

| 校验 | 规则 | 依据 |
|---|---|---|
| 格式/大小 | 仅 .csv/.xlsx；≤1.5MB；≤1000 数据行；单元格≤10k 字符；公式/宏/外部链接/压缩炸弹拒收（另含 200 zip 条目与 12MB 解压上限） | transfer.py:8-13, 54, 69, 71, 107-112 现成 |
| 编码 | CSV：utf-8-sig / gb18030 | transfer.py:40-44 现成 |
| 表头 | strip 后与 8 列标准列名**完全一致**（含顺序、无重复）；不一致=文件级 422 `IMPORT_HEADERS_MISMATCH`，文案附标准表头 | F2-①=a 新增 |
| sheet | 默认取第一个 sheet；多 sheet 预览提示「仅导入第一个 sheet」 | transfer.py:82-83；service.py:1348 |

### 5.2 行级校验（错误 details 带 `row`（数据行从 2 起）、`header`、原因——对齐 service.py:1417-1428 惯例）

| 列 | 校验 | 错误形态 |
|---|---|---|
| 项目名称 | 非空、≤200 字；新名=建项目（created_by=导入者）；**同名已有项目=该项目所有行报错（F2-④=b：项目名称唯一，R1），有错不许提交、不做部分导入**——用户改名或删掉该项目行后重新上传 | 行级 422「项目名称唯一：已存在同名项目 X」（带行号）；创建路径另有 422 `NAME_CONFLICT`（R4） |
| 阶段 | ∈ 六阶段名（创意/设计/开发/测试/量产/应用迭代） | 行级 422，文案列可选值 |
| 轨道 | ∈ 主线/并行 | 行级 422 |
| 节点名称 | 非空、≤500（对齐任务标题上限 service.py:1428） | 行级 422 |
| 日期 | 文本严格 YYYY-MM-DD+真实历法校验（复用 validate_due 语义 service.py:90-101，去「未设置」哨兵）；.xlsx 数值日期按**序列号换算，限 1950–2100 整数**（序列号 18264–73051：下界避开 1900 纪元闰年 bug 区、上界挡 YYYYMMDD 式手敲数字）；**非整数序列号（带时间如 46234.5）明确拒收**（陪审补丁①）；1904 日期系统 Mac 老文件偏移 1462 天，本团队 Windows 环境可忽略（注记） | 行级 422；CSV 文本变形（Excel 打开 CSV 日期列被转性）的报错文案加「**在 Excel 中编辑请改用 .xlsx 导入**」（陪审补丁②） |
| 间隔 | **整列忽略、不校验内容**（Q6 冻结） | 无 |
| 状态 | ∈ 三态或空（D12=B）：「已完成」→ done_at=导入时刻；「未开始/进行中」→ 仅参考、落库按日期重算；空 → 按日期派生；其他文本 → 行级报错 | 非三态=行级 422 |
| 备注 | 可空，≤500 | 行级 422 |
| 文件内重复 | 同项目+同轨+同日+同名，第二行起 | 行级 422「与第 N 行重复」 |
| ~~库内重复~~ | ~~跳过+预览汇总~~ —— **随 F2-④=b 失去适用路径（无追加模式，R2）**；文件内重复报错保留 | — |

### 5.3 两段式与安全界

- 载体 `timeline_import_batches`（§1.5）；commit 资格走 previewed/committed 状态机，内容在事务内重放 preview_json 并复查名称唯一与全部行级规则（§3.7）；不提交 project base_version、不比较 sha256；previewed 批次无过期清理（维护注记）。
- 行数/大小上限沿用现有安全界不改（F2-⑥）：10 项目×几十节点≈数百行，余量一个数量级以上，项目数翻十倍再议。
- 用户附注（2026-08-18）：未来将提供标准格式 Excel 模板（导出即天然模板）、由 agent 清洗数据按规范整理后再导入——格式摩擦由工作流前置消化。

---

## §6 v16 迁移 runbook（B1 · F3 执行序）

依据：F3/F3-i/F3-ii（8- §0.1）、D1、STATE §5 红线「迁移前必须备份且可恢复」。当前库 `SCHEMA_VERSION=15`（database.py:10）。

| 步 | 动作 | 代码依据 |
|---|---|---|
| 0 | 停服窗口（迁移在启动时执行，避免迁移与写并发） | server.py:434 |
| 1 | **`python flowboard_ops.py backup`（强制，F3-i=是）** → 完整包（DB 快照+附件+sha256 manifest+自校验）；`verify` 复核。CLI 包是唯一「可 verify、可整包恢复」的完整单元（自动快照只备库文件不带清单） | operations.py:52-78, 81-108；flowboard_ops.py:15-23 |
| 2 | 启动新版本：`create_server` → `migrate()` | server.py:414-417 |
| 2a | 自动序：探测 `PRAGMA user_version`=15 < 16 且库非空 → `_backup_database` 生成 `backups/flowboard-pre-v16-<时间戳>.db`（**先 integrity_check 再快照**，快照失败=迁移中止） | database.py:68-83, 48-65 |
| 2b | `_migration_v16`：**单事务**（BEGIN IMMEDIATE+异常回滚）内纯 CREATE TABLE——timeline_projects（含 R4 部分唯一索引）/ timeline_nodes / timeline_change_batches / timeline_node_changes / timeline_import_batches（**五表一次建齐，F3-ii=是**：全纯 CREATE TABLE 零数据变换，一次建一张和建五张失败模式完全相同，拆两次=双倍仪式零风险收益）→ 写 schema_migrations 行 → `PRAGMA user_version=16` → 事务外 foreign_key_check + integrity_check（对齐 v2–v15 每步惯例） | database.py:25-33；228-233；392-397 与 927-939 |
| 2c | 迁移尾部：journal_mode=WAL + foreign_keys=ON | database.py:116-117 |
| 3 | **冒烟**：迁移前只读记录存量表动态计数基线（至少 users/workspaces/boards/groups_/tasks）→ 迁移后逐项比对完全一致；user_version=16；五新表 COUNT=0；`flowboard_ops.py list` 显示包 valid；登录+看板+时间轴页可开。固定数量只允许存在于隔离测试 fixture，不写死运行库 runbook | N3；基线为迁移前只读 COUNT |
| 4 | **回滚**：迁移中失败=单事务自动回滚，库停 v15；迁移成功后要退数据=停服 `flowboard_ops.py restore <包>`（自动 pre-restore 安全备份、staged 原子替换、失败自动复原旧库） | operations.py:134-167（含 maintenance_lock 40-49） |

规格注记：① `_backup_database` 快照名取**目标**版本号、一次 migrate() 只备一次（现存 **13 个**快照即证，v8→v11 一跳无 pre-v9/pre-v10；修正单元 ① 草案「14 个」笔误）；② pre-vN 快照是裸 .db（无 manifest），retention 只清 `flowboard-` 前缀目录（CLI 包），二者不互删（operations.py:116, 126）；③ 回滚到 v15 备份后再跑 v16 代码会自动重放迁移（纯 CREATE TABLE 新表空建）——**回滚语义=丢时间轴侧新增写入，存量无损（预期内）**。

---

## §7 回归与测试（F4 · B3 修订版）

### 7.1 新增 timeline 测试清单（12 组，编码期落）

| # | 组 | 覆盖条款 |
|---|---|---|
| 1 | 权限/归属/项目生命周期：member 改他人项目、路径 workspace 不符均 403；跨项目 node 注入 422；viewer 读/创建 403；member/admin 网页新建成功且 created_by 正确；仅 admin 软删、节点不硬删；软删后单项目 GET/batch 写入/重复 DELETE 均 404 且零写入；未登录 401 | E5/B2/B5c；DRAG Q18-B |
| 2 | created_by / initial_date：通用路径改两字段必败；initial-correction 仅 admin，多节点同批、自由日期不钳制不级联；重复/越界 node 422；全等值 no-op；软删项目 correction 404 零写入 | D3/B5a/C1 |
| 3 | 并发：batch/correction/delete 缺版本 428；base_version 不符→整请求 409 零写入；batch 冲突体带 nodes/segments/stage_intervals/metrics 最新视图 | E2/E3/B4/B5a/B5c；DRAG 确认 5 |
| 4 | undo：撤最新成功（old/new 互换、created 反向软删、deleted 反向恢复）；撤非最新 409；batch_id 不存在 404；undo 批不可再撤；三连批撤中间必败；member 撤 initial_correction 403、admin 成功；软删项目 undo 404 零写入 | E4/B1；确认 12/16/17 |
| 5 | 混合批次：同批 date+done_at→批次主类型 direct_edit、行级 field 区分、details_json.kinds | E7c=a；UX R1 |
| 6 | 写入/顺延：interval_days 0..3650、无前驱/create/同批改 track 拒绝、date 优先；done_at 严格布尔；single/cascade 服务端钳制；前置快照邻居；同日自然序+id 兜底；只顺延本轨、间隔保持、多锚点钉住+分段平移、direct 绝对优先 | B3；STATE §2；E7d/E8 |
| 7 | 派生/视图/复盘：M1–M5；三类响应恒含 nodes/segments/stage_intervals，row_index/node_ids 确定；复盘项目/节点汇总完整、批次最近 50+has_more、viewer 403；直接改日期后 undo，direct_edit_count 不因 undo 反向行额外 +1 | D6–D13/B4/B5b |
| 8 | Excel 导入：表头不匹配文件级报错；非法日期/轨道/阶段/状态行级报错带行号（从 2 起）；xlsx 序列号日期换算+非整数序列号拒收；已完成保留+状态重算；间隔忽略；**同名项目拒绝（名称唯一，报错带行号、有错不许提交）**；文件内重复报错 | Q6/D12/F2 全项 |
| 9 | Excel 导出→导入往返等价（除 done_at 时刻与状态重算的既定差异）；**按新 workspace 构造（同名即拒，R5）** | Q6 |
| 10 | 迁移：v15→v16 五表建成、user_version=16、存量计数不变、FK/integrity 通过、schema_migrations 记账 | D1；红线 |
| 11 | 预览两段式：preview 存完整批；commit 只收 batch_id、无 project base_version/sha 比对；事务内名称唯一+行级重校验；preview 后同名竞态 422 零写入；查无 404、重复提交 409 | F2/N1/N2 |
| 12 | 空 batch/correction 数组 422；全等值 200 no-op（不建批、version 不动）；项目名冲突由 service 422 与部分唯一索引双保险 | E7b/R4/B5a |

### 7.2 第一阶段回归主体（自动化）

- **现有测试原样全跑通过 = 回归验收**：79 个 Python 测试（12 文件，含 9 个 Chromium E2E：test_views_e2e 6 + collaboration/i12/i13 各 1）+ 5 个 Node 前端测试文件。v16 纯增量 ⇒ 这套测试**一行不该改、一个不该挂；任何测试需要修改才能通过=红灯，停下排查**。
- 命令（README.md:107-113 原文）：`python -m unittest discover -s tests -p 'test_*.py' -v`；`node --test (Get-ChildItem tests -Filter *.test.js | ForEach-Object FullName)`；外加 py_compile / node --check / git diff --check。
- E2E 全为 DOM/文本断言、**无像素比对**（test_views_e2e.py:38-103；tests/ 全目录 grep 截图/像素 API 零命中）——CSS 改动不挂自动化，视觉回归靠 7.3 手工冒烟。

### 7.3 UI 手工冒烟（约 15 分钟，每次上线点一遍）

看板一旅程（开板→拖卡→刷新顺序还在）、甘特一旅程（切视图能渲染）、仪表盘 widgets 一旅程（图表出数）、登录+权限一角（普通成员登录正常）。**结果留一行文字记录（过/不过+日期）。**

---

## §8 视觉与前端基线（F1 + 已冻结交互基线）

### 8.1 浅色优先范围（F1 · 2026-08-19 覆盖拍板）

- **feature01 v1 三个页面（编辑器 + 单项目仪表盘 + 全项目仪表盘）均优先开发浅色版**，与 Flowboard 当前整体浅色基调保持一致。
- 单项目仪表盘以 `（视觉UI升级留档）single-project-visual-options.html` 的**方向 A「大标题 · 白卡」**为当前执行基线；编辑器与全项目仪表盘复用同一套浅色语义 token 和信息层级，不要求机械复制单项目页面布局。
- **未来整体暗色皮肤不进 feature01 v1**：本轮不实现主题切换、暗色 CSS 运行态或全站硬编码色值改造。保留语义 token 抽象只是为了降低未来换肤成本，不构成暗色开发任务。

### 8.2 token 层（方向 A 浅色冻结 + STATE §3）

- 核心 tokens：canvas `#f5f5f7` / card `#ffffff` / ink `#1d1d1f` / ink2 `#6e6e73` / ink3 `#aeaeb2` / hairline `#e8e8ed` / today 与 overdue `#e5484d`。
- **v3.2 六阶段色板（当前执行色板）亮色版**：创意 `#ab5fe8` / 设计 `#1746b0` / 开发 `#0aa67e` / 测试 `#c9641a` / 量产 `#64bc46` / 应用迭代 `#8f6a10`；精确色值仍可在门 5 真实数据验收中做不改变色相方向的微调。
- 阶段分界=**) 形**（前段圆尾+后段直角，顺时间轴右行）；亮色底节点圈=白色 2px；逾期红圈=`#e5484d`。时间条仍为 2px 小圆角矩形。
- 方向 A 的结构基线：浅灰画布 + 白卡、项目大标题、KPI 压为一行次级摘要、时间轴作为核心视觉点；今日线与逾期提示必须同时有文字/形状辅助，不能只靠颜色表达。
- 可访问性已知项：量产绿对白底对比约 2.38，低于 3:1；门 4 必须保留阶段直标/图例/节点形状等冗余编码，门 5 再结合真实数据核定最终色值。
- 实现模式：三个页面以语义变量引用颜色，不散落主题判断；但 v1 只交付浅色变量值，不交付换肤入口或暗色变量集。

### 8.3 视觉与交互基线（STATE §3 / UX Q+R / DRAG 覆盖注记）

- 时间条=连续条形，**2px 小圆角矩形**；不用透明混色承担主要信息表达。
- 拖拽入口=节点**右键四项菜单**：【拖拽（仅当前节点）】仅在不足 1 天时最小碰撞顺延／【拖拽（顺延）】同轨后续整体平移／【已完成】／【未完成】；**无默认档**——每次拖动必须右键重新选择；**两仪表盘同一套菜单**（UX R2）。前端提供即时手感，服务端按 §3.1 同规则再次钳制，不能靠伪造请求越界。1 天只约束拖拽，不改变编辑器间隔、14 天最细缩放或 `<18px` 密集节点聚合。
- 拖动精度=局部放大带 **±10 天 ×8 倍**；磁吸默认档=**标准**（纯 1 日吸附）；「强」档磁铁参数**留集成验收**微调。
- 拖拽**全程零网络**（授权/钳制/磁吸/放大带全在浏览器内完成），唯一点红色【更新日期】才 POST 一批（E6；DRAG §1-6「未点【更新日期】不改写原始数据」）；批次 details 记 {mode, magnet, zoom_band}。
- 状态切换与日期修改**共用同一草稿批次**：一次【更新日期】提交、【放弃更改】回滚（纯前端丢弃）、提交后一次撤销；审计区分修改类型（UX R1 → E7c）。
- 全项目左侧 `.timeline-portfolio-meta` 右键菜单恒渲染【在单仪表盘中查看】与【撤销】；打开菜单时按目标项目的 `lastBatchId / dirty / editable` 即时计算撤销可用性，不可撤销时使用原生 `disabled`。前者只改变前端视图与返回来源，不发起数据写请求；返回来源随单项目/编辑器页签切换保留。普通入口目标为 `home`（文案【← 我的工作】），全项目右键入口目标为 `all`（文案【← 返回】），二者共享方案 D 箭头回弹 hover/focus 动画，并遵守 `prefers-reduced-motion`。
- 行模型（UX Q7/Q8）：单/多项目统一「默认主线/并行两行 + 展开按钮拆重叠阶段」；未展开时**仅重叠段**上下分半、六阶段原色纯净不遮挡——配套数据=§2.4 服务端阶段区间列表（画法 A）。
- 共享绝对日历标尺 + 红色今日线贯穿；多项目每项目一条泳道，默认最多两轨。
- 编辑器排序=独立按钮：按日期（默认）/按六阶段分组（阶段内日期升序）；**排序只改显示不改数据**。全项目筛选=顶部项目多选+排序下拉（开始日期/当前阶段先后/最近临近节点/逾期未完成节点数），行内只用克制小色点（橙=本周、红=逾期，红左橙右）。
- 工程边界：feature01 为新页面/样式，可直接使用浅色语义 token；现有全站约 158 处硬编码色值不在本轮改造范围。未来整体暗色皮肤须另行立项并补全站视觉回归，不得借本轮顺带实施。

---

## §9 溯源与未尽事项

### 9.1 冻结条款 → 本文条款溯源表

| 冻结条款（出处） | 本文落位 |
|---|---|
| STATE §2 双轨日期链/顺延规则（日期优先、只顺延本轨、间隔保持、删除只重算、保存后一次撤销） | §1 间隔派生原则、§3.1 行角色与规则、§7 组 6 |
| STATE §2 状态三态派生（2026-08-14 确认）；「不单开完成日期列」 | §2.1（含 D4 认定边界）、§1.2 done_at |
| STATE §5 权限红线（服务端执行/迁移前备份可恢复/不破坏第一阶段数据/软删除优先/检查点五件套） | §4、§6、§7、全文 |
| DRAG 确认 3（连续拖动最终草稿为准） | §3.1 同 node_id 多行最终值语义 |
| DRAG 确认 4/5 + 问卷 Q10（跨项目整批全成全败/冲突零写入/展示服务端最新让用户重新确认） | §3.1（E1/E2/E3） |
| DRAG 确认 8（离开拦截）、确认 11（提交无二次确认） | 前端行为（§8.3 草稿批次），不新增服务端条款 |
| DRAG 确认 10/Q6（已完成节点可拖+【历史日期修正】标记） | §3.1 historical_correction + 与 initial_correction 概念区分 |
| DRAG 确认 12/16/17（一次撤销/反向批次/不删原记录/无倒计时/跨项目整批回滚） | §3.2（E4 四件套+undo_group 等价确认） |
| DRAG 确认 2 + UX R3（钳制边界） | §8.3 双模式钳制 |
| DRAG Q18-B（viewer 连看都不行） | §4.1/§4.2 |
| DRAG Q20–Q22（created_by 永不可改/initial_date 纠正仅 admin/导入 created_by=导入者） | §3.3、§4.3/§4.4 |
| UX R1（共用草稿批次/审计区分类型） | §3.1（E7c） |
| UX R2（双仪表盘同菜单）、R3（单节点档双向钳制） | §8.3 |
| UX Q7/Q8（两行+展开+仅重叠分半） | §8.3 + §2.4 阶段区间列表 |
| UX Q5（全项目筛选排序+红橙点）+ D10 修订（本周窗口） | §2.2 M5、§8.3 |
| Q6（Excel 大框架）+ D12=B（日期优先只认已完成） | §5 |
| 画法 A 链式（对照稿拍板）+ D13（双份契约） | §2.4 |
| mainline §4 交付范围 / §9 完成边界 | 全文验收基准（每检查点五件套：数据层/API/可操作 UI/测试/文档） |
| 门 3 初审 B1–B5 + C1/C2 + N1–N4 | §0.1、§1.5、§2.1/2.4、§3.1–3.8、§4、§5.3、§6、§7 |
| 用户 B5c=b（网页新建+admin 软删+v1 不改名） | §1.1、§3.6、§4.4、§7 组 1 |

### 9.2 未来候选（用户提出、明确预留，**不进 feature01 v1**；升级须用户显式拍板）

- **每周看板（本周工作提示）**：以 D10 本周窗口为语义地基；feature01 只做橙点，不建每周看板页面。
- **md/json 导入**：提供空白标准模板，先让 agent 清洗数据再上传；v1 维持 Q6 冻结的 Excel 单一格式（D12=B 的状态语义与文件格式无关，天然兼容）。标准 Excel 模板可由导出天然获得（§5.3 用户附注）。
- 其他已留口的未来项：GET `project_ids` 可选参数（§3.4）；项目改名/恢复入口（§3.6 明确不进 v1）；409「并排+一键以我的草稿重放」升级路径（§3.1，锚点契约不变）；**Flowboard 整体暗色皮肤**（§8.1 仅留语义 token 种子）；派生指标缓存（§2.3，量级 ×100 再议）。

### 9.3 留集成验收项清单（门 5 前基于真实数据收口，不阻塞门 4 编码）

- v3.2 六阶段精确色值真实数据微调（§8.2）。
- 磁吸「强」档磁铁参数（§8.3；标准档已定）。
- 像素项：条形粗细、节点点样式、字号、行高、留白、响应式（2px 圆角已冻结；mainline §7 第 3 条）。

---

## §10 门 3 初审修订吸收记录（2026-08-18）

1. 原蒸馏缺口 G1–G3 均已吸收：导出=workspace 全量（§3.7）；导入路径=`timeline/imports/preview|commit`、均 201（§3.7）；undo batch_id 查无=404（§3.8/§7 组 4）。
2. 初审阻断 B1–B5 已吸收：undo admin 门槛、workspace/project/node 归属、核心写入 schema/钳制/稳定序、stage_intervals、initial-correction/review/project lifecycle API 分别落入 §2–§4 与 §7。
3. N1–N4/C1–C2 已吸收：导入表完整 DDL（§1.5）、导入状态机+事务内重校验（§3.7/§5.3）、动态迁移计数（§6）、索引精确计数（§0）、initial_date 可见性（§1.2/§4.3）、错误分层（§3.8）。
4. 流程项 N5–N7：最终增量复审已 PASS；4/5/6/7/8 已归档且本文/STATE 引用已同步，10- 已降级为历史修订记录。commit 与新 planner↔coder run 均须用户显式授权；mc-expert KB 契约入口已修复并完成增量陪审。

门禁证据：独立增量复审先指出 `require_active=True` 与 undo 计数两个局部阻断；最小修订后再次逐项取证，结论为 **PASS、高置信**。门 3 技术契约至此关闭。

---

## §11 F1 视觉窄修订记录（2026-08-19）

1. 用户基于 Flowboard 当前整体浅色基调，显式推翻 2026-08-18 的 F1=b 深色执行方向，指定视觉样张**方向 A 优先开发**；未来再考虑整体暗色皮肤。
2. 本次只替换 §0 F1 与 §8 视觉基线，并同步 mainline/STATE/UX 覆盖注记与三份样张的当前/历史标识；§1–§7 的数据、派生、API、权限、Excel、迁移和测试契约不重开。
3. 门 4 范围因此减少：不开发主题切换与暗色运行态；仍保留语义 token。交互、画法 A 链式、两轨模型、右键双模式拖拽及所有服务端安全契约不变。
4. 门禁结论：三处活跃文档尾差修正后，F1/§8 定向增量复审 **PASS（高置信）**；门 3 已恢复关闭态。coder 只能按本版方向 A 浅色基线开工。
