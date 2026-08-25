# Coder Report — B-004 CP0a

日期：2026-08-20  
failure_key：`B004_CP0_FROZEN_CLAUSE_UNMAPPED`  
结论：已做唯一最小补图，等待 planner 复验；**不声明 PASS**。

## 唯一修正

- 保留原 B01–B36 初始快照；新增 B37，把冻结 §3.1 节点 `create` / `remove` 的生产 UI、真实 batch、刷新验证唯一归入 CP3，具名槽位 `test_timeline_node_create_remove_batch_journey`。
- 新增 B38，把冻结 §5.1 的 1.5MB/12MB/1000 行/单元格 10k、公式/宏/外链与严格 8 列表头文件级拒绝唯一归入 CP5，具名槽位 `test_timeline_import_file_safety_and_strict_headers`。
- 明确避免重复计数：B38 不覆盖 B31 行级错误，也不覆盖 B33 preview/commit gate。

## 终态

- 初始：36 行，`PASS=0`、`GAP-B004=31`、`CONFLICT=5`。
- 终态：38 行，`PASS=0`、`GAP-B004=33`、`CONFLICT=5`。
- 只修改 `team-progress/B-004-coverage-map.md` 并新增本报告；实现、测试、`team-task.md`、`team-progress.md`、`.copilot-*` 与真实库均未改。

## 验证

- 已复跑 `team-progress/verification/B-004-CP0/validate_coverage_map.py team-progress/B-004-coverage-map.md --json`。旧 validator 仍硬编码 B01–B36，正确读到 `row_count=38` 与 `GAP-B004=33/CONFLICT=5`，但以 `EXTRA_MAPPING:B37,B38` 和对应 ownership 报 `ok=false`。这不是隐藏为绿；需 planner 按 CP0a 终态更新/参数化其独立验收器后复验。
- coverage map SHA-256：`767E2CFACC8891873EDA3CF3E6697E5B13AA5D25174CC0CAE1E44726CF7B8A68`。该指纹用于 CP0a 交接，不是 planner 签注。

真实库复核仍为 446464 bytes、LastWriteTime `2026-08-12 14:31:25`、SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
