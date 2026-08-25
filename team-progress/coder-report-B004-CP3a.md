# B-004 CP3a coder report

## 结论

两项 planner 外跑纠偏已落盘；静态、Node 与测试语法检查 PASS，等待主 agent / planner 沙箱外复跑 Chromium。没有放宽断言或权限。

## 修正

1. `CP3_RIGHT_MENU_FIFTH_ITEM_CONFLICT`
   - 从右键菜单移除“移除节点”，恢复并显式断言冻结的恰四项。
   - B37 remove 改为编辑器动作区独立按钮“移除末个节点”；真实 click 后仍进入同一 draft，并由 R06 混合 batch 提交。
2. `CP3_MEMBER_CORRECTION_GUARD_FIXTURE`
   - member 负例改为 `created_by=u2` 的独立项目和节点，确保穿过项目 write 权限。
   - 精确断言 HTTP 403 且结构化错误码为 `ADMIN_REQUIRED`，toast 为“仅管理员可纠正初始日期”，四表 content hash 零变化；不接受 `PROJECT_FORBIDDEN` 或任意 403。

## 验证

- `node --check timeline-ui.js`：PASS。
- `node --check app.js`：PASS。
- `node tests/timeline_ui.test.js`：11/11 PASS。
- `python -X utf8 -m py_compile tests/test_timeline_e2e.py`：PASS。
- `git diff --check -- timeline-ui.js timeline.css app.js tests/timeline_ui.test.js tests/test_timeline_e2e.py`：PASS（仅既有 LF→CRLF 提示）。
- 未在已知 `PLAYWRIGHT_DRIVER_WINERROR5` 沙箱重复启动 Playwright；外跑命令保持：`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`。

## 隔离

未编辑 `team-task.md`、`team-progress.md`、coverage map、真实 `flowboard.db` 或 `.copilot-*`。

