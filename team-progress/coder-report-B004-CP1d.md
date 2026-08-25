# B-004 CP1d coder report

## 结论

已最小修复 `CP1_SINGLE_HEADING_LOCATOR_STRICT` 与 `CP1_EXPECTED_VIEWER_403_CONSOLE`，等待主 agent 沙箱外复跑。

## 修正

- 单项目页有顶层单项目白卡标题和内嵌编辑器标题，二者同名是生产结构的合理结果。admin/member 旅程的标题断言收窄为唯一结构：`[data-timeline-page="single"] > .timeline-project-card > header h2`；仍验证真实进入单项目模式，没有删减三模式断言。
- viewer 点击生产时间管理入口后，response 监听现严格断言 R01 `/api/workspaces/1/timeline` 的状态序列恰为 `[403]`，toast 错误展示与 modal 保持关闭仍必须成立。
- viewer 403 对应的 console error 严格限定为恰好一条且含 `403`，pageerror 必须为零；随后只清除此已证明的预期条目，再执行旅程末尾 console/pageerror 全零硬门。没有全局忽略任何 403。

## 复跑命令

`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`

两个 failure key 均为第一次出现，不触发同 key 两次熔断。
