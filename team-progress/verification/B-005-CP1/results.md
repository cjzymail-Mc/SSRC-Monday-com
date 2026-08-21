# B-005 CP1 独立审计结果

日期：2026-08-20
命令：`python team-progress/verification/B-005-CP1/validate_cp1.py`
终值：`exit 0` / `status=PASS` / `errors=[]`
验证器 SHA-256：`EBA7EA631A03AEE8F4914D3288AB01AD05316AE8A725D6EF38ABC58D632D1846`

## 基线与文件完整性

- Gate 3 commit 完整值：`2e906c5467bd2a9683e069964d73db529471edb8`。
- 基线清单：12 个 Python 文件、5 个 Node 文件；当前 17/17 逐个存在。
- `git hash-object --path=<file> <file>` 的 clean-filter blob 与 `<baseline>:<file>` 逐个相同。
- `git diff --name-status --find-renames 2e906c5 -- <17 files>`：exit 0、stdout 空。
- `test_collaboration.py` / `test_schedule.py` 仅出现 Git 的 LF→CRLF 工作树提示；两文件 clean-filter blob 分别仍是 `a2a6c9d...` / `b33c49d...`，不是可观察内容修改。

| 旧测试 | 基线 blob = 当前 clean-filter blob |
|---|---|
| `test_collaboration.py` | `a2a6c9d69cfb915e6ee1184f5c5ef47fc1f1dcd8` |
| `test_collaboration_e2e.py` | `57fb047f6503432b5b54e4186a6e16e90afcbd49` |
| `test_collaboration_http.py` | `6dfb362665b1c2ce4a52ec74d769b7d453667f6e` |
| `test_dashboards.py` | `4b09e9a71e60636b91cab4af916a7df0581ab18e` |
| `test_i12.py` | `41d703dcdc9a93eac93b379454283a2560a1e940` |
| `test_i12_e2e.py` | `5b8548fc2bfadd398d2657ce9279e0c5b6094626` |
| `test_i13.py` | `7d09e189051790c33909dfafd1e43bbdb1e521eb` |
| `test_i13_e2e.py` | `d3aa7a8257a4e656e4d1a0999f8ae2df0b928222` |
| `test_i13_operations.py` | `f406afe21030d8955cd362d9ea567698d352f1df` |
| `test_schedule.py` | `b33c49dcec4ff8c9284c6319ddd83dd1464a36d6` |
| `test_secure_foundation.py` | `10d76a13d8e334d3fdb9e220d8ff3fddbaebf50d` |
| `test_views_e2e.py` | `e84f876e36d25d21052b26747338947113dfd3bb` |
| `dashboard_ui.test.js` | `d42245072d019a97cc5a2aab53c4fdb23c17bef9` |
| `i12_ui.test.js` | `8a0b82d5a9b17e0044920e7180e37f94495a4236` |
| `schedule_ui.test.js` | `8bec027968fde333307a91514c3e905e96aaf87c` |
| `view_state.test.js` | `5259cf07393c32ab21b2e72f4ec284a818d23671` |
| `view_ui.test.js` | `c998ee31d9e810d92478997045879fb1576730a0` |

## 用例与 skip 双算

| 口径 | 结果 |
|---|---:|
| 基线旧 Python AST 方法 | 79 |
| 当前旧 Python AST 方法 | 79 |
| 当前旧 Python loader 可发现 | 79 |
| timeline AST / loader | 63 / 63 |
| timeline 分栏 | 29 service + 10 HTTP + 24 Chromium |
| 当前 Python AST / loader 总数 | 142 / 142 |
| 当前 Node 文件 | 6 = 旧 5 + timeline 1 |

测试 ID 排序哈希：旧 79=`C00331E15FE246324DAD859945DB0F52FA828713BB30C4D9E35B96858574159D`；timeline 63=`5E300E29D6F22EF50631F14E8A7ADAEADC81E4B11953F64E2562029B7EC23CF5`；全部 142=`1B50823CAECC39970601FF6CE5AF454204DECB9C64380DB6CC0C6788E90D46DD`。

当前 `tests/` 的 Python/Node 文本扫描对 `unittest.skip/skipIf/skipUnless/expectedFailure`、`pytest.mark.skip/skipif`、`skipTest(`、Node `test/it/describe.skip` 及 `skip: true` 均为零命中。旧 Node 文件采用混合 harness，故以 5/5 精确 blob 为防篡改强证据，不用单一 `test(...)` 正则低估自定义 assertion script。

## 阳性对照与锁盘

- 内存清单删除一个旧 Python 文件：审计器判定 11≠12，阳性失败被捕获。
- 内存文本插入 `@unittest.skip('control')`：命中 `memory_control.py:1:unittest.skip`，阳性失败被捕获。
- `flowboard.db` 和 `.copilot-state/task/message` 的 SHA-256、bytes、mtime_ns 在验证器前后完全相同；四个终值 SHA-256 分别为 `9C782261...`、`C9EB2A0A...`、`34A98149...`、`FCEEEE50...`。

注：验证器第一次自检发现从深层目录启动时仓库根未进入 `sys.path`，因此 loader 报 15 个模块导入错误；仅修正验证器的 `sys.path` 后终值双算为 142/142。该问题未涉及测试或产品代码，也不是回归失败。
