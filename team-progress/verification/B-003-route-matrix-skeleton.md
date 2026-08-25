# B-003 HTTP 路由矩阵独立验收骨架（planner / CP0）

> 状态：`STATIC_ONLY / NOT_SIGNED`。本文件只定义下一波动态验收标准并记录 2026-08-19 的静态发现；不签 CP0 PASS。  
> 唯一标尺：`team-task.md` §10；`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` §3–§5、§7.1。  
> 刻意不采用 coder 自述、coder coverage map 或 service 直调测试来定义 HTTP 标准。

## 0. CP0 验收硬门

- 端点集合必须严格等于下文 R01–R11：少一条、多一条、改 method、加入单项目导出或 `export project_ids` 均失败。
- 每条必须由真实 HTTP 证明：method/path/status、认证、写路由 CSRF、权限、请求/响应形状、错误 code、实际 service 接线。
- service 直调测试只能作为数据准备与底座；不能填充任一路由的 HTTP 测试槽位。
- 每条至少有一个成功用例和一个会穿过该路由的契约负例；401 的全局抽样不能替代每路由的关键 403/404/409/422/428。
- coverage 验收器必须做两项阳性对照：在隔离临时副本删除任一路由行后返回非零；把任一测试名替换为不存在名称后返回非零。不得改工作树制造对照。
- `STATIC_ONLY`、测试名仅出现在 Markdown、mock service 未由真实 HTTP 命中，均不得签 PASS。

## 1. 路径分段真值（`path.strip("/").split("/")`）

| ID | method/path | `parts` 长度 | ID 索引 | 所属 CP |
|---|---|---:|---|---|
| R01 | `GET /api/workspaces/{workspace_id}/timeline` | 4 | workspace=`parts[2]` | CP1 |
| R02 | `GET /api/timeline/projects/{project_id}` | 4 | project=`parts[3]` | CP1 |
| R03 | `GET /api/workspaces/{workspace_id}/timeline/review` | 5 | workspace=`parts[2]` | CP1 |
| R04 | `POST /api/workspaces/{workspace_id}/timeline/projects` | 5 | workspace=`parts[2]` | CP1 |
| R05 | `DELETE /api/workspaces/{workspace_id}/timeline/projects/{project_id}` | 6 | workspace=`parts[2]`; project=`parts[5]` | CP1 |
| R06 | `POST /api/workspaces/{workspace_id}/timeline/batches` | 5 | workspace=`parts[2]` | CP2 |
| R07 | `POST /api/workspaces/{workspace_id}/timeline/batches/undo` | 6 | workspace=`parts[2]` | CP2 |
| R08 | `POST /api/workspaces/{workspace_id}/timeline/batches/initial-correction` | 6 | workspace=`parts[2]` | CP2 |
| R09 | `POST /api/workspaces/{workspace_id}/timeline/imports/preview` | 6 | workspace=`parts[2]` | CP3 |
| R10 | `POST /api/workspaces/{workspace_id}/timeline/imports/commit` | 6 | workspace=`parts[2]` | CP3 |
| R11 | `POST /api/workspaces/{workspace_id}/timeline/export` | 5 | workspace=`parts[2]` | CP4 |

所有 11 路由都要求有效 session。GET 不要求 CSRF；POST/DELETE 必须带 `X-CSRF-Token`，缺失或不匹配预期 `403 CSRF_INVALID`。无 session 预期 `401 AUTH_REQUIRED`，无效 session 预期 `401 SESSION_INVALID`。

## 2. 十一路由冻结矩阵与动态信号

### R01 · workspace timeline GET

- 请求：无 body、无分页；返回全部活跃项目。
- 成功：`200 {projects:[...], server_today:"YYYY-MM-DD"}`；项目项至少含 `project_id/name/created_by/version/metrics/nodes/segments/stage_intervals`，且与写响应共用派生器。
- 权限：workspace admin/member 可读；viewer `403 PROJECT_FORBIDDEN`。
- 关键错误：`401 AUTH_REQUIRED|SESSION_INVALID`、`403 PROJECT_FORBIDDEN`。
- 成功槽位：`test_http_r01_workspace_timeline_get_200_full_shape`
- 负例槽位：`test_http_r01_workspace_timeline_get_viewer_403`
- 成功信号：真实 HTTP JSON 同时出现 `server_today` 及三类视图数组；负例信号：viewer 返回 403 且无数据泄露。

### R02 · single project GET

