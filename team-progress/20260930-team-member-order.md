# 团队项目成员卡片个人排序（2026-09-30）

## 用户范围

用户在 8081 调试页圈选【团队项目】中的整张成员卡片，要求管理员和普通成员可自由拖拽卡片；每个账户各存自己的顺序，并沿用仓库已有拖拽动画。

## 实现

- 每张成员卡片增加左侧拖拽把手，复用“我的项目”的指针浮层、卡片让位动画、边缘滚动和 Esc 取消反馈。点击项目药丸仍进入项目页；拖动只改变当前账户的成员卡片展示顺序。
- 新增 `GET/PUT /api/workspaces/{id}/timeline/member-order`。服务端从会话取用户身份，按工作区活跃成员全集核对提交；重复 ID、失效成员、缺失版本、旧版本均拒绝。每个用户和工作区一条版本化记录，成功写入审计。新加入成员按姓名追加，失效成员不显示。
- schema v20 增加 `timeline_member_orders`。迁移前自动备份，并验证外键与完整性；正式库迁移在用户随后明确授权后完成，见下文。
- 831px 与 390px 浏览器实测时修正主页团队网格的最小宽度；手机宽度下成员信息与项目药丸分两行，避免新增把手使页面横向溢出。

## 验证

- `python -m unittest discover -s tests -p 'test_timeline_http.py' -v`：16/16 PASS；覆盖账户隔离、管理员与成员提交、viewer 拒绝、CSRF、版本冲突、成员集合变动和审计。
- `python -m unittest discover -s tests -p 'test_timeline.py' -v`：35/35 PASS；包含 v19→v20 备份、恢复、幂等和完整性验证。
- `node tests/timeline_ui.test.js`、`node --check app.js`、`node --check timeline-ui.js`、Python 编译和 `git diff --check`：PASS。
- 8081 隔离服务健康检查返回 schema v20；本地测试库迁移前备份为 `local-test-data/backups/flowboard-pre-v20-20260930-090919-717731.db`。浏览器实际拖动成员卡片后显示保存提示，刷新后顺序仍保持；831px 视口下页面宽度 816px、成员卡片宽度 563px，390px 视口下页面宽度 375px，均没有横向溢出。

## 当前边界

正式 `flowboard.db` 已在用户明确授权后由 v19 升至 v20，备份恢复与正式启动器 `--check` 通过。本次未启动 8080 服务，未 commit、push 或部署；拖拽体验待用户确认。

## 正式启动拦截后的副本预检

用户反馈正式启动器的 v19/v20 版本不匹配错误后，以 `mode=ro` 读取正式库并通过 SQLite backup API 生成隔离快照。该预检阶段没有写入或迁移正式库。

- 隔离产物：`local-test-data/v20-preflight-20260930-092414/`，详细结果为其中的 `report.json`。
- 已用仓库备份/恢复工具生成并校验备份包，恢复至隔离目录，执行 v19→v20，再从备份恢复至 v19：全部 PASS。
- 升级前后 44 张原有非迁移记录表、1,452 行数据的完整内容指纹一致；新增空表 `timeline_member_orders` 和一条 schema 迁移记录。升级幂等检查通过，完整性 `ok`，外键错误 0。
- 正式库预检前后 SHA-256 相同，仍为 v19：`c538f5cabea5785bf13efeb06888ca7d81c24d61a55fdcd5ad5ae25937304764`。附件引用为 0。
- 该阶段依据 `AGENTS.md` 第 3 节请求用户授权，用户随后回复 `ok`，授权备份正式库、升级至 v20 并验证启动检查。

## 获授权后的正式库升级

- 2026-09-30 09:27（本地时间）完成。维护前确认 8080 没有监听，取得维护锁后重新校验正式库、备份与隔离恢复，随后执行仓库现有迁移函数。
- 完整备份包：`backups/flowboard-pre-v20-authorized-20260930-012635-360012/`；迁移函数额外生成 `backups/flowboard-pre-v20-20260930-092739-491444.db`。两个备份均验证为升级前 v19 数据。
- 恢复实测：完整备份包恢复至 `local-test-data/authorized-v20-20260930-092737/flowboard.db`，全部表数据指纹与升级前正式库一致。
- 首次恢复检查发现读取 WAL 模式备份时产生的空 WAL / SHM 文件；在隔离备份上 checkpoint 并关闭连接后消除临时文件，复核清单及数据库 SHA-256 通过。后续对静态副本使用 `immutable=1` 只读检查，正式库仍按普通只读连接检查。
- 正式库现为 v20，原有 44 张非迁移记录表、1,452 行数据指纹不变；仅新增空的 `timeline_member_orders` 和 schema 迁移记录。integrity `ok`、外键违规 0。
- `cmd /c start-flowboard.cmd --check`：退出码 0，输出 `Database schema: v20; required: v20; integrity: ok; foreign keys: 0` 和 `Flowboard local launcher is ready.`
- 机器可读证据：`team-progress/20260930-v20-production-migration.json`。本次授权范围已完成，没有启动生产服务。
