# B-005 CP2 独立全量自动化验收报告

- 时间：2026-08-20 15:12–15:16 (Asia/Shanghai)
- 角色：planner 独立验收
- 结论：**REWORK / CP2 熔断**
- failure key：`B005_CP2_PY_V16_BASELINE_CONTRACT_STALE`
- 环境阻断键：`B005_CP2_PLAYWRIGHT_SANDBOX_WINERROR5`

## 1. 冻结盘面与不变式

执行前后指纹一致：

| 对象 | SHA-256 |
|---|---|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` |

`flowboard.db` 属性仍为 446464 bytes，mtime `2026-08-12 14:31:25`；未写真实运行库，未改旧编排文件。

## 2. README Python 全量：非零

命令：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v
```

结果：exit `1`，`Ran 118 tests in 234.654s`，`FAILED (failures=11, errors=13)`，无 `skipped` 记录。预期动态发现为 142；`test_timeline_e2e.TimelineProductionE2E.setUpClass` 因 Playwright 启动失败，该类 24 条未进入运行计数，`118 + 24 = 142`。

原始日志：`team-progress/verification/B-005-CP2/python-unittest-full.log`

- bytes：177497
- SHA-256：`B6F02C07E5D85105D031F7CAEB6C5085CD1C9B9CBB99DD200C0010D9CE9DB29F`

### 2.1 确定性产品/测试合同失配

11 个 FAIL 可归为同一根因：生产迁移最新 schema 已为 v16，但历史全量测试仍断言 v15 或 `pre-v15` 备份名。

- `test_collaboration...test_v12_to_v14_subscription_merge_backup_restore_and_idempotence`：期待 `v12-pre-v15-`，实际已迁移到 v16。
- `test_i12...test_v13_to_v14_backup_restore_and_idempotence`：期待 `v13-pre-v15-`。
- `test_i13...test_admin_backup_api_surface_is_verified_and_viewer_is_denied`：期待 schema 15，实际 16。
- `test_i13...test_v15_description_retention_and_five_atomic_batch_operations`：期待 schema 15，实际 16。
- `test_i13_operations...test_backup_manifest_corruption_retention_and_real_restore_with_blob`：期待 manifest schema 15，实际 16。
- `test_i13_operations...test_restore_injected_failure_rolls_back_current_database_and_attachment`：期待 safety backup schema 15，实际 16。
- `test_secure_foundation...test_migration_preserves_existing_tasks_and_creates_backup`：期待 schema 15，实际 16。
- `test_secure_foundation...test_v1_to_v2_migration_preserves_data_and_activity`：期待 schema 15，实际 16。
- `test_secure_foundation...test_v6_to_v7_migration_backup_restore_and_idempotence`：期待 schema 15，实际 16。
- `test_secure_foundation...test_v7_to_v8_migration_backup_restore_and_idempotence`：期待 schema 15，实际 16。
- `test_secure_foundation...test_v8_to_v9_migration_backup_restore_and_idempotence`：期待 schema 15，实际 16。

另有 3 个非浏览器 ERROR 是同类断言失败后 SQLite 连接未走完正常关闭路径，随后在 `TemporaryDirectory` 清理时命中 `WinError 32`：

- `test_dashboards...test_v10_to_v11_backup_preserves_views_and_is_idempotent`（首先失配 `16 != 15`）。
- `test_i13...test_v15_description_retention_and_five_atomic_batch_operations` tearDown。
- `test_schedule...test_v9_to_latest_preserves_saved_views_backup_and_is_idempotent`。

这一类失败与 Playwright 沙箱限制无关，不能签 PASS。

### 2.2 Playwright 沙箱阻断

按合同只尝试一次。真实 Chromium 测试在 `sync_playwright().start()` 创建子进程时命中：

```text
PermissionError: [WinError 5] 拒绝访问。
```

受影响为 collaboration E2E 1、I12 E2E 1、I13 E2E 1、timeline E2E 类 24、views E2E 6。需主 agent 在已授权的沙箱外/提权环境执行同一 README 全量命令；不得跳过这些断言。

## 3. 未执行门禁

根据委托中“任何产品测试非零给 failure key 且停”，本轮在 Python 全量非零后立即熔断，未继续执行：

- Node 全量 6 文件。
- Python `py_compile`。
- 所有正式 JS `node --check`。
- 字面 `git diff --check` 及 scoped 定位。

上述必须在 `B005_CP2_PY_V16_BASELINE_CONTRACT_STALE` 收敛后重启同一 CP2，不能以本轮部分结果替代终验。

## 4. 最小返工裁定

