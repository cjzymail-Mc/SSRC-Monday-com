# B-004 CP3 coder report

## 结论

`BLOCKED_DYNAMIC`，不申请 CP3 PASS。生产实现、Node 快测和两条 CP3 真实 Chromium 具名旅程已落盘；静态、Node、HTTP 与 timeline service 回归通过。当前受限 Windows 环境仍无法启动 Playwright driver，须由 planner / 主 agent 在允许子进程与 overlapped pipe 的环境独立外跑后签注。

## 范围与产物

- `timeline-ui.js`：在 CP2 草稿模型上增加 B37 节点 create/remove；新增唯一 `batchRequest()` 转换边界，将日期、状态、create、remove 合成一个 R06 request，并固定携带 `mode/magnet/zoom_band/historical_correction`；新增提交、撤销、初始日期纠正和轻量复盘生产控件。
- `app.js`：薄接线 R03/R06/R07/R08。更新按钮有 submitting latch，恰一次 POST；成功、undo 和 409 都以服务端 view 重建 editor；409 直接展示 `details.conflicts[0].view`，不发补写；member 的纠正动作仍真实请求，由服务端 403 裁决。
- `timeline.css`：只补动作换行与轻量复盘列表，不扩视觉。
- `tests/timeline_ui.test.js`：11/11，新增混合 batch payload（日期/状态/create/remove + details）快测。
- `tests/test_timeline_e2e.py`：新增两条 CP3 生产入口旅程：
  - `test_timeline_cp3_submit_mixed_batch_refresh_review_correction_and_undo`
  - `test_timeline_cp3_conflict_latest_view_zero_write_and_member_correction_denied`
  使用临时 DB、随机端口、真实 Chromium 生产入口；记录 batch request 次数与 JSON；校验真实 undo、刷新持久化、R03 actor/change_rows、admin correction、member 403，以及冲突前后四张 timeline 表内容 hash 不变。

## 已完成验证

- `node --check timeline-ui.js`：PASS。
- `node --check app.js`：PASS。
- `node tests/timeline_ui.test.js`：11/11 PASS。
- `python -X utf8 -m py_compile tests/test_timeline_e2e.py server.py flowboard/timeline.py`：PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'`：10/10 PASS。
- `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`：29/29 PASS（33.650s）。
- `git diff --check -- timeline-ui.js timeline.css app.js tests/timeline_ui.test.js tests/test_timeline_e2e.py`：PASS（仅既有 LF→CRLF 提示）。

## 动态阻断与外跑命令

- `PLAYWRIGHT_DRIVER_WINERROR5`：本 CP 1 次。`sync_playwright().start()` 在创建 Windows overlapped pipe 时 `PermissionError: [WinError 5]`，0 tests executed；按熔断纪律未在同一沙箱重试。
- 外跑命令：`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`
- planner 应重点独立核对：R06 仅一次 POST；payload 四类 changes 与三项 details；提交/刷新/undo 的 DB 状态；409 返回最新 view 且 content hash 零变化；member R08 403；R03 显示 actor 与 change_rows 数量。

## 安全与隔离

- 所有新动态 fixture 均为 `TemporaryDirectory` + 随机端口；未触碰真实运行库。
- 真实 `flowboard.db`：446464 bytes，mtime `2026-08-12 14:31:25`，SHA256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-state.json` / `.copilot-task.md` / `.copilot-message.md` 未编辑；本报告不改 `team-task.md`、`team-progress.md` 或 coverage map。

