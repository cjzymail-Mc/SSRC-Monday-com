# B-004 CP1b coder report

## 结论

已最小修复 `CP1_LOGIN_READY_LOCATOR_STRICT`，等待主 agent 沙箱外复跑。

## 根因与修正

- `#currentUser span` 同时命中 `.avatar` 与显示名称节点，Playwright strict locator 正确拒绝歧义；生产登录/bootstrap/query 本身无失败。
- 就绪 locator 收窄为唯一且有语义的 `#currentUser > span:not(.avatar)`。
- 不仅等待可见，还按登录用户断言生产 DOM 显示身份：`u1=管理员`、`u2=成员`、`u3=只读`；随后仍等待 `#loadState == 刚刚同步`。
- console error/pageerror 监听与断言、点击事件序、R01/R02/R04/R05、刷新持久化和权限旅程均原样保留。

## 复跑命令

`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`

本 failure key 为第一次出现，不触发两次同 key 熔断。
