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