1. 仅更新受 v16 最新迁移影响的历史测试预期：schema/version/backup prefix 应与 v16 合同一致，不放宽其他数据保全、幂等、integrity/foreign-key 断言。
2. 确保断言失败时 SQLite 连接也能关闭，避免 `WinError 32` 遮蔽首因；这不能用于隐藏上述 `16 != 15`。
3. 修正后在同一冻结盘面从 Python 全量开始重跑 CP2，然后再跑 Node/语法/diff 门禁。

---

## 5. Recovery 追加验收（2026-08-20 15:37–15:41）

> 本节仅追加 recovery 证据；上文首轮 REWORK 历史保留，不覆写。

- 功能自动化结论：**PASS（非浏览器 Python + Node + 语法）**
- 字面仓库卫生结论：**CONFLICT**
- 字面 failure key：`B005_CP2_LITERAL_DIFFCHECK_HISTORICAL_MCPLAN_WHITESPACE`
- 完整 142 Chromium 终值：**PENDING_MAIN_AGENT_EXTERNAL_RUN**

### 5.1 coder CP2a diff 独立审计：合规

审计范围为 7 个历史测试文件：

- `tests/test_collaboration.py`
- `tests/test_dashboards.py`
- `tests/test_i12.py`
- `tests/test_i13.py`
- `tests/test_i13_operations.py`
- `tests/test_schedule.py`
- `tests/test_secure_foundation.py`

`git diff --stat -- tests` 在这 7 文件上为 21 insertions / 21 deletions。逐 hunk 审计确认：

1. 仅新增/复用 `SCHEMA_VERSION`，将“最新 schema”断言由字面 15 改为动态常量。
2. 仅将 `v12-pre-v15-` / `v13-pre-v15-` 改为 `pre-v{SCHEMA_VERSION}` 派生前缀/匹配模式。
3. 历史旧库自身版本（9/10/12/13）、各历史 migration checksum、数据保全、FK/integrity、幂等、备份恢复和权限断言未删除、未放宽。
4. 7 文件具名测试方法数 `67 -> 67`；skip decorator / `skipTest` 仍为 0。

### 5.2 Python 非浏览器全量：PASS

因首轮已按合同在沙箱内尝试过一次 Playwright，recovery 不重复触发已知 `WinError 5`，而是独立发现并执行所有非 `*_e2e.py` 模块。

- 发现：10 modules / 109 test cases。
- 执行：`Ran 109 tests in 219.838s`。
- 结果：`OK`，exit `0`，skip `0`。
- 首轮 11 个 schema FAIL 和 3 个连带清理 ERROR 均消失。

证据：

- `python-nonbrowser-modules.txt`：SHA-256 `9302664BA294CF3C33AF4D8A8C59024256A1FBB0F5A2776DA3A01E6088BF68EA`
- `python-nonbrowser-discovery.log`：SHA-256 `DF82F17B880918192DA8D62466A1E5FD0E294AB9372CF9F2554A842D5B8A79F6`
- `python-nonbrowser-recovery.log`：74041 bytes，SHA-256 `5B1898FF0658F543C25879F97579E2FB483B9563318CCFDFEFAAF6C170340A8B`

### 5.3 Node 六文件全量：PASS（提权重跑）

发现文件数为 6。沙箱首跑六文件全部在 `node:test` worker 创建处命中 `spawn EPERM`，没有进入测试体；保留日志后，以完全相同的 6 文件在受控提权环境重跑：

- tests `6`，pass `6`，fail `0`，skipped `0`，todo `0`。
- duration `532.6026ms`，exit `0`。

证据：

- `node-test-files.txt`：SHA-256 `3DE0A579020566DBF9EDE51728E3FACE92651684612FCE21FF2BC8745BC1E2A4`
- `node-full-recovery.log`（沙箱 EPERM 原始记录）：SHA-256 `B6722849FFBB2BB3BCDE07C0DFE4B3CA297973A7B55D502D56C8E664BB4EF6B7`
- `node-full-recovery-elevated.log`（终值）：SHA-256 `D58920FA14E45EAFA25A1AE9976970AA51446926E5D31F43E12D63927FF6B308`

### 5.4 语法门禁：PASS

- Python：仓库根 `*.py` + `flowboard/**/*.py` + `tests/test_*.py`，去重合计 28 文件，`python -X utf8 -m py_compile ...` exit `0`。
- JavaScript：仓库根 `*.js` + `tests/*.test.js`，去重合计 13 文件，逐一 `node --check`，13/13 exit `0`。

