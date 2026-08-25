# B-005 CP2b coder 唯一最小修正报告

- 时间：2026-08-20（Asia/Shanghai）
- 角色：coder
- 结论：**静态 PASS；具名浏览器测试被已知沙箱 WinError5 阻断**
- 修正对象：仅 `tests/test_i13_e2e.py`

## 1. 精确修改

仅有以下两处 diff：

```diff
+from flowboard.database import SCHEMA_VERSION
-        health=page.evaluate("fetch('/api/health').then(r=>r.json())");self.assertEqual(health,{"status":"ok","schema_version":15})
+        health=page.evaluate("fetch('/api/health').then(r=>r.json())");self.assertEqual(health,{"status":"ok","schema_version":SCHEMA_VERSION})
```

`git diff --numstat`：2 insertions / 1 deletion。没有修改产品代码、其他测试或任何历史 version 15 / checksum / snapshot 断言；本文件不存在其他此类历史断言。

修改后 `tests/test_i13_e2e.py`：

- bytes：3375
- SHA-256：`8A82DB707BDD2290E76891CA7B30FB408871E13C45819149BE343D984E0097E5`

## 2. 静态检查

- `python -X utf8 -m py_compile tests/test_i13_e2e.py`：exit 0。
- `git diff --check -- tests/test_i13_e2e.py`：exit 0；仅有 Git 的 LF→CRLF 工作树提示，不是 diff error。
- `rg` 复核：`schema_version` 当前预期仅引用 `SCHEMA_VERSION`；未残留硬编码 15。

## 3. 具名测试唯一尝试

测试：

```text
test_i13_e2e.I13E2E.test_mobile_atomic_batch_and_admin_backup_surface
```

按约定在当前沙箱只尝试一次。结果为 `Ran 1 test in 0.720s`、exit 1；失败发生在 `setUp` 的 `sync_playwright().start()`，Windows pipe 创建处返回：

```text
PermissionError: [WinError 5] 拒绝访问。
```

浏览器未启动、测试方法及 health 断言均未执行。这是已知环境阻断，不是修改后断言失败；未重复尝试。测试只创建临时数据库并输出 `flowboard-pre-v16-*` 临时备份，未访问真实运行库。

## 4. 不变式

- `flowboard.db` SHA-256：`9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`
- `.copilot-message.md` SHA-256：`FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`
- `.copilot-state.json` SHA-256：`C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`
- `.copilot-task.md` SHA-256：`34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`

以上与 CP2a / planner 冻结指纹一致；未写真实 DB 或旧编排文件。

## 5. 交棒

请主 agent / planner 在已授权的沙箱外环境复跑该具名 Playwright 测试或从 Python 全量起点重启 CP2。本 coder 不自行推进 CP3。
