# B-005 CP3 主 Codex 验收报告

日期：2026-08-20
执行模式：按用户裁定，由主 Codex 单 session 连续施工；本报告不冒充独立 planner 签注。

## 四态

| Coverage 行 | 状态 | 证据 |
|---|---|---|
| A01 真实 v15 形状 | PASS | 五个代表存量表均非空，任务 sentinel 5 行 |
| A02 v15→v16 纯增量 | PASS | 五表齐、version 16、migration v16 恰一条 |
| A03 pre-v16 备份 | PASS | 非空、可独立打开、v15、计数和 sentinel 一致 |
| A04 v16 幂等 | PASS | 二次无备份，shape/index/migration count 不变 |
| A05 计数/FK/integrity | PASS | 旧表计数不变，新五表全空，FK=[]，integrity=ok |
| A06 故障回滚与离线恢复 | PASS | authorizer 阳性对照无半表；CLI backup/verify/restore/再迁移全绿 |

## 重要修复

独立故障注入发现 `_migration_v16` 使用 `executescript()` 会越过外层事务并留下半表。经 mc-expert（Codex custom 模拟、非 Claude 原生）高置信陪审，复用仓内 `_execute_ddl()` 做最小修复。schema 字面和业务行为均未改变。

## 终值

- CP3 verifier：exit 0。
- timeline 回归：29/29。
- py_compile：exit 0。
- 全仓 `git diff --check`：exit 0。
- 真实运行库及弃用编排指纹：不变。

详细证据见 `team-progress/verification/B-005-CP3/results.md`。

**结论：CP3 PASS；允许进入 CP4。**