证据：`py-compile-files.txt` / `py-compile.log` / `node-check-files.txt` / `node-check.log`。

### 5.5 字面 `git diff --check`：CONFLICT

不带 pathspec 的字面命令 exit `2`，确定命中既存历史文件：

```text
mc-plan/Mc思考01-阶段完工-下阶段计划.md:1053: trailing whitespace.
mc-plan/Mc思考01-阶段完工-下阶段计划.md:1195: new blank line at EOF.
```

依委托约束，planner 未修改历史 `mc-plan`，也不将 scoped 结果冒充字面 PASS。仅作定位的产品/tests scoped `git diff --check -- README.md app.js flowboard index.html server.py tests` exit `0`。

证据：

- `git-diff-check-literal.log`：SHA-256 `095F91EAD8999E05C154E73C0A4AF0FD16DD2FD1AF20D24B0A1F188DE5B71E94`
- `git-diff-check-product-tests-scoped.log`：SHA-256 `A11F7F2B6D91C60B03ABFD177BF6A069277CA983D9839C26E30A5750B5F44696`

### 5.6 不变式复核

recovery 后指纹仍与首轮前完全相同：

| 对象 | SHA-256 |
|---|---|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` |

`flowboard.db` 仍为 446464 bytes，mtime `2026-08-12 14:31:25`。

## 7. 用户裁定后的 D07 恢复与 CP2 最终签注

用户于 2026-08-20 明确要求主 Codex 单 session 继续完成剩余计划；该授权承接上文已呈报的“仅空白卫生”最小裁定。实际处理严格限定于历史文件 `mc-plan/Mc思考01-阶段完工-下阶段计划.md`：

1. 删除原 line 1053 的两个行尾空格；
2. 删除 EOF 多余空行；
3. 首次复跑后又暴露同一文件标题 `## 注意适当放权，让 codex 自主选择施工方式，可能会更好` 的一个既存尾空格，继续仅删除该空格。

没有改动任何文字、时序或历史语义。最终从仓库根运行字面命令 `git diff --check`，exit `0`；输出仅含 Git 的 LF/CRLF 提示，无 whitespace error。

| 行 | 最终四态 | 依据 |
|---|---|---|
| D03 Python 全量 | `PASS` | 142/142，exit 0，真实 Chromium |
| D04 Node 全量 | `PASS` | 6/6，skip 0 |
| D05 Python 语法 | `PASS` | 28/28，并复核 CP2b |
| D06 JavaScript 语法 | `PASS` | 13/13 |
| D07 全仓补丁空白门 | `PASS` | 字面 `git diff --check` exit 0 |

CP2 最终统计：`PASS=5 / GAP-B005=0 / CONFLICT=0 / OUT_OF_SCOPE=0`。

**最终结论：CP2 PASS；允许进入 CP3。** 上文首轮 REWORK、恢复期 GAP 与 failure key 均保留为历史，不回写成从未发生。

### 5.7 CP2 终值边界

planner 本地 recovery 可签“非浏览器功能门禁已收敛”，但 B-005 CP2 全局终签仍需同时合并：

1. 主 agent 在沙箱外执行的完整 142 条（含真实 Chromium）结果。
2. 用户/主 agent 对 `B005_CP2_LITERAL_DIFFCHECK_HISTORICAL_MCPLAN_WHITESPACE` 作范围裁定：修正历史文件，或显式接受该既存冲突。

---

## 6. CP2b + 完整 142 终值追加（2026-08-20）

> 本节是 CP2 当前最新终值，证据与状态分类均超越上文中的临时等待/分类；上文作为施工历史保留。

### 6.1 CP2b 单文件 diff 独立审计：PASS

对 `tests/test_i13_e2e.py` 的完整 diff 逐 hunk 审计：

```diff
+from flowboard.database import SCHEMA_VERSION
-        ... self.assertEqual(health,{"status":"ok","schema_version":15})
+        ... self.assertEqual(health,{"status":"ok","schema_version":SCHEMA_VERSION})
```

- `git diff --stat`：2 insertions / 1 deletion。
- 仅将 `/api/health` 的“当前 schema”断言改为生产单一常量；未更改浏览器交互、批量操作、备份或权限断言。
- 测试方法数 `1 -> 1`，skip `0`。
- 文件 3375 bytes，SHA-256 `8A82DB707BDD2290E76891CA7B30FB408871E13C45819149BE343D984E0097E5`。
- planner 独立复核：单文件 `py_compile` exit `0`，单文件 `git diff --check` exit `0`。

