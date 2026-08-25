# B-004 CP5 coder report — Timeline Excel 真实导入/导出 UI

日期：2026-08-20  
范围：team-task §11 CP5；coverage B30–B35/B38  
结论：**BLOCKED_DYNAMIC（仅当前 Windows 沙箱 Playwright WinError 5）/ READY_FOR_EXTERNAL_RERUN**

## 1. 契约纠偏与生产实现

开工 prompt 中曾使用 `preview_id` 一词；读取 B-003 冻结实现、HTTP 测试及主 agent 纠偏后，以后端单一真源为准：R09 返回 `batch_id`，R10 请求体严格为 `{batch_id}`。本轮没有为 prompt 术语改后端。

- `timeline-ui.js`：新增写权限下的 Excel/CSV transfer 面板；真实 file input、预览摘要、项目/node 数、warnings、文件/行级错误表、严格 commit gate、导出下载链接。
- `app.js`：
  - file chooser 读取真实 bytes 并 base64 后 POST R09；成功消费 `batch_id/projects/warnings`，422 消费 `error.details.rows` 或 `details.row`。
  - 仅无错且 preview 存在时允许物理提交，R10 严格发送 `{batch_id}`，成功后重新 GET timeline 刷新生产视图。
  - R11 严格 POST `{}`；只解码服务端 `content_base64`，Web Crypto 重算 SHA-256 并与服务端值比对；不匹配不生成下载入口。匹配后由真实 Blob + download anchor 下载，不在前端重造 workbook。
- `timeline.css`：补齐浅色 transfer card、warnings、行级错误表、禁用态与已校验下载态；未引入暗色入口。

未修改 `server.py`、`flowboard/timeline.py`、`flowboard/transfer.py` 或任何 B-003 后端契约；未发现需要停报的 B-003 契约缺口。

## 2. B30–B35/B38 真实 Chromium 用例

`tests/test_timeline_e2e.py` 现有 14 条保持，新增 coverage map 要求的 7 个具名测试（总计 21 条）：

1. `test_timeline_excel_preview_commit_real_file`：真实 XLSX → R09 201 → summary/warnings → 物理 commit → R10 201 → UI/DB 回读；验证只有“已完成”保留 `done_at`。
2. `test_timeline_import_errors_are_actionable`：同名全部冲突行、重复、阶段枚举、日期错误逐个真实上传；错误表可操作呈现，R10 请求数为零，四表 hash 不变。
3. `test_timeline_import_warnings_multisheet_and_csv_date`：真实双 sheet OOXML 只取首 sheet 提示；CSV 数字日期明确提示改用 `.xlsx`，commit 禁用。
4. `test_timeline_import_status_warning_and_commit_gate`：状态重算提示；合法 preview 可提交，随后错误状态立即清除 preview/禁用 commit，零 R10/零四表写入。
5. `test_timeline_export_decodes_server_bytes_and_hash`：物理点击 R11、物理下载；下载 bytes SHA-256 必须等于服务端值，并由后端 parser 回读严格 8 列。
6. `test_timeline_export_reimport_new_workspace`：工作区 1 真实导出下载 → 独立用户/工作区 2 真实 file chooser → R09 → R10 → DB 项目/node 回读。
7. `test_timeline_import_file_safety_and_strict_headers`：真实上传并验证 1.5MB、12MB 解压、1001 行、10001 字符、公式、宏、外链、错序 8 表头、重复表头拒绝；另真实上传 1000 行且单格恰好 10k 的边界文件并通过 preview。所有拒绝均禁 commit，四表 hash 不变。

file chooser 使用 Playwright `set_input_files`（真实 File/change 流程）；所有按钮/下载入口使用 bounding box 中心的真实 `mouse.down → mouse.up`，没有 `force`、`element.click()`、handler 直调、mock fetch 或 `set_content`。每条用例仍使用随机端口、临时 DB、真实 HTTP、console/pageerror 分段清零。

## 3. 本地静态与冻结回归

- `node --check timeline-ui.js`：PASS
- `node --check app.js`：PASS
- `node tests/timeline_ui.test.js`：**24/24 PASS**（原 21 + transfer 3）
- `python -m py_compile tests/test_timeline_e2e.py`：PASS
- `python -m unittest discover -s tests -p test_timeline_http.py`：**10/10 PASS**
- `python -m unittest discover -s tests -p test_timeline.py`：**29/29 PASS**
- `git diff --check -- app.js timeline-ui.js timeline.css tests/timeline_ui.test.js tests/test_timeline_e2e.py`：PASS（其余 4 个 B-004 文件为当前未跟踪施工文件，另以 trailing-whitespace 扫描为 PASS）

说明：最初用 `python -m unittest tests.test_*` 触发 `tests` 非 package 的收集错误，改用仓库既定 `discover -s tests -p ...` 后上述冻结套件全绿；这不是产品 failure_key。

## 4. 动态边界

按指令只尝试一次：

```powershell
python -m unittest discover -s tests -p test_timeline_e2e.py
```

结果：Playwright driver 在 `sync_playwright().start()` 创建 Windows pipe 时 `PermissionError: [WinError 5]`，浏览器尚未启动，`Ran 0 tests`。  
动态 failure_key：`CP5_PLAYWRIGHT_SANDBOX_WINERROR5`（环境阻断，非产品失败）。本 worker 不重复尝试；请主 agent 在沙箱外执行同一命令，期望收集 **21 条**。

## 5. 指纹与边界锁

- `app.js` `FF3BF78E18DE54C62AB81B95E144CD409F127D5053E9D3F9A976218D9C4D4C47`
- `timeline-ui.js` `436167262465366B97EAD535FA0C3E6B9AB6C98712CA949EEFA299854F15071C`
- `timeline.css` `48C749FD2FB8D478614970DB7DB7A89FD2300E3603A17C2C9B36A8F78D74D278`
- `tests/timeline_ui.test.js` `1F64BE20DD97289007EE32A3D9CDEA3000D2A86868733E97A8405C96B798E6F2`
- `tests/test_timeline_e2e.py` `B6DFAF9D577EF83F282F97BD905EE7769B67485A47B16C568861257A5D9EB62F`
- 真实 `flowboard.db`：446,464 bytes，mtime `2026-08-12 14:31:25`，SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-task.md/.copilot-state.json/.copilot-message.md` mtime 保持 `2026-08-19 09:48:23 / 14:00:55 / 13:57:38`。

未进入 B-005，未改治理、planner 证据、coverage map、`.copilot-*` 或真实数据库。
