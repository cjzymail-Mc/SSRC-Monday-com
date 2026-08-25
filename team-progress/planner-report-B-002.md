# planner-report-B-002 · wave-2 正式独立验收

> 验收对象：team-task §8 的 B-002 九项 + lead 自主裁决 #6 的追加项⑩。  
> 验收盘面：CP0/CP1/CP2/CP3 后同一冻结工作树。  
> 正式结论：**PASS**。B-002 的 1–9 + ⑩ 均可签注关闭；无 REWORK、BLOCKED 或 STATIC_ONLY。B-003/B-004/B-005 未进入。

## 1. 冻结盘面与零副作用

| 对象 | 开始 SHA256 | 结束 SHA256 | 结论 |
|---|---|---|---|
| `flowboard/timeline.py` | `c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b` | 同左 | 稳定 |
| `tests/test_timeline.py` | `8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf` | 同左 | 稳定 |
| `team-progress/B-002-coverage-map.md` | `d6e8f7356113e9ee8f6aeb9a848dc5c1a713ef9b448d9f0eac1cc28b1477cada` | 同左 | 稳定 |

真实 `flowboard.db` 只做 `stat`：开始/结束均为 446464 bytes、`mtime_ns=1786516285465474700`（UTC `2026-08-12T06:31:25.4654747Z`）。专项 unittest 的 `setUp` 与全部 planner 探针均使用 `tempfile.TemporaryDirectory` 内的隔离库/备份；未对运行库执行 migrate、purge、restore 或写入。

## 2. 独立动态证据

1. 同一冻结盘面独立运行 `python -X utf8 -B -m unittest discover -s tests -p test_timeline.py -v`：**Ran 29 tests in 39.241s，OK**。
2. wave-2 重新执行并修正验收探针：B-002 范围内 **40/40 PASS_PROBE，0 FAIL**；设置/安全探针 **2/2 PASS**。旧 wave-1 的 43/43 仅作为脚本起点，不作为本签注计数。
3. `P2-illegal` / `P2-weifenjian` 已补合法 project、track、stage、date；两者均精确命中 `422 VALIDATION_ERROR`、`details.row=2`、`message="status 必须是 已完成/未开始/进行中 或留空"`，不再由 `value is required` 冒充 PASS。
4. 同类拒收探针同步收紧：P1b/P1c/P1d 锁定日期拒绝理由，P3b 锁定四键重复与 `duplicate_of`，P4b/P4d/P4f 锁定对应长度理由，P6b 锁定 `NAME_CONFLICT`；未发现仍以“任意 422”直接放行的范围内探针。
5. `P3d` 明确记为 **OUT_OF_SCOPE/B-003**，不计入 B-002 PASS/FAIL；它只保留“同名项目全行错误清单”诊断记录。
6. coverage map §E 有十行：第 9 项是 map 文档本体；其余九个可执行 unittest 条目均真实存在、逐一 `loadTestsFromName` 得 1 个 case，并逐一运行 **9/9 OK**。

## 3. 按检查点四态签注

### CP0 · 项 9 coverage map — PASS

- `B-002-coverage-map.md` 完整覆盖冻结 §7.1 组 1–12、§5.1/§5.2/§5.3 与 §3.7 导出侧，并提供 §E 九项+⑩总表。
- §D 的非本包缺口仍显式隔离，没有被抹成 PASS；追加项⑩已映射到真实 unittest。
- map 的静态映射由本波次 29/29、40/40 探针和九个具名单载结果补成动态证据，故不是 STATIC_ONLY。

### CP1 · 项 1–5、项 6、追加项⑩ — PASS

- **⑩ 表头**：契约字面八列正例通过；乱序/缺列精确返回 `IMPORT_HEADERS_MISMATCH`；导出表头逐列一致。
- **1 xlsx 序列号**：18264、中段、73051 换算正确；分数、上下越界和 CSV 整数文本均按具体日期理由行级拒收。
- **2 状态三态**：三态+空动态落库/派生正确；两个非法状态负例已修正输入并命中状态枚举理由。
- **3 多行聚合**：preview 精确为 1 项目/3 节点，commit 精确返回 1/3，DB 仍为 1/3；仅真四键重复拒收。
- **4 字段上限**：节点/备注 500 通过、501 拒收；项目 200 通过、201 拒收，中文按字符计数。
- **5 导出边界**：1000 行导出物可进入新 workspace 导入链；1001 行 fail-closed 为 `EXPORT_LIMIT` 且 `details={total:1001,max:1000}`。具名 unittest 进一步完成 1000 行 commit 往返。
- **6 真实字节往返**：`export_timeline()` 返回字节的 SHA256 与 preview 批保存 SHA256 相同；新 workspace 语义等价及 R5 同名拒收均通过。

