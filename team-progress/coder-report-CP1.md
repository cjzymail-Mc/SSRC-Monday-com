# coder-report-CP1（B-002 项 1–5 + 项 6 + 追加项⑩）· 2026-08-19

## 1. 检查点与 done_when 映射

- CP1 计划面=项 1（xlsx 序列号）/2（状态三态）/3（多行聚合）/4（字段上限）/5（导出边界）；实际交付含项 6（真实字节 round-trip，随 group-9 重写一并落地）与追加项⑩（表头对齐，lead 裁决 #6 并入）。
- 对应 B-002 关闭判据：每项=具名测试 + 动态 PASS + 负例真跑真失败（见 §3）。

## 2. 实际改动

### flowboard/timeline.py（7 处）

1. `IMPORT_HEADERS` → 契约字面 8 列 `["项目名称","阶段","轨道","节点","日期","间隔","状态","备注"]`（项⑩；导入导出同源）。
2. 新增 `_parse_import_date(value, row, file_format)`：文本 YYYY-MM-DD 严格历法；xlsx 整数字符串 18264..73051 按 1899-12-30 基准换算；分数/越界/CSV 整数文本 422 带 row（项 1）。
3. `_validate_timeline_rows` 重写：校验顺序 project(≤200) → 库内 NAME_CONFLICT → track → stage → name(≤500) → date → status(三态+空) → remark(≤500) → 文件内四键重复（第二行起 422 带首次行号）；字段级 422 统一补 `details={"row": n}`（项 1/2/3/4；校验顺序设计保证 group-8 既有断言语义不变）。
4. 新增 `_group_import_rows`；`preview_import` projects 列聚合后实际节点数；`commit_import` 按项目分组创建、返回去重项目数+总节点数（项 3）。
5. `_validate_node` 与 batch set 路径 name/remark 上限 200/2000 → 500/500（项 4）。
6. `_timeline_rows` 行内容换契约列序；尾部 `rows[:1000]` 静默截断 → 超 1000 抛 422 `EXPORT_LIMIT` `{"total": n, "max": 1000}`（项 5；lead 点名处 timeline.py:720，已排查全文件与 server.py 接入侧无其他同类截断——review LIMIT 51/[:50] 为 B5b 契约明示分页）。
7. MISMATCH 报错文案附标准表头（项⑩③）。

### tests/test_timeline.py

- 新增 6 测：`test_import_headers_contract_literal`（⑩）、`test_import_xlsx_serial_positive_and_boundaries`（1）、`test_import_status_three_states_and_recompute`（2）、`test_import_multirow_aggregation_and_counts`（3）、`test_import_field_limits_boundaries`（4）、`test_export_exact_1000_and_over_limit_fail_closed`（5）；重写 `test_group9_excel_round_trip_in_new_workspace`（6）。
- 按 #4/#6 裁定的现有测试收敛修改：**逐条清单见 `B-002-coverage-map.md` §C（C1–C6）**，要点：未完成→未开始合法化 8 处 + 「未完成」反造为 422 锋利负例（cases 新增「非法状态旧值」）；duplicate 用例改真四键重复（断言结构不变+文案断言加强）；group-9 伪造 workbook 段删除改真实字节；全部 Excel fixture 列序换契约字面；`details==None` 断言 → `details["row"]==2`（加强）；590 行 tamper 注入保留原值（守卫不弱化）。

## 3. 实际验证与证据（本 session 实跑）

- 15:51 中途回归 21/21（裁定内修改+项 1–5 实现后）；15:56–16:08 多次全量 **29/29 OK**（21 存留 + 8 新增；命令 `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`）。
- 负例真跑点（对齐验收手册）：18263/73052/46234.5/CSV 整数各 422 row=2；「未完成」422；四键重复 422 row/duplicate_of+文案；501/201 六方向；1001 行 422 `EXPORT_LIMIT` `details=={"total":1001,"max":1000}`（1000 行经服务端 5×200 create 真实构造，导出物在新 workspace 导回 (5,1000)）；round-trip `raw` 单变量贯穿无二次构造，最难样本（双项目/双轨/三态/跨 3 月/500 字节点名）。
- 期望值独立预计算：序列号用 `datetime(1899,12,30)+timedelta(days=n)` 测试内自算；状态重算期望按 view 的 server_today 独立推导；不 import 实现换算函数。

## 4. 纠偏三问

1. 服务 CP1 六项（1/2/3/4/5/6/⑩）的 done_when。
2. 是否偷偷扩范围：**一处交叠披露**——「行级错误统一带 row details」落在 mc-expert 陪审要点项 1（「float cell 422 且 details 带 row」）/项 3（「错误断言必须带 code/details 区分拒收理由」）的验收判据 与 lead 隔离裁定 #7 原列 OPEN-3（字段级 row details）的交叠区。实现取统一包装（所有字段级 422 带 row，方向=加强、贴 §5.2 字面），连带 C1 断言 `details==None`→`details["row"]==2`（加强非放松）。若 lead/planner 判定越界，回滚方案=仅日期/status 列带 row+恢复 cases 原断言（一处可改）。其余 OPEN-2…7 均未触碰。
3. 实现/文档/证据一致：map §E/§B 状态=实测；本报告 diff 清单与工作树一致。

## 5. 三清单

- 自主裁决（本 CP 新增）：AD-1 上述 row details 交叠区处置（保持+披露+可回滚）。AD-2 删除自造 flaky 断言（group9 曾加「两次 export sha256 相等」——make_xlsx zip 条目含 DOS 时间戳（2 秒粒度），跨窗时两次导出字节合法地不同，该断言非契约判据且有间歇失败风险，已删；「真实字节」由单变量贯穿+parse 结构断言保证，planner 侧 sha256 比对不受影响）。
- OPEN_BLOCKERS：无。
- PENDING_HUMAN_NONBLOCKING：无新增（OPEN-2…7 由 lead 隔离为 B-003 候选，未动）。
