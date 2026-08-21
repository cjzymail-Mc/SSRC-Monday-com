# B-003 coverage map（CP0 缺口快照 + CP5 终态收口）

> 盘点日期：2026-08-19
> 外部真相：`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` §3–§5、§7.1；执行边界：`team-task.md` §10。
> 本文件只登记静态事实与后续验收路由，不代表任何端点已通过动态 HTTP 验收。service 直调测试不计 HTTP 证据。

## A. 证据盘面与状态口径

本 map 绑定以下快照；文件内容变化后必须重做受影响行，不能沿用本结论：

| 证据 | SHA256 |
|---|---|
| `server.py` | `8bed2b95119aa479b99f34d4727ed558a331c48fa860360e8064fcdbb09b242c` |
| `flowboard/timeline.py` | `c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b` |
| `tests/test_timeline.py` | `8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf` |
| `feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` | `4a83bfecf75b05c5bdbdc26d41dca7710e2e7867bc590a6a5027fa9fae901070` |
| `team-task.md` | `c35287e9ddb6c84d5b9eda7e55d4466baca0a412a450bef96cb95961c71e99ab` |

状态定义：

- `PASS`：静态接线、冻结形状及具名 HTTP 证据均已存在；仍不代替 planner 动态签注。
- `GAP-B003`：冻结能力缺失或缺具名 HTTP 证据，且未发现相反实现。
- `CONFLICT`：现有接线或响应形状与冻结契约直接相反。
- `OUT-OF-SCOPE`：明确属于 B-004/B-005/backend-data follow-up，不得在 B-003 假记 PASS。

认证/CSRF 的共同静态事实：`Handler.dispatch` 在所有非公开 API 路由匹配前调用 `current_user`；GET 只认证，POST/PATCH/DELETE 同时校验 `X-CSRF-Token`。因此冻结写路由按机制应有 401 `AUTH_REQUIRED`/`SESSION_INVALID` 与 403 `CSRF_INVALID`，但除路由 1 的未登录 401 外，当前没有 timeline 具名 HTTP 测试证明这些分支。不存在或 method 错误的路由即使先经过认证/CSRF，仍不能视为端点已接通。

## B. 11/11 冻结路由矩阵（CP0 原始快照，保留作发现轨迹）

