# B-004 CP4c coder report — 全项目节点真实 hit target

日期：2026-08-20  
planner 结论前值：CP4 REWORK  
产品 failure_key：`CP4_ALL_DASHBOARD_NODE_HIT_TARGET`（第一次）  
结论：**READY_FOR_EXTERNAL_RERUN**；若外跑仍报同产品键，按熔断纪律停报，不继续试探性修改。

## 1. 证据与根因

读取 planner 独立探针与 results 后确认：右键的 `mousedown → mouseup → contextmenu` 三事件完整，但 document capture 中三次 `event.target.closest('.timeline-dashboard-node')` 都是 null。问题不是 recorder 丢事件，也不能由隐藏菜单中已有四个 DOM 项替代。

当前生产节点按钮只有 `width:18px`，没有显式 `height/min-height`，命中盒依赖内部 12px 圆点及 UA 按钮布局；内部 `i/span` 也未明确退出 hit-testing。筛选/排序重渲染后的真实中心因此没有稳定、显式的节点命中面。原 coder E2E 只在右键后数菜单项，没有 `elementFromPoint` 或 document capture，确有盲区。

## 2. 最小生产修复

仅修改 dashboard 节点层与相应测试；没有分叉 single/all controller：

- `timeline.css`
  - `.timeline-dashboard-node` 明确为 `28px × 28px`（含 min-width/min-height），`z-index:20`、`pointer-events:auto`、`isolation:isolate`。
  - top 从 44px 校正到 38px，使 28px 命中面中心仍与原圆点中心近似一致；可见圆点仍为 12px + 2px 白圈，视觉语义不放大。
  - 装饰子元素 `i/span` 使用 `pointer-events:none`，物理中心 target 稳定落在 button 本身；文字仍可见。
- `timeline-ui.js`
  - 节点增加 `data-dashboard-hit-target="node"` 与带名称/阶段/日期/右键提示的 `aria-label`；single/all 仍由同一 `renderDashboard()` 产生、同一 `bindContextController()` 绑定。
  - 未改阶段 interval DOM、宽度算法、row_index、六阶段映射或 2px 连续条。

## 3. 回归盲区修复

`tests/test_timeline_e2e.py` 增加两层真实命中证据，均使用 locator 实际 bounding box 中心和真实 `page.mouse.down/up(button='right')`，没有 force、`element.click()`、handler 直调或伪造事件：

1. 单项目共享 controller 用例：
   - `document.elementFromPoint(center).closest('.timeline-dashboard-node')` 必须是预期 node id；
   - document capture 的 down/up/contextmenu 三次实际 target 必须全部是同一预期 node id。
2. 全项目 sort=`overdue` + 多选 filter 重渲染后：
   - 再次执行同样的 `elementFromPoint` 与三事件 document capture；
   - 菜单必须可见，点击“已完成”后原 node 必须有 `data-dashboard-action=done` 和 `is-context-target`；
   - 网络请求计数不增、四表内容 hash 不变的原断言继续保留。

`tests/timeline_ui.test.js` 补充节点显式 hit target 与冗余 aria 标签的静态断言。B22–B29 原全部断言保留；阶段 interval 的设计/量产 data-stage+class、可见文字、aria、2px、正宽连续条、node_ids 均未削弱。

## 4. 本地结果

- `node --check timeline-ui.js`：PASS
- `node tests/timeline_ui.test.js`：**21/21 PASS**
- `python -X utf8 -m py_compile tests/test_timeline_e2e.py`：PASS
- `git diff --check -- timeline-ui.js timeline.css tests/timeline_ui.test.js tests/test_timeline_e2e.py`：PASS
- 按指令未在当前沙箱运行浏览器；交由主 agent 外跑 coder 14 条与 planner 独立探针。

外跑命令：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'
python -X utf8 team-progress/verification/B-004-CP4/probe_cp4_browser.py
```

## 5. 指纹与边界

- `timeline-ui.js` `71A0142DBC1B6DB8835D80F14293860BFD79B1086409C887884359EC5C2A7B04`
- `timeline.css` `F802EBB62DF3D3150C288CA70312D59B0B24F5CEBC6D69DBC1A594649EBD0D14`
- `tests/timeline_ui.test.js` `417E82F02F75E06C468C67A62D4BC6BE71D6296F0952EA1F496ED865E2C55FFC`
- `tests/test_timeline_e2e.py` `FD8D64A7A0FF9E4334D419C74666B9FA7B096BD9BAC4681ACF9B75C46D614ED8`
- 真实 `flowboard.db`：446,464 bytes，mtime `2026-08-12 14:31:25`，SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。

未进入 CP5/B-005，未改治理、planner 证据、`.copilot-*` 或真实数据库。