- 请求：无 body；路径不带 workspace，由 project 反查 membership。
- 成功：`200` 单项目视图，至少含 `nodes/segments/stage_intervals/metrics/version`。
- 权限：admin/member 可读；viewer/无 membership/顶层项目不存在统一 `403 PROJECT_FORBIDDEN`；已获授权但项目软删为 `404 PROJECT_NOT_ACTIVE`。
- 关键错误：`401 AUTH_REQUIRED|SESSION_INVALID`、`403 PROJECT_FORBIDDEN`、`404 PROJECT_NOT_ACTIVE`。
- 成功槽位：`test_http_r02_single_project_get_200_full_shape`
- 负例槽位：`test_http_r02_single_project_get_soft_deleted_404`
- 成功信号：path 中 `parts[3]` 的 project id 实际传入 `get_project`；负例信号：软删后不回退为空视图或 403。

### R03 · review GET

- 请求：可选查询 `project_ids=1,2`；缺省为全部活跃项目；不带 base_version。
- 成功：`200 {projects:[...],server_today}`。项目项严格含 `project_id/name/version/summary:{direct_edit_total}/nodes/batches/has_more`；node 含 `node_id/name/track/stage/initial_date/date/delta_days/direct_edit_count`；最近 50 条 batch 每项含 `batch_id/change_kind/trigger_source/actor:{id,name}/created_at/change_rows:[{node_id,node_name,change_role,field,old_value,new_value}]`。
- 权限：admin/member 可读；viewer `403 PROJECT_FORBIDDEN`。
- 关键错误：`401 AUTH_REQUIRED|SESSION_INVALID`、`403 PROJECT_FORBIDDEN`；非法 `project_ids` 必须是受控 4xx，不能 500。
- 成功槽位：`test_http_r03_review_get_200_exact_nested_shape`
- 负例槽位：`test_http_r03_review_get_viewer_403`
- 成功信号：真实 HTTP 同时核实 actor、change_rows、50 条截断与 `has_more`；负例信号：viewer 读被服务端挡住。

### R04 · create project POST

- 请求：仅 `{"name":"项目名称"}`；trim 后 1..200 字。
- 成功：`201 {project_id,name,created_by,version}`，created_by 必须等于当前操作者，version=1；写入 `timeline.project_created` audit。
- 权限：admin/member 可建；viewer `403 PROJECT_FORBIDDEN`；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN`、`422 NAME_CONFLICT`/字段校验。
- 成功槽位：`test_http_r04_project_create_201_created_by`
- 负例槽位：`test_http_r04_project_create_csrf_and_name_conflict`
- 成功信号：member 经 HTTP 创建并可在 R01 读取；负例信号：无 CSRF 或同 workspace 活跃同名时零写入。

### R05 · delete project DELETE

- 请求：`{"base_version":7}`；project id 必须取 `parts[5]`。
- 成功：`200 {project_id,version,deleted_at}`；仅软删项目、version+1，节点/批次保留，写 `timeline.project_deleted` audit。
- 权限：仅 workspace admin；member（含创建者）`403 ADMIN_REQUIRED`；跨路径 workspace/无权 `403 PROJECT_FORBIDDEN`；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN|ADMIN_REQUIRED`、`404 PROJECT_NOT_ACTIVE`、`409 VERSION_CONFLICT`、`428 VERSION_REQUIRED`。
- 成功槽位：`test_http_r05_project_delete_200_soft_delete`
- 负例槽位：`test_http_r05_project_delete_index_admin_version_guards`
- 成功信号：删除目标 id 等于 URL 最后一段，节点计数不减；负例信号：重复删 404、缺版本 428、错版本 409 均零写入。

### R06 · submit batches POST