| # | method | path | 冻结成功状态 | 请求形状 | 冻结响应形状 | 认证 / CSRF | 权限与关键错误码 | 当前 `server.py` 接线 | `TimelineService` 公开签名 / 当前返回 | 当前具名 HTTP 测试 | 状态 | 后续 CP |
|---:|---|---|---:|---|---|---|---|---|---|---|---|---|
| 1 | GET | `/api/workspaces/{id}/timeline` | 200 | 无 body；v1 缺省返回全部活跃项目，不分页 | `{projects:[{project_id,name,created_by,version,metrics,nodes,segments,stage_intervals}],server_today}` | 认证；无 CSRF | admin/member 可读；viewer/非成员 403 `PROJECT_FORBIDDEN`；未登录 401 | `server.py:167-168` 正确命中 `len=4`，调用 `list_projects(user, workspace_id)` | `list_projects(self,user,workspace_id)`；当前形状基本同冻结，项目 view 额外含 `server_today` | `TimelineCoreTests.test_group1_unauthenticated_http_401`，**只证 401** | `GAP-B003`：缺 200、viewer 403、形状的真实 HTTP 证据 | CP1 |
| 2 | GET | `/api/timeline/projects/{id}` | 200 | 无 body | 单项目 view：至少含 `project_id/name/created_by/version/nodes/segments/stage_intervals/metrics` | 认证；无 CSRF | membership 反查；viewer/不可见 403 `PROJECT_FORBIDDEN`；软删 404 `PROJECT_NOT_ACTIVE`；未登录 401 | **无匹配分支**；认证用户落通用 404 `NOT_FOUND` | `get_project(self,user,project_id)` 已存在并返回 `_view` | 无；现有 `test_project_create_then_batch_nodes_and_derived_view` 等均为 service 直调 | `GAP-B003`：HTTP 路由缺失 | CP1 |
| 3 | GET | `/api/workspaces/{id}/timeline/review` | 200 | 可选 query `project_ids=1,2`；无 body | `{projects:[{project_id,name,version,summary:{direct_edit_total},nodes:[...],batches:[{batch_id,change_kind,trigger_source,actor:{id,name},created_at,change_rows:[...]}],has_more}],server_today}`；每项目最近 50 批 | 认证；无 CSRF | admin/member 可读；viewer 403 `PROJECT_FORBIDDEN`；未登录 401 | `server.py:177-179` 路径/方法可达，逗号分隔参数转 int 后调用 `review` | `review(self,user,workspace_id,project_ids=None)`；当前 `batches[]` 是 `details+change_count`，**缺 `actor` 与 `change_rows`** | 无 | `CONFLICT`：当前响应与冻结形状直接不一致，且无 HTTP 证据 | CP1 |
| 4 | POST | `/api/workspaces/{id}/timeline/projects` | 201 | 仅 `{"name":"项目名称"}`；trim 后 1..200 | `{project_id,name,created_by,version}` | 认证 + CSRF | admin/member 可建；viewer 403；同名活跃项目 422 `NAME_CONFLICT` | `server.py:191-192` 可达，调用 `create_project(user,workspace_id,data)` | `create_project(self,user,workspace_id,data)`；当前返回与冻结同形并写 audit | 无；创建/created_by 测试均为 service 直调 | `GAP-B003`：缺 HTTP 正例、CSRF、viewer/同名负例 | CP1 |
| 5 | DELETE | `/api/workspaces/{id}/timeline/projects/{project_id}` | 200 | `{"base_version":7}` | `{project_id,version,deleted_at}` | 认证 + CSRF | 仅 admin；非 admin 403 `ADMIN_REQUIRED`；不可见 403；软删/重复删 404；冲突 409；缺版本 428 | `server.py:175-176` 的 `len=6`/前缀正确，但把 `parts[4]`（字面 `projects`）转 int；合法请求在到达 service 前变成 422 `VALIDATION_ERROR`，应取 `parts[5]` | `delete_project(self,user,workspace_id,project_id,data)`；service 形状/软删逻辑存在 | 无 | `CONFLICT`：现有路由索引必错 | CP1 |
| 6 | POST | `/api/workspaces/{id}/timeline/batches` | 200 | `{"requests":[{project_id,base_version,trigger_source?,details?,changes:[...]}]}`，1..20 项目、每项目 1..200 行 | `{results:[{project_id,batch_id?,version,no_op?,view:{nodes,segments,stage_intervals,metrics}}]}`；冲突 409 details 只列冲突项目完整 view | 认证 + CSRF | 每项目 write/active；403 `PROJECT_FORBIDDEN`、404 `PROJECT_NOT_ACTIVE`、409 `VERSION_CONFLICT`、422 行级/上限、428 `VERSION_REQUIRED` | `server.py:169-170` 可达并透传 `data` | `submit_batches(self,user,workspace_id,data)`；当前公开签名与主返回同形 | 无；所有 batch 测试均为 service 直调 | `GAP-B003`：缺 HTTP 正例与 CSRF/权限/版本/原子性负例 | CP2 |
| 7 | POST | `/api/workspaces/{id}/timeline/batches/undo` | 200 | `{"batch_ids":[118,119]}` | `{results:[{project_id,batch_id,version,view}]}` | 认证 + CSRF | write/active；含 initial-correction 时仅 admin；403 `PROJECT_FORBIDDEN`/`ADMIN_REQUIRED`、404 `TIMELINE_BATCH_NOT_FOUND`/`PROJECT_NOT_ACTIVE`、409 `UNDO_TARGET_STALE` | `server.py:171-172` 写成 `len(parts)==5`，实际路径是 **6 段**，分支不可达；认证后落 404 | `undo_batches(self,user,workspace_id,data)` 已存在并返回 results | 无；undo 测试均为 service 直调 | `GAP-B003`：路由长度缺口 + 全套 HTTP 证据缺失 | CP2 |
| 8 | POST | `/api/workspaces/{id}/timeline/batches/initial-correction` | 200 | `{project_id,base_version,corrections:[{node_id,initial_date}]}`，1..200 | 非等值 `{results:[{project_id,batch_id,version,view}]}`；全等值同形并 `no_op:true` | 认证 + CSRF | 仅 workspace admin；403 `ADMIN_REQUIRED`/`PROJECT_FORBIDDEN`、404 `PROJECT_NOT_ACTIVE`、409 `VERSION_CONFLICT`、422 行级、428 `VERSION_REQUIRED` | `server.py:173-174` 同样写成 `len==5`，实际 **6 段**，分支不可达 | `initial_correction(self,user,workspace_id,data)` 已存在 | 无；correction 测试均为 service 直调 | `GAP-B003`：路由长度缺口 + D-2 HTTP 观察证据缺失 | CP2 |
| 9 | POST | `/api/workspaces/{id}/timeline/imports/preview` | 201 | `{filename,content_base64}` | `{batch_id,format,row_count,projects:[...],warnings:[...]}`；错误为完整行级清单，有错不可提交 | 认证 + CSRF | admin/member；viewer 403；文件/表头/行规则 422（表头 `IMPORT_HEADERS_MISMATCH`）；安全上限含文件 1.5MB/1000 行 | `server.py:180-185` 写成 `len==5`，实际 **6 段**；且分支内使用未从 `flowboard.service` 导入的 `require_text`，即使只修长度也会 NameError | `preview_import(self,user,workspace_id,filename,raw)`；当前同名项目首错即停；warnings 只有状态重算提示；共享 transfer 丢失 xlsx 数值/文本类型差异 | 无；import 测试均为 service 直调 | `CONFLICT`：不可达，且 D-4/D-5/D-7 与冻结字面相反 | CP3 |
| 10 | POST | `/api/workspaces/{id}/timeline/imports/commit` | 201 | 仅 `{"batch_id":123}` | `{batch_id,projects,nodes}` | 认证 + CSRF | admin/member；查无/非本人/跨 workspace 404 `TIMELINE_IMPORT_BATCH_NOT_FOUND`；已提交 409；重校验失败 422；viewer 403 | `server.py:186-187` 写成 `len==5`，实际 **6 段**，分支不可达 | `commit_import(self,user,workspace_id,data)`；当前按 workspace+created_by 取批，但未独立重查当前 membership/viewer 状态 | 无；two-phase 测试为 service 直调 | `GAP-B003`：路由长度、HTTP 旅程及 commit 权限复核待补 | CP3 |
| 11 | POST | `/api/workspaces/{id}/timeline/export` | 200 | workspace 全量导出；不接受单项目或 `project_ids` 扩展（可用空对象作为 POST body） | JSON 至少含可解码 `content_base64` 与匹配的 `sha256`；字节为 8 列单 sheet xlsx，最多 1000 行 | 认证 + CSRF | workspace admin/member；viewer 403；超 1000 行 422 `EXPORT_LIMIT` | 现有分支是 **GET**（`server.py:188-190`），接受 `project_ids`，写原始附件响应；还以第三个业务参数 `selected` 调 service，运行时签名不匹配导致 500 | `export_timeline(self,user,workspace_id)` 仅返回 xlsx bytes；没有 JSON/base64/sha256 envelope；`_timeline_rows` 行序缺 track 维度 | 无；export/round-trip 测试均为 service 直调 | `CONFLICT`：method、扩展范围、调用签名、响应形状和 D-6 均冲突 | CP4 |

