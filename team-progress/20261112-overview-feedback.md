# 2026-11-12 现场体验修改

状态：本轮六处修改已实现并同步至 8083 独立预览，等待用户继续提出修改点和现场确认。用户明确要求本批修改结束后再统一全盘测试，本轮没有执行全盘回归。

## 已实现

- 项目概览：普通成员每次重新登录默认“我的项目”，管理员默认“全部项目”。同一次登录期间手动切换后，刷新保留选择；退出再登录重新按角色设置默认范围。
- “项目进展”展开区显示距离服务端今天最近的最多 5 个有日期节点，包含已完成和未来节点，主线与并行共用自适应日期范围。“需要关注”继续显示全部逾期未完成节点。用户已撤回“今天轴居中”要求，展开区仍隐藏今天轴。
- 本周、本月的项目名称右键菜单新增“在单仪表盘中查看”，复用项目时间轴的菜单、跳转及返回逻辑，保留既有编辑权限、归档和撤销约束。
- 今天左侧历史蒙版：从两条轨道内部移至项目双轨共同容器，使用一张覆盖整行的蒙版，完整覆盖伸出轨道的旗标和引线。聚焦行蒙版使用与浅蓝背景一致的 RGB 底色、保留原 0.7 透明度，消除横向白色条带；逾期红旗及显式拖拽态仍在蒙版上方。项目概览内嵌区继续隐藏蒙版。

- 项目概览展开区：仅把内层时间轴的 `overscroll-behavior-y` 从完整画布继承的 `contain` 覆盖为 `auto`，让鼠标滚轮继续滚动整页；内嵌时间轴仍不能缩放。

## 现有验证与待办

- `tests/test_overview_recent_e2e.py` 三项定向浏览器验证 PASS（13.473 秒）：成员/管理员重新登录重置范围、刷新保留选择；未来/完成/空项目展开和隐藏今天轴；普通成员查看他人近期节点仍只读。日志：`local-test-data/20261112-overview-recent-e2e.log`；截图：`team-progress/verification/20261112-overview-recent/`。
- CUA 在 8083 的独立核验页实测本周/本月右键入口可见，本周入口能打开所选项目单仪表盘，返回恢复本周视图。原用户页有浏览器批注浮层拦截项目行点击，故使用临时页核验，结束后已关闭临时页并保留原用户页。
- `node --check`（app.js、overview-ui.js、timeline-ui.js）及 `git diff --check` PASS。
- 用户追加要求改后实际视觉检查。CUA 在独立 8083 页查看“晨曦休闲鞋 · 概念款（演示）”展开状态，分别检查整体缩放及放大到约半年日期范围后的双轨旗标：完整淡化、无半截遮盖或横向白带。DOM 几何确认蒙版与项目双轨容器同高 168px，全部可见旗标纵向位于其内。
- 另实看“疾风跑鞋 · 二代研发”单项目仪表盘：蒙版高 190px，右边界与今天线误差小于 0.001px，三个逾期红旗均在蒙版上方，未来节点未被淡化。截图保存在 `team-progress/verification/20261112-row-mask/expanded-completed-project.jpg` 和 `single-overdue-and-future.jpg`。没有刷新用户正在操作的原页面；原页面刷新后加载新版。
- 已更新相关旧用例的默认范围/近期节点预期，后续统一执行时须覆盖 `overview_inline.test.js`、`overview_ui.test.js`、`test_overview_e2e.py`、`test_overview_ux_e2e.py`、`test_overview_recent_e2e.py` 与时间轴菜单、跳转/返回回归。本条不代表这些待跑用例已 PASS。
- 蒙版旧测试已从每轨一张改为每项目一张，并保留双轨淡化、今天边界、图层及未来项目负例；补充原几何检查对整行高度和可见旗标覆盖的断言。`timeline_ui.test.js`、`timeline_period_mask.test.js`、`test_timeline_e2e.py`、`test_timeline_period_mask_e2e.py` 留待批次结束统一运行，本轮只做语法检查及上述实际视觉核验。

- 滚轮实页复现及核验：修复前鼠标位于展开区滚动后 `window.scrollY` 仍为 0；修复后相同位置向下滚动变为 360，再在展开区向上滚动回到 0；内层 `scrollTop` 始终为 0，日期范围始终为 2026-09-08 至 2026-10-18，未触发缩放。截图与结构化证据：`team-progress/verification/20261112-overview-scroll/`。原评论页保留且未刷新，核验临时页已关闭；未增加或运行整套测试。

