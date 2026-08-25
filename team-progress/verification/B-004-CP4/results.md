# B-004 CP4 independent verification results

结论：**REWORK**。

## 唯一产品失败键

`CP4_ALL_DASHBOARD_NODE_HIT_TARGET`

复现路径：管理员登录 → 时间管理生产入口 → 单项目仪表盘 → 全项目仪表盘 → 原生四种排序切到“逾期数量” → 多选筛选为一个项目 → 恢复显示三个项目 → 对第一项目的 `.timeline-dashboard-node` 中心执行真实右键 mouse down/up。

期望：三个事件的实际 hit target 均位于该 `.timeline-dashboard-node` 内；共享 controller 展示可见的严格四项菜单，点击“已完成”后该节点获得 `data-dashboard-action=done` 与 `is-context-target`，且不发写请求。

实际：document capture 收到完整物理事件序列，但三个实际 target 的 `closest('.timeline-dashboard-node')` 均为 null：

```text
mousedown  node=None
mouseup    node=None
contextmenu node=None
```

这证明不是 recorder 丢事件，也不能由“DOM 中存在四个 menuitem”替代。全项目节点在该真实交互盘面上没有命中，controller 无法接收节点 contextmenu。

## 已通过到失败点的独立门禁

- 单项目方向 A：白卡、大标题、KPI 次级，时间轴在 1440×900 首屏可见且为主视觉。
- 单/全绝对日历与今日线；今日线含“今天”文字。
- main/parallel 双轨；两轨都由服务端派生出 row_index=1，折叠分半、真实点击后展开拆行。
- stage interval 连续宽度、2px 圆角、node_ids；六阶段中文→token、data-stage、class、可见文字和 aria 语义一致。
- 单项目真实右键事件序完整，菜单严格四项。
- 全项目共享 start/end，六阶段齐全；红逾期在左、橙本周在右且都有文字。
- 多选筛选可从三项目变一项目并恢复；四个排序项存在，“逾期数量”排序正确。
- 生产入口 GET timeline 阳性对照有效。

由于探针在全项目右键处停止，planner 独立探针没有执行其后的最终网络零写、四表 hash 与 click canary；coder 14/14 不能替代未通过的真实 target 门禁。

## 最小修复目标（给 coder）

只修全项目仪表盘节点的真实 hit-testing/层叠与相应测试盲区：

1. 保证筛选/排序重渲染后 `.timeline-dashboard-node` 在自身可见圆点中心可命中，必要时校正节点的尺寸、pointer-events、z-index/stacking context 或区间覆盖关系。
2. coder E2E 在全项目路径增加 document capture（或等价真实 target 证据），必须断言 down/up/contextmenu 的 target 均 closest 到预期 node；不能只数隐藏菜单内已有的四个 DOM 项。
3. 保持所有既有 CP4 断言和零写边界，不得移动/伪造点击坐标绕过实际控件，也不得用 handler/element.click 代替。

修复后复跑同一 planner probe；同产品键若再次失败，按熔断纪律停止。

## 安全边界

探针仅使用临时 DB 与随机端口；未改生产实现/coder tests，未触碰 B-005、治理、真实 `flowboard.db` 或 `.copilot-*`。

## CP4c 后恢复态与熔断

CP4c 修复后，主 agent 外跑同一命令 `python -X utf8 team-progress/verification/B-004-CP4/probe_cp4_browser.py`，结果仍为 exit 1；同一产品键 `CP4_ALL_DASHBOARD_NODE_HIT_TARGET` 第二次复现，capture 仍为 `[mousedown:null, mouseup:null, contextmenu:null]`。

- `failure_count=2`
- 状态：`WAIT_HUMAN / CIRCUIT_BREAKER_OPEN`
- CP4 保持 `REWORK`；CP5 禁止
- 不再修改或第三次运行该探针，不再试探性修改产品