静态汇总：`PASS=0`、`GAP-B003=7`、`CONFLICT=4`、`OUT-OF-SCOPE=0`，合计 11。这里的零 PASS 只表示没有任何一路同时具备完整静态契约与具名 HTTP 证据，不否认 service 层已有大量可复用底座。

## C. B-002 §D 唯一归属（不得重复计数）

| 原项 | 去重后的可观察验收点 | 唯一归属 | 主要路由 | 备注 |
|---|---|---|---|---|
| D-2 | `created_by` 系统写入且经读取返回（原“组2 created_by 用例”并入同一项） | CP1 | 1/2/4 | 只算一次，不另建重复测试债 |
| D-2 | M3 非空、M5 非零、红橙指标并存 | CP1 | 1/2 | 通过真实 GET 响应观察 metrics |
| D-2 | 重叠阶段的 `row_index>0` | CP1 | 1/2 | 通过真实 GET 响应观察 `stage_intervals` |
| D-2 | timeline 入口认证/权限安全界独立负例 | CP1 | 1/2/3 | 401 + viewer/不可见 403；不以通用机制静态推断代替 |
| D-2 | correction 不钳制、不级联、不改 current date；越界 node 422；全等值 no-op | CP2 | 8 | 同一 initial-correction HTTP 组关闭 |
| D-2 | 软删项目 correction/undo 404、member 撤 initial-correction 403 | CP2 | 7/8 | 必须同时断言零写入 |
| D-2 | `interval_days` 3650 接受、3651 拒绝 | CP2 | 6 | 单一边界测试对 |
| D-2 | batch 缺 `base_version` → 428 | CP2 | 6 | correction/delete 的各自 428 属本路由常规负例，不重复冒充本遗留项 |
| D-4 | 同名已有项目的**所有行**进入错误清单 | CP3 | 9 | 不接受当前首错即停形态 |
| D-5 | 多 sheet 提示“仅导入第一个 sheet”；CSV 日期变形提示改用 xlsx | CP3 | 9 | 两条均在 preview 的 warnings/error 文案观察 |
| D-7 | xlsx 只对数值单元格作序列号换算；文本整数字符串不换算 | CP3 | 9 | 共享 transfer 只做必要定向回归 |
| D-6 | 导出行序项目→轨道→日期→节点名自然序→id | CP4 | 11 | 从解码后的真实 xlsx 行序观察 |
| D-2 | 部分唯一索引兜底直触 | **backend/data follow-up（B-003 后置）** | — | 数据库直触，不是 HTTP 黑盒；明确不得在 CP0–CP5 记 PASS |

