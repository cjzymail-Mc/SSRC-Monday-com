# B-002 coverage map（CP3 终版 · 2026-08-19）

> 产物：team-task §8 第 9 项 + lead 追加项⑩的条款级映射终版。逐条映射 `9-GATE3_TECH_FREEZE.md` §7.1 组 1–12 + §5 Excel 规则（含 §5.1 表头行，追加项⑩）→ **真实存在且本 session 实跑通过**的具名动态测试。
> 证据三分类（对齐防漂移指南块⑦）：本 map 全部 PASS 均为「实际执行证据」——2026-08-19 16:05 `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'` → **29/29 OK**（本 session 多次复跑稳定）；单测可用 `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py' -k <测试名>` 单独加载运行。
> 无「计划中/SKIP/占位」条目。GAP-非九项 = 字面缺口但不在 B-002 九+1 项与 planner 探针 8 缺口内，留 lead/planner 排序（见 §D）。
> 实现锚点（本 CP 结束时）：`flowboard/timeline.py`（修 9 处）、`tests/test_timeline.py`（21 存留 + 8 新增 = 29 测；4 处按自主裁决 #4/#6 收敛方向修改）。

---

## A. §7.1 十二组逐条映射（测试均为 `test_timeline.TimelineCoreTests.<name>`）

### 组 1 权限/归属/项目生命周期（E5/B2/B5c/DRAG Q18-B）

| 判据 | 具名测试（断言形态） | 状态 |
|---|---|---|
| member 改他人项目 403 | `test_group1_project_permissions_and_lifecycle`（other 提交 403） | PASS |
| 路径 workspace 不符 403 | 同上（owner 向 workspace 999 提交 403） | PASS |
| 跨项目 node 注入 422 | 同上（node_id 999999 → 422） | PASS |
| viewer 读/创建 403 | 同上 + `test_name_conflict_and_viewer_denied` | PASS |
| member/admin 网页新建成功 | `_create_as_member`（member 建成功） | PASS（created_by 字段显式断言缺失→§D-2） |
| 仅 admin 软删、节点不硬删 | 同上（member 403 / admin 200 / deleted_at 非空） | PASS（节点行保留断言缺失→§D-2） |
| 软删后 GET/batch/重复 DELETE 404 且零写入 | 同上（三操作 404） | PASS |
| 未登录 401 | `test_group1_unauthenticated_http_401`（AUTH_REQUIRED） | PASS |

### 组 2 created_by / initial_date（D3/B5a/C1）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| 通用路径改两字段必败 | `test_group2_initial_date_lock_and_group3_conflict_views`（set initial_date 422） | PASS（created_by 用例→§D-2） |
| initial-correction 仅 admin | 同上（member 403） | PASS |
| 多节点同批 | 同上（两节点一次成功） | PASS |
| 自由日期不钳制不级联 | 断言补强缺 | §D-2 |
| 重复 node 422 | 同上 | PASS（不存在 node_id→§D-2） |
| 全等值 no-op | — | §D-2 |
| 软删项目 correction 404 零写入 | — | §D-2 |

### 组 3 并发（E2/E3/B4）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| 缺版本 428 | `test_group3_missing_versions_and_exact_zero_writes`（correction/delete 428） | PASS（batch 428 用例→§D-2） |
| base_version 不符→409 零写入 | 同上 + `test_group2…`（counts 不变） | PASS |
| 冲突体带 nodes/segments/stage_intervals/metrics | `test_group2…`（四键） | PASS |

### 组 4 undo（E4/B1）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| 撤最新成功（old/new 互换） | `test_group4_undo_guards` + `test_group7_view_metrics_review_pagination_and_undo_count`（remark 批撤后 date 断言） | PASS |
| **created 反向软删（行仍在）** | `test_group4_undo_three_batch_middle_and_reverse_roles`（deleted_at 非空 + 物理行仍在 + 不在 view；同时抓出并修复了实现反向互换 bug） | PASS |
| **deleted 反向恢复** | 同上（次节点 deleted_at=NULL、回 view、中批 remark 保留） | PASS |
| **三连批撤中间 409 零写入** | 同上（b1<b2<b3 严格递增；409 `UNDO_TARGET_STALE`；version/batches/node_changes/audit_log/节点表五处快照不变） | PASS |
| 撤非最新 409 / 404 / undo 不可再撤 | `test_group4_undo_guards`；undo-of-undo 亦在新测试复测 | PASS |
| member 撤 initial_correction 403 | — | §D-2（admin 成功=`test_initial_correction_undo_and_review` PASS） |
| 软删项目 undo 404 零写入 | — | §D-2 |

