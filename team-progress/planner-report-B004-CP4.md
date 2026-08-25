# Planner Report — B-004 CP4

结论：**REWORK**。CP4 暂不得进入 CP5。

唯一未关闭产品失败键：`CP4_ALL_DASHBOARD_NODE_HIT_TARGET`。

planner 独立 Chromium 探针在方向 A、共享日历/今日线、双轨重叠、展开、阶段连续区间与六阶段冗余语义、风险提示、筛选和四种排序全部通过后，于“全项目仪表盘复用同一右键控制器”的真实 hit-testing 门禁失败。浏览器 document capture 明确记录了完整 `mousedown → mouseup → contextmenu`，但三个实际 target 的 `closest('.timeline-dashboard-node')` 均为 null；所以事件没有命中项目节点，不能用 DOM 中本来就存在的四个 menuitem 宣称该节点右键可操作。

coder 外跑 14/14 虽通过，但其全项目用例没有记录节点实际 hit target，因此未覆盖该盲区。planner 首轮 recorder 诊断不足后只做了一次加固；第二轮以 capture 证据确认产品失败，未第三次更换探针假设。

最小返工范围：修正筛选/排序重渲染后的全项目 node hit area/层叠关系，并给 coder E2E 增加实际 target 断言；不得放宽右键四项、事件序、零网络/零 DB 写、共享 controller 或其它已通过门禁。修复后复跑 `team-progress/verification/B-004-CP4/probe_cp4_browser.py`。

证据：

- `team-progress/verification/B-004-CP4/probe_cp4_browser.py`
- `team-progress/verification/B-004-CP4/outside-run.txt`
- `team-progress/verification/B-004-CP4/results.md`

本报告只裁 B-004 CP4，不触碰 CP5/B-005、double-workflow、真实数据库或 `.copilot-*`。

## CP4c 后熔断追加（2026-08-20）

主 agent 外跑同一命令 `python -X utf8 team-progress/verification/B-004-CP4/probe_cp4_browser.py`，结果 exit 1；同一 `failure_key=CP4_ALL_DASHBOARD_NODE_HIT_TARGET` 再次复现，capture 仍为 `[mousedown:null, mouseup:null, contextmenu:null]`。累计 `count=2`，现正式进入 `WAIT_HUMAN / CIRCUIT_BREAKER_OPEN`：CP4 保持 **REWORK**，CP5 禁止，不得第三次修探针、复跑或继续试探性实现。

当前哈希：`timeline-ui.js=71A0142D…A7B04`、`app.js=7242565B…5C90`、`timeline.css=F802EBB6…0D14`、`timeline_ui.test.js=417E82F0…55FFC`、`test_timeline_e2e.py=FD8D64A7…14ED8`、`probe=1911856D…A6CE6`；完整值见 `verification/B-004-CP4/results.md`。

mc-expert 陪审为 **Codex custom agent 模拟，非 Claude 原生 mc-expert**；其高置信建议是维持真实缺陷裁定并遵守熔断，等待人工复核/拍板。

## 根因证据推翻旧 REWORK 裁定（2026-08-20）

用户授权的只读根因诊断已证明：旧失败不是产品节点层叠或 hit area 缺陷。一个项目时目标 node 中心 `y=545`（viewport 900），顶层和三事件均命中 node；恢复三个项目后目标中心 `y=944`，已在 viewport 外，`elementsFromPoint=[]`，事件落到 HTML。旧 probe 的 `physical()` 没有 `scroll_into_view_if_needed()`，将视口外 bounding-box 中心直接用于 mouse 坐标。

故先前产品 **REWORK** 裁定被推翻：`CP4_ALL_DASHBOARD_NODE_HIT_TARGET` 不再计为产品 failure，重分类为 `CP4_PLANNER_OFFVIEWPORT_MOUSE_COORDINATE` fixture；原 `count=2` 不构成产品熔断。根因证据：`team-progress/verification/B-004-CP4/root-cause/results.md`。

当前不是 CP4 PASS：需要先仅修 planner probe 的 `physical()`（滚动 → fresh box → viewport 内断言 → 原真实 mouse/capture），再完整复跑且保留所有原断言。复验前 CP5 仍禁止；生产代码和 coder tests 无需因本根因修改。

## 最终复验签注：PASS（2026-08-20）

修正后的 planner probe（SHA256 `DEEFA0EB8CE9B24DFF0715256ABD39A8B995147F062032E80465DE4E56DA0AE3`）已由主 agent 沙箱外完整运行，exit 0、JSON `status=PASS`。滚动后 fresh box 与 viewport 硬断言证明所有关键 mouse 序列实际命中视口内产品控件；single/all context capture、严格四项菜单、action、零 timeline 写、四表 hash、bad/good canary 和 locked-file guard 全部通过。

结合 coder Playwright E2E 14/14、Node 20/20、HTTP 10/10、timeline service 29/29，以及当前 CP4c 产品哈希（`timeline-ui.js=71A0142D…A7B04`、`app.js=7242565B…5C90`、`timeline.css=F802EBB6…0D14`、`timeline_ui.test.js=417E82F0…55FFC`、`test_timeline_e2e.py=FD8D64A7…14ED8`），B22–B29 全部正式关闭。

最终结论：**CP4 PASS，允许进入 CP5**。历史 REWORK→熔断→根因取证→fixture 更正链全部保留；`CP4_ALL_DASHBOARD_NODE_HIT_TARGET` 已撤销产品归类，真正关闭的是 planner fixture `CP4_PLANNER_OFFVIEWPORT_MOUSE_COORDINATE`。本签注不提前签 CP5/CP6，不授权发布、提交或真实库迁移。