UI、真实浏览器事件序和视觉交互属于 B-004；全量历史回归、文档总收口和 Gate 5 交接属于 B-005。它们未进入上表 11 路由状态统计。

## D. 各 CP 最小缺口清单

- **CP1（1–5）**：补单项目 GET；修 DELETE `parts[5]`；补 review 的 `actor/change_rows`；为 1–5 建真实 HTTP 正例及各自关键 401/403/404/409/428；关闭本文件 C 表分配给 CP1 的 D-2 项。
- **CP2（6–8）**：修 undo/initial-correction 路径长度；建立三条写路由的 HTTP 正例、CSRF、权限、软删、版本与零写入负例；关闭 CP2 的 D-2 项。
- **CP3（9–10）**：修两条 imports 的路径长度与 preview `require_text` 引用；完成 preview→commit HTTP 旅程和 commit 时权限复核；只在必要范围关闭 D-4/D-5/D-7。
- **CP4（11）**：将 export 收敛为严格 POST workspace 全量；返回 base64+sha256 JSON；真实字节解码、解析、再导入，并关闭 D-6。
- **CP5（独立关门）**：planner 对同一冻结盘面复跑 11/11、全部写路由 CSRF 和代表性权限/原子性负例；任何 `STATIC_ONLY` 都不能关门。

## E. CP0 独立验收接口

planner 应至少验证：

1. 本文件恰有 11 个冻结端点，method/path 与 `team-task.md` §10.1 完全一致且无扩展项。
2. 每行均有冻结成功状态、请求/响应、认证/CSRF、权限/错误、server 接线、service 签名、具名 HTTP 测试、四态与唯一后续 CP。
3. 所列具名测试真实存在；当前只有 `TimelineCoreTests.test_group1_unauthenticated_http_401` 可计 timeline HTTP 证据。
4. 在验收器的临时输入中删除任一路由，必须失败；把上述测试名替换成不存在的名字，必须失败。阳性对照只能在临时输入/内存中做，不改本文件和测试。

本文件作者不宣称 CP0 已通过 planner 验收。

## F. CP5 终态覆盖（2026-08-20）

本节是终态真值；B、C、D、E 节保留 CP0 发现与施工分派原貌，不回写抹除历史。以下 PASS 均引用 planner 独立真实 HTTP 报告，coder 不冒充签注者。

