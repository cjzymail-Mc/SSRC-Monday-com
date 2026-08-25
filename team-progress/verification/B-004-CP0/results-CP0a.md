# B-004 CP0a 独立复验结果

日期：2026-08-20

- 真实 map：exit 0；B01–B38 共 38 行，`PASS=0`、`GAP-B004=33`、`CONFLICT=5`；状态、唯一 CP、未来具名槽位均合法。
- 删除 B37：exit 1，`MISSING_MAPPING:B37`。
- 删除 B38：exit 1，`MISSING_MAPPING:B38`。
- B01 改 PASS + 伪造测试：exit 1，`TEST_NOT_FOUND`、`STATIC_ONLY_AS_PASS`。
- B01 改 PASS + 引用真实存在的 HTTP 测试（非真实 Chromium）：exit 1，`STATIC_ONLY_AS_PASS`；证明“测试存在”不能绕过 CP0 的零 PASS 口径。
- 删除 B37 的“软删节点”语义键：exit 1，`SEMANTIC_KEY_MISSING:B37:软删节点`。
- 删除 B38 的“12MB”语义键：exit 1，`SEMANTIC_KEY_MISSING:B38:12MB`。

验收器已显式登记 B37/CP3、B38/CP5，并逐键校验：B37 的 create/新增、remove/软删/不得硬删、batch/刷新；B38 的 1.5MB、12MB、1000、10k、公式/宏/外链、严格 8 列、不进入 preview/commit。不是只把行数常量从 36 改为 38。

所有阳性对照均只存在于 `%TEMP%` 内存落盘副本并于运行后删除；真实 map 未由 planner 修改。

指纹复核：

- `flowboard.db` SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`，446464 bytes，mtime `2026-08-12 14:31:25`。
- `.copilot-state.json` SHA-256 `C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`，只读未改。