### 组 5 混合批次（E7c）

`test_group5_mixed_batch_audit_kinds`：主类型 direct_edit、行级 field 区分、details_json.kinds——PASS。

### 组 6 写入/顺延（B3/STATE §2/E7d/E8）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| interval_days 0..3650 | `test_group6_write_chain_rules_and_snapshot_neighbor`（6/99 正例） | PASS（3650/3651 边界→§D-2） |
| 无前驱/create/同批改 track 拒绝 | 同上（三例 422） | PASS |
| date 优先覆盖 interval | `test_cascade_anchors_status_only_and_date_priority` | PASS |
| done_at 严格布尔 | `test_group6…`（"yes" 422） | PASS |
| single/cascade 钳制 | `test_single_and_cascade_clamping` | PASS |
| 前置快照邻居/多锚点/direct 优先 | `test_cascade_anchors…` + `test_batch_update_conflict_noop_and_cascade` | PASS |
| 同日自然序+id 兜底 | `test_group6…`（B2<B10<B1） | PASS |

### 组 7 派生/视图/复盘（D6–D13/B4/B5b）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| M1/M2/M3 空集/M4/M5=0 | `test_group7_view_metrics_review_pagination_and_undo_count` + `test_project_create_then_batch_nodes_and_derived_view` | PASS |
| M3 非空同日多节点、M5 非零、红橙并存 | — | §D-2 |
| 三数组恒返、row_index/node_ids 确定 | 同上（stage_intervals 精确断言）+ 组3 冲突视图 | PASS（row_index>0 重叠场景→§D-2） |
| 复盘汇总完整、50+has_more、viewer 403、undo 不加计数 | 同上 | PASS |

### 组 8 Excel 导入（Q6/D12/F2）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| 表头不匹配文件级报错 | `test_import_headers_contract_literal`（契约字面正例 + 旧表头/乱序/缺列/多列 4×422 `IMPORT_HEADERS_MISMATCH`，details 带标准 8 列、文案含标准表头）；`test_group8_excel_negative_controls`（CSV 2 列文件级拒） | PASS（追加项⑩） |
| **xlsx 整数序列号换算 18264..73051** | `test_import_xlsx_serial_positive_and_boundaries`（18264→1950-01-01、46234、73051→2100-01-01 数值单元格正例；期望值用 `datetime(1899,12,30)+timedelta(days=n)` 测试内独立预计算，不回读实现） | PASS |
| 分数/越界行级 422（带 row） | 同上（18263、73052、46234.5 各 422 `details["row"]==2`）；CSV 整数文本 422 | PASS |
| 文本日期路径不串扰 | 同上（xlsx inlineStr "2026-08-01" 正例） | PASS |
| **状态三态+空、仅已完成落 done_at、其余按日期重算** | `test_import_status_three_states_and_recompute`（五态行：已完成保留×2、未开始+过去→落库进行中、进行中+未来→未开始、空+未来→未开始；done_at 计数=2；期望按 view 的 server_today 独立推算） | PASS |
| 非法状态 422（含旧值「未完成」锋利负例） | 同上（"未完成" 422 row=2）+ `test_group8…`（"maybe" + cases 含「非法状态旧值」） | PASS |
| 间隔整列忽略 | `test_group11_import_two_phase_race_and_replay`（999 被忽略、preview_json 无 interval 键） | PASS |
| 同名既有项目拒绝（R1） | `test_group8…`（NAME_CONFLICT）+ `test_import_multirow_aggregation_and_counts`（commit 后重导 NAME_CONFLICT 且 import_batches 不落批） | PASS（全行报错形态→§D-4） |
| **文件内重复=四键，第二行起 422 带行号** | `test_group8…`（真四键重复→422 row=3、文案「与第 2 行重复」）+ `test_import_multirow…`（row=5/duplicate_of=4、「与第 4 行重复」） | PASS |
| **多行项目聚合成功** | `test_import_multirow_aggregation_and_counts`（3 行同名→preview projects 恰 1 且 node_count=3；commit (1,3)；DB 节点 COUNT=3 防 upsert 覆盖；四键任一不同的两变体不拒） | PASS |
| 字段上限（节点 500/备注 500/项目 200） | `test_import_field_limits_boundaries`（中文样本 500/200 accept、501/201 reject 六方向；batch API set name 500 过/501 拒） | PASS |

