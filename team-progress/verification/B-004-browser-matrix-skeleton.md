# B-004 CP0 · 真实浏览器独立验收骨架

> 状态：**STATIC_ONLY / NOT_ACCEPTED**  
> 角色：planner；本文件只冻结验收方法和关门信号，不签任何实现项 PASS。  
> 外部真相：`team-task.md` §11；`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` §3–§5、§7、§8.3；`.claude/memory/browser-event-order-testing.md`。  
> 独立性：验收标准由冻结契约和生产入口推出，不以 coder 报告或现有静态渲染结果为标准。

## 1. 当前静态盘点（不构成 PASS）

- 生产入口已存在 `index.html` → `timeline-ui.js` → `app.js`，`#timelineBtn` 打开 `#timelineModal`；当前 `app.js` 只见全项目 GET + 静态 `renderAll` 接线。
- 当前 `timeline-ui.js` 具备部分两轨、阶段、筛选/排序静态 HTML，但未据此认定右键、草稿、提交、冲突、撤销、导入/导出等交互完成。
- Python Playwright 包已可 import；仓内已有 `tests/test_views_e2e.py`、`test_collaboration_e2e.py`、`test_i12_e2e.py`、`test_i13_e2e.py` 的 Chromium 先例。受当前受限执行环境的子进程权限影响，runner 启动探针得到 `WinError 5`；这不是产品失败，也不授权安装、下载或改配置。正式验收须在允许 Playwright 启动子进程的既有项目环境执行。
- 无 `package.json`，不把 Node 浏览器 runner 当作既有能力；本轮不安装任何 runner。

## 2. 统一隔离夹具与取证协议

每个浏览器测试必须：

1. 用 `TemporaryDirectory(prefix="flowboard-timeline-e2e-")` 建独立 `flowboard.db`、附件、备份目录；以既有 legacy fixture 建库并走正常迁移，不复制、不打开生产库写连接。
2. `create_server("127.0.0.1", 0, temp_db)` 使用 OS 分配随机端口；线程启动后只访问 `server.server_address[1]`，结束时关闭 browser/context/server/thread/tempdir，并恢复环境变量。
3. 从真实 `index.html` 登录，点击生产导航进入，不以 `page.set_content()`、组件样张或直接调用 `FlowboardTimeline.*` 代替。
4. 为每页挂真实 recorder：捕获 `mousedown`、`mouseup`、`click`、`contextmenu`、pointer/drag 事件（含 `event.target`/坐标/时间），同时记录 request/response（method、URL、status、post_data）及页面 console/pageerror。关键点击必须断言同一可命中目标的 `mousedown → mouseup → click` 次序；右键须由真实鼠标 secondary button 触发。
5. 状态证据用测试库 SQL 快照：相关五表逐表 `COUNT(*)`、目标行/version/deleted_at、batch/change/import 行与必要 payload/details；失败前后比较。真实 `flowboard.db` 和 `.copilot-*` 在波次前后记录 size/mtime/sha256，必须不变。
6. 网络“零请求”先证明 recorder 能捕获一个已知健康 GET；数据库“零写入”先在另一个临时夹具或事务内制造一笔可回滚写入并证明快照检测器会报差异。阳性对照不得污染被验收旅程。

### 2.1 吞 click canary（每次关门波次必跑）

在隔离测试页放置可见按钮；document 的 `mousedown` 处理器故意隐藏/移除按钮。用 Playwright `locator.click()` 或真实 mouse hit-testing 点击，必须观测 `mousedown`，且目标上的 `mouseup/click` 缺失，动作计数保持 0。随后用安全实现（目标内不隐藏）必须完整记录 `mousedown → mouseup → click` 且动作计数为 1。若 canary 未红/未绿，本波次所有点击证据作废。

禁止把 `element.click()`、handler 直调、单个合成 click、对已隐藏元素手工派三事件当 canary 或产品 PASS。

## 3. CP0–CP6 关门矩阵

