# B-005 coder report · CP1 旧测试防篡改审计

日期：2026-08-20  
基线：Gate 3 commit `2e906c5`  
结论：**PASS（coder 审计结果，等待 planner 独立复核）**。基线 12 个 Python + 5 个 Node 测试文件全部存在，每个文件的 Git clean-filter blob 与 `2e906c5` 完全相同；无删除、改名、用例减少、skip/expectedFailure/skipTest 或断言放松。本 CP 未修改任何测试或生产文件，也未执行 CP2 全量回归。

## 1. 边界与审计方法

- 权威旧清单：`git ls-tree -r --name-only 2e906c5 -- tests`，筛得 12 个 `test_*.py` 与 5 个 `*.test.js`。
- 对每个旧文件同时执行：存在性检查、`git diff --quiet 2e906c5 -- <file>`、基线 blob 与 `git hash-object --path=<file> <file>` 比对。共17 个文件均为 `exists=True / diffExit=0 / blob 相同`。
- `git diff --name-status --find-renames 2e906c5 -- tests` 输出为空，因此无旧测试删除、改名或内容改动。
- 基线与当前工作树分别搜索 `unittest.skip/skipIf/skipUnless/expectedFailure`、`pytest.mark.skip`、`@skip` 和 `skipTest(`，两次均为零命中（搜索 exit 1）。
- 只读调用 `unittest.defaultTestLoader.discover('tests', pattern='test_*.py')` 枚举当前用例，再以 AST 统计交叉核对；两者都得到 142 个 Python 方法。未运行任何用例体。

## 2. Gate 3 旧 Python 清单（79 方法 / 12 文件）

| 当前文件 | loader 可发现方法数 | `2e906c5` blob = 当前 clean blob | 结论 |
|---|---:|---|---|
| `tests/test_collaboration.py` | 6 | `a2a6c9d69cfb915e6ee1184f5c5ef47fc1f1dcd8` | PASS |
| `tests/test_collaboration_e2e.py` | 1 | `57fb047f6503432b5b54e4186a6e16e90afcbd49` | PASS |
| `tests/test_collaboration_http.py` | 3 | `6dfb362665b1c2ce4a52ec74d769b7d453667f6e` | PASS |
| `tests/test_dashboards.py` | 12 | `4b09e9a71e60636b91cab4af916a7df0581ab18e` | PASS |
| `tests/test_i12.py` | 9 | `41d703dcdc9a93eac93b379454283a2560a1e940` | PASS |
| `tests/test_i12_e2e.py` | 1 | `5b8548fc2bfadd398d2657ce9279e0c5b6094626` | PASS |
| `tests/test_i13.py` | 4 | `7d09e189051790c33909dfafd1e43bbdb1e521eb` | PASS |
| `tests/test_i13_e2e.py` | 1 | `d3aa7a8257a4e656e4d1a0999f8ae2df0b928222` | PASS |
| `tests/test_i13_operations.py` | 3 | `f406afe21030d8955cd362d9ea567698d352f1df` | PASS |
| `tests/test_schedule.py` | 7 | `b33c49dcec4ff8c9284c6319ddd83dd1464a36d6` | PASS |
| `tests/test_secure_foundation.py` | 26 | `10d76a13d8e334d3fdb9e220d8ff3fddbaebf50d` | PASS |
| `tests/test_views_e2e.py` | 6 | `e84f876e36d25d21052b26747338947113dfd3bb` | PASS |
| **合计** | **79** | 12/12 匹配 | **PASS** |

当前 loader 枚举的这 79 个旧 test ID 排序后 SHA-256 为 `C00331E15FE246324DAD859945DB0F52FA828713BB30C4D9E35B96858574159D`。因 12 个文件的归一化 blob 均与基线相同，用例名、decorator、fixture 与断言体均没有变更。

### 行尾状态特别裁定

