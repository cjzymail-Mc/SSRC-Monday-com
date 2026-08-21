# B-004 CP0 Coverage Map — 可操作 UI 与真实浏览器旅程

日期：2026-08-20
依据：`team-task.md` §11；`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` §3–§5、§7、§8.3。
状态词：`PASS` / `GAP-B004` / `CONFLICT` / `OUT-OF-SCOPE`。

> 硬口径：本表的 `PASS` 只允许由生产 `index.html` / `app.js` 入口发起、经过真实 HTTP 与真实 Chromium hit-testing 的具名测试支撑。现存 DOM 字符串、CSS token 与 `tests/timeline_ui.test.js` Node 快测只能证明静态骨架，不能计作 B-004 浏览器 PASS。因此 CP0 初盘没有 PASS 项，不等于已存在的静态代码无价值。

## A. 生产入口与现有证据

| 入口/文件 | 当前事实 | 证据性质 |
|---|---|---|
| `index.html:20,35,39` | 有“时间管理”按钮、overlay 容器，并加载 `timeline-ui.js` 后加载 `app.js` | 静态生产入口；未证明真实点击链 |
| `app.js:40-42,249` | `#timelineBtn` 点击后仅 GET workspace timeline，随后 `renderAll()`；只有打开/关闭 | 生产薄接线骨架；无 lifecycle/editor/import/export/batch 等 UI 接线 |
| `timeline-ui.js` | 仅提供 bounds、静态 editor/single/all/dashboard HTML renderer；无状态控制器、右键、拖拽、草稿、提交或导入控制器 | Node 可加载纯函数；不是浏览器旅程 |
| `timeline.css` | 有浅色 tokens、双轨/节点/阶段卡基础样式 | CSS 静态证据；不是交互/像素验收 |
| `tests/timeline_ui.test.js` | 4 个手写断言：bounds、双轨字符串、阶段类、色板映射 | Node 快测；0 个真实浏览器断言 |
| `tests/test_views_e2e.py` 等 | repo 已有 Playwright/Chromium 测试基建，但测试的是第一阶段 schedule/timeline 字段视图，不是 feature01 项目时间管理 | 能力先例；不得冒充 B-004 证据 |

## B. 冻结条款逐项映射