下列测试名是 coverage map 应绑定的具名浏览器测试目标；最终名称可机械调整，但必须由独立验收器确认真实、可加载、唯一归属且能执行。每项均需 Chromium 正例、独立负例和可观察状态证据。

| CP | 建议具名测试 / 真实操作 | 必须同时成立的关门信号 | 独立负例与阳性对照 |
|---|---|---|---|
| CP0 coverage map | `test_b004_coverage_map_is_complete_and_loadable`（独立 validator） | 冻结 §3–§5、§7、§8.3 每条均映射生产入口、一个可加载浏览器测试和唯一 CP；状态词合法；无重复/悬空测试名 | 删除任一映射副本必须报 `MISSING_MAPPING`；替换为伪造测试名必须报 `TEST_NOT_FOUND`；真实 map 才可 exit 0 |
| CP1 入口与生命周期 | `test_cp1_real_navigation_create_read_delete_refresh_and_roles` | admin 登录后真实点击进入全项目、单项目、编辑器三模式；创建后 DOM 出现且刷新仍在；admin 软删后刷新消失且 DB `deleted_at` 非空；member 可读/可按冻结权限操作，viewer 连读 timeline 都 403；所有写请求有真实 HTTP status 与 DB 差分 | viewer/越权/缺 CSRF 分别经 UI 或同 context 的真实请求触发 403/403/403 且零写；去掉目标按钮或服务端拒绝时测试必红；导航点击事件序完整 |
| CP2 本地草稿 | `test_cp2_real_context_menu_drag_draft_discard_and_leave_guard` | 对节点真实右键出现四项；每次拖动必须重新选 single/cascade；single 双向钳制、cascade 前驱钳制并只平移本轨后续；标准 1 日磁吸、±10 天 ×8 放大带；状态+日期进入同一草稿；日期/阶段排序只改显示；放弃复原；有草稿离开被拦截 | 拖拽窗口内 timeline mutation 请求数严格 0 且 DB 快照不变；先做健康 GET 网络 canary；故意在 mousedown 隐藏菜单项的吞 click canary 必红；绕过重选、跨轨级联、排序改数据任一出现即红 |
| CP3 提交/冲突/撤销/纠正/复盘 | `test_cp3_real_submit_conflict_undo_correction_review_journey` | 点击红色【更新日期】只产生一次 batch POST，payload/details 含 `mode/magnet/zoom_band` 且状态+日期同批；成功后刷新持久；真实点击 undo 生成反向批次并恢复；admin initial correction 可用，member 403；review 显示 actor/change_rows/审计类型 | 两 context 制造 stale version：409 后 UI 使用服务端最新视图、草稿不得静默重放，DB 四表快照零写；缺 CSRF/权限失败亦零写；response/DB recorder 的失败探针先被已知写入证明可检测 |
| CP4 单/全仪表盘 | `test_cp4_real_single_all_dashboard_filters_tracks_overlap_and_shared_menu` | 单/全项目共享绝对日历和今日线；每项目主线/并行最多两轨；仅重叠段上下分半，展开后阶段可区分；阶段区间与节点一致；本周橙、逾期红且红左橙右；项目多选及四种排序真实生效；两个仪表盘对同一节点右键得到同一四项菜单控制器 | 切换筛选/排序不得写 DB；构造重叠/不重叠、红/橙/同时命中 fixture 防假阳；移除任一轨/今日线/菜单项或令两页面菜单行为分叉时测试必红；DOM token/截图不能代替几何与 hit-test 断言 |
| CP5 Excel UI | `test_cp5_real_preview_commit_export_and_reimport_journey` | 用真实 file chooser 上传 XLSX：preview 显示行级 `row/header/reason`、多 sheet 首 sheet 提示、CSV 日期转换提示；只在 commit 后写库；导出点击捕获真实 POST，解 base64，校验 sha256 与下载字节；在新 workspace 将导出字节重新上传 preview→commit 并核对项目/节点/轨道/顺序/值 | 文件级拒绝、行级错误、过期/跨 workspace batch 均零写；伪造 hash 或改一字节必须被校验器抓住；上传 preview 前后 DB 不变，commit 前先用已知写入证明 diff recorder 有效；不得用自行拼装 workbook 替代服务端导出字节 |
| CP6 独立关门 | `test_cp6_fresh_db_edit_discard_submit_refresh_undo`；`test_cp6_fresh_db_single_all_dashboard_journey`；`test_cp6_fresh_db_import_export_reimport_journey` | planner 在全新隔离库依次复跑三条完整旅程；每条有 Chromium trace/事件序、request/response、DB 前后快照；三条均独立通过；真实库与 `.copilot-*` 指纹不变 | 同波次执行吞 click canary、网络/DB recorder 阳性对照；任一 canary 不按预期失败，整波次证据无效；不得引用 coder 自跑作为独立签注 |

