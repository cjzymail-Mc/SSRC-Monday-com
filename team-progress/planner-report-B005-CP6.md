# B-005 planner report · CP6 independent terminal sign-off

日期：2026-08-20
角色：独立终签 reviewer（未修改生产、tests、README、coverage map、治理/冻结文档、真实库或 `.copilot-*`）
裁定：**CP6 PASS；B-005 自动门禁收口；唯一终态为 `WAIT_GATE5_HUMAN`。**

这不是 Done、门 5 PASS、真实库已迁移、已 commit/push、已发布、已部署或已上线。

## 独立终值

CP6 可复跑验证器最终 exit 0。32 条 coverage 义务唯一且完整，终态为：`PASS=25 / OUT_OF_SCOPE=7 / GAP-B005=0 / CONFLICT=0`。CP0 map 是施工时点冻结记录，其历史 `GAP-B005` 单元不回写；本报告和 CP6 validator 承载终值签注。

| 条目 | 终态 | 条目 | 终态 | 条目 | 终态 | 条目 | 终态 |
|---|---|---|---|---|---|---|---|
| A01 | PASS | A02 | PASS | A03 | PASS | A04 | PASS |
| A05 | PASS | A06 | PASS | A07 | PASS | B01 | PASS |
| B02 | PASS | C01 | PASS | D01 | PASS | D02 | PASS |
| D03 | PASS | D04 | PASS | D05 | PASS | D06 | PASS |
| D07 | PASS | D08 | PASS | D09 | PASS | D10 | PASS |
| D11 | PASS | D12 | PASS | D13 | PASS | E01 | PASS |
| E02 | PASS | F01 | OUT_OF_SCOPE | F02 | OUT_OF_SCOPE | F03 | OUT_OF_SCOPE |
| F04 | OUT_OF_SCOPE | F05 | OUT_OF_SCOPE | F06 | OUT_OF_SCOPE | F07 | OUT_OF_SCOPE |

A07/D13 的 CP0→CP6 终值锁已独立关闭：真实 `flowboard.db` 及 `.copilot-state/task/message` 的 SHA-256、bytes、mtime_ns 与 CP0 完全相同。真实库只读打开仍为 schema v15，`integrity_check=ok`。

## 动态复跑与全量回执

独立代表性复跑全部通过：

- CP3/CP4/CP5 三个 validator：均 exit 0 / PASS。
- timeline service：29/29，26.869s，OK。
- timeline HTTP：10/10，18.870s，OK。
- Node 全量：6/6 文件、skip 0、exit 0。
- 全仓 Python `py_compile`：54/54，exit 0。
- 全仓 JavaScript `node --check`：13/13，exit 0。
- 字面全仓 `git diff --check`：exit 0，仅 LF/CRLF 提示，无 whitespace error。

主 agent 另在沙箱外按 README 命令完成修复后全量：exit 0，`Ran 142 tests in 413.528s`，`OK`，包含真实 Chromium。本 reviewer 将其作为主 agent 外部动态证据合并，不冒充由本 reviewer 本地执行。

Node 首次沙箱内尝试命中一次 `B005_CP6_NODE_SANDBOX_SPAWN_EPERM`，六文件均在 test body 前被 Windows sandbox 阻止 worker spawn；同命令沙箱外 6/6 PASS，因此按环境键记录，不计产品 failure。

## 重点审计裁定

### v16 事务修复

`_migration_v16` 当前只有一个 `_execute_ddl(conn, <DDL literal>)`，没有 `executescript()`。DDL 字面仍是冻结的五表五索引，DDL SHA-256 为 `026655EE79D45088B2D22CD23DD3E72EE08B3C8FD8C26F0C31A8A1FDA48FF88D`；schema 列、约束、索引、migration checksum、API 与业务规则未随事务修复改变。

CP3 authorizer 阳性对照拒绝第二张表创建后，库保持完整 v15、无 timeline 半表、无 v16 migration row；正常迁移、幂等、pre-v16 备份、CLI verify/restore/再迁移均通过。故 `executescript()` 隐式提交根因已由最小修复真实关闭，而非只改报告。

### 旧测试授权差异

Gate 3 的 12 个 Python + 5 个 Node 旧文件仍全在，旧 Python 方法 79/79，skip 0。相对 `2e906c5`，旧测试变化严格等于用户授权的 8 个 Python 文件；仅把“当前 schema/当前备份前缀”的过期 v15 预期改为 `SCHEMA_VERSION`。历史 v7/v8/v9/v10/v11/v14/v15 checksum、旧备份 schema、存量数据、FK/integrity、权限与恢复断言均保留；旧 Node 零修改。

因此 CP1 的早期“17 文件 blob 完全相同”只保留为当时历史，终签采用 CP4/CP6 的授权差异终值，不将过期口径冒充当前事实。

### 文档与范围

README 明确自动终点只是 `WAIT_GATE5_HUMAN`，且真实库仍为 v15；没有冒充门 5、正式迁移或上线完成。CP4/CP6 复核未发现暗色运行态/主题切换、周看板、timeline 改名/恢复、md/json 导入、`project_ids` 导出、分页/缓存或冻结范围外未来能力。

F01–F07 继续保留给 Gate 5/用户显式授权：真实 2–3 项目试用、精确色值/强磁吸/像素微调、约 15 分钟手工冒烟、真机与部署环境、真实库 v15→v16、commit/push/发布/上线决定，以及未来能力新立项。

## 验证器历史

CP6 无产品 failure key。另有两个各一次且互不相同的 validator-only 键：路径夹具 `B005_CP6_CP3_NONZERO`、Git LF/CRLF 警告解析 `B005_CP6_OLD_TEST_DIFF_SCOPE`；均只修 CP6 验证器后转绿，未触碰产品/tests 或降低门禁。

## 正式证据

- `team-progress/verification/B-005-CP6/verify_cp6.py`
- `team-progress/verification/B-005-CP6/results.md`
- `team-progress/verification/B-005-CP3/results.md`
- `team-progress/verification/B-005-CP4/evidence-matrix.md`
- `team-progress/verification/B-005-CP5/results.md`
- `team-progress/B-005-WAIT_GATE5_HUMAN.md`

**最终签注：门 4 自动施工计划已完成；当前且最高状态为 `WAIT_GATE5_HUMAN`。门 5 仍未执行。**