### 组 9 导出→导入往返（R5 新 workspace）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| **export_timeline() 真实字节往返** | `test_group9_excel_round_trip_in_new_workspace`（重写后：`raw` 单一变量贯穿 preview，无二次 workbook 构造；parse_upload(raw) 验证 8 表头+6 行；最难样本=双项目/双轨/已完成+未开始+进行中三态/跨 7-8-9 三月/中文长备注/500 字节点名） | PASS |
| 语义等价（逐节点 track/stage/name/date/remark） | 同上（源/新视图逐项目比对） | PASS |
| 既定差异四件 | 同上（已完成保留=done_at 布尔相等+status=已完成；非完成 done_at 空且 status 按 server_today 独立推算期望；interval 忽略但重派生逐轨相等；done_at 只比存在性不比时刻） | PASS |
| 按新 workspace 构造 + 同名再导 422（R5） | 同上（workspace 2 全新；再 preview 同字节→422 NAME_CONFLICT） | PASS |

### 组 10 迁移（D1/红线）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| v15→v16 五表建成、user_version、存量计数不变、FK/integrity、schema_migrations 记账 | `test_group10_true_v15_to_v16_migration_backup_and_idempotence`（真 v15 种子动态迁移） | PASS |
| **备份非空且含代表性 v15 存量（断言对象=备份本体）** | `test_group10_backup_content_idempotence_rollback`（备份 size>0、user_version==15、五 timeline 表不存在、7 表存量计数与迁移前基线一致、tasks sentinel 行逐一相等、backups 目录恰 1 个 `-pre-v16-` 文件） | PASS |
| **v16 重跑 migrate 幂等** | 同上（重跑返回 None、无新备份、user_version 仍 16、schema_migrations v16 COUNT==1、五表 COUNT 仍 0） | PASS |
| **回滚语义可证** | 同上（备份复制为 restore 库→v15+sentinel 完好；重放 migrate→v16 五表重建且存量无损，对应 §6 注记③） | PASS |
| 全程隔离库 | 两测试均 `tempfile.TemporaryDirectory`；真实 `flowboard.db` mtime 停留 2026-08-12 14:31（本 session stat 取证） | PASS |

### 组 11 预览两段式（F2/N1/N2）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| preview 存完整批、commit 只收 batch_id、无 base_version/sha 比对 | `test_group11_import_two_phase_race_and_replay` | PASS |
| 竞态 422 零写入、查无 404、重复 409 | 同上 | PASS |
| preview_json 篡改重放 422 零写入（守卫保留：注入 track=unknown+status=未完成 双非法点） | 同上 | PASS |

### 组 12 空批/no-op/名称双保险（E7b/R4）

| 判据 | 具名测试 | 状态 |
|---|---|---|
| 空 batch/correction 422 | `test_group12_empty_and_project_unique_contract` | PASS |
| 全等值 200 no-op | `test_batch_update_conflict_noop_and_cascade` | PASS |
| service 422 名称冲突 | 组 1/组 12 | PASS（部分唯一索引兜底直触→§D-2） |

---

## B. §5 Excel 规则逐条

### 5.1 文件级