## 4. CP 内部最小断言清单

### CP1

- 三模式必须由可见入口真实点击到达，URL/模式标记/可操作控件三者至少两项可观察，不能只断言 modal 文本。
- admin/member/viewer 使用独立 browser context；不得通过改前端全局变量模拟角色。
- 删除只接受服务端软删证据；DOM 消失本身不足。

### CP2

- 鼠标移动要从节点实际 bounding box 起点出发，使用真实 `mouse.down/move/up`；不得直接设置 draft state。
- 每轮 drag 前断言菜单模式未选择；完成一次后再次 drag 必须重新右键选择。
- 连续拖同 node 最终草稿为准；离开拦截分别覆盖取消离开、确认离开。

### CP3

- `expect_request/expect_response` 精确限制 timeline batch endpoint；断言提交次数恰为 1。
- 409 前后比较 batch/change/node/project 目标状态；页面展示必须对应冲突响应里的 server latest，而非额外 GET 偶然覆盖。
- undo 通过真实控件点击；直接 service/API 调用只能造 fixture，不能算旅程动作。

### CP4

- 共享日历用相同日期在不同项目的几何 x 坐标容差断言；今日线跨泳道高度用 bounding box 断言。
- “仅重叠段分半”至少三段 fixture：无重叠、局部重叠、边界相接。
- 排序按实际业务键和稳定行序断言，不只看 select 的 value。

### CP5

- 上传必须用 `set_input_files` 驱动生产 file input；preview/commit 皆记录真实 HTTP。
- 下载/导出须以 response JSON 的 base64 解码字节为源；sha256 同时与 response 字段、下载字节比对。
- 新 workspace 重导后以 HTTP 读回并用 DB 辅证；不能在原 workspace 自循环掩盖 workspace 错接线。

## 5. 明确不算 PASS 的证据

- `timeline_ui.test.js`、纯函数/Node 快测、DOM 字符串包含、CSS token、静态 selector 数量。
- 截图、像素对比或人工“看起来正常”（Gate 5 人工视觉另行处理）。
- mock fetch、route fulfill、service 直调、测试内直接写 DOM、孤立 `page.set_content()` 组件。
- `element.click()`、`evaluate("handler()")`、单一 synthetic click，或对已隐藏目标固定派三事件。
- 只查 HTTP 200 不查请求 payload/响应/DB；只查 DOM 不查刷新持久化；只查无请求却未证明 recorder 能抓请求。
- coder 报告、自跑日志、旧 E2E 绿灯或 CP0 静态存在性检查，均不能代替 planner 新隔离库的 CP 签注。

## 6. CP0 输出判定

本文件只提供独立验收骨架：**STATIC_ONLY**。它不表示 coverage map 已完整、不表示任何浏览器旅程存在，也不表示 Chromium 在当前受限进程环境已经执行。待 coder 的 CP0 coverage map 落盘后，planner 应以本文件的 validator 规则执行真实 map + 两个阳性对照，合格后才可签 CP0，并严格按 CP1→CP6 顺序推进。
