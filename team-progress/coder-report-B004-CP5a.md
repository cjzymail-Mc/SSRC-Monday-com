# B-004 CP5a coder report — 预期 422 分段核销与 B38 边界 fixture 修正

日期：2026-08-20  
输入：主 agent 沙箱外完整 E2E `Ran 21`，17 PASS / 4 FAIL  
结论：**READY_FOR_EXTERNAL_RERUN**；本次仅修改 `tests/test_timeline_e2e.py`，没有生产代码变更。

## 1. failure keys 与根因

### `CP5_EXPECTED_422_CONSOLE_ACCOUNTING`（一组，测试证据问题）

三条失败旅程的真实 HTTP 状态、错误 code 和页面错误 UI 均已通过；失败只因 Chromium 会为每个预期 422 另记一条 `Failed to load resource ... 422`，而 CP5 首版没有像既有 CP1/CP3 用例一样逐次核销，导致旅程末尾严格 console 门禁看到 4/1/1 条残留。

最小修正集中在 `upload_timeline(...)`：

- 每次预期错误前记录 console/pageerror 游标；
- 精确等待 `POST .../timeline/imports/preview` response；
- 同时断言 response URL、HTTP 422、`response.json().error.code` 与该 fixture 的预期 code；
- 等待对应 `[data-timeline-import-error="CODE"]` 生产 UI 出现后，断言本段恰新增 1 条 console error，且同时包含 `Failed to load resource` 与 `422`；
- 断言本段 pageerror 新增 0 条；
- 只删除本段从游标开始的这 1 条预期 console，随后继续旅程；每条旅程末尾原 `assert_clean_browser` 全零门禁保持不变。

没有全局过滤、忽略或放宽 console/pageerror。

### `CP5_B38_BOUNDARY_FIXTURE_BUSINESS_FIELD_LIMIT`（一次，fixture 问题）

主 agent 提示优先检查重复业务键；复核结果表明原 1000 行 fixture 的项目名 `边界0..边界999` 已逐行唯一，不是重复键。用冻结 `TimelineService.preview_import` 对同一 fixture 直调，实际错误为：

```text
VALIDATION_ERROR: remark is too long
```

原 fixture 为了命中 transfer “单格恰好 10k 可接受”的边界，把 10k 字符放进了“备注”列；transfer 层确实允许 10k，但 timeline 业务层备注另有 500 字符上限，所以 R09 正确返回 422。

最小修正：把同一 10k 字符移到严格 8 列中的“间隔”列。该列仍真实经过 XLSX parser 的 `MAX_CELL_LENGTH=10_000` 检查，但 timeline 导入契约不会把它写入业务字段。项目名继续逐行唯一。冻结服务直调验证修后结果：`row_count=1000`、`projects=1000`、preview 成功。1001 行拒绝 fixture 与 `IMPORT_TOO_MANY_ROWS`、四表零写断言均未改变。

因此提示中的 `CP5_B38_BOUNDARY_FIXTURE_DUPLICATE_KEY` 条件未证实，不作错误归因；按实际证据记录上述 business-field-limit key。

## 2. 修改范围

- 仅 `tests/test_timeline_e2e.py`
  - `upload_timeline` 增加严格的预期 error code / 422 console 分段核销。
  - 所有 CP5 预期 422 上传均显式传入冻结 error code。
  - 1000 行 + 10k cell 成功边界 fixture 将 10k 值从“备注”移到“间隔”。

未修改 `app.js`、`timeline-ui.js`、`timeline.css`、server/flowboard backend、B-005、治理或 planner 证据。

## 3. 本地验证

- 冻结 service 定向复现（修前）：`VALIDATION_ERROR: remark is too long`
- 冻结 service 定向验证（修后）：`row_count=1000`、`projects=1000`、R09 preview 成功
- `node tests/timeline_ui.test.js`：**24/24 PASS**
- `python -m py_compile tests/test_timeline_e2e.py`：PASS
- `git diff --check -- tests/test_timeline_e2e.py`：PASS
- trailing-whitespace 扫描：无命中
- 按指令未在 worker 沙箱重复运行浏览器；由主 agent 完整外跑 21 条。

外跑命令：

```powershell
python -m unittest discover -s tests -p test_timeline_e2e.py
```

## 4. 指纹与边界锁

- `tests/test_timeline_e2e.py` SHA-256：`559DB55B627223F1FA3CB3564A34542F600C7B0A109F77BBA5C383709ED463B9`
- 真实 `flowboard.db`：446,464 bytes，mtime `2026-08-12 14:31:25`，SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。

未进入 CP6/B-005，未改 `.copilot-*` 或真实数据库。
