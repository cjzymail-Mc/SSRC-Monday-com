# B-004 CP1 planner 独立验收结果

最终结论：`PASS`。独立探针已由主 agent 在允许 Playwright driver/Chromium 子进程的环境复跑，exit 0、JSON `status=PASS`。

## 已落独立探针

`probe_cp1_browser.py` 从生产 `index.html` / `app.js` 入口、新迁移临时数据库与随机端口运行，不导入 coder 的 E2E 测试，也不把 Node/静态证据冒充浏览器证据。它独立覆盖：

- mousedown 移除目标必吞 click 的红 canary，以及安全目标 `mousedown → mouseup → click` 绿 canary；
- admin 真实登录、入口点击、R04 新建、R01/R02 读取、编辑器/单项目/全项目三模式、刷新持久化和 R05 软删；
- admin/member/viewer 控件矩阵；member 强制 R05 得到服务端 `403 ADMIN_REQUIRED`；viewer 生产入口 R01 得到 403；
- 登录前 `/api/session` 恰一条 401 与对应 console、viewer R01 恰一条 403 与对应 console，均与其余登录后 console/pageerror 零错误分段；
- member 失败 R05 与 viewer 失败 R01 前后，临时库 `timeline_projects/timeline_nodes/audit_log` 全内容 SHA-256 和逐表行数完全不变；
- 真实 `flowboard.db` 的 size/mtime/SHA-256 前后不变。

## 本环境执行

- `python -X utf8 -m py_compile team-progress\verification\B-004-CP1\probe_cp1_browser.py`：PASS。
- `python -X utf8 team-progress\verification\B-004-CP1\probe_cp1_browser.py`：在 `sync_playwright()` 创建 driver overlapped pipe 时得到 `PermissionError: [WinError 5] 拒绝访问`，尚未运行任何产品断言。
- failure key：`PLAYWRIGHT_DRIVER_WINERROR5`。这是本 planner 的一次执行；依据既有同环境边界不重复启动、不安装、不降级签注。

## 沙箱外复跑

从 repo 根运行：

`python -X utf8 team-progress\verification\B-004-CP1\probe_cp1_browser.py`

exit 0 且 JSON `status=PASS` 后，planner 才能把 CP1 改签 PASS；任何断言 failure key 均应回 coder 定点修复。完整 stdout/stderr 应保存在本目录 `outside-run.txt`。

沙箱外 canary 两次暴露验收器假设过窄：Playwright 调用不必抛异常；目标在 `mousedown` 被移除后，浏览器还可能把 `mouseup` 重新 hit-test 到旁边的安全目标。最终判据按硬门本义锁定：坏路径必须从 `bad:mousedown` 开始、移除的 bad 不得收到 mouseup、全路径不得产生 click、动作计数必须为 0；随后清空事件，以真实点击精确证明 good 的三事件及动作计数 1。未移除 canary、未直接调用 handler。

canary 通过后的首次产品段运行暴露独立探针监听 URL 写成 `/api/login`，而生产真实登录路由是 `/api/auth/login`；因此 POST 200 虽发生，监听器未收 payload 并触发 `LOGIN_CSRF_MISSING`。已只修正监听 URL，仍要求真实 200 JSON 含 `csrf_token`，未绕过 CSRF 断言。

后续运行通过 canary 与 admin 旅程，进入 member 零写 hash 时暴露探针把真实审计表名 `audit_log` 误写为 `audit_logs`，`PRAGMA table_info` 返回空列。现已限定并显式校验三张真实表 `timeline_projects`、`timeline_nodes`、`audit_log`，仍对每张表全部列、全部行排序后做同一内容 hash，没有削弱零写范围。

再运行到 member 越权时，探针从外层 `[data-timeline-page=editor]` 读取不存在的项目属性，错误构造了 `/null`。生产项目 id 实际在其内的 `.timeline-editor[data-timeline-project]`；现从该真实 DOM 属性读取并先硬断言非空数字，再发 R05，三表 hash 比较原样保留。

member R05 随后已真实返回 `403 ADMIN_REQUIRED` 且三表 hash 门通过；浏览器按预期为该 resource 403 产生一条 console error。现像预登录 401/viewer R01 403 一样做局部分段：R05 code 已精确断言后，console 必须恰一条且含 403、pageerror 必须为 0，随后只清除此条，再要求 member 余程全零；没有全局忽略 403。

## 最终动态结果

- canary：坏路径从 `bad:mousedown` 开始、无 click、动作计数 0；好路径精确 `mousedown → mouseup → click`、动作计数 1。
- admin：生产入口、单项目、全项目三处关键点击均完整三事件；R04=201、R01/R02=200，刷新后项目仍在，R05=200 且软删后 DOM 脱离。
- member：新建控件存在、删除控件不存在；强制 R05 精确 `403 ADMIN_REQUIRED`，`timeline_projects/timeline_nodes/audit_log` 全内容 hash 前后一致（输出前缀 `c9b8...`）。
- viewer：生产入口真实 R01 精确 403，modal 不打开且无新建/删除控件；三表全内容 hash 前后一致（输出前缀 `20de...`）。
- console/pageerror：预登录 401、member R05 403、viewer R01 403 均各自结构化证明并局部清除；登录后的其余 console error/pageerror 为 0。
- 真实 `flowboard.db`：size、mtime_ns、SHA-256 前后完全一致。

耐久摘要见 `outside-run.txt`。验收器修正 keys 全部属于 planner probe，而非产品 failure：`CANARY_HIDDEN_TARGET_DID_NOT_FAIL`、`CANARY_BAD_SEQUENCE`、`LOGIN_CSRF_MISSING`、`PROBE_CONTENT_HASH_ZERO_COLUMN_OBJECT`、`PROBE_MEMBER_PROJECT_ID_NULL`、`PROBE_EXPECTED_MEMBER_403_CONSOLE`。最终产品断言无 failure key。
