# B-004 CP1e coder report

## 结论

已修复 `CP1_DELETE_UI_STALE_AFTER_200` 的真实 E2E 同步根因，等待主 agent 沙箱外复跑。

## 根因与修正

- 生产 `deleteTimelineProject()` 在 DELETE 200 后执行 `timelineState.mode='home'; await loadTimeline()`，会以 R01 最新结果替换 `timelineState.projects` 并重渲染，接线本身完整。
- 原测试在删除点击后等待 `[data-timeline-page="home"]`，但刷新前页面已经处于 home；该等待立即成功，随后 `count()` 抢在异步 DELETE→R01→render 完成前读到旧项目卡。
- 修正后先锁定“浏览器项目”的具体 card，用 `expect_response` 等待该真实 DELETE 响应并断言 200，再等待原 card `state="detached"`，最后仍断言同名项目卡数量为 0，并继续验证临时 DB 的 `deleted_at IS NOT NULL`。
- 未使用 sleep、未删除 UI 持久化断言、未绕开真实点击/confirm/HTTP。

## 复跑命令

`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`

本 failure key 为第一次出现，不触发同 key 两次熔断；上一轮 member/viewer 已由主 agent 沙箱外确认 PASS。