- 请求：`{"requests":[{project_id,base_version,trigger_source?,details?,changes:[...]}]}`；项目≤20、每项目 changes≤200；change 白名单、interval/done_at/钳制/级联规则均按冻结 §3.1。
- 成功：`200 {results:[{project_id,batch_id?,version,view:{nodes,segments,stage_intervals,metrics},no_op?}]}`；全等值时 `no_op=true`、无 batch、version 不动。
- 权限：admin 可写全部；member 仅写 created_by=自己；viewer/他人项目 `403 PROJECT_FORBIDDEN`；软删 `404 PROJECT_NOT_ACTIVE`；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN`、`404 PROJECT_NOT_ACTIVE`、`409 VERSION_CONFLICT`（details 只列冲突项目完整视图）、`422` 行级/上限/类型、`428 VERSION_REQUIRED`。
- 成功槽位：`test_http_r06_batches_post_200_full_view`
- 负例槽位：`test_http_r06_batches_csrf_version_permission_atomicity`
- 成功信号：HTTP 返回服务端派生完整 view；负例信号：任一权限/版本/行错误使整个多项目请求零写入。

### R07 · undo batches POST

- 请求：`{"batch_ids":[118,119]}`；每个目标必须是所属项目最新批，undo 批不可再撤。
- 成功：`200 {results:[{project_id,batch_id,version,view:{nodes,segments,stage_intervals,metrics}}]}`；每项目创建 undo 批，同请求共享 undo_group，原批保留。
- 权限：admin 可撤；member 仅在项目写权限范围内可撤；目标含 initial_correction 时 member `403 ADMIN_REQUIRED`；软删项目 404；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN|ADMIN_REQUIRED`、`404 TIMELINE_BATCH_NOT_FOUND|PROJECT_NOT_ACTIVE`、`409 UNDO_TARGET_STALE`、`422` batch_ids 形状。
- 成功槽位：`test_http_r07_undo_post_200_reverse_batch`
- 负例槽位：`test_http_r07_undo_stale_admin_softdelete_zero_write`
- 成功信号：反向变更、version+1、完整 view 经 HTTP 可见；负例信号：三连批撤中间、撤 undo 批、任一无效目标全部零写入。

### R08 · initial-correction POST

- 请求：`{"project_id":3,"base_version":8,"corrections":[{"node_id":41,"initial_date":"YYYY-MM-DD"}]}`，1..200 行。
- 成功：`200 {results:[{project_id,batch_id?,version,view:{nodes,segments,stage_intervals,metrics},no_op?}]}`；只改 initial_date，不钳制、不级联、不改 date；全等值为 no-op。
- 权限：仅 workspace admin；member/viewer `403 ADMIN_REQUIRED|PROJECT_FORBIDDEN`；软删 404；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN|ADMIN_REQUIRED`、`404 PROJECT_NOT_ACTIVE`、`409 VERSION_CONFLICT`、`422` 重复/越界 node/字段/日期、`428 VERSION_REQUIRED`。
- 成功槽位：`test_http_r08_initial_correction_200_no_clamp_cascade`
- 负例槽位：`test_http_r08_initial_correction_admin_node_version_guards`
- 成功信号：自由日期原样写入且 current date 不变；负例信号：member、越界 node、软删、缺/错版本全部零写入。

### R09 · import preview POST

- 请求：`{"filename":"timeline.xlsx","content_base64":"..."}`；路由层必须可调用实际导入的文本 helper 并以严格 base64 解码为 bytes，再传 `preview_import(user,workspace_id,filename,raw)`。
- 成功：`201 {batch_id,format,row_count,projects:[...],warnings:[...]}`；warnings 含“状态将按日期重算，仅『已完成』保留”，多 sheet 另提示只导入第一个 sheet。
- 权限：admin/member 可用；viewer `403 PROJECT_FORBIDDEN`；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN`、`422 IMPORT_HEADERS_MISMATCH`、行级 422（details 带 row/header）、非法 base64/文件受控 422。
- 成功槽位：`test_http_r09_import_preview_201_base64_helper_shape`
- 负例槽位：`test_http_r09_import_preview_headers_rows_and_csv_warnings`
- 成功信号：合法 base64 不触发 NameError/500，batch 持久化后可供 R10 使用；负例信号：表头/同名全行/数值日期/多 sheet 与 CSV 提示均经 HTTP 观察。

### R10 · import commit POST

