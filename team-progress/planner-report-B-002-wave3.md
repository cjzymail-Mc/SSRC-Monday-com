# planner-report-B-002-wave3 · 第 9 项独立验收

> 对象：B-002 第 9 项 coverage map；依据为 team-task §8「恢复澄清」及冻结 `9-GATE3_TECH_FREEZE.md` §7.1/§5。  
> 正式四态：**REWORK**。仅第 9 项退回；不改写 map，不进入 B-003。

## 动态结果

- 结构覆盖：§7.1 组 1–12 全部存在；63 个组内要求无漏项。§5.1 的 4 项、§5.2 的 10 项、§5.3 的 1 个闭环映射均存在。合计 **78/78**。
- 状态门：检查 80 行，全部可归一到允许集合。计数为 `PASS=71`、`GAP-非九项=8`、`N/A=1`、`GAP-B002=0`、`CONFLICT=0`；无非法状态。
- 测试门：从 map 解析出 29 个具名/唯一可解析的动态测试引用，**29/29 真实存在且可由 unittest 加载**；无 PASS 条款缺测试。
- 范围隔离门：失败，验收器 exit 1。唯一 failure_key：`OUT_OF_SCOPE_ROUTE_MISSING`。
- 阳性对照 1：只在内存副本删除 `空 batch/correction 422` 映射，exit 1，命中 `MISSING_MAPPING`。
- 阳性对照 2：只在内存副本把 `test_import_headers_contract_literal` 换成不存在的 `test_wave3_definitely_missing`，exit 1，命中 `TEST_NOT_FOUND`。

## 唯一最小缺口

map §D 的共享说明只写“留 lead/planner 排序”。D-4 行内已有 B-003 语义，但 **D-2、D-5、D-6、D-7 未显式绑定 B-003 候选去向**，不满足恢复澄清的“GAP-非九项必须绑定 B-003 候选去向”。

最小返工口径：只需在 §D 前言增加一条共享声明，明确 D 表全部条目均路由为 B-003 候选；无需逐行改写，也不得把这些条目标为 PASS。planner 不代 coder 修改正本。

## 冻结盘面

验收开始/结束完全一致：

- `flowboard/timeline.py`：`c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b`
- `tests/test_timeline.py`：`8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf`
- `team-progress/B-002-coverage-map.md`：`d6e8f7356113e9ee8f6aeb9a848dc5c1a713ef9b448d9f0eac1cc28b1477cada`
- 冻结契约：`4a83bfecf75b05c5bdbdc26d41dca7710e2e7867bc590a6a5027fa9fae901070`
- 真实 `flowboard.db`：446464 bytes，`mtime_ns=1786516285465474700`；仅只读 stat，前后未变。

## 证据

- `team-progress/verification/wave-3/coverage_map_verifier.py`
- `team-progress/verification/wave-3/coverage_map_verification.json`
- `team-progress/verification/wave-3/positive_controls.json`
- `team-progress/verification/wave-3/run_console.json`
