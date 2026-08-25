# B-004 CP4 root-cause evidence results

结论：旧 `CP4_ALL_DASHBOARD_NODE_HIT_TARGET` 不是产品层叠/命中缺陷，而是 planner 验收器用视口外坐标发鼠标事件。重分类为诊断 fixture：`CP4_PLANNER_OFFVIEWPORT_MOUSE_COORDINATE`，不计产品 failure。

## 执行

- 命令：`python -X utf8 team-progress/verification/B-004-CP4/root-cause/diagnose_hit_target.py`
- exit：`0`
- 诊断脚本 SHA256：`A60321C611AD89BC2CD5630C9FDE1A57CB2483D144B2AC9192257D2D27967C29`
- 诊断键：`CP4_RC_HIT_STACK_CAPTURE`（不增加旧产品键计数）

## 一个项目对照态

- 目标：`.timeline-dashboard-node[data-node-id="1"]`
- bounding box：`x=628.5, y=531, width=28, height=28`
- center：`y=545`，位于 `1440×900` viewport 内。
- `elementsFromPoint(center)` 顶层是 `BUTTON.timeline-dashboard-node`，node id 为 1。
- `mousedown / mouseup / contextmenu` capture 均命中该 node；菜单能够显示并执行本地 action。

这证明 CP4c 的生产 hit area、pointer target 与共享 controller 在目标处可工作，排除了“节点按钮自身始终不可命中”。

## 恢复三个项目复现态

- 目标 bounding box：`x=870.171875, y=930, width=28, height=28`
- center：`y=944`，超过 viewport 高度 `900`。
- `elementsFromPoint(center)=[]`；`elementFromPoint(center)=null`；目标盒内扫描网格全部为 null。
- 实际 `mousedown / mouseup / contextmenu` target 均为 `HTML`，不是 node；菜单不可见。

DOM、computed style、z-index 或 pointer-events 不是这次 null target 的决定因素。旧 planner `physical()` 直接取得 locator 的 bounding box 中心并调用 `page.mouse`，没有先 `scroll_into_view_if_needed()`；Playwright mouse 使用 viewport 坐标，因此把事件发送到了视口外的 `y=944`。这完整解释了三事件存在但 `closest('.timeline-dashboard-node')=null` 的现象。

## 隔离证据

- timeline 写请求：`[]`
- 临时 DB 四表内容 hash：前后不变
- console errors：`[]`
- page errors：`[]`
- 真实 `flowboard.db` 与 `.copilot-*`：指纹不变

## 最小验收器修正设计（尚未实施/运行）

只需修改 planner 原 probe 的 `physical()` helper；不需要改生产或 coder tests：

1. `locator.scroll_into_view_if_needed()`。
2. 滚动完成后重新取得 fresh `bounding_box()`，不得复用滚动前 box。
3. 读取 viewport 大小，断言中心满足 `0 <= x < width` 且 `0 <= y < height`；否则报独立 fixture key。
4. 再执行真实 `mouse.move/down/up`。
5. 保留现有 document capture，继续要求 down/up/contextmenu 三次 actual target 都 closest 到同一目标 node；菜单可见、action、零网络/零 DB 写与 canary 断言均不得放宽。

本轮未修改或运行原 probe。CP4 在修正后的 planner probe 真正复跑通过前，仍不得签 PASS 或进入 CP5。