| ID | 冻结条款/可观察行为 | 当前生产入口/行为 | 当前具名证据 | 状态 | 唯一 CP / 未来具名 E2E 槽位 |
|---|---|---|---|---|---|
| B01 | 登录后真实点击进入编辑器、单项目、全项目三种模式（§8.3） | 只有 `#timelineBtn -> openTimeline -> renderAll`，无模式导航 | 无 | GAP-B004 | CP1 <code data-historical-slot>test_timeline_entry_click_chain_and_three_modes</code> |
| B02 | 真实读取、member/admin 新建、admin 软删、刷新持久化（§3.4/§3.6） | 仅 workspace GET；无 create/delete 控件 | 无 | GAP-B004 | CP1 <code data-historical-slot>test_timeline_project_lifecycle_persists_after_reload</code> |
| B03 | admin/member/viewer UI 与服务端权限矩阵（§4） | UI 未按 timeline 权限呈现；服务端证据属于 B-003 | 无浏览器证据 | GAP-B004 | CP1 <code data-historical-slot>test_timeline_ui_role_matrix_is_server_enforced</code> |
| B04 | 单项目 GET 与软删后 404 的 UI 处理（§3.4/§3.6） | 无单项目读取接线、无 deleted-state UX | 无 | GAP-B004 | CP1 <code data-historical-slot>test_timeline_single_project_deleted_state</code> |
| B05 | 项目名 trim/限长/同名错误可操作呈现（§3.6/§3.8） | 无生命周期表单/错误呈现 | 无 | GAP-B004 | CP1 <code data-historical-slot>test_timeline_project_create_validation_ui</code> |
| B06 | 本地草稿；拖拽全程零网络（§8.3） | 无草稿模型/拖拽控制器 | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_drag_is_local_until_submit</code> |
| B07 | 右键四项；每次重选 single/cascade；无默认档（§8.3） | 节点只是 button；无 contextmenu | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_context_menu_requires_mode_each_drag</code> |
| B08 | single 双向钳制、cascade 前驱钳制/仅本轨平移（§3.1/§8.3） | 无交互计算 | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_drag_modes_clamp_and_cascade_locally</code> |
| B09 | 标准 1 日磁吸、±10 天×8 放大带（§8.3） | 无磁吸/放大带 | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_standard_magnet_and_zoom_band</code> |
| B10 | 状态+日期共享草稿批；混合修改（§3.1/§8.3） | 无状态菜单动作/草稿 | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_mixed_date_status_draft</code> |
| B11 | 编辑器按日期/六阶段排序只改显示不改数据（§8.3） | 有两个无 handler 的静态按钮；渲染顺序沿 API nodes | Node 仅查字符串 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_editor_sort_is_display_only</code> |
| B12 | 放弃更改纯前端回滚；离开拦截（§8.3） | 无 dirty state/放弃/拦截 | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_discard_and_navigation_guard</code> |
| B13 | hit-testing 点击链 mousedown→mouseup→click | 无事件记录/真实浏览器测试 | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_real_pointer_click_chain</code> |
| B14 | canary：mousedown 隐藏目标会吞 click | 无 canary | 无 | GAP-B004 | CP2 <code data-historical-slot>test_timeline_hidden_on_mousedown_canary</code> |
| B15 | 一次真实 batch POST；payload 含 mode/magnet/zoom_band（§3.1） | 无 submit 接线 | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_submit_one_batch_with_drag_details</code> |
| B16 | 提交后用服务端完整 view 刷新、刷新页仍持久（§3.1） | 无写入/响应消费 | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_submit_refreshes_from_server_view</code> |
| B17 | 409 并排“我的草稿/服务端最新”、整批零写入（§3.1） | 无冲突 UI | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_conflict_preserves_draft_and_shows_server_view</code> |
| B18 | 提交后一次 undo；刷新/新编辑后入口消失（§3.2/§8.3） | 无 undo 接线 | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_undo_once_and_ui_lifetime</code> |
| B19 | initial correction 仅 admin；自由日期不钳制/级联（§3.3） | 无纠正 UI | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_initial_correction_admin_boundary</code> |
| B20 | 复盘完整汇总、最近 50、actor/change rows/has_more（§3.5） | 无 review GET/UI | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_review_real_http_rendering</code> |
| B21 | 4xx/409 阴性路径观察请求/响应与库前后；探针阳性对照 | 无 B-004 隔离库浏览器 harness | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_failed_write_zero_state_delta_with_canary</code> |
| B22 | 单项目方向 A：大标题/白卡/KPI 次级/时间轴核心（§8.1–§8.3） | `renderSingle()` 有标题/白卡/KPI，但内部调用 `renderEditor()`，不是阶段仪表盘 | Node 仅双轨字符串 | CONFLICT | CP4 <code data-historical-slot>test_timeline_single_dashboard_structure</code> |
| B23 | 共享绝对日历、红色今日线贯穿且非纯颜色（§8.3） | bounds 为每项目局部；无 today line/文字 | 无 | CONFLICT | CP4 <code data-historical-slot>test_timeline_shared_calendar_and_today_marker</code> |
| B24 | 默认主线/并行两行；重叠段分半；展开拆重叠（§2.4/§8.3） | 有两轨静态行；无 overlap/expand 控制 | Node 仅查“主线/并行”字符串 | GAP-B004 | CP4 <code data-historical-slot>test_timeline_overlap_split_and_expand</code> |
| B25 | stage_intervals / 连续条形 / 2px 小圆角 / 阶段冗余编码（§2.4/§8） | `renderDashboard()` 存在但生产 `renderSingle()` 未调用；CSS stage border-radius=4px | Node 验证 stage class | CONFLICT | CP4 <code data-historical-slot>test_timeline_stage_intervals_semantics</code> |
| B26 | 两仪表盘复用同一右键菜单控制器（§8.3） | 无控制器 | 无 | GAP-B004 | CP4 <code data-historical-slot>test_timeline_dashboards_share_context_controller</code> |
| B27 | 全项目多选+四种排序（开始/阶段/临近/逾期） | 静态 select 和纯函数筛排存在；无 change handler；排序 option 未反映当前 selected | Node 未覆盖筛排交互 | GAP-B004 | CP4 <code data-historical-slot>test_timeline_all_dashboard_filter_and_sort</code> |
| B28 | 行内橙=本周、红=逾期，红左橙右，含非颜色提示（§8.3） | 仅逾期红文字，无本周橙点/左右序 | 无 | GAP-B004 | CP4 <code data-historical-slot>test_timeline_dashboard_risk_markers</code> |
| B29 | 浅色语义 token、六阶段色板、不开发暗色运行态（§8.1/§8.2） | CSS tokens 与六阶段类已存在；无暗色入口 | Node 仅验证一个映射；无生产浏览器 computed-style 证据 | GAP-B004 | CP4 <code data-historical-slot>test_timeline_light_tokens_and_redundant_labels</code> |
| B30 | Excel 真实文件 preview→commit；错误禁止提交（§3.7/§5） | 现有 import UI 是 board import，非 `/timeline/imports/*` | 无 | CONFLICT | CP5 <code data-historical-slot>test_timeline_excel_preview_commit_real_file</code> |
| B31 | 表头/逐行错误（row/header）、同名全行、重复、枚举/日期等 UI 呈现（§5） | 无 timeline import UI | 无 | GAP-B004 | CP5 <code data-historical-slot>test_timeline_import_errors_are_actionable</code> |
| B32 | 多 sheet 仅首 sheet提示；CSV 日期变形提示改用 xlsx（§5） | 无 timeline import UI | 无 | GAP-B004 | CP5 <code data-historical-slot>test_timeline_import_warnings_multisheet_and_csv_date</code> |
| B33 | 状态重算提示，仅“已完成”保留；有错不许提交（§3.7/§5） | 无 timeline preview UI | 无 | GAP-B004 | CP5 <code data-historical-slot>test_timeline_import_status_warning_and_commit_gate</code> |
| B34 | workspace 全量 export，消费真实 base64/sha256 字节（§3.7） | 现有 export 是 board export，非 timeline | 无 | CONFLICT | CP5 <code data-historical-slot>test_timeline_export_decodes_server_bytes_and_hash</code> |
| B35 | 新 workspace 导出→重新上传→导入（既定差异除外） | 无 timeline 往返 UI | 无 | GAP-B004 | CP5 <code data-historical-slot>test_timeline_export_reimport_new_workspace</code> |
| B36 | CP6 三条完整真实旅程在新隔离库复跑 | 无 B-004 E2E 文件 | 无 | GAP-B004 | CP6 <code data-historical-slot>test_timeline_journey_edit_submit_refresh_undo</code>; <code data-historical-slot>test_timeline_journey_dashboards</code>; <code data-historical-slot>test_timeline_journey_import_export_reimport</code> |