静态审计日志：`cp2b-static-audit.log`，SHA-256 `6AA4B49646601801B8D34F8BEF06C6D7CD8EC8029ADBF82740348F53ABC624E1`。

### 6.2 主 agent 沙箱外真实 Chromium 终值：PASS

CP2a 后的第二次精确全量回执曾稳定暴露唯一漏网项：`tests/test_i13_e2e.py:29` 仍硬编码当前 schema 15；该项与前轮同属 `B005_CP2_PY_V16_BASELINE_CONTRACT_STALE`，当时已按同键两次熔断。用户授权 CP2b 单点修正后，主 agent 在已授权的沙箱外环境复跑具名真实 Chromium：

```text
test_i13_e2e.I13E2E.test_mobile_atomic_batch_and_admin_backup_surface
Ran 1 test in 4.257s
OK
```

结论：1/1 PASS，真实浏览器已进入测试体并通过 health 当前 schema 断言。

### 6.3 主 agent 沙箱外完整 Python 全量：PASS

命令：

```powershell
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

过滤输出终值：

```text
EXIT_CODE=0
Ran 142 tests in 323.846s
OK
```

结论：142/142 PASS，含真实 Chromium；回执中无 failure / error / skip。`B005_CP2_PY_V16_BASELINE_CONTRACT_STALE` 已收敛。

主 agent 终值回执摘要已落盘为 `main-agent-external-python-results.md`（1393 bytes，SHA-256 `421B6152DA165710BFF3B28ADB27C4840677A426C70266D9130F362FED94A863`）。该文件明确标注证据来源为主 agent 终端回执，planner 不冒充持有未落盘的原始全量 console。

### 6.4 CP2 严格四态终值

`team-progress/B-005-coverage-map.md` 规定状态词只允许 `PASS` / `GAP-B005` / `CONFLICT` / `OUT_OF_SCOPE`，且 D07 明文规定：既存 mc-plan 尾空白若导致失败，必须如实报 GAP。因此本节对上文临时 `CONFLICT` 分类作正式纠偏：

| 行 | 终值 | 依据 |
|---|---|---|
| D03 Python 全量 | `PASS` | 完整 142/142，exit 0，真实 Chromium |
| D04 Node 全量 | `PASS` | 提权环境 6/6，skip 0 |
| D05 Python 语法 | `PASS` | 原 28 文件全绿；CP2b 单文件修改后再 `py_compile` exit 0 |
| D06 JavaScript 语法 | `PASS` | 13/13 `node --check` exit 0；CP2b 未改 JS |
| D07 全仓补丁空白门 | `GAP-B005` | 字面 `git diff --check` exit 2，仅命中既存历史 mc-plan 两处尾白 |

CP2 切片统计：`PASS=4 / GAP-B005=1 / CONFLICT=0 / OUT_OF_SCOPE=0`。

因 D07 仍为 `GAP-B005`，**planner 不签 CP2 PASS；当前编排状态为 `WAIT_HUMAN`**。

### 6.5 D07 终值复核与最小人工裁定

CP2b 后重跑不带 pathspec 的字面 `git diff --check`，仍为 exit `2`，且唯一差错仍是：

```text
mc-plan/Mc思考01-阶段完工-下阶段计划.md:1053: trailing whitespace.
mc-plan/Mc思考01-阶段完工-下阶段计划.md:1195: new blank line at EOF.
```

- 日志：`git-diff-check-literal-post-cp2b.log`，SHA-256 `A88B9E349FCCAE69E9C415D4ED28E1A35CEC1C44B076B5A56BD9986CD304DBA0`。
- 只作定位的产品/tests scoped 结果仍 exit `0`：`git-diff-check-product-tests-post-cp2b.log`，SHA-256 `E810D284C79915EDDDCEF374695B50D76A5E517B39E619E8F08C0260971AECD3`。

**推荐的最小人工裁定**：用户显式授权一次“仅空白卫生”例外，允许删除 line 1053 的两个行尾空格和 EOF 多余空行；不改任何文字、时序或历史语义。授权后只需重跑字面 `git diff --check`与指纹锁，D07 才可由 `GAP-B005` 转 `PASS`。

备选裁定：用户显式豁免 D07 的该既存历史噪声；若选此路径，必须保留字面 exit 2 记录和豁免来源，不得把命令本身伪记为 exit 0。

### 6.6 不变式终核

CP2b 及外跑回执落盘后，真实运行库与弃用编排仍与 CP0 指纹相同：

| 对象 | SHA-256 |
|---|---|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` |

`flowboard.db` 仍为 446464 bytes，mtime `2026-08-12 14:31:25`。