- 请求：仅 `{"batch_id":123}`；不接收 project base_version、sha256 或原文件。
- 成功：`201` commit 确认（至少可识别 batch_id 及本次创建的项目/节点数量）；每项目建立 import 批，状态条件迁移为 committed。
- 权限：admin/member 可提交本人、当前 workspace 的 preview；viewer 403；必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN`、`404 TIMELINE_IMPORT_BATCH_NOT_FOUND`、`409 TIMELINE_IMPORT_ALREADY_COMMITTED`、`422` commit 时名称/行规则重校验失败。
- 成功槽位：`test_http_r10_import_commit_201_preview_journey`
- 负例槽位：`test_http_r10_import_commit_scope_replay_race_zero_write`
- 成功信号：R09→R10 全程真实 HTTP 且新项目可由 R01 读到；负例信号：查无、跨操作者、重复、preview 后同名竞态按专属 code 零写入。

### R11 · workspace export POST

- 请求：workspace 全量导出；不得使用 GET，不得接收单项目 id 或 `project_ids` 扩展。空 JSON 对象可作为 HTTP 载体。
- 成功：`200 application/json`，至少含 `content_base64` 与 `sha256`（允许同时返回 filename/media_type/format/row_count/headers 元数据）；`sha256 == sha256(base64_decode(content_base64))`。
- 字节契约：解码后为可解析 8 列单 sheet xlsx；≤1000 行；项目→轨道→日期→节点名自然序→id；导出物可在新 workspace 经 R09→R10 再导入。
- 权限：admin/member 可导出；viewer `403 PROJECT_FORBIDDEN`；作为 POST 必须校验 CSRF。
- 关键错误：`401`、`403 CSRF_INVALID|PROJECT_FORBIDDEN`、`422 EXPORT_LIMIT`；`GET` 必须非 200（当前 dispatcher 惯例可为 `404 NOT_FOUND`）。
- 成功槽位：`test_http_r11_export_post_200_base64_sha256_roundtrip`
- 负例槽位：`test_http_r11_export_rejects_get_project_ids_viewer_and_limit`
- 成功信号：响应不是裸 xlsx，hash 对解码字节成立且可解析/再导入；负例信号：GET、viewer、超限、单项目/project_ids 入口均不能形成成功扩展。

## 3. 跨路由独立验收波次

### CP0 · coverage map 验收器

1. 从冻结端点集合构造 11 个 `(method,path-pattern)` 键，要求与被验 map 精确相等。
2. 对每键核实 method/path/status/request/response/auth/CSRF/permissions/error/service/test 名字段非空。
3. 通过 Python unittest discovery/loader 或等价静态 AST 读取真实 test method；仅 Markdown 字符串不算存在。
4. 在 `%TEMP%/flowboard-b003-map-control-*` 复制被验 map：删除 R02（或任一随机路由）后，验收器必须非零并报告 `ROUTE_MISSING`。
5. 在另一临时副本把 R11 成功测试名改为不存在名，验收器必须非零并报告 `TEST_NOT_FOUND`。
6. 两项阳性对照只改临时副本，结束后清理；工作树、真实数据库、`.copilot-*` 不动。

建议具名槽位：

- `test_b003_coverage_exactly_eleven_frozen_routes`
- `test_b003_coverage_control_missing_route_fails`
- `test_b003_coverage_control_fake_test_name_fails`

### CP1–CP4 · 动态 HTTP

- CP1：R01–R05；特别锁 R02 单项目 GET、R03 完整 review、R05 `len=6/project=parts[5]`。
- CP2：R06–R08；每路由 CSRF、版本、权限、软删、零写入，并验证写响应完整视图。
- CP3：R09–R10；preview helper/base64 接线与真实 preview→commit 旅程；仅跑共享 transfer 定向回归。
- CP4：R11；POST JSON、base64/sha256、xlsx 可解析、自然序、再导入。

### CP5 · 同盘独立关门

- 同一隔离数据库复跑 11/11 成功路径；所有 8 条写路由（R04/R05/R06/R07/R08/R09/R10/R11）逐条做缺 CSRF 403，不得漏测。
- 抽查跨路径 workspace、viewer、member 写他人项目、admin-only、软删、版本冲突、undo stale、导入 replay/竞态、导出错误 method。
- 对所有声明零写入的 4xx 前后比较项目/节点/批次/change/import/audit 的计数与目标行内容；只比总计数不足以证明 UPDATE 零发生。
- 真实 `flowboard.db` 的 size/mtime/sha256（若文件存在）在波次前后必须不变；`.copilot-*` 保持只读冻结。

## 4. 隔离临时库与随机端口策略

- 每个测试类或每个原子性场景使用 `tempfile.TemporaryDirectory(prefix="flowboard-b003-http-")`，数据库固定为该目录下 `flowboard.db`；禁止把 repo 根 `flowboard.db` 传给 server/service。
- 以 `create_server("127.0.0.1", 0, temp_db)` 启动，端口只从 `server.server_address[1]` 读取；禁止硬编码 8080 或探测后再绑定造成竞态。
- 后台线程 `serve_forever`; `finally` 中依次 `shutdown()`、`server_close()`、`thread.join(timeout=...)`、清理 TemporaryDirectory。
- 所有身份均经真实 `/api/auth/login` 获取 cookie 与 csrf；至少准备 admin、项目 owner member、非 owner member、viewer 四种身份。
- HTTP helper 必须保留 status、响应 headers、原始 bytes；仅在 `application/json` 时解 JSON。R11 必须从 JSON 的 base64 字段取得字节。
- 每个关键负例在请求前保存表计数 + 目标行 version/deleted_at/date/initial_date 等快照，请求后复核；不要依赖后续测试顺序。
- 导入/导出文件只放临时目录/内存；使用唯一项目名，R11 往返导入到全新 workspace，避免 R1 同名规则误报。

## 5. B-002 §D 遗留归属（不得混记）

| 遗留 | 纳入 CP | HTTP 关门信号 |
|---|---|---|
| D-2 `created_by` | CP1/R04 | member/admin 创建后响应及 R01 均显示当前操作者；通用写不得改 |
| D-2 correction 不钳制、不级联、no-op、越界 node | CP2/R08 | HTTP 原样自由 initial_date；date/相邻节点不变；全等值零批次；越界 422 |
| D-2 软删 correction/undo 404 | CP2/R07–R08 | `PROJECT_NOT_ACTIVE` 且零写入 |
| D-2 member 撤 initial-correction 403 | CP2/R07 | `ADMIN_REQUIRED` 且零写入 |
| D-2 M3/M5、红橙指标、重叠 row_index | CP1/R01–R03 为主，CP2/R06–R08 写后复核 | 三类 HTTP view 由同一派生器返回，索引/指标稳定一致 |
| D-2 interval 3650/3651 | CP2/R06 | 3650 成功，3651 为行级 422 |
| D-2 缺版本 428 | CP1/R05 + CP2/R06/R08 | 三路由均 `VERSION_REQUIRED` 且零写入 |
| D-2 timeline 认证/权限安全界 | CP1–CP4 分路由，CP5 总复跑 | 401/CSRF/viewer/member/admin/路径 workspace 均由服务端执行 |
| D-4 同名项目所有行报错 | CP3/R09–R10 | preview 行级清单覆盖该项目每一行；不得 commit；竞态重校验 422 |
| D-5 多 sheet/CSV 提示 | CP3/R09 | warnings/错误文案经 HTTP 可观察 |
| D-7 xlsx 数值单元格类型 | CP3/R09 | 整数序列号换算；非整数序列号行级 422 |
| D-6 项目→轨道→日期→节点名自然序→id | CP4/R11 | 解码 xlsx 后逐行断言稳定自然序 |

明确后置且本包不得假记 PASS：

- 部分唯一索引兜底的数据库直触：backend/data follow-up。
- UI、真实浏览器事件序、视觉交互：B-004。
- 全量历史回归、文档总收口、Gate 5 交接：B-005。
- PATCH 改名/恢复、单项目导出、export `project_ids`、分页、缓存：禁止扩展，不是后置验收项。

## 6. 2026-08-19 当前工作树静态发现（不等于动态结论）

以下只来自对当前 `server.py` / `flowboard/timeline.py` 的只读核实；它们是下一棒修正/验证入口，不构成任何 CP 签注：

1. R02 单项目 GET：`TimelineService.get_project` 已存在，但 `server.py` 当前没有 `/api/timeline/projects/{id}` 分支，HTTP 不可达。
2. R05 DELETE：分支长度 6 正确，但当前读取 `int(parts[4])`；该段字面为 `projects`，正确 project id 是 `parts[5]`。现状会落受控 422 而非删除目标项目。
3. R07/R08/R09/R10：实际路径均为 6 段，当前分支写成 `len(parts)==5`，条件不可命中。
4. R09 preview：分支调用 `require_text`，但 `server.py` 当前只从 service 导入 `ApiError/FlowboardService/require_object`；即使先修长度，合法请求也会因 helper 未导入而 500。
5. R11 export：当前仍是 GET + 可选 `project_ids` + 裸 xlsx 响应；冻结要求 POST + workspace 全量 + JSON `content_base64/sha256`，且 POST 必须走统一 CSRF。
6. R03 review 路由的长度/索引静态正确；但当前 review service 的 `batches[]` 返回 `details/change_count`，没有冻结要求的 `actor{id,name}` 与逐行 `change_rows[]`，响应形状尚未闭合。
7. R01/R04/R06 的分段条件静态与路径真值相符；这只说明条件可命中，不证明 status、权限、原子性或响应契约通过。

因此当前只能标记 `STATIC_GAPS_FOUND`，必须等待实现后在隔离临时库、随机端口下跑完对应具名 HTTP 测试与 planner 独立负例，才允许逐 CP 签注。
