# B-004 CP1a coder report

## 结论

修复 `CP1_LOGIN_WAIT_TASK_ROW` 的真实 fixture 根因，等待主 agent 在沙箱外复跑；不申请本地浏览器 PASS。

## 根因与修正

- 沙箱外服务证据已证明登录、bootstrap 与 board query 均成功；超时发生在 E2E helper 固定等待 `.task-row`。
- CP1 使用 `migrate()` 创建的全新隔离库，任务行不是登录成功或生产应用完成首轮 refresh 的不变量；空看板合法渲染 `.empty-state`，因此 `.task-row` 会稳定超时。
- `tests/test_timeline_e2e.py::login` 改等生产 `refresh()` 在 bootstrap/query/render 完成后设置的两个信号：`#currentUser span` 与 `#loadState == 刚刚同步`。
- 同时在导航前注册真实 `console(error)` 与 `pageerror` 监听，并在登录就绪后断言均为空。此修正没有删除业务断言、没有降级成静态证据，也不会把实际脚本异常误判为“空数据”。

## 本地验证

- 本地受限环境仍遵守既有 `PLAYWRIGHT_DRIVER_WINERROR5` 边界，不重复启动浏览器。
- 应由主 agent 沙箱外复跑：`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`。
- 若复跑再次得到同一 `CP1_LOGIN_WAIT_TASK_ROW`，按两次同 key 熔断；本修正已完全移除该等待点，预期不会再现。
