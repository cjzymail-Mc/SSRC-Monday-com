# B-004 CP1c coder report

## 结论

已最小修复 `CP1_EXPECTED_PRELOGIN_401_CONSOLE`，等待主 agent 沙箱外复跑。

## 根因与修正

- 生产 `restoreSession()` 在未登录首次加载时会真实请求 `GET /api/session`，预期得到 401 后展示登录框；Chromium 同时记录一条 401 resource console error。这是鉴权入口证据，不是登录后的脚本错误。
- E2E 现结构化捕获 response，并严格断言登录前 `/api/session` 状态序列恰好为 `[401]`；没有全局忽略其他 401。
- 对登录前 console 也严格限定为恰好一条且包含 `401`，pageerror 必须为零；随后分段清空 console/pageerror。
- 新增 `assert_clean_browser()`，三条旅程在关闭 context 前均断言登录后至旅程结束的 console error/pageerror 为零。
- 身份、同步就绪、真实点击事件序、R01/R02/R04/R05、刷新持久化和角色权限断言均保留。

## 复跑命令

`python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'`

本 failure key 为第一次出现，不触发两次同 key 熔断。