CP4c 后哈希：`timeline-ui.js=71A0142DBC1B6DB8835D80F14293860BFD79B1086409C887884359EC5C2A7B04`、`app.js=7242565B63BED48AB42BD43B12D9E0701C106EB718D09B4F761D80326A785C90`、`timeline.css=F802EBB62DF3D3150C288CA70312D59B0B24F5CEBC6D69DBC1A594649EBD0D14`、`tests/timeline_ui.test.js=417E82F02F75E06C468C67A62D4BC6BE71D6296F0952EA1F496ED865E2C55FFC`、`tests/test_timeline_e2e.py=FD8D64A7A0FF9E4334D419C74666B9FA7B096BD9BAC4681ACF9B75C46D614ED8`、planner probe=`1911856D023F45FD209BFA57A9BACFBFE7EA9E1B16190AF0699D9A2FCFDA6CE6`。

mc-expert 陪审（**Codex custom agent 模拟，非 Claude 原生 mc-expert**）高置信建议维持真实缺陷裁定并执行熔断，等待人工复核/拍板。

## 根因取证后的裁定更正

后续经用户显式授权的只读根因取证已推翻上面的产品缺陷判断。一个项目对照态中 node 中心 `y=545`，`elementsFromPoint` 顶层与三事件 target 均为 node；恢复三个项目后同一目标中心变为 `y=944`，超出 900px viewport，`elementsFromPoint=[]`、网格全 null，三事件 target 均为 HTML。

因此旧 `CP4_ALL_DASHBOARD_NODE_HIT_TARGET` 撤销产品归类，改记 planner fixture：`CP4_PLANNER_OFFVIEWPORT_MOUSE_COORDINATE`。原因是原 probe `physical()` 未先滚动目标，直接把 bounding-box 中心当 viewport 鼠标坐标。此前 `count=2 / WAIT_HUMAN` 只描述旧探针重复结果，不再构成产品熔断。

完整证据见 `root-cause/results.md`。最小修正只需改 planner probe：先 `scroll_into_view_if_needed()`，再取 fresh box 并断言中心在 viewport 内，然后执行原 capture/菜单/action/零写/canary 断言。该修正和复跑尚未执行；CP4 当前为“产品 REWORK 已撤销、planner 复验待执行”，在复验 PASS 前仍禁止进入 CP5。

### 验收器修正已实施，等待动态复跑

经用户授权，planner probe 已仅修改 `physical()`：`scroll_into_view_if_needed()` → fresh `bounding_box()` → viewport 中心硬断言 → 原真实 mouse 序列。未改生产或 coder tests，原 capture/菜单/action/网络零写/四表 hash/canary 断言全部保留。动态 PASS 前仍不改变 CP4 状态。

## 修正后独立复验：最终 PASS

主 agent 沙箱外运行修正后的独立 probe（SHA256 `DEEFA0EB8CE9B24DFF0715256ABD39A8B995147F062032E80465DE4E56DA0AE3`），exit 0，JSON `status=PASS`。

- 方向 A、共享绝对日历/今日线、main/parallel 双轨、row_index 重叠分半及展开全部通过。
- 六阶段中文→token/data-stage/class/可见文字/aria、2px 连续区间与 node_ids 全部通过。
- 全项目多选、四种排序、红逾期左/橙本周右与文字提示全部通过。
- single/all 的真实事件序分别为 down/up/click 与 down/up/contextmenu；两仪表盘右键菜单严格复用同四项，all 实际 target 命中 node。
- timeline 写请求 0，GET 阳性对照存在；临时 DB 四表内容 hash 不变。
- swallowed-click bad/good canary 均按预期区分；console/pageerror 无异常。
- 真实 `flowboard.db` 与 `.copilot-*` 指纹不变。
- coder 外跑 E2E 14/14、Node 20/20、HTTP 10/10、timeline service 29/29 均通过。

最终裁定：**CP4 PASS**。历史 REWORK 是 `CP4_PLANNER_OFFVIEWPORT_MOUSE_COORDINATE` 验收 fixture 导致，已由根因证据和修正后的全量复验关闭，不计产品 failure。允许进入 CP5。
