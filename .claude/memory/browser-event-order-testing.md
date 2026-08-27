---
name: browser-event-order-testing
description: HTML 样张交互测试必须用真实事件序（mousedown→mouseup→click），合成 .click() 会掩盖被吞掉的点击
type: reference
---

# 真浏览器事件序测试坑（2026-08-18，feature01 交互样张实测踩坑）

**坑**：真实浏览器事件序是 mousedown → mouseup → click。如果某处理器在 **mousedown** 阶段就隐藏/移除了目标元素（如「点击菜单外关闭菜单」逻辑），浏览器随后派发的 click 会落空——表现为「菜单弹出来了，但点菜单项没反应」。

**为什么测试没发现**：合成 `element.click()` 只派发 click 单个事件，不经过完整事件序，**会掩盖这类 bug**——合成测试全绿、真浏览器必现。

**怎么测**：凡验证「点击/拖拽/右键菜单」类交互，测试脚本必须按真实顺序逐个派发事件（本项目样张中的 `realClickMenu` 助手即此模式：依次 fire mousedown → mouseup → click）。

**修法示例**（隐藏菜单改为不吞目标）：

```js
document.addEventListener('mousedown', e => {
  if (!ctx.contains(e.target)) hideMenu();  // 判断在监听器里做，不在目标元素上做
});
```

适用范围：feature01 门 4 纵向切片的前端交互测试、后续所有 HTML 样张验证。

## 同族增补：UI 集成期竞态（2026-08-21 Gate5 CP2 实测，同属「真浏览器才能暴露的 UI 真缺陷」族）

- **双重渲染竞态**：异步落页探测与用户手动打开同一视图交错，`innerHTML` 整体替换会吞掉测试/用户正在交互的元素（表现为 set_input_files 静默无 change、bounding_box 求得后元素消失）。修法：入口幂等短路（已可见即 return）+ 拉取在飞去重（共享同一 promise），保证任何交错下只渲染一次。
- **视图切换可见性竞态**：测试 harness 常等待某状态控件（如同步状态徽标）「可见」；该控件若位于会被整体隐藏的区块内，视图切换会随机吃掉等待条件。修法：把常显状态控件迁出可隐藏区块（如 topbar）。
- 详见 `feature-01-项目时间管理-仪表盘/11-GATE5_UX_REALIGNMENT_TASK.md` §14.4（此处只留族级钩子，不复制细节）。

## 同族增补：hover 显隐命中测试环（2026-08-23 Gate5 反馈修复实测；Playwright actionability 子模式，跨项目通用）

- **症状**：hover 才浮现的控件，attached/visible/enabled/stable 断言全过，但物理 click 超时——中心点被行按钮/兄弟层/底层元素拦截。
- **根因**：控件只在父级 `:hover` 后才可命中，而 Playwright 命中测试要求指针完成 hover 前目标就有效；`opacity: 0` + `pointer-events: none` 组合把自己锁进「要先 hover 才可命中、要可命中才能 hover」的死循环，可见性断言照样过。
- **诊断流**：① 取 `getBoundingClientRect()` + computed `opacity`/`visibility`/`pointer-events`；② `document.elementFromPoint()` 在控件中心探针、查最近可操作祖先；③ 用真实指针点击复现——**禁止以 `force`、DOM `.click()`、直调 handler 收尾**（与主坑同源：合成路径掩盖真 bug）。
- **修法规则**：视觉淡入保留、但操作层始终可命中；`:focus-within` 留键盘通道；`@media (hover: none)` 触屏直接常显；终态用真实指针移动 + 物理点击验证（覆盖浏览器命中测试与事件序，而非只测应用 handler）。

## 同族增补：`:focus-within` 纸面键盘通道订正（2026-08-26 AUD-02 实证）

- 上文「`:focus-within` 留键盘通道」在无 tabindex 时是**纸面通道**：hover 呈现的控件 `display:none` 且无可聚焦子元素时 `:focus-within` 永不触发——实测连按 Tab 45 次均无法到达目标撤销按钮。CSS 规则存在 ≠ 键盘可达。
- **升级规则**：hover-only 操作必须有**条件性 `tabindex=0` + `role=group` + 明确 ARIA 提示**——仅当操作可用（如该项目处于 is-undo-only）时给 tabindex，避免无条件全局 tabindex 污染 Tab 序；父级聚焦即触发展开、失焦由既有 focus-within 收起、给可见焦点框。
- **验证标准**：真实 Tab 巡检命中目标按钮才算数；不是 CSS 里写了 focus-within 就算数。