### CP2 · 项 6–8 — PASS

- **6 真实字节 round-trip**：同上，独立探针与具名单测双证据均通过。
- **7 迁移**：隔离 v15 备份本体非空且保留 sentinel/存量；迁移后 v16、五表空、计数不变、integrity/FK 正常；重跑仅一条 v16 记录；备份恢复回 v15 语义成立。
- **8 undo**：三连续批撤中间批精确返回 `409 UNDO_TARGET_STALE` 且六表/节点/version 零写入；created 反向软删保留物理行、deleted 反向恢复为 NULL 均动态成立。
- 行级 422 共用 `details.row` 按 lead 恢复裁定保留为 B-002 元数据补强；未借此验收同名全行清单等 B-003 候选。

### CP3 · 回归、map 终版、九项+⑩汇总 — PASS

- 29/29 专项回归在本波次实际执行，而非沿用 coder 或 wave-1 文字记录。
- §E 九个可执行测试逐一加载运行 9/9；第 9 项 map 文档存在且已完成机械核对。
- 动态链前后冻结哈希及运行库 stat 完全一致，故 CP3 签注绑定有效。

## 4. 逐项最终签注

| 项 | 正式四态 | planner 依据 |
|---|---|---|
| 1 xlsx 序列号 | PASS | P1a–P1f + 具名单测 |
| 2 状态三态 | PASS | 修正后的 P2 六探针 + 具名单测 |
| 3 多行聚合 | PASS | P3a–P3c；P3d 已剔除 + 具名单测 |
| 4 字段上限 | PASS | P4a–P4f + 具名单测 |
| 5 导出边界 | PASS | P5a/P5b + 具名单测 |
| 6 真实字节 round-trip | PASS | P6a/P6b + 具名单测 |
| 7 迁移证据 | PASS | P7a–P7c + 具名单测 |
| 8 undo 证据 | PASS | P8a/P8a-ctl/P8b/P8c/P8d + 具名单测 |
| 9 coverage map | PASS | map 条款级机械核对 + 动态证据闭环 |
| ⑩ 契约字面表头 | PASS | P0a–P0d + 具名单测 |

**failure_key：无。** 本波次未产生 REWORK。coder 报告只用于定位；上述签注以冻结契约、实际动态输出与机械加载结果为依据。

## 5. 范围隔离与剩余风险

- 不验收、不实现 map §D 的同名项目全行错误清单、多 sheet/CSV 提示文案、导出含轨道排序、xlsx 文本整数形态细分及其他 B-003 候选。
- coverage map 对这些字面缺口的 `GAP-非九项` 留痕仍有效；本报告的 PASS 只关闭 lead 已钉死的 B-002 九项+⑩，不代表冻结契约全文已无缺口。
- §E 的精确结构为“九个 unittest + 一个 map 文档项”，不是十个 unittest；本波次已分别验证，未把文档冒充测试。

## 6. 可复跑证据索引

- `team-progress/verification/wave-2/b002_wave2_verification.py`
- `team-progress/verification/wave-2/verification_summary.json`
- `team-progress/verification/wave-2/full_suite_console.txt`
- `team-progress/verification/wave-2/b002_probe_results.json`
- `team-progress/verification/wave-2/probe_index.txt`
- `team-progress/verification/wave-2/named_tests_results.json`
- `team-progress/verification/wave-2/named_tests_console.txt`
- `team-progress/verification/wave-2/baseline_start.json`
- `team-progress/verification/wave-2/baseline_end.json`
- `team-progress/verification/wave-2/BASELINE-START.md`
- `team-progress/verification/wave-2/BASELINE-END.md`
