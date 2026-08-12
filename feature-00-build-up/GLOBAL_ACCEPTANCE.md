# Flowboard 全局验收索引

验收基线：schema v15，Python 3.10+，约 15 人 Windows 局域网自托管。权威范围来自 `.copilot-task.md`；实现证据来自当前 worktree、真实 SQLite/HTTP/Chromium 和隔离运维演练。本文件不把未来候选纳入验收。

## 最终命令证据

| 层级 | 命令 | 结果 |
|---|---|---|
| Python 全量 | `python -m unittest discover -s tests -p 'test_*.py' -v` | 79/79 PASS，0 skip，含 9 个真实 Chromium E2E |
| Node 全量 | `node --test tests/*.test.js`（PowerShell 中以发现出的 5 个文件执行） | 5/5 文件 PASS；0 skip |
| Python 语法 | 对 `rg --files -g '*.py'` 全部执行 `python -m py_compile` | PASS |
| JavaScript 语法 | 对 `rg --files -g '*.js'` 全部执行 `node --check` | PASS |
| diff | `git diff --check` | 无 whitespace error；只有 Git 的 LF→CRLF 工作树提示 |
| 运行库只读检查 | `PRAGMA user_version/integrity_check/foreign_key_check` | `15 / ok / []` |
| 运维 CLI | `flowboard_ops.py --help` 及五个子命令 `--help` | PASS；命令与 `WINDOWS_OPERATIONS.md` 一致 |

测试发现审计：12 个 `test_*.py` 文件、5 个 `*.test.js` 文件；未发现 `skip`、`expectedFailure` 或删除/重命名规避。浏览器与 Node 子进程因 Windows sandbox 会报 `WinError 5`/`spawn EPERM`，相同套件在获准的沙箱外运行并全部通过。

## 全局 done_when 1～17

| # | requirement | 权威实现与接口 | 当前证据 | 结论 |
|---:|---|---|---|---|
| 1 | I3～I13 独立验收 | `database.py` v3～v15；各 checkpoint 服务/UI | double-session seq 3～56 的逐棒审核；I13 独立复现 restore 回滚 | PASS |
| 2 | 核心任务与高级模型 | `service.py` 生命周期、层级/依赖/关系；`advanced.py`；`transfer.py` | `test_secure_foundation`、`test_collaboration`、`test_views_e2e` | PASS |
| 3 | 七类视图可操作 | `app.js`、`view-*.js`、`schedule-ui.js`、`dashboard-ui.js` | 6 个 views E2E 覆盖 table/Kanban/calendar/timeline/gantt/chart/dashboard | PASS |
| 4 | 共享数据/查询/权限/version | `query.py` 与统一 task/field 表；所有视图调用 board query | 跨视图 E2E、stale 409、viewer/private ACL 测试 | PASS |
| 5 | 筛选/排序/保存视图 | `/api/boards/*/query`、saved views v4～v6 | view-state 45、view-ui 14、HTTP/E2E | PASS |
| 6 | 团队协作链 | comments/mentions/attachments/subscriptions、notifications/search/activity/audit | collaboration HTTP/service/E2E 与 I12 两上下文 E2E | PASS |
| 7 | 实时/降级/冲突 | SSE cursor、轮询降级、version 409 | I12 E2E 断线恢复；I12 raw-cursor positive/negative tests | PASS |
| 8 | 批量/详情/回收/保留恢复 | batch API、task detail、trash preview/purge、operations | I13 7 个 service/operations tests + 390px E2E | PASS |
| 9 | 服务端权限与输入安全 | `security.py`、service ACL、CSRF、thin server routes | admin/member/viewer、IDOR、MIME、size、path、CSV/XSS/SQL/静态 allowlist 矩阵 | PASS |
| 10 | 迁移连续/幂等/保数据 | `schema_migrations` 1..15，checksum `flowboard-schema-vN` | legacy fixtures 连续 migrate、pre-v15 backup、重复 migrate、integrity/FK | PASS |
| 11 | 备份/保留/真实恢复 | `operations.py`、`flowboard_ops.py` | manifest/checksum、成功 DB+blob restore、损坏拒绝、8 点失败回滚 | PASS |
| 12 | 完整回归与关键旅程 | `tests/` 12 Python + 5 Node files | 79 Python + 5 Node files + syntax/diff 全过 | PASS |
| 13 | 桌面与 390px | responsive CSS、移动可替代按钮/批量条 | collaboration/I12/views mobile E2E；I13 390px 无横向溢出 | PASS |
| 14 | 文档一致 | README、架构、主线、subplan、Windows 运维、本文件 | CLI help、schema/API/static allowlist/恢复顺序交叉核对 | PASS |
| 15 | 不扩范围 | `PROJECT_MAINLINE.md`、feature map 排除清单 | 未实现 CRM/AI/workdocs/automation/SSO/native app 等未来项 | PASS |
| 16 | 无阻断与人工项 | double-session 累积清单 | `OPEN_BLOCKERS=[]`；`PENDING_HUMAN_NONBLOCKING=[]` | PASS |
| 17 | 无表面通过 | 全部历史测试保留；统一模型不复制 | 测试发现审计、运行库计数/Unicode/完整性、权限负测 | PASS |

## I3～I13 / schema / 测试映射