### CP0a 终态增补（保留上方 36 行初始快照）

> `B004_CP0_FROZEN_CLAUSE_UNMAPPED` 最小修正：以下两行只补原表遗漏的冻结条款，不重分配 B01–B36，不重复计算 B31 的行级错误或 B33 的 preview/commit gate。

| ID | 冻结条款/可观察行为 | 当前生产入口/行为 | 当前具名证据 | 状态 | 唯一 CP / 未来具名 E2E 槽位 |
|---|---|---|---|---|---|
| B37 | §3.1 `changes[]` 的节点 `create` / `remove`：生产编辑器可新增节点、软删节点，并在同一次真实 batch 旅程提交后刷新验证；remove 不得硬删 | 当前无节点新增/移除控件、无对应 batch payload 接线 | 无 | GAP-B004 | CP3 <code data-historical-slot>test_timeline_node_create_remove_batch_journey</code> |
| B38 | §5.1 文件级安全与严格表头：1.5MB 文件、12MB 解压、1000 数据行、单元格 10k、公式/宏/外链拒绝；8 列 strip 后名称/顺序/重复严格匹配；UI 经真实文件上传呈现文件级错误且不进入 preview/commit。此行只计文件级拒绝，B31 继续只计行级错误 | 当前 timeline Excel UI 不存在；现有 board import UI 不能替代 | 无 | GAP-B004 | CP5 <code data-historical-slot>test_timeline_import_file_safety_and_strict_headers</code> |

## C. 范围隔离

| 条款 | 处理 |
|---|---|
| §3–§5 中纯 service/HTTP 正确性（事务、SQL、错误码内部算法、解析器安全上限） | OUT-OF-SCOPE：B-003 已关；B-004 仅验证 UI 可观察消费和阴性状态证据，不重写路由层 |
| §7.1 Python service/HTTP 12 组 | OUT-OF-SCOPE：B-002/B-003 既有证据；B-004 不以其替代浏览器证据 |
| §7.2 全量历史回归与文档总收口 | OUT-OF-SCOPE：B-005 |
| §7.3 Gate 5 人工冒烟、像素/真实数据微调、强磁铁参数 | OUT-OF-SCOPE：Gate 5 / B-005；B-004 只验结构、可操作性、冻结语义 |
| 暗色运行态/主题切换、改名/恢复、分页、缓存、工作负载、OKR、自动化等候选 | OUT-OF-SCOPE：冻结禁止扩项 |

