# B-004 CP1 coder report

## 结论

`BLOCKED_DYNAMIC`，不申请 CP1 PASS。生产代码与具名真实浏览器测试已落盘；静态、Node、HTTP 与 timeline service 回归均通过，但当前受限 Windows 环境无法启动 Playwright driver，尚无可签注的真实 Chromium 动态结果。

## 本轮范围与产物

- `index.html`：生产页接入 `timeline.css`，保留从真实登录后的 `#timelineBtn` 入口进入时间管理 overlay。
- `app.js`：实现 R01 工作区读取、R02 单项目读取，及“项目列表 / 编辑器 / 单项目仪表盘 / 全项目仪表盘”生产导航；实现网页 R04 新建、R05 admin 软删并重新读取；依据 bootstrap 的 `capabilities.write/admin` 控制 member/viewer/admin 操作面。
- `timeline-ui.js` / `timeline.css`：增加 CP1 所需的项目列表、三页面模式导航、新建表单、admin 删除控制和浅色生产样式。未进入 CP2 编辑拖拽、CP3 提交、CP4 仪表盘细节或 CP5 Excel。
- `tests/test_timeline_e2e.py`：3 个从生产 `index.html/app.js`、真实登录和真实 HTTP 出发的 Playwright 旅程；不使用 `set_content`、mock fetch、handler 直调或 `element.click()`。admin 测试记录并断言入口和模式按钮的 `mousedown -> mouseup -> click`；覆盖创建、R01/R02、三模式、刷新持久化、软删及临时库落盘；member 覆盖可读可建但无删除；viewer 覆盖服务端 403 且页面不开放。

## 验证证据

- `python -X utf8 -m py_compile tests/test_timeline_e2e.py server.py flowboard/timeline.py`：PASS。
- `node --check app.js`、`node --check timeline-ui.js`：PASS。
- `node tests/timeline_ui.test.js`：4/4 PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'`：10/10 PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`：29/29 PASS。
- `git diff --check -- index.html app.js timeline-ui.js timeline.css tests/test_timeline_e2e.py`：PASS（仅 Git 的既有 LF→CRLF 提示）。
- 浏览器命令 `python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`：0 tests executed；`setUpClass` 在 `sync_playwright().start()` 创建 Windows overlapped pipe 时失败：`PermissionError: [WinError 5] 拒绝访问`。

## failure keys

- `TEST_INVOCATION_MODULE_PATH`：首次误用 `python -m unittest tests.test_timeline_e2e`，因 `tests` 非 package 导入失败；改为仓库惯用 discover 后消除，不是实现失败。
- `PLAYWRIGHT_DRIVER_WINERROR5`：1 次。依指令不在同一受限环境重试、不安装、不以 Node 替代 PASS。需 planner/主 agent 在允许 Playwright 子进程与管道的环境运行上述 discover 命令进行独立签注。

## 安全与隔离

- 所有 HTTP/E2E 测试设计均使用 `TemporaryDirectory`、临时 DB、`create_server("127.0.0.1", 0, ...)` 随机端口。
- 真实 `flowboard.db`：446464 bytes，mtime `2026-08-12 14:31:25`，SHA256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-state.json` SHA256 `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`；`.copilot-task.md` `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`；`.copilot-message.md` `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`。本轮未编辑上述文件。
