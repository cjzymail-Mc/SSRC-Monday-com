# coder-report-CP2（B-002 项 6–8 · 恢复交付）· 2026-08-19

> 本报告是 Claude team-task 中断后的 coder 恢复交付。恢复者未修改实现或测试，只按当前工作树盘面重建 CP2 五件套并复跑具名测试。下述 PASS 是本次实际执行证据，不是 planner 正式签注；旧的 43/43 planner 备战探针不作为本报告验收依据。

## 1. 检查点与 done_when 映射

- 项 6（真实字节 round-trip）：`test_timeline.TimelineCoreTests.test_group9_excel_round_trip_in_new_workspace`。必须由 `export_timeline()` 的真实返回字节贯穿新 workspace 的 preview/commit，覆盖语义等价、完成态保留、非完成态按日期重算、interval 重派生及 R5 同名拒收。
- 项 7（迁移证据）：`test_timeline.TimelineCoreTests.test_group10_backup_content_idempotence_rollback`。必须在隔离库证明 v15 备份非空且含代表性存量、备份可恢复并重放到 v16、v16 重跑幂等、version 16 迁移记录唯一、integrity/FK 正常。
- 项 8（undo 证据）：`test_timeline.TimelineCoreTests.test_group4_undo_three_batch_middle_and_reverse_roles`。必须证明三连续业务批次中间批次 undo 为 409 且零写入，并动态证明 created 反向软删、deleted 反向恢复。

## 2. 当前盘面实现与测试锚点

本恢复回合没有补写代码；以下是开始恢复时已存在、经逐行读取确认的磁盘事实，代码落地历史归属原 team-task coder：

- 项 6：`tests/test_timeline.py:488` 的 `raw = self.service.export_timeline(...)` 后，同一 `raw` 直接进入 `parse_upload`、新 workspace `preview_import` 和 R5 再导入拒收；没有第二份手工 workbook 覆盖真实字节。语义比对见该测试的节点五元组、完成态、按 `server_today` 重算与分轨 interval 断言。
- 项 7：`tests/test_timeline.py:907` 的测试从代表性 v15 库生成备份，直接读取备份本体核对 `user_version=15`、旧表计数与 task sentinel；复制备份恢复、再迁移到 v16；最后重跑原库迁移并断言无第二份备份、version 16 记录恰一条、五张 timeline 表空、integrity/FK 正常。所有路径位于 `TemporaryDirectory`。
- 项 8：`flowboard/timeline.py:623` 当前反向语义为 `created -> deleted_at=stamp`、`deleted -> deleted_at=NULL`；`tests/test_timeline.py:849` 用三批 fixture 对中间批次拒收前后做项目、节点、批次、changes、audit 五类快照相等断言，并核对创建节点仍有物理行但已软删、被删节点恢复进 view。恢复盘面不采纳“此前两分支互换”的历史归因，只确认当前语义和动态结果。
- 行级 422 共用错误元数据按 lead 恢复裁定保留在 B-002：`_validate_timeline_rows` 为缺少 details 的行级 422 补 `{"row": n}`。该裁定不扩展到“同名项目全行清单”、CSV 提示文案、导出含轨道排序或其他 coverage map §D 的 B-003 候选。

## 3. 本次实际验证与证据

工作目录：repo 根；运行参数 `-B`，测试数据库/备份均写入测试自身临时目录。

| 项 | 本次命令 | 结果 |
|---|---|---|
| 6 | `python -X utf8 -B -m unittest discover -s tests -p test_timeline.py -k test_group9_excel_round_trip_in_new_workspace` | exit 0；Ran 1 test in 0.648s；OK |
| 7 | `python -X utf8 -B -m unittest discover -s tests -p test_timeline.py -k test_group10_backup_content_idempotence_rollback` | exit 0；Ran 1 test in 1.459s；OK |
| 8 | `python -X utf8 -B -m unittest discover -s tests -p test_timeline.py -k test_group4_undo_three_batch_middle_and_reverse_roles` | exit 0；Ran 1 test in 0.788s；OK |

证据分类：上表为本恢复回合实际复跑；CP0 的 21/21、CP1 的多次 29/29、planner 的 43/43 均只属历史记录，本报告不把它们冒充本次验收。负路径来自测试内冻结契约断言；coder 的文字说明不构成独立验收。

## 4. 冻结快照绑定

本报告只对下列完整 SHA256 的同一盘面有效：

- `flowboard/timeline.py`：`c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b`
- `tests/test_timeline.py`：`8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf`
- `team-progress/B-002-coverage-map.md`：`d6e8f7356113e9ee8f6aeb9a848dc5c1a713ef9b448d9f0eac1cc28b1477cada`

任一文件哈希变化后，CP2 的动态证据须按新盘面重跑，不得沿用本报告。

## 5. 纠偏三问

1. 服务哪个检查点：仅 CP2 的项 6–8，为 CP3 的 B-002 回归交棒。
2. 是否扩大范围：否。未进入或运行 B-003/B-004/B-005；未修 coverage map §D 的候选缺口；未触碰真实 `flowboard.db`。
3. 实现、文档、证据是否一致：当前三份冻结输入哈希一致；三条具名测试均在本回合按盘面实跑通过；报告明确与 planner 签注分权。

## 6. 三清单

- 自主裁决：无。只执行 lead 已给定的 row-details 恢复裁定和范围隔离。
- OPEN_BLOCKERS：无实现阻塞；等待 planner 对同一哈希盘面作独立验收，不视为 coder 自签关闭。
- PENDING_HUMAN_NONBLOCKING：无。

