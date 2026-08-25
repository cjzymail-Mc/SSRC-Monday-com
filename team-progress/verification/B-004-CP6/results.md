# B-004 CP6 terminal verification results — wave 1

结论：**REWORK**。独立动态三旅程尚未启动；终态 coverage 引用硬门先失败。

## Failure key

`B004_CP6_COVERAGE_TEST_REFERENCE_MISSING`（首次）

`team-progress/B-004-coverage-map.md` 有完整 B01–B38 共 38 行，并登记 40 个唯一具名测试引用；当前 `tests/test_timeline_e2e.py` 可加载 21 个测试，其中仅 15 个与 map 引用同名，25 个登记引用不存在。

缺失引用：

```text
test_timeline_conflict_preserves_draft_and_shows_server_view
test_timeline_context_menu_requires_mode_each_drag
test_timeline_discard_and_navigation_guard
test_timeline_drag_is_local_until_submit
test_timeline_drag_modes_clamp_and_cascade_locally
test_timeline_editor_sort_is_display_only
test_timeline_entry_click_chain_and_three_modes
test_timeline_failed_write_zero_state_delta_with_canary
test_timeline_hidden_on_mousedown_canary
test_timeline_initial_correction_admin_boundary
test_timeline_journey_dashboards
test_timeline_journey_edit_submit_refresh_undo
test_timeline_journey_import_export_reimport
test_timeline_mixed_date_status_draft
test_timeline_node_create_remove_batch_journey
test_timeline_project_create_validation_ui
test_timeline_project_lifecycle_persists_after_reload
test_timeline_real_pointer_click_chain
test_timeline_review_real_http_rendering
test_timeline_single_project_deleted_state
test_timeline_standard_magnet_and_zoom_band
test_timeline_submit_one_batch_with_drag_details
test_timeline_submit_refreshes_from_server_view
test_timeline_ui_role_matrix_is_server_enforced
test_timeline_undo_once_and_ui_lifetime
```

B36 要求的三条 CP6 旅程名全部缺失。现有 21 个聚合 E2E 的通过事实不能让这些具体引用变成“可加载”，也不能把 CP0 的未来槽位在关门时继续当作未来。

## 四态终态

- B01–B21：`REWORK`（登记引用部分/全部不可加载；既有 CP1–CP3 PASS 报告保留，但终态 traceability 未闭合）。
- B22–B29：`PASS`（引用名称均已存在，且 CP4 最终独立 probe/报告 PASS）。
- B30–B35：`PASS`（引用名称均已存在，且 CP5 独立 probe/报告 PASS）。
- B36：`REWORK`（三条要求的完整旅程具名测试均不存在，动态同库关门尚未执行）。
- B37：`REWORK`（登记的 `test_timeline_node_create_remove_batch_journey` 不可加载；CP3 聚合旅程证据不能满足当前终态引用硬门）。
- B38：`PASS`（引用存在，CP5 B38 独立动态证据 PASS）。
- C 区明确范围：`OUT-OF-SCOPE`，未升级为 B-004 任务。

## 下一步最小返工

coder 需要让 coverage map 的既定测试引用真实可加载，并增加 B36 三条同库完整旅程。可以选择按登记名拆出/包装真实测试，但不得做空壳 alias、跳过或仅改 map 名称掩盖缺口；每个引用必须执行相应冻结行为。完成后 planner 先复跑本 validator，再在同一新临时 DB/随机端口运行 J1/J2/J3 独立 probe。

本波没有运行 Playwright、没有创建/迁移真实库、没有改生产/tests/map 或 CP0–CP5 历史。

---

# B-004 CP6 terminal verification results — recovery / final

结论：**PASS**。wave 1 的 REWORK 历史保留；CP6a/CP6b 已闭合 coverage 引用硬门，独立 Chromium 三旅程在同一份全新临时数据库和随机端口上全部通过。

## Coverage terminal gate

`python -X utf8 team-progress/verification/B-004-CP6/validate_terminal_coverage.py` → exit 0 / PASS：B01–B38 共 38/38 行；24 个唯一 E2E 引用全部可加载；missing `[]`；B36 三条完整旅程 missing `[]`；伪测试名阳性对照被正确拒绝。

## Independent Chromium probe

最终 probe SHA256：`50173BCBCD70F3D8EE120EA3065C90F43CE01E700511B84088B469669A7EF9FF`。

沙箱外执行 `python -X utf8 team-progress/verification/B-004-CP6/probe_cp6_browser.py` → exit 0 / JSON `status=PASS`：

- J1：混合草稿 `date/status/create/remove` 放弃零写；重新编辑后 R06 恰一次，服务端 view/DOM 与临时库证实持久；同一编辑会话立即 R07 恢复，reload 后恢复态持久且 undo disabled；409 与 member R08 `ADMIN_REQUIRED` 代表负例均零写。
- J2：single/all 共享日历、双轨、重叠/展开、阶段、今日线、红橙风险、筛选/排序、共享四项右键全部通过真实 mouse 与视口内 hit-testing；有 GET 阳性对照、timeline 写请求为 0；四张 timeline 表 start/end 内容 hash 完全一致。
- J3：真实 XLSX R09→R10→R01，R11 POST 返回的 server bytes / sha256 / WebCrypto / 实际下载三方一致；新 workspace 重新上传→R09→R10→R01 语义回读通过；代表 422 保持 commit disabled 且四表零写。
- 预期 409/403/422 console 分段与 pageerror 门禁均通过；独立 canary 得到 bad=`[bad:mousedown]`、good=`[good:mousedown, good:mouseup, good:click]`。
- `database_instances=1`；真实 `flowboard.db`、`.copilot-*` 和 `app.js`/`timeline-ui.js`/`timeline.css` 前后指纹不变。完整 stdout JSON 见 `outside-run.txt`。

## Planner fixture history

- `CP6_PLANNER_UNDO_AFTER_RELOAD_EXPECTATION`：一次。初版探针错误地把 R07 放到整页 reload 后，与冻结 B18“提交后一次 undo；刷新/新编辑后入口消失”冲突。修为 R06→立即 R07→reload 验证入口消失与恢复态持久；J1 随后全绿。
- `CP6_PLANNER_DASHBOARD_SEED_RETURN_SHAPE`：一次。初版把 planner CP4 seed 的 `(project_id, node_ids)` 元组直接拼入 selector；严格验证返回结构并提取 project id 后全绿。

两项均为互不相同、各一次的 planner fixture，不计产品 failure，没有放宽任何产品断言。

## Regression matrix

- coder E2E：外跑 24/24 PASS（94.895s）。
- `node tests/timeline_ui.test.js`：24/24 PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'`：10/10 PASS（23.499s）。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`：29/29 PASS（32.666s）。
- `python -X utf8 -m unittest discover -s tests -p 'test_secure_foundation.py' -k transfer`：1/1 PASS。

终态：B01–B38 均为 `PASS`；C 区保持 `OUT-OF-SCOPE`。**CP6 PASS，B-004 CLOSED，允许进入 B-005。**