## D. 浏览器能力盘点（只读，未安装）

- Python `playwright`：可导入；CLI 位于 `C:\Users\xy198\AppData\Local\Programs\Python\Python312\Scripts\playwright.exe`。
- 系统 Chrome：`C:\Program Files\Google\Chrome\Application\chrome.exe`，版本 `151.0.7922.138`。
- 系统 Edge：`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`，版本 `151.0.4129.86`。
- repo 既有 `tests/test_views_e2e.py`、`test_collaboration_e2e.py`、`test_i12_e2e.py`、`test_i13_e2e.py` 均以 Python Playwright `chromium.launch(headless=True)` 运行，说明已有 Chromium E2E 施工先例。
- Node 侧 `playwright` / `playwright-core` / `puppeteer` 均不可 resolve；B-004 应沿用 Python Playwright，不安装新依赖。

## E. CP0 指纹

| 文件 | SHA-256 |
|---|---|
| `index.html` | `A2EE2EA93E72C7E8BD8D1896C5D9299073DEED95C0CD5DD80F2FC3634BF64021` |
| `app.js` | `3172F712762C7818E054C66D9F95F197BCD6FC43C557E0BD68B144D1AA37275A` |
| `timeline-ui.js` | `9DEEFA4105E9DC07FD199388054C074439303BD2FBBBFF3013D9823BCDFB267D` |
| `timeline.css` | `F34FD1CE73D2DF8F9700A33B0F976B28FA44F4FF5F14E3882BEA6A5AC458E6F7` |
| `tests/timeline_ui.test.js` | `A23ACD2E93311DE479C6687C31B4349BD16048E69B2C1DD3F69DA03FCFE6562E` |
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` |

真实 `flowboard.db` stat：446464 bytes；LastWriteTime `2026-08-12 14:31:25`。本 CP 只读，未启动生产库迁移/写入。

## F. CP0 结论（coder 自检，非 planner 签注）

- 条款行：36；`PASS=0`、`GAP-B004=31`、`CONFLICT=5`。
- 5 个冲突均是“当前生产入口指向不同/不完整行为”，不是扩大范围：B22/B23/B25/B30/B34。
- CP1–CP6 每条冻结行为均有唯一归属；未来 E2E 名称只是登记槽位，当前均不存在，不得验收为真。
- CP0 产物仅供 planner 独立验收；不得据此越过 CP0 或宣称 B-004 PASS。

## G. CP0a 终态计数与验收请求

- 初始快照仍为 B01–B36：36 行，`PASS=0`、`GAP-B004=31`、`CONFLICT=5`。
- CP0a 终态为 B01–B38：38 行，`PASS=0`、`GAP-B004=33`、`CONFLICT=5`。
- B37 唯一落 CP3，覆盖节点 create/remove 的生产 UI→真实 batch→刷新旅程；不与 B02 项目生命周期或 B15 通用提交重复计数。
- B38 唯一落 CP5，单列文件级安全/严格表头；B31 仍只计行级错误呈现，B33 仍只计状态提示与 commit gate。
- 此终态仍为 coder 自检，等待 planner 复跑 validator 与冻结语义审计，不声明 PASS。

## H. CP6 终态真实 E2E 可追溯表（不回写 CP0/CP0a 历史事实）

> 上方 B 表与 CP0a 增补表保留 2026-08-20 开工时的生产缺口、状态和“未来槽位”历史快照；其中名称只表示当时计划，并非关门引用。以下表是 CP6 唯一终态引用：每个名字均为 `tests/test_timeline_e2e.py` 当前可加载且实际执行冻结语义的方法。一个聚合旅程可覆盖多条语义，但不以空 alias、test 互调或 skip 代替执行。

| ID | CP6 终态真实 E2E 引用 | 覆盖说明 |
|---|---|---|
| B01 | `test_admin_real_entry_modes_create_delete_and_refresh_persistence` | 真实入口点击链与 editor/single/all 三模式 |
| B02 | `test_admin_real_entry_modes_create_delete_and_refresh_persistence` | admin 创建/软删/刷新持久化；member 行为另见 B03 |
| B03 | `test_member_can_read_and_create_but_has_no_delete_control`; `test_viewer_is_denied_by_server_and_cannot_open_timeline` | member/admin 可写边界、viewer 服务端拒绝与 UI 不开放 |
| B04 | `test_admin_real_entry_modes_create_delete_and_refresh_persistence` | 单项目 GET；双会话软删后陈旧 UI 再 GET 得 404 并呈现错误 |
| B05 | `test_admin_real_entry_modes_create_delete_and_refresh_persistence` | maxlength、trim 后同名 422、console/零写 |
| B06 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | 拖拽草稿期间请求数不增 |
| B07 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | 右键四项、mode 一次消费、无默认档 |
| B08 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | cascade 本轨移动与未重选 mode 不再拖动 |
| B09 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | 真实 drag、标准日粒度与 ±10 天 ×8 放大带 |
| B10 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | 日期 cascade 与 done 状态进入同一草稿 |
| B11 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | stage sort 只改本地显示、零网络 |
| B12 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | 离开拦截与 discard 本地回滚 |
| B13 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | context/drag 真实 mousedown/up 事件序 |
| B14 | `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard` | mousedown 隐藏目标吞 click 的阳性 canary |
| B15 | `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo` | 单次真实 batch POST 与 mode/magnet/zoom_band payload |
| B16 | `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo` | 消费完整服务端 view、刷新持久化 |
| B17 | `test_timeline_cp3_conflict_latest_view_zero_write_and_member_correction_denied` | 409 最新 view UI、四表 hash 零写 |
| B18 | `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo` | 一次 undo 与后续持久提交 |
| B19 | `test_timeline_cp3_conflict_latest_view_zero_write_and_member_correction_denied` | member initial correction 403、零写；admin 正例见 CP3 聚合旅程 |
| B20 | `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo` | 真实 review GET 与 actor/change rows UI |
| B21 | `test_timeline_cp3_conflict_latest_view_zero_write_and_member_correction_denied`; `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo` | 409/403 请求响应与 hash 阴性门，配套成功写阳性对照 |
| B22 | `test_timeline_single_dashboard_structure` | 方向 A 白卡、大标题、KPI 次级、时间轴核心 |
| B23 | `test_timeline_shared_calendar_and_today_marker` | 共享绝对日历、今日红线与文字冗余 |
| B24 | `test_timeline_overlap_split_and_expand` | 双轨、row_index 分半与展开 |
| B25 | `test_timeline_stage_intervals_semantics` | 连续阶段条、2px、六阶段文字/aria/node_ids |
| B26 | `test_timeline_dashboards_share_context_controller` | single/all 同一四项 controller、只读零写 |
| B27 | `test_timeline_all_dashboard_filter_and_sort` | 多选、四排序、重渲染后真实 node hit |
| B28 | `test_timeline_dashboard_risk_markers` | 红左橙右与逾期/本周文字 |
| B29 | `test_timeline_light_tokens_and_redundant_labels` | 浅色 computed style、六阶段标签、无暗色入口 |
| B30 | `test_timeline_excel_preview_commit_real_file` | 真实 XLSX preview→batch_id commit→刷新 |
| B31 | `test_timeline_import_errors_are_actionable` | 同名全行、重复、枚举、日期行级错误 UI |
| B32 | `test_timeline_import_warnings_multisheet_and_csv_date` | 多 sheet/CSV 日期提示 |
| B33 | `test_timeline_import_status_warning_and_commit_gate` | 状态重算提示与错误 commit gate |
| B34 | `test_timeline_export_decodes_server_bytes_and_hash` | R11 真实 base64、SHA-256、物理下载 |
| B35 | `test_timeline_export_reimport_new_workspace` | 导出文件跨 workspace R09→R10 回读 |
| B36 | `test_timeline_journey_edit_submit_refresh_undo`; `test_timeline_journey_dashboards`; `test_timeline_journey_import_export_reimport` | 同库关门三条完整真实旅程 |
| B37 | `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo` | create/remove 同一 batch、刷新与 undo DB 回读 |
| B38 | `test_timeline_import_file_safety_and_strict_headers` | 文件级上限/公式宏外链/严格 8 表头真实上传与零写 |
