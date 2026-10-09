# 2026-10-08 feature02 项目总览开发交付

用户明确授权根 temp.md 中 feature02 目标作为 goal 推进。temp 已同调用读出→清空→长度0验证；首次输出中文受 PowerShell 编码影响，后续统一 UTF-8。范围与实现口径保存于 `feature-02-进阶仪表盘/01-PROJECT_OVERVIEW_CONTRACT.md`。

交付状态：`DEVELOPMENT_READY / HUMAN_ACCEPTANCE_PENDING / NOT_DEPLOYED`。总览后端HTTP5/5、既有服务35/35、真实Chromium12/12、总览Node4/4、既有UI Node及语法/差异检查PASS。原图SHA256、同尺度视觉对照、真实页截图、实测尺寸、基线快照及feature02独立共享文件diff均在 `verification/20261008-feature02/`。

本轮修复登录初始加载覆盖提前导航竞态和旧登录会话总览响应隔离；默认查询三次SELECT、同一读快照，无新增schema。新增总览CSS/JS/投影及测试，最小接入 app.js/index.html/server.py/timeline-ui.js；TimelineService._view仅新增可选批量nodes/today参数，旧调用行为不变。原timeline.css及既有测试未修改。

隔离体验服务8083，库固定 `local-test-data/feature02-preview/flowboard.db`。管理员test/test，成员u2/localtest。完整体验路径、交付对账、已知限制和截图索引：`feature-02-进阶仪表盘/02-DELIVERY.md`。

未 commit/push/部署，未写真实 flowboard.db，未改变机器配置；用户视觉与手感确认仍待进行。

## 追加体验反馈

用户要求增加不同完成阶段的多项目模拟数据，并批注去掉两条分组横向滚动条。已在8083隔离库新增30项目/240节点，六阶段各覆盖0/25/50/75/100%进度；原有样本保留，新增前SQLite backup完整性ok，新增使用TimelineService创建/批量写入并保留审计。当前全部日期＋含已完成显示37项目/254节点，30样本分为12关注/18推进。两组滚动条CSS隐藏并更新资源版本，实际浏览器核对scrollbar-width=none且两组仍可横向滚动。页面已切到完整比较视图，截图 `verification/20261008-feature02/more-projects-no-scrollbars.jpg`，数据分布和备份路径见 `more-preview-projects.json`。本次未写正式库、未提交或部署。

用户继续指出8节点固定模拟过于简化，要求查看真实库后更真切模拟。只读实库快照：25活跃项目/230节点，中位数11，最大21，日期跨度7–590天；主线219/并行11。已将30个本轮拥有且无用户后续修改的样本按25真实结构＋5密集结构重做为300节点（先备份隔离库，原8节点软删除并保留审计，再创建节点）。保留真实节点词汇、阶段/轨道/日期/完成分布，名称和账户为演示值，备注改为模拟内容。新进度为33/45/50/58/67/73/75/82/83/100%等，不再强制均匀档位。实际浏览器筛出30项目/300节点并展开21节点项目，验证全部21条、多轮打样/测试、同日日期及主线/并行。当前证据 `production-structure-profile.json`、`realistic-preview-projects.json`、`realistic-21-node-detail.jpg`；上一段首批计数为历史。本轮正式库始终mode=ro/query_only，未做业务写入。

用户反馈访问8083看不到改动：核对HTTP全量37项目/314节点、演示筛选30/300，用户当前DOM为默认本周＋未完成18/25，21节点全完成项目因此被筛掉。已恢复当前页全部日期＋含已完成＋搜索（演示），截图 `preview-full-filter-proof.jpg`。另复现快速改筛选即输入搜索时，旧响应重绘取消延迟搜索；改为状态持有计时器、响应校验查询条件和页面/状态绑定回调，更新JS版本。Chromium总览8/8、Node4/4 PASS；新用例覆盖延迟筛选响应与本地展开同时发生的搜索，保留其他会话/权限/草稿断言。首轮测试词「材料」同时命中长备注，改为唯一「鞋面材料」后完整复验。证据 `search-race-regression.log`。正式库本轮未读取或写入。