| 规则 | 具名测试/实现锚点 | 状态 |
|---|---|---|
| 8 列标准表头 strip 后完全一致（含顺序）＝**契约字面「项目名称｜阶段｜轨道｜节点｜日期｜间隔｜状态｜备注」**（追加项⑩） | `test_import_headers_contract_literal`；实现 `timeline.py` `IMPORT_HEADERS`（导入导出同源，导出行序同步换列） | PASS |
| 格式/大小/行数/单元格/公式/宏/外链/压缩炸弹安全界 | `flowboard/transfer.py:8-13,54,69,71,107-112` 公共层（timeline 复用同一 `parse_upload`）；公式拒收动态例=`tests/test_secure_foundation.py:83` | PASS（公共层动态；timeline 入口独立重复造例未做→§D-2） |
| CSV 编码 utf-8-sig/gb18030 | transfer.py:40-44 | 同上 |
| 默认第一 sheet | transfer.py:82-83 代码行为；「仅导入第一个 sheet」预览提示文案未实现 | §D-5 |

### 5.2 行级（错误 details 统一带 `row`，数据行从 2 起）

| 列 | 规则 | 具名测试 | 状态 |
|---|---|---|---|
| 项目名称 | 非空、≤200 | `test_import_field_limits_boundaries`（200/201） | PASS |
| 阶段 | ∈六阶段 | `test_group8…`（"未知" 422 row=2） | PASS |
| 轨道 | ∈主线/并行 | `test_group8…`（"unknown" 422 row=2） | PASS |
| 节点名称 | 非空、≤500 | `test_import_field_limits_boundaries`（500/501 中文） | PASS |
| 日期 | 文本 YYYY-MM-DD+历法；xlsx 整数序列号换算；分数/越界拒收 | `test_import_xlsx_serial_positive_and_boundaries`；`test_group8…`（"08/01/2026" 422） | PASS |
| 间隔 | 整列忽略不校验 | `test_group11…` | PASS |
| 状态 | 三态+空；仅已完成落 done_at=导入时刻；其余按日期重算 | `test_import_status_three_states_and_recompute` | PASS |
| 备注 | 可空、≤500 | `test_import_field_limits_boundaries` | PASS |
| 文件内重复 | 四键第二行起 422 带行号 | `test_group8…` + `test_import_multirow…` | PASS |
| 库内重复 | 随 R2 失效 | N/A | N/A |

### 5.3 两段式与安全界

组 11 全 PASS（见 §A）。

### §3.7 导出侧

| 规则 | 具名测试 | 状态 |
|---|---|---|
| 8 列同格式/间隔=计算值/状态=派生三态 | `test_group9…`（导出字节 parse 后三态列值经导入重算验证） | PASS |
| 上限 1000 闭环：恰 1000 导出成功且产物可再导入；超限 fail-closed | `test_export_exact_1000_and_over_limit_fail_closed`（5 项目×200 节点经服务端真实创建；parse 断言恰 1000 行；新 workspace 导回 (5,1000)；SQL 直插 1 行→422 `EXPORT_LIMIT` `details=={"total":1001,"max":1000}`） | PASS |
| 行序=项目→轨道→日期→节点名→id | 现排序键不含轨道维度 | §D-6 |

---

## C. 已按裁定处置的现有测试修改（自主裁决 #4/#6，全部向契约收敛，逐条供 planner 复核）

| # | 位置 | 修改内容 | 方向 |
|---|---|---|---|
| C1 | `test_group8…` cases | 基行/各负例行 status「未完成」→「未开始」；**新增「非法状态旧值」case 使「未完成」成为 422 锋利负例**；断言 `details==None` → `details["row"]==2`（加强：行级错误带行号，§5.2 字面） | 收敛+加强 |
| C2 | `test_group8…` duplicate | 两行同名不同节点名（旧行为误拒）→ 两行真四键重复；断言 (422,row=3) 结构保留 + 新增文案「与第 2 行重复」断言 | 收敛+加强 |
| C3 | `test_group8…` fractional 源行 / same_name 行 | status「未完成」→「未开始」（fractional 的 E2 数值替换逻辑与断言不变） | 收敛 |
| C4 | `test_group9…` | 整体重写：删除伪造 workbook 覆盖段（497-500 行），改用 `export_timeline()` 真实字节单一变量贯穿；断言按多行聚合新语义（2 项目 6 节点、语义等价、既定差异四件、R5 同名拒） | 收敛（planner 返工合同明文） |
| C5 | `test_group11…`（2 处）/ `test_excel_import…`（1 处） | fixture status「未完成」→「未开始」；断言零改动；**590 行 preview_json 注入的「未完成」保留**（tamper 守卫内容） | 收敛 |
| C6 | 全部 Excel 测试 fixture（6 处 headers 定义 + 全部数据行 + group9 表头断言 + CSV 文本） | 列序/列名换契约字面 8 列（追加项⑩；`headers.index` 动态取列位的用例自动适配） | 收敛（裁定 #6） |

