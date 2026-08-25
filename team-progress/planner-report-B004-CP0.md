# Planner Report — B-004 CP0

日期：2026-08-20  
结论：**REWORK**  
failure_key：`B004_CP0_FROZEN_CLAUSE_UNMAPPED`

## 裁定

结构验收通过：map 的 36 行四态、唯一 CP、未来具名槽位与 `PASS=0` 口径均正确；删除映射、伪造测试名/STATIC_ONLY 冒充 PASS 两个阳性对照均被验收器捕获。

但 CP0 要求以冻结 §3–§5、§7、§8.3 为外部真相“逐条映射”，而非验证 map 自报的 36 行。语义复核发现两处明确漏项：

- §3.1 节点 create/remove 生产 UI 与浏览器旅程未登记唯一 CP；项目生命周期 B02 和 drag batch B15 均未覆盖该行为。
- §5.1 文件级安全界（大小/解压/行数/单元格、公式/宏/外链、严格表头）未登记；B31 的行级/表头概括不能替代文件级安全组。

因此 CP0 暂不签 PASS，不得进入 CP1。coder 只需最小补图，不得动实现/测试；补齐后 planner 复跑同一 validator 与语义审计即可。

证据：`team-progress/verification/B-004-CP0/results.md`、`validate_coverage_map.py`。

浏览器探针在当前受限环境报 WinError 5，不影响本次静态 REWORK 判断；后续动态 CP 必须换到真实 Chromium 可启动环境。
