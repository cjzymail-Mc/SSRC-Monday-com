# B-005 CP2a coder 最小修正报告

- 时间：2026-08-20（Asia/Shanghai）
- 角色：coder
- 结论：**PASS，交 planner 重启 CP2 全量独立验收**
- failure key：`B005_CP2_PY_V16_BASELINE_CONTRACT_STALE`

## 1. 修正边界

先对授权的 7 个旧测试文件中全部 `15` / `pre-v15` 命中做静态分类：

1. **当前最新 schema 合同**：迁移完成后的 `PRAGMA user_version`、备份 manifest / 管理 API 返回的 `schema_version`、迁移目标备份名前缀。此类已改用 `flowboard.database.SCHEMA_VERSION`；备份模式由该常量动态构造。
2. **历史迁移证据**：`schema_migrations WHERE version=15` 与 `flowboard-schema-v15`。此类原样保留；历史旧库 `user_version=6/7/8/9/10/12/13` 等断言也未改。

未修改生产代码、新 timeline 测试、README、coverage map、治理/冻结/历史文档、`.copilot-*` 或真实运行库；未增加 skip，旧测试方法名和数量不变。

## 2. 逐文件变更

- `tests/test_collaboration.py`
  - v12 迁移目标备份名前缀与计数 glob 改为基于 `database.SCHEMA_VERSION` 构造。
  - 迁移后 `PRAGMA user_version` 改为断言 `database.SCHEMA_VERSION`。
- `tests/test_dashboards.py`
  - 导入 `SCHEMA_VERSION`；v10 迁移完成后的当前版本断言引用该常量。
- `tests/test_i12.py`
  - v13 迁移目标备份名前缀和迁移后当前版本引用 `database.SCHEMA_VERSION`。
  - v14/v15 migration checksum 历史断言保持不变。
- `tests/test_i13.py`
  - 导入 `SCHEMA_VERSION`；迁移后当前版本及管理备份 API 当前 schema 断言引用该常量。
  - v15 migration checksum 历史断言保持不变。
- `tests/test_i13_operations.py`
  - 导入 `SCHEMA_VERSION`；普通备份 manifest 与恢复前 safety backup 的当前 schema 断言引用该常量。
- `tests/test_schedule.py`
  - 导入 `SCHEMA_VERSION`；v9 迁移完成后的当前版本断言引用该常量。
- `tests/test_secure_foundation.py`
  - 导入 `SCHEMA_VERSION`；5 处迁移完成后的当前版本断言引用该常量。
  - 旧备份版本、数据保留、FK、integrity、checksum、恢复与幂等断言均未放松。

scoped diff 统计为 7 文件各等量替换：共 21 insertions / 21 deletions，内容仅为上述导入及字面/表达式变化。

## 3. 定向验证

仅复跑 planner 报告列出的 11 个失败方法（不含 Playwright）：

```text
Ran 11 tests in 12.431s
OK
```

覆盖：collaboration 1、I12 1、I13 2、I13 operations 2、secure foundation 5；11 条全部通过。测试使用各自的临时数据库/备份目录。

第一次尝试从 `tests/` 目录调用时，仓库根未进入模块搜索路径，11 条均在加载阶段报 `ModuleNotFoundError: flowboard`，没有执行任何测试方法。未修改代码；修正调用器搜索路径后，对同一 11 个方法得到上述 PASS。该预检失误不是产品 failure key 的复现。

## 4. 静态门禁与不变式

- `python -X utf8 -m py_compile`（授权 7 文件）：exit 0。
- `git diff --check -- <授权 7 文件>`：exit 0；仅有 Git 的 LF→CRLF 工作树提示，不是 diff error。
- 残留 `15` 静态复核：仅 `tests/test_i12.py`、`tests/test_i13.py` 中的 v15 migration version/checksum 历史证据。
- `flowboard.db` SHA-256：`9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`，未变。
- `.copilot-message.md` SHA-256：`FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`，未变。
- `.copilot-state.json` SHA-256：`C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`，未变。
- `.copilot-task.md` SHA-256：`34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`，未变。

## 5. 交棒

`B005_CP2_PY_V16_BASELINE_CONTRACT_STALE` 已按用户授权的最小边界收敛。请 planner 从 Python 全量起点重启 B-005 CP2，并继续 Node、语法和 scoped diff 独立门禁；本报告不替代终验。
