# coder-report-CP3（B-002 · 29 测试回归 + coverage map 终版 + 九项与⑩汇总）· 2026-08-19

> 本报告是 Claude team-task 中断后的 coder 恢复交付。恢复者只新增 CP2/CP3 两份报告，未改 `flowboard/timeline.py`、`tests/test_timeline.py` 或 coverage map。结论是“同一冻结哈希盘面的 coder 交付已具备 planner 验收条件”，不是 planner 正式签注，也不引用旧 43/43 探针冒充正式验收。

## 1. CP3 done_when 与交付范围

- B-002 专项回归：当前 `tests/test_timeline.py` 共 29 个 unittest，本恢复回合全量运行 29/29 OK。
- coverage map 终版：`team-progress/B-002-coverage-map.md` 已存在 CP3 终版，包含 §7.1 十二组、§5 Excel 规则、§3.7 导出侧、既有测试收敛清单、GAP-非九项隔离和九项+⑩具名测试总表。本恢复回合逐行读完并绑定其当前哈希，没有重写该产物。
- 汇总范围：team-task §8 九项，加 lead 自主裁决 #6 的追加项⑩。B-003/B-004/B-005 未进入、未运行、未宣称完成。

## 2. 九项 + ⑩ 盘面汇总

| 项 | 具名动态测试/产物 | 本次证据 |
|---|---|---|
| ⑩ 契约字面表头 | `test_import_headers_contract_literal` | 纳入本次 29/29；正例及旧表头/乱序/缺列/多列负例 |
| 1 xlsx 序列号 | `test_import_xlsx_serial_positive_and_boundaries` | 纳入本次 29/29；整数边界正例及分数/越界/CSV 整数负例 |
| 2 状态三态 | `test_import_status_three_states_and_recompute` | 纳入本次 29/29；三态+空、done_at 和非法旧值负例 |
| 3 多行聚合 | `test_import_multirow_aggregation_and_counts` | 纳入本次 29/29；preview/commit 计数、四键重复与非重复变体 |
| 4 字段上限 | `test_import_field_limits_boundaries` | 纳入本次 29/29；500/501、200/201 边界 |
| 5 导出边界 | `test_export_exact_1000_and_over_limit_fail_closed` | 纳入本次 29/29；1000 往返、1001 `EXPORT_LIMIT(total/max)` |
| 6 真实字节 round-trip | `test_group9_excel_round_trip_in_new_workspace` | 本次单测 1/1 OK，且纳入 29/29 |
| 7 迁移证据 | `test_group10_backup_content_idempotence_rollback` | 本次单测 1/1 OK，且纳入 29/29 |
| 8 undo 证据 | `test_group4_undo_three_batch_middle_and_reverse_roles` | 本次单测 1/1 OK，且纳入 29/29 |
| 9 coverage map | `team-progress/B-002-coverage-map.md` CP3 终版 | 本次逐行核对；终版具名映射含本表全部十行，绑定当前哈希 |

上表的测试 PASS 是 coder 侧动态交付证据；第 9 项的 map 完整性是文档盘面事实。B-002 是否正式关闭仍必须由 planner 以独立负例对同一哈希签注，不能由本报告自证。

## 3. 本次实际回归证据

执行命令：

`python -X utf8 -B -m unittest discover -s tests -p test_timeline.py`

结果：exit 0；`Ran 29 tests in 26.646s`；`OK`。其中未登录 HTTP 负例实际返回 401。运行只使用测试自身临时数据库/备份；真实 `flowboard.db` 仍为 446464 bytes，`LastWriteTimeUtc=2026-08-12 06:31:25`。

证据三分：

- 协议/设计保证：coverage map 对冻结 §7.1/§5/§3.7 的条款级映射，以及测试对正负路径的断言形态。
- 本恢复回合实际执行：项 6/7/8 各自 1/1 OK；随后同一盘面的 B-002 unittest 29/29 OK。
- 未在本恢复回合独立复跑的历史记录：CP0 21/21、CP1 多次 29/29、planner 43/43 备战探针。它们仅供追溯，不进入本报告的正式动态计数。

## 4. coverage map 终版核对与范围隔离

- §E 已有追加项⑩行，映射到真实存在的 `test_import_headers_contract_literal`；表头正例与四类负例已经是 unittest，不依赖 planner 临时探针代替。
- map §A/§B 中 B-002 九项+⑩均有具名动态测试；§D 仍明确列出 GAP-非九项，没有被本恢复回合抹平或偷算 PASS。
- 行级 422 共用错误元数据按 lead 恢复裁定保留为 **B-002 行级 422 共用错误元数据补强**。这不授权扩展到同名项目全行错误清单、CSV 提示文案、导出按轨道排序、xlsx 文本整数形态细分或其他 B-003 候选。
- map 中关于 undo 的历史“互换 bug”归因不作为 CP3 结论；本报告只陈述当前实现 `created -> 软删`、`deleted -> 恢复` 及本次动态 PASS。

## 5. 冻结快照绑定

本报告和 CP2 共同冻结到以下完整 SHA256：

- `flowboard/timeline.py`：`c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b`
- `tests/test_timeline.py`：`8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf`
- `team-progress/B-002-coverage-map.md`：`d6e8f7356113e9ee8f6aeb9a848dc5c1a713ef9b448d9f0eac1cc28b1477cada`

任一哈希变化即使测试名不变，也必须重新运行 CP2 具名测试和 CP3 29 测试回归后再签注。

## 6. 实际改动

- 新增 `team-progress/coder-report-CP2.md`。
- 新增 `team-progress/coder-report-CP3.md`。
- 零实现、零测试、零 coverage map 改动；未触碰 `.copilot-*`、`team-progress.md` 或真实运行库。

## 7. 纠偏三问

1. 服务哪个检查点：CP3 的 29 测试专项回归、coverage map 终版核对和九项+⑩交付汇总。
2. 是否扩大范围：否。回归模式只匹配 `test_timeline.py`；未进入 B-003/B-004/B-005，也未将 map §D 候选顺手实现。
3. 实现、文档、证据是否一致：三份冻结输入哈希已绑定；29 个测试在本恢复回合一次全绿；历史证据与本次证据分栏；coder 报告与 planner 签注边界明确。

## 8. 三清单

- 自主裁决：无。恢复交付严格执行 lead 的哈希冻结、row-details 保留和 B-003 候选隔离裁定。
- OPEN_BLOCKERS：无实现/测试阻塞；B-002 的正式关闭待 planner 对同一哈希独立签注。
- PENDING_HUMAN_NONBLOCKING：无新增；lead 既有待用户复盘确认项 #4/#6 不由 coder 重判。
