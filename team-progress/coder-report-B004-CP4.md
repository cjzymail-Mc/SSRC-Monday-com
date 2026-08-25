# B-004 CP4 coder report — 单项目 / 全项目仪表盘

日期：2026-08-20  
角色：coder（Codex worker）  
结论：**BLOCKED_DYNAMIC**（实现与静态/Node/后端回归已完成；当前沙箱无法启动 Playwright 子进程，真实 Chromium 0 条执行，等待外层 planner 动态验收）

## 1. 范围与落盘

严格限定 `team-task.md` §11 CP4 与 coverage map B22–B29；未触碰 Excel/B-005、服务端路由/领域实现、运行库或 `.copilot-*`。

- `timeline-ui.js`
  - 单项目方向 A：大标题、白卡、KPI 次级摘要，时间轴成为主体；不再把 editor 嵌进 dashboard。
  - `dashboardRange()` 为全项目生成同一绝对日历范围；每卡渲染同一 `data-calendar-start/end` 与带文字的红色今日线。
  - 默认主线/并行两行；直接消费服务端 `stage_intervals[].row_index/node_ids`；折叠时重叠段分半，按钮展开后按确定行号拆行。
  - 阶段区间为连续实色条，保留六阶段文字标签与 node_ids 穿透证据。
  - `bindContextController()` 是 editor、单项目、全项目共同使用的右键四项控制器；仪表盘操作只形成本地可观察意图，不发请求。
  - 全项目支持项目多选和开始日期/当前阶段/临近节点/逾期数量四种前端排序。
  - 逾期红、本周橙可并存，DOM 顺序固定红左橙右，并有文字与形状冗余。
- `timeline.css`
  - 只提供浅色语义 token；无暗色变量集、主题判断或切换入口。
  - 方向 A 画布/白卡层级、共享标尺、今日线、双轨/重叠、2px 阶段条、六阶段色板、风险提示及窄屏布局。
- `app.js`
  - 薄接线：把 `timelineFilters` 传入渲染，single/all 模式绑定同一 dashboard controller；无全局前端重构。
- `tests/timeline_ui.test.js`
  - Node 补充共享标尺、今日线文字、重叠折叠/展开、风险顺序、多选/排序及单一菜单控制器断言。
- `tests/test_timeline_e2e.py`
  - 新增真实临时库 fixture：主线和并行均有同日重叠（两轨 `row_index=0/1`），另含三项目用于筛排。
  - 新增 8 个具名 Chromium 用例，逐条对应 B22–B29：
    - `test_timeline_single_dashboard_structure`
    - `test_timeline_shared_calendar_and_today_marker`
    - `test_timeline_overlap_split_and_expand`
    - `test_timeline_stage_intervals_semantics`
    - `test_timeline_dashboards_share_context_controller`
    - `test_timeline_all_dashboard_filter_and_sort`
    - `test_timeline_dashboard_risk_markers`
    - `test_timeline_light_tokens_and_redundant_labels`
  - 关键点击/右键使用真实鼠标 `mousedown → mouseup → click/contextmenu`；筛排与右键操作断言网络计数不增且临时库内容 hash 不变。没有 `element.click()`、handler 直调或孤立组件替代生产入口。

## 2. 已执行验收

| 命令 | 结果 |
|---|---|
| `node --check timeline-ui.js` | PASS |
| `node --check app.js` | PASS |
| `python -X utf8 -m py_compile tests/test_timeline_e2e.py` | PASS |
| `node tests/timeline_ui.test.js` | **18/18 PASS** |
| `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'` | **29/29 PASS**（30.302s） |
| `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'` | **10/10 PASS**（20.337s） |
| `python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'` | **BLOCKED_DYNAMIC：0 tests executed** |

动态阻塞原文关键路径：`sync_playwright().start()` → `asyncio.create_subprocess_exec()` → `_winapi.CreateFile` → `PermissionError: [WinError 5] 拒绝访问`。这是当前沙箱对子进程管道的环境限制，Chromium 和测试实现均尚未开始执行；不可据此签 PASS，也不计业务 failure_key。

外层非沙箱复跑命令：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'
```

planner 必须以外跑真实 Chromium 结果决定 CP4 PASS/REWORK，并重点观察：两轨重叠 fixture、展开后的 `row_index=1`、全项目共享 start/end、物理事件序、右键/筛排零网络与 DB hash。

## 3. 安全与指纹

- 真实 `flowboard.db`：446,464 bytes；mtime `2026-08-12 14:31:25`；SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-task.md`：`34A9814963951EB0ACD0A886F33D8746C0ABDE23BD3ABC3317370B9D328F1BCA`
- `.copilot-state.json`：`C9EB2A0A0B4E48B7A66DCE279B704DEA32854AB3E5FDA78BDFB0679BB3EE96A7`
- `.copilot-message.md`：`FCEEEE50F16D6A85C8FC26DA3847E88BA53C64B9542D57DFF6A299D778515F72`

产物 hash（交接时）：

- `timeline-ui.js` `0D27C88883DD30758A2F0368BF9FB8B709F70724AA8D305092BD927EA635C7B7`
- `timeline.css` `7418102AF403D3BF293D2D6E0A5008CA247B5915CF5712DDF12100CF358E8096`
- `app.js` `7242565B63BED48AB42BD43B12D9E0701C106EB718D09B4F761D80326A785C90`
- `tests/timeline_ui.test.js` `95242BDF64DCC79BE0E7EA8ADDB53D7056D3217F10646CB0F8E510A31B02AA46`
- `tests/test_timeline_e2e.py` `FAF6C127DE8897F39FDCD2592032A35E18BAEDABD68775F516F0A2758CB6AED4`

## 4. failure_key 记录

- `NODE_TEST_SYNTAX_FIX`：首次 Node 扩展测试漏写对象属性冒号；修正后 18/18 PASS，未复发。
- `E2E_INVOCATION_PATH`：首次用不存在的 `tests` package 指定单测；改用 discover 后定位到环境 WinError 5，未复发。
- `PLAYWRIGHT_SANDBOX_WINERROR5`：环境阻塞一次；按约定不在同沙箱重复硬跑，状态记 `BLOCKED_DYNAMIC`。

没有同一业务 failure_key 连续两次失败。
