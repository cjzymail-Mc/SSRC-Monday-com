# B-005 CP2 主 agent 沙箱外 Python 终值回执

- 日期：2026-08-20 (Asia/Shanghai)
- 证据来源：主 agent 在已授权的沙箱外环境执行后向 planner 传递的终端终值回执。
- planner 边界：本文仅如实记录回执，不声称持有未落盘的原始全量 console 文件。

## 1. CP2a 后的熔断历史

1. 第一次 post-CP2a 完整全量出现 1 FAIL + 1 ERROR，但输出被截断；疑似具名项分别复跑为 PASS。
2. 第二次使用过滤输出精确得到：`Ran 142 tests in 344.731s`，`failures=1`。
3. 唯一失败定位到 `tests/test_i13_e2e.py:29`：`/api/health` 仍硬编码期待 `schema_version: 15`，实际为 16。
4. 失败归类到已有 failure key `B005_CP2_PY_V16_BASELINE_CONTRACT_STALE`，且连续两次全量出现，当时按纪律停工。

## 2. CP2b 后具名真实 Chromium

具名测试：

```text
test_i13_e2e.I13E2E.test_mobile_atomic_batch_and_admin_backup_surface
```

终值：

```text
Ran 1 test in 4.257s
OK
```

结论：PASS；真实 Chromium 已进入测试体并通过 `/api/health` 当前 schema 断言。

## 3. CP2b 后最终完整全量

命令：

```powershell
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

终值：

```text
EXIT_CODE=0
Ran 142 tests in 323.846s
OK
```

结论：PASS；完整动态发现 142 条，包含真实 Chromium，无 failure/error/skip 回执。
