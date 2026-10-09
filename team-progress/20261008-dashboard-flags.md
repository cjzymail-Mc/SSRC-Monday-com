# 2026-10-08 登录默认账号与工作仪表盘旗标裁切

用户反馈：登录框每次显示 u1；正式运行的本周/本月仪表盘偶发节点名称/日期显示残片，需要反复刷新，8081 测试界面似乎正常。

## 结论与改动

- `index.html` 的登录用户名原有 `value="u1"`。移除该默认值，为用户名/密码增加 `name`，保留 `username/current-password` 自动填充提示。浏览器是否自动填入保存凭据由浏览器控制。
- 本周视图 `.is-week-locked .timeline-stage-plot` 设置 `overflow:hidden`，聚焦项目的主线旗标向上伸出 plot、并行旗标向下伸出 plot，因此被裁切。截图中只剩日期残片的现象与此吻合。
- 仅聚焦的本周项目 plot 改为 `overflow:visible`；范围筛选与阶段条裁切继续由原有 `clipRange` 逻辑执行。更新样式版本为 `20261008-week-flags`，避免浏览器复用旧样式。
- 本月没有该 overflow 规则，本次隔离回归未复现同样裁切；不能据此认定用户报告的本月异常已全部解决，已向用户询问本月异常具体表现。

## 验证

- 新增 `test_week_and_month_focused_flags_are_not_vertically_clipped`：临时库构造七项目，每项目主线/并行各一个当前节点，1600×900 浏览器反复切换本周→本月→本周、聚焦中间项目，验证两轨旗标不会被 plot 纵向裁切且名称/日期元素可见。
- 修复前：两个本周子用例 FAIL，主线与并行均报告 `overflow=hidden, clipped=True`；本月通过。
- 修复后：新增回归、既有本周/月范围与交互回归、既有 E/D4/P1 全项目画布回归共 3/3 PASS，`Ran 3 tests in 18.578s; OK`。日志：`team-progress/20261008-dashboard-flags-e2e.log`。
- `node tests/timeline_ui.test.js` PASS；修改文件 `git diff --check` PASS。
- 首次沙箱浏览器启动受 WinError 5 限制；经沙箱外审批执行相同临时库浏览器测试，未跳过断言。
- 8080 根页面只读检查返回与仓库一致的旧 CSS/JS 版本标识；未通过正式账号登录或执行任何正式业务写入。未迁移/修改真实库、未重启正式服务、未 commit/push。

正式环境仍需用户确认，尤其是本月异常。