未删除任何测试；未放松任何断言（C1/C2 为加强）。21 个原测试全部存留且全绿。

## D. 未关闭项（GAP-非九项；统一路由为 B-003 候选）

> D-2 / D-4 / D-5 / D-6 / D-7 全部属于 `GAP-非九项`，统一路由为 B-003 候选：不阻塞 B-002，也不代表这些缺口已经实现。下表仅保留缺口事实与后续排序依据，不授权在 B-002 内顺手修复。

| # | 项 | 说明 |
|---|---|---|
| D-2 | 组1/2/4/7 小缺口集合 | created_by 显式断言、correction 不钳制不级联断言、越界 node correction、correction 全等值 no-op、软删项目 correction/undo 404、member 撤 correction 403（B1）、M3 非空/M5 非零/红橙并存、row_index>0 重叠、interval 3650/3651 边界、batch 缺 base_version 428、部分唯一索引兜底直触、timeline 入口安全界独立负例、组 2 created_by 用例 |
| D-4 | R1「该同名项目的行全部报错」形态 | 现为首错即拒（单 row+project）；全行清单形态属预览 API（B-003）语义 |
| D-5 | 多 sheet「仅导入第一个 sheet」预览提示、陪审补丁② CSV 变形文案 | 未实现，§5 字面但不在九+1 项 |
| D-6 | 导出行序含轨道维度 | 现按 (date, 节点名自然序, id) 跨轨混排；planner 探针未列 |
| D-7 | 序列号换算按 format+整数字符串判定 | xlsx 文本存储的整数字符串亦换算（transfer 层不区分数值/文本单元格形态）；CSV 整数文本拒收。已在实现注记 |

## E. 九+1 项 → 具名测试总表（全部本 session 实跑 PASS）

| 项 | 具名测试（`test_timeline.TimelineCoreTests.<name>`） |
|---|---|
| ⑩ 表头对齐 | `test_import_headers_contract_literal` |
| 1 xlsx 序列号 | `test_import_xlsx_serial_positive_and_boundaries` |
| 2 状态三态 | `test_import_status_three_states_and_recompute` |
| 3 多行聚合 | `test_import_multirow_aggregation_and_counts` |
| 4 字段上限 | `test_import_field_limits_boundaries` |
| 5 导出边界 | `test_export_exact_1000_and_over_limit_fail_closed` |
| 6 真实字节 round-trip | `test_group9_excel_round_trip_in_new_workspace`（重写） |
| 7 迁移证据 | `test_group10_backup_content_idempotence_rollback` |
| 8 undo 证据 | `test_group4_undo_three_batch_middle_and_reverse_roles` |
| 9 coverage map | 本文件（CP3 终版） |

实现侧修复锚点（`flowboard/timeline.py`）：`IMPORT_HEADERS` 契约字面 8 列；`_parse_import_date`（序列号换算/分数/越界/CSV 拒收）；`_validate_timeline_rows`（三态+空、四键重复、NAME_CONFLICT 前置、字段上限 500/500/200、行级错误统一带 row）；`_group_import_rows` + preview/commit 聚合计数；`_validate_node`/set 路径上限 500；`_timeline_rows` 超 1000 → 422 `EXPORT_LIMIT`(total/max)；undo created/deleted 反向互换 bug 修复（E4③）。