## 预览与边界

- 8083 静态文件来自 `local-test-data/feature02-interaction-preview/frontend/`，数据库仍为独立的 `local-test-data/feature02-preview/flowboard.db`。已同步 app.js、overview-ui.js、timeline-ui.js、index.html，保留“交互预览”标题。
- 资源版本：app/overview 为 `20261112-overview-recent`；timeline JS/CSS 为 `20261112-flag-hover`，overview CSS 为 `20261112-overview-scroll`。后续改动需同步该前端副本，不能只修改仓库根文件后刷新。
- 没有写正式库、迁移、重启正式服务或执行 commit/push。既有防锁屏改动保留，本记录不改变其状态。

## 待确认：原位放大旗帜样张

用户要求只做显示效果确认；随后明确悬浮后原小旗帜消失，原位置出现包含备注的大旗帜。已制作自包含 HTML `team-progress/20261112-node-flag-hover-sample.html`，A 延续 8° 倾角，B 放大时改为 3°，均保留左下锚点并原位替换，不改变行高。提供短/长/无备注与保持展开开关。

独立样张由 127.0.0.1:8084 提供，服务目录仅为 `local-test-data/20261112-node-flag-hover/`；不连接数据库，也没有改动产品悬浮实现。CUA 已实看短/长/空备注、收起和真实指针悬浮替换，控制台无 error；比较截图在 `team-progress/verification/20261112-flag-hover/long-remark-comparison.jpg`。用户原调试页和样张页均保留，等待用户选定方案后再确定产品实施范围。

用户随后否定初版放大幅度，明确接受2倍且备注必须截断、保持固定排版。样张已收敛为小旗110×38px、大旗220×76px（宽高各2倍）；名称/日期各1行，备注固定2行，超出省略。短、长、空备注在A/B两版实页测量均为220×76，已视觉检查长备注省略及固定布局；最新截图 `team-progress/verification/20261112-flag-hover/fixed-2x-long-remark.jpg`。仍仅更新样张，产品未实施。

## A 方案已接入，待 test 人工验收

用户明确选定 A 并要求施工。共用时间轴悬浮预览已替换为 220×76px 固定大旗帜，保持 -8°，名称/日期各一行，备注两行超出省略，保留原备注换行。原小旗仅在展开期间隐藏，移出恢复；主线保持左下锚点，并行保持原左上锚点，不改变项目行高。沿用节点原灰/逾期红色标识。大旗帜可继续双击编辑、右键操作，已有编辑器及保存/取消/撤销逻辑保留。

- 产品文件：`timeline-ui.js`、`timeline.css`；资源版本已更新为 `20261112-flag-hover` 并同步 8083 前端副本。
- 定向 Chromium 2/2 PASS（16.138 秒）：空备注/长备注固定尺寸与两行截断，移出恢复，悬停大旗保持可读，右键菜单与备注入口，双击编辑，保存/撤销/刷新持久化，纯文本安全，只读预览及全屏 Escape。日志：`local-test-data/20261112-flag-hover-e2e.log`。首轮发现备注预览换行被合并，已保留换行；只读用例按本批成员默认“我的项目”新约定补选“全部项目”。实页右键曾因原节点失焦关闭预览，已阻止大旗鼠标按下夺走焦点并补入回归。
- CUA 在 8083 实看“凌云竞速跑鞋 · 轻量款（演示）”主线和“疾风跑鞋 · 二代研发”并行节点：大旗均 220×76px、小旗 opacity=0，原位锚点误差 <0.04px；右键菜单、进入编辑/取消正常。截图：`team-progress/verification/20261112-flag-hover/implemented-a-main.jpg`、`implemented-a-parallel.jpg`。
- test 页面已刷新并保留在“疾风跑鞋 · 二代研发”单仪表盘，等待用户实际验收。本批全盘回归仍按用户要求留至全部修改结束；上述定向 PASS 不代表全盘验收。未写正式库、重启正式服务、commit/push。

用户验收反馈大旗帜看起来太方：已把右上/右下圆角从5px增至10px，保持旗杆左边直角和固定220×76尺寸。timeline CSS版本更新为 `20261112-flag-round`，已同步并刷新8083；CUA实页确认圆角10px、尺寸不变，截图 `team-progress/verification/20261112-flag-hover/implemented-a-rounded.jpg`。本次纯CSS微调未新增或重跑测试，diff检查PASS。