| checkpoint | schema | 核心能力 | 主要自动化 |
|---|---:|---|---|
| I3 | v3 | 动态字段与类型化值 | secure foundation 动态字段矩阵 |
| I4 | v4 | 查询、排序、保存视图 | view-state/view-ui、query HTTP |
| I5 | v5–v6 | table/Kanban/calendar presentation/order | views E2E |
| I6 | v7 | 子任务、依赖、进度、日期策略 | hierarchy/dependency service + E2E |
| I7 | v8 | 高级字段、关系/镜像/公式 | advanced ACL/formula/cycle tests + E2E |
| I8 | v9 | 模板与导入导出 | transfer safety/round-trip + E2E |
| I9 | v10 | timeline/gantt/schedule | schedule 7 tests + E2E |
| I10 | v11 | chart/dashboard/widgets | dashboard service/HTTP/Node/E2E |
| I11 | v12–v13 | 评论、提及、附件、订阅 | collaboration service/HTTP/two-user E2E |
| I12 | v14 | 通知、搜索、SSE、审计 | I12 service/Node/two-context E2E |
| I13 | v15 | description、batch、retention/purge、backup/restore、mobile | I13 service/operations/390px E2E |

运行库 `schema_migrations` 恰为 1～15 连续集合，每项 checksum 为 `flowboard-schema-v1` … `flowboard-schema-v15`。关键索引、唯一约束与外键由迁移和查询/并发测试共同覆盖；当前运行库只读计数保持 `workspaces=1, boards=1, groups=2, tasks=5, attachments=0, audit_log=2`。

## 关键旅程覆盖矩阵

| 旅程 | 桌面/双用户 | 390px | 证据 |
|---|---|---|---|
| 登录→board/group/task→字段→保存查询→三视图 | 是 | 是 | views E2E + secure foundation |
| 子任务/依赖/关系/镜像/公式 | 是 | 基础详情 | views hierarchy/cross-board E2E |
| 模板/导入导出→timeline/gantt→chart/dashboard | 是 | 时间线 fallback | views E2E + dashboard/schedule tests |
| 评论/提及/附件/订阅→通知/搜索/实时降级/冲突 | 双上下文 | 是 | collaboration + I12 E2E |
| 批量→详情→回收站/保留→备份 | 是 | 批量真实操作 | I13 E2E + I13 service/operations |

这些旅程合理拆为多个隔离 E2E，避免一个超长浏览器脚本掩盖失败定位；它们共享同一真实 server、SQLite、HTTP 与原生 UI 路径。

## 权限与安全矩阵

| 边界 | 正/负证据 |
|---|---|
| 未认证、session/cookie/header、CSRF | 登录/session/CSRF/header spoofing HTTP tests |
| admin/member/viewer、open/private、撤权 | secure foundation、dashboard/private ACL、I12 mixed backlog |
| mutation、stale、IDOR、父资源状态 | lifecycle/field/relation/collaboration/batch 403/409/422 tests |
| query/view/aggregate/dashboard/search/notification/SSE | 权限过滤与来源失权测试；隐藏事件推进 raw cursor |
| XSS/SQL/CSV/formula | escaping/参数 SQL、CSV prefix、受限 formula AST、transfer tests |
| attachment/path/MIME/size/static | content signature、1MB/20-file bounds、path traversal、exact GET/HEAD allowlist |
| purge/backup/restore | admin-only、hash/confirmation、pre-purge backup、包名约束、offline-only restore |
| 失败副作用 | batch activity/audit/realtime 计数；stale/duplicate/viewer 零污染；restore 8 点回滚 |

依赖仅使用 Python 标准库与浏览器原生能力；因此没有第三方应用依赖清单需要联网漏洞数据库。Playwright 仅为测试环境工具，离线/受限网络下未伪造外部漏洞扫描结果。

## Windows 冷启动、升级与恢复

- 冷启动与升级由每个 HTTP/E2E fixture 在临时目录调用 legacy fixture→`create_server` 完成；验证迁移备份、health/login/static/core API 和安全 shutdown。
- legacy/v1/v6/v7/v8/v9/v13/v14 路径由 migration tests 逐段保数据并验证幂等；v14→v15 会生成 `flowboard-pre-v15-*`。
- CLI 与 operations 测试在隔离目录完成 backup/list/verify/retention/restore，含真实 blob、数据改变后成功恢复、损坏包拒绝、8 个故障点回滚和 pre-restore 包验证。
- 最终 CLI 命令级演练使用 fail-fast JSON 包装：backup `.package` 与 list 同名 `valid=true` 交叉验证，verify 得到 format 1/schema 15，retention 无误删，restore 副本得到 schema 15/integrity ok/FK 0；临时目录随后确认清理。
- 当前运行库只做只读 PRAGMA/计数；未对其 purge、restore、重建或猜测修复。
- 运行服务、NTFS、防火墙和 HTTPS 的机器级配置未在测试中改动；可安全执行部分及人工部署边界见 `WINDOWS_OPERATIONS.md`。

## 范围与卫生

主线七问结论：目标仍是 15 人 LAN 看板；当前变更直接服务 board/view；动态字段与 query 是共享底座；没有复制任务模型；权限/version/activity 统一在 service；SQLite/原生 Web 足够；未引入未来产品线。测试只使用 TemporaryDirectory/临时端口；运行库迁移备份被保留，没有删除用户或既有未跟踪文件，也没有执行 commit/push/发布。

最终结论：17 项全部有当前权威证据，`OPEN_BLOCKERS` 与 `PENDING_HUMAN_NONBLOCKING` 均为空，候选状态为 PASS，等待 planner 独立 completion audit。
