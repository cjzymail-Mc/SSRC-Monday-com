# B-004 CP2 coder report

## 结论

`BLOCKED_DYNAMIC`，不申请 CP2 PASS。CP2 生产实现、Node 快测和具名真实浏览器旅程均已落盘；静态、Node、HTTP 与 timeline service 回归通过。当前受限 Windows 环境仍无法启动 Playwright driver，因此必须由 planner/主 agent 在允许子进程与 overlapped pipe 的环境独立执行 Chromium 旅程后签注。

## 范围与产物

- `timeline-ui.js`：新增纯本地 `editorState`/draft Map；右键四项菜单；每次消费后清空的 single/cascade 拖拽档；single 前后邻双向钳制、cascade 前驱钳制与仅本轨后续平移；标准日磁吸和 `±10d×8` 放大带；日期与 `done_at` 混合草稿；日期/阶段排序；放弃恢复；DOM 控制器只监听真实鼠标事件。
- `app.js`：只做编辑会话、DOM 重绑与离开/关闭/刷新拦截薄接线；CP2 不调用 batch/undo/import/export。
- `timeline.css`：补右键菜单、armed/draft、放大带和编辑器动作状态；菜单不在 `mousedown` 隐藏，避免吞掉随后 click。
- `tests/timeline_ui.test.js`：补 single/cascade、同轨隔离、混合草稿、放弃和放大带快速单元。
- `tests/test_timeline_e2e.py`：新增 `test_timeline_cp2_local_draft_real_mouse_drag_context_and_discard`。从生产登录/入口/真实 HTTP 开始，用临时 DB 与随机端口；以 Playwright mouse hit-testing 执行右键、菜单点击和拖拽，记录右键 `mousedown→mouseup→contextmenu`、菜单 `mousedown→mouseup→click`、拖拽 `mousedown→mouseup`；断言拖拽/状态/排序请求数不增长、档位一次消费、离开拦截、放弃恢复。另有“mousedown 隐藏目标会吞 click”的阳性 canary。

## 验证证据

- `node --check timeline-ui.js`、`node --check app.js`：PASS。
- `node tests/timeline_ui.test.js`：9/9 PASS。
- `python -X utf8 -m py_compile tests/test_timeline_e2e.py server.py flowboard/timeline.py`：PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'`：10/10 PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`：29/29 PASS。
- `git diff --check -- timeline-ui.js timeline.css app.js index.html tests/timeline_ui.test.js tests/test_timeline_e2e.py`：PASS（仅既有 LF→CRLF 提示）。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`：0 tests executed；`setUpClass` 在 `sync_playwright().start()` 创建 Windows overlapped pipe 时 `PermissionError: [WinError 5] 拒绝访问`。

## failure keys

- `PLAYWRIGHT_DRIVER_WINERROR5`：本 CP 1 次。与 CP1 的环境阻断同源，但本 CP 未重试；不以 Node 或合成 DOM 结果冒充浏览器 PASS。

## 安全与隔离

- E2E fixture 使用 `TemporaryDirectory`、临时数据库与 `create_server("127.0.0.1", 0, ...)` 随机端口；没有提交/undo/import/export 请求。
- 真实 `flowboard.db` 保持 446464 bytes、mtime `2026-08-12 14:31:25`、SHA256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-state.json` `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`；`.copilot-task.md` `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`；`.copilot-message.md` `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`。本轮未编辑上述文件。