| 路由 | 终态 | 真实具名 HTTP 测试 | planner 独立验收 |
|---|---|---|---|
| R01 `GET /api/workspaces/{id}/timeline` | PASS | `TimelineHTTPTests.test_r01_r02_list_and_single_get_auth_permissions_and_shapes` | `planner-report-B003-CP1.md`；CP5 同盘 200 |
| R02 `GET /api/timeline/projects/{id}` | PASS | `TimelineHTTPTests.test_r01_r02_list_and_single_get_auth_permissions_and_shapes` | `planner-report-B003-CP1.md`；CP5 同盘 200 |
| R03 `GET /api/workspaces/{id}/timeline/review` | PASS | `TimelineHTTPTests.test_r03_review_actor_change_rows_metrics_and_overlap_rows` | `planner-report-B003-CP1.md`；CP5 同盘 200 |
| R04 `POST /api/workspaces/{id}/timeline/projects` | PASS | `TimelineHTTPTests.test_r04_create_lifecycle_conflict_csrf_and_viewer` | `planner-report-B003-CP1.md`；CP5 201、CSRF 403/零写 |
| R05 `DELETE /api/workspaces/{id}/timeline/projects/{project_id}` | PASS | `TimelineHTTPTests.test_r05_delete_path_version_admin_soft_delete_and_repeat` | `planner-report-B003-CP1.md`；CP5 200、CSRF 403/零写 |
| R06 `POST /api/workspaces/{id}/timeline/batches` | PASS | `TimelineHTTPTests.test_r06_batch_http_complete_view_csrf_version_atomic_and_interval_bounds` | `planner-report-B003-CP2.md`；CP5 200、CSRF 403/零写 |
| R07 `POST /api/workspaces/{id}/timeline/batches/undo` | PASS | `TimelineHTTPTests.test_r07_undo_http_success_csrf_stale_soft_delete_and_zero_write` | `planner-report-B003-CP2.md`；CP5 200、CSRF 403/零写 |
| R08 `POST /api/workspaces/{id}/timeline/batches/initial-correction` | PASS | `TimelineHTTPTests.test_r08_initial_correction_http_noop_no_cascade_permissions_and_invalid_node` | `planner-report-B003-CP2.md`；CP5 200、CSRF 403/零写 |
| R09 `POST /api/workspaces/{id}/timeline/imports/preview` | PASS | `TimelineHTTPTests.test_r09_r10_import_http_preview_commit_permissions_state_and_race`；`TimelineHTTPTests.test_r09_import_d4_d5_d7_error_rows_warnings_and_cell_types` | `planner-report-B003-CP3.md`；CP5 201、CSRF 403/零写 |
| R10 `POST /api/workspaces/{id}/timeline/imports/commit` | PASS | `TimelineHTTPTests.test_r09_r10_import_http_preview_commit_permissions_state_and_race` | `planner-report-B003-CP3.md`；CP5 201、CSRF 403/零写 |
| R11 `POST /api/workspaces/{id}/timeline/export` | PASS | `TimelineHTTPTests.test_r11_export_post_json_order_permissions_and_round_trip` | `planner-report-B003-CP4.md`；CP5 200 JSON/base64/sha256、CSRF 403/零写 |

终态汇总：`PASS=11`、`GAP-B003=0`、`CONFLICT=0`。CP1–CP4 已签 D-2/D-4/D-5/D-6/D-7 的 HTTP 可观察部分，并由 `planner-report-B003-CP5.md` 全矩阵复跑保持 PASS。独立证据脚本与全文位于 `team-progress/verification/B-003-CP1/` 至 `B-003-CP5/`。

### F.1 明确后置、未在 B-003 假记关闭

- 部分唯一索引数据库直触：backend/data follow-up。
- 可操作 UI、真实浏览器事件、视觉交互：B-004。
- 全量历史回归、文档总收口、Gate 5 交接：B-005。

### F.2 终态文件指纹

- `server.py`: `509862B60E8DB7FAB23F61CC8B67C7E39F87A7148D46C77C489EFFECC9621FD8`
- `flowboard/timeline.py`: `D68FA1BD3797263FEAFDA75BD508F86BFCCB73D603E81681A9AB1D878357A8D5`
- `flowboard/transfer.py`: `5364288E96A5ED16133471F5F02742DD8CCA258E7E6D1B7EF5B6311DB96CBC9E`
- `tests/test_timeline_http.py`: `A8F95CEC755CC9C6CFA79820EA3A2774A9C5FC0F2755CC234622EC9FCF41D432`
- `tests/test_timeline.py`: `8B30F9536B199F244C00438B706689074AF0E403D2016A7905DBA46A7A7221CF`
- 真实 `flowboard.db`: `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`，446464 bytes，mtime UTC `2026-08-12T06:31:25.4654747Z`；收口过程只读。
