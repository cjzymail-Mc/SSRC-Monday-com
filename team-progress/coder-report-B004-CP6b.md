# B-004 CP6b coder report — B04 删除后 404 toast 响应真源

日期：2026-08-20  
外跑前值：完整 E2E `Ran 24`，23 PASS / 1 ERROR  
failure_key：`CP6_B04_404_TOAST_TEXT_ASSUMPTION`（首次，测试断言问题）  
结论：**READY_FOR_EXTERNAL_RERUN**；仅修改测试，未改生产。

## 1. 根因与最小修正

双会话 B04 旅程已经真实发出 `GET /api/timeline/projects/{id}` 并得到 404；超时来自测试把 toast 文案硬编码成权限拒绝文案“资源不存在或不可访问”。冻结删除态实际响应来自 `PROJECT_NOT_ACTIVE`，生产 `showError(error)` 的合同是把响应 `error.message` 原样交给 toast。

`tests/test_timeline_e2e.py` 现改为：

- 从同一次 `deleted_get.value.json()` 读取响应真源；
- 精确断言 HTTP 404、`error.code == "PROJECT_NOT_ACTIVE"`；
- 断言 `error.message` 是非空字符串；
- 等待 `#toast.show`，断言 toast 实际 visible，且 `inner_text()` **严格等于**该响应 `error.message`；
- 断言本段 console 恰新增 1 条，同时包含 `Failed to load resource` 和 `404`；
- 断言本段 pageerror 新增 0 条，只清理该条预期 console，随后原 `assert_clean_browser` 全零门保持；
- 原 DB `deleted_at IS NOT NULL` 软删断言完整保留。

没有删除 toast 门、接受任意文案、全局忽略 console，亦未改生产错误文案。

## 2. 本地验证

- `python team-progress/verification/B-004-CP6/validate_terminal_coverage.py`：PASS（38 rows、24/24 refs loadable、missing 0、B36 missing 0）
- `node tests/timeline_ui.test.js`：24/24 PASS
- `python -m py_compile tests/test_timeline_e2e.py`：PASS
- `git diff --check -- tests/test_timeline_e2e.py team-progress/B-004-coverage-map.md`：PASS
- 按指令未在 worker 沙箱运行浏览器；主 agent 外跑完整 24 条。

外跑命令：

```powershell
python -m unittest discover -s tests -p test_timeline_e2e.py
```

## 3. 指纹与边界锁

- `tests/test_timeline_e2e.py` SHA-256：`FE7BDA2F4F3E3C16515EA736258F3C24CF6B6B14D25CD1B122FD7A4F17CC539B`
- 真实 `flowboard.db`：446,464 bytes，mtime `2026-08-12 14:31:25`，SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-task.md/.copilot-state.json/.copilot-message.md` mtime 保持 `2026-08-19 09:48:23 / 14:00:55 / 13:57:38`。

未进入 B-005，未改生产、真实 DB、治理或 `.copilot-*`。
