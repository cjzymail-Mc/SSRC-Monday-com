# memory 索引（技术细节 · 按需加载）

- [真浏览器事件序测试坑](browser-event-order-testing.md) — mousedown 隐藏目标会吞 click；合成 .click() 掩盖此 bug，测试须用真实事件序；同族增补：双重渲染竞态、视图切换可见性竞态、hover 显隐命中环（opacity:0+pointer-events:none 锁死 Playwright 物理点击）
- [Gate5 收口状态](gate5-cp2-cp4-status.md) — 门4已签字+两轮 Gate5 用户反馈已修复（08-23，149/24/7 全绿），停在 WAIT_GATE5_HUMAN 等用户复测；工作树未 commit/push 勿误判；Gate5 拍板后删
