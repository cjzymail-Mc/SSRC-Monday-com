# Planner Report — B-004 CP6 wave 1

结论：**REWORK**。B-004 暂不得 CLOSED，不得进入 B-005。

唯一失败键：`B004_CP6_COVERAGE_TEST_REFERENCE_MISSING`（首次）。

CP6 明确要求 coverage map B01–B38 的终态测试引用现在必须可加载。独立 AST validator 实测：38 行完整，40 个唯一引用中 25 个不存在于当前 E2E 模块；其中 B36 三条关门旅程全部缺失。因此终态 traceability 先失败，不能用 coder E2E 21/21 或 CP1–CP5 聚合报告替代这些具体具名引用，也不能在此状态下声称逐行全 PASS。

四态签注：B22–B35、B38 为 PASS；B01–B21、B36、B37 因测试引用不可加载为 REWORK；C 区仍 OUT-OF-SCOPE，无范围升级。详细缺失清单与证据见：

- `team-progress/verification/B-004-CP6/validate_terminal_coverage.py`
- `team-progress/verification/B-004-CP6/results.md`

本波按硬门顺序没有启动 Playwright 三旅程，避免在已知 coverage gate 失败时制造“动态全绿即可关门”的错误口径。最小返工是补齐真实可执行的既定具名引用及 B36 三条同库旅程；不得用空测试、skip 或只改 map 文案取巧。返工后 planner 复跑 validator，再执行同一新临时库的 J1/J2/J3 独立关门 probe。

本报告不改生产/tests/map/CP0–CP5 历史，不触碰 B-005、真实 `flowboard.db` 或 `.copilot-*`。

---

# Planner Report — B-004 CP6 recovery / final

最终结论：**CP6 PASS；B-004 CLOSED；允许进入 B-005。** wave 1 的 REWORK 及其失败键原样保留在上文，不回写历史。

CP6a/CP6b 后，独立 terminal validator 已验证 coverage B01–B38 为连续 38 行、24 个登记 E2E 名称全部可加载、missing `[]`、B36 三条完整旅程 missing `[]`，且伪测试名阳性对照有效。当前 map SHA256 为 `6E079AD021F0219897DD5DB1CB1B59F5F123F171919FB261EE4372E29A3F4BE3`，E2E 文件 SHA256 为 `FE7BDA2F4F3E3C16515EA736258F3C24CF6B6B14D25CD1B122FD7A4F17CC539B`。

最终独立 probe SHA256 `50173BCBCD70F3D8EE120EA3065C90F43CE01E700511B84088B469669A7EF9FF`，由主 agent 在沙箱外真实 Chromium 执行，exit 0 / JSON PASS。它在同一份全新临时 DB 和随机端口依次完成：

- J1 编辑/放弃零写→混合 R06 恰一次→服务端 view/DB 持久→会话内 R07 恢复→reload 验证恢复态与 undo 生命周期；409 与 member R08 `ADMIN_REQUIRED` 零写。
- J2 single/all 的共享绝对日历、双轨重叠、阶段/今日/风险、筛选/四排序与共享四项右键；真实 mouse 会先滚动、重取 box 并校验中心在 viewport；timeline GET 为阳性、写请求为 0、四表 start/end hash 相同。
- J3 真文件 R09→R10→R01→R11 server bytes/sha256/WebCrypto/下载一致→新 workspace 重传/提交/R01 语义闭环；422 代表负例 commit disabled 且四表零写。

console/pageerror 分段门与 click 吞噬 canary 全绿；真实 `flowboard.db`、`.copilot-*` 和三项生产前端文件指纹未变。完整 JSON 与逐表 hash 在 `team-progress/verification/B-004-CP6/outside-run.txt`。

两次外跑纠正均为 planner 自有 fixture，各只出现一次且互不重复：

1. `CP6_PLANNER_UNDO_AFTER_RELOAD_EXPECTATION`：错误期待 reload 后仍可 R07；按 B18 改为提交会话内立即 undo，reload 只证入口消失和恢复态持久。
2. `CP6_PLANNER_DASHBOARD_SEED_RETURN_SHAPE`：未解包 CP4 seed 的 `(project_id, node_ids)`；加返回结构/非空/DOM 存在硬断言后纠正。

它们不计产品 failure，也没有删减、跳过或放宽验收门禁。

## B01–B38 终态逐行四态签注

| 条目 | 状态 | 条目 | 状态 | 条目 | 状态 | 条目 | 状态 |
|---|---|---|---|---|---|---|---|
| B01 | PASS | B11 | PASS | B21 | PASS | B31 | PASS |
| B02 | PASS | B12 | PASS | B22 | PASS | B32 | PASS |
| B03 | PASS | B13 | PASS | B23 | PASS | B33 | PASS |
| B04 | PASS | B14 | PASS | B24 | PASS | B34 | PASS |
| B05 | PASS | B15 | PASS | B25 | PASS | B35 | PASS |
| B06 | PASS | B16 | PASS | B26 | PASS | B36 | PASS |
| B07 | PASS | B17 | PASS | B27 | PASS | B37 | PASS |
| B08 | PASS | B18 | PASS | B28 | PASS | B38 | PASS |
| B09 | PASS | B19 | PASS | B29 | PASS | — | — |
| B10 | PASS | B20 | PASS | B30 | PASS | — | — |

C 区仍为 `OUT-OF-SCOPE`，没有升级候选范围。

回归终值：coder E2E 24/24（外跑 94.895s）、Node 24/24、HTTP 10/10、timeline 29/29、transfer 定向 1/1，全部 PASS。本签注只关闭 B-004 并允许依既定计划进入 B-005；不授权 commit/push/发布或真实库迁移。
