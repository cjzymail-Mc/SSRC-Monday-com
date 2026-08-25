# B-004 CP0 独立验收结果

日期：2026-08-20

## 机器校验

- 真实 map：exit 0；36/36 ID，`GAP-B004=31`、`CONFLICT=5`、`PASS=0`；四态合法；每行唯一 CP1–CP6；每行未来测试槽位明确，且未把未来测试计为 PASS。
- 删除 B12 的内存副本：exit 1，`MISSING_MAPPING:B12`。
- 将 B01 改为 PASS 并伪造 `test_timeline_definitely_fake` 的内存副本：exit 1，`TEST_NOT_FOUND` + `STATIC_ONLY_AS_PASS`。
- 验收器：`validate_coverage_map.py`。两个对照只写 `%TEMP%` 且已删除，没有改 coverage map。

## 外部真相语义复核

36 是 map 自己选择的行为聚合数，不是冻结文档给出的规范条款数；不能仅凭 36/36 宣称“逐条映射”。逐读冻结 §3–§5、§7、§8.3 后发现至少两类未登记行为：

1. §3.1 的节点 create/remove（含首次 `initial_date=date`、删除为软删）没有独立条目或明确并入说明。B02 是“项目生命周期”，B15 仅写“一次 batch POST + drag details”，不能证明节点新增/删除生产 UI 已归属唯一 CP。
2. §5.1 文件级安全界没有映射：1.5MB、解压 12MB、1000 行、单元格 10k、公式/宏/外链拒绝及标准表头严格匹配。B31 只写“表头/逐行错误、同名、重复、枚举/日期等”，不能覆盖这些文件级规则；B32/B33 也不包含它们。

建议 map 只做最小收敛：补一条 CP2 节点新增/软删（或在现有行逐字声明并入并补具名槽位），补一条 CP5 文件级安全界；之后重跑同一验收器。是否仍为 36 行不重要，关键是外部条款无漏且唯一 CP。

## 环境与指纹

- Playwright 启动探针在当前受限环境于 driver 子进程创建阶段报 `PermissionError: [WinError 5]`。这不阻塞纯静态 CP0；CP1–CP6 动态签注必须在允许真实 Chromium 启动的环境执行，不能以静态/Node 证据替代。
- `flowboard.db`: SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`；446464 bytes；mtime `2026-08-12 14:31:25`。
- `.copilot-state.json`: SHA-256 `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`；只读未改。

