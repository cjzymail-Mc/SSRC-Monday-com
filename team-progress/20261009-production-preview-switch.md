# 8083临时连接生产数据库

2026-10-09，用户明确要求将调试入口数据库切换为当前真实生产数据库以验收实际效果。当前8083直接使用仓库根 `flowboard.db`，不是快照；真实库25活跃项目/230节点。原演示数据仍在 `local-test-data/feature02-preview/flowboard.db`。

## 当前入口与行为

- URL：`http://127.0.0.1:8083/`，刷新页面后使用现有生产账号。真实库不存在test账号；没有新增或修改账户/密码。
- 启动：`feature-02-进阶仪表盘/production-preview.cmd`；Python启动器固定连接根真实库，先只读检查schema与完整性/外键，拒绝缺失库或版本不匹配，不调用迁移或演示seed。
- HTTP服务、鉴权与业务能力沿用现有生产Handler/Service；保存、导入、归档等操作直接写真实数据，用户已在切换前收到说明。未自动执行这些业务操作。正常登录会写会话及审计。
- 使用独立cookie `flowboard_production_preview_session`，避免8083登录/退出覆盖8080浏览器登录cookie。附件/备份路径与生产库匹配，不改机器级配置。
- 启动时PID17444；只替换经命令行路径核验的8083演示进程PID8784，没有操作8080。

## 验证与恢复

证据目录：`verification/20261009-production-preview/`。只读预检schema v20、integrity ok、外键违规0；切换前用SQLite backup生成一致快照，备份路径和SHA256见`before.json`。启动后`/api/health`为ok，日志明确记录实时生产库路径；`after.json`显示用户/成员、项目/节点、标签/关系及已有个人顺序表哈希没有变化。没有迁移、恢复、清理、账号改写或业务验证写入。

备份仅用于恢复保障，没有将备份作为预览数据源。不要为了测试而在真实库执行演示初始化。后续自动测试继续使用临时库，不能把8083当作可随意修改的隔离环境。

切回演示时，先核验并停止当前8083 production-preview进程，再启动 `feature-02-进阶仪表盘/local-preview.cmd`；原演示库与项目仍保留。此次为临时验收连接，不等同于feature02正式上线、Git提交或迁移授权。