`git status --short` 对 `tests/test_collaboration.py` 和 `tests/test_schedule.py` 显示 `M`，Git 同时警告工作树 LF 在 Git 下次写入时将转为 CRLF。这是行尾/working-tree stat 信号，不是可观察内容差异：两文件的 `git diff --quiet` 均为 0，且 `git hash-object --path` 结果分别与基线 blob `a2a6c9d...` / `b33c49d...` 精确相同。本 CP 没有用 `update-index` 或改写文件来“消除”该状态。

## 3. Gate 3 旧 Node 清单（5 文件）

| 当前文件 | `2e906c5` blob = 当前 clean blob | 结论 |
|---|---|---|
| `tests/dashboard_ui.test.js` | `d42245072d019a97cc5a2aab53c4fdb23c17bef9` | PASS |
| `tests/i12_ui.test.js` | `8a0b82d5a9b17e0044920e7180e37f94495a4236` | PASS |
| `tests/schedule_ui.test.js` | `8bec027968fde333307a91514c3e905e96aaf87c` | PASS |
| `tests/view_state.test.js` | `5259cf07393c32ab21b2e72f4ec284a818d23671` | PASS |
| `tests/view_ui.test.js` | `c998ee31d9e810d92478997045879fb1576730a0` | PASS |

这些 Node 文件沿用第一阶段的混合 harness（`node:test` 与自定义 assertion script），因此 Gate 3 冻结口径是“5 个测试文件”，不把文件数冒充为 test method 数。CP2 才会在当前终值工作树动态执行全部 Node 文件。

## 4. 新增 timeline 测试分栏（不替代旧基线）

| 新增文件 | 当前可发现/静态明示量 | 性质 |
|---|---:|---|
| `tests/test_timeline.py` | 29 Python test methods | timeline service/迁移/Excel 领域测试 |
| `tests/test_timeline_http.py` | 10 Python test methods | R01–R11 真实 HTTP 黑盒测试 |
| `tests/test_timeline_e2e.py` | 24 Python test methods | 真实 Chromium 生产 UI 旅程 |
| `tests/timeline_ui.test.js` | 24 个明示 `ok(...)` assertion | timeline Node 快测文件 |

当前 Python 动态可发现总数为 **142 = 旧 79 + timeline 63**，共 15 个 Python 文件；当前 Node 清单为 **6 = 旧 5 + timeline 1 个文件**。因此“79 + 5”只是 Gate 3 旧回归基线，不是当前全仓测试总数。timeline 63 个 Python test ID 排序后 SHA-256 为 `5E300E29D6F22EF50631F14E8A7ADAEADC81E4B11953F64E2562029B7EC23CF5`；全部 142 个为 `1B50823CAECC39970601FF6CE5AF454204DECB9C64380DB6CC0C6788E90D46DD`。

## 5. 真实库与弃用编排锁

本 CP 只做 hash/stat，未打开或写入真实库，也未改写 `.copilot-*`。终值与 CP0 指纹相同：

| 对象 | SHA-256 | bytes | LastWriteTime (Asia/Shanghai) |
|---|---|---:|---|
| `flowboard.db` | `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D` | 446464 | `2026-08-12 14:31:25.4654747 +08:00` |
| `.copilot-state.json` | `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7` | 2144 | `2026-08-19 14:00:55.4931559 +08:00` |
| `.copilot-task.md` | `34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA` | 13690 | `2026-08-19 09:48:23.4936218 +08:00` |
| `.copilot-message.md` | `FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72` | 7317 | `2026-08-19 13:57:38.6945649 +08:00` |

## 6. CP1 交接

- D01：PASS——12 Python + 5 Node 旧文件 17/17 存在，无删除/改名。
- D02：PASS——17/17 归一化 blob 精确匹配，79 个旧 Python 方法仍可发现，skip/expectedFailure/skipTest 零命中，无断言放松。
- failure key：无。
- 修改集：仅新增本报告；未改 `tests/`、生产、README、coverage map、planner validator、治理/冻结文档、`.copilot-*` 或真实 DB。
- 本报告只申请 planner 独立复核 CP1；不代替 CP2 的 Python/Node 全量动态回归，也不授权跳过 CP2。
