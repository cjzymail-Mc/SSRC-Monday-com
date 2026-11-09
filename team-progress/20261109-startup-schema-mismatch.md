# 2026-11-09 正式启动失败：代码 v21 / 数据库 v20

状态：用户已明确授权备份、升级并启动；正式库已升级至 v21，原有数据核对及正式备份恢复验证通过，8080 已恢复后台运行。

## 原因与修复路径

- `cmd /d /c start-flowboard.cmd --check` 返回 `Database v20; code requires v21`。
- 最新合并 `4a0191c` 包含 `e205ad9`（样鞋下单），将 `flowboard/database.py` 的 `SCHEMA_VERSION` 从 20 升至 21，增加两张样鞋数据表。故障发生时本机代码已更新，正式数据库仍为 v20。
- 启动脚本上次功能修改是 `b021383`（2026-10-13），此次未被更新损坏；启动器按既有规则拒绝自动迁移正式库。
- 应使用现有 `python -X utf8 flowboard_deploy.py upgrade` 完成完整备份、迁移和核验，再运行 `start-flowboard.cmd`；不需要重新安装、替换数据或再拉代码。

## 本次代码变更

- `start-flowboard.cmd` 无参数启动失败时保留错误窗口，按任意键后退出；带参数的自动化检查保留直接返回原退出码的行为。
- `flowboard_deploy.py` 对旧库给出明确的备份升级命令，对比代码更新的数据库提示使用匹配代码、禁止降级。
- README 补充双击失败及代码已更新但数据库未升级的处理说明。
- 两项新增部署回归覆盖 v20 拒绝启动、升级保留数据与完整备份，以及实际 CMD 错误窗口与退出码。

## 验证

- 部署回归：`python -X utf8 -m unittest discover -s tests -p test_deployment.py -v`，17/17 PASS，85.065 秒。
- 首次沙箱运行在结束测试进程时被 `taskkill` 权限拒绝；已在获准的沙箱外清理本轮隔离进程并重跑，完整通过。未以修改测试断言处理环境限制。
- 正式源库以 SQLite `mode=ro` 读取并通过 SQLite backup API 复制到 `local-test-data/20261109-startup-verified/`；真实数据和派生指纹仅保留在该 Git 忽略目录。
- 副本复现旧版本拒绝启动；经现有 `upgrade` 工具升级到 v21，完整性 `ok`、外键违规 0。
- 原有 46 张表中，45 张表（包括账号、密码哈希及全部业务数据）内容和建表结构保持一致；`schema_migrations` 原 20 条完全保留，仅新增 v21 记录。新增 `sample_orders`、`sample_order_files` 两张空表。
- 升级前完整备份通过校验，并实际恢复到另一隔离目录；恢复库与源库全部表及版本一致。
- 实际 CMD 启动副本成功：health 200/schema21；首页和样鞋页面 200，未登录 bootstrap 与样鞋 API 401，数据库路径 404。验证后停止该临时服务。
- 验证前后正式源库的全部表内容、结构和版本一致。`git diff --check` PASS。
- 本机隔离原始证据：`local-test-data/20261109-startup-verified/proof.json`、`startup.log` 及 `backups/deployment-*.json`。

## 获授权后的正式执行

用户回复“授权备份、升级并启动”后执行；继续使用仓库父目录 `flowboard-host.json`，未重新安装或改动现有配置。

- 升级前确认 8080/8083 均无服务，正式库 v20、完整性 `ok`、外键违规 0。使用现有 `upgrade` 命令生成完整备份，再升级。
- 正式升级记录：`../flowboard-backups/deployment-20261109-030702-8b55607f.json`，`READY`、20→21。
- 正式备份包：`../flowboard-backups/flowboard-before-upgrade-20261109-030702-397051/`。已实际恢复到 `local-test-data/20261109-production-upgrade/restore-check/`，恢复库全部内容、结构和版本与升级前一致。
- 正式库原有 46 张表全部旧记录及建表结构一致，包括账号和密码哈希；迁移记录仅增加 v21，新增两张样鞋空表，完整性与外键检查通过。
- 正式备份首次附加检查以 `mode=ro` 打开 WAL 格式快照，产生空 WAL/SHM 文件，后续包校验因多出文件而拒绝。确认 WAL 为 0 字节后，通过 SQLite 正常读连接关闭清理其空临时文件；原备份 DB 的 SHA-256 与 manifest 完全一致，原包校验及真实恢复均通过。没有重做迁移或改动备份数据库内容。
- `start-flowboard.cmd --check` PASS；11:09 使用当前 Python 启动部署监督程序，后台监督 PID 14088，服务日志确认 `[OK] Flowboard ready on port 8080`。
- 本机回环 HTTP：health 200/schema21、首页及样鞋页面 200，未登录 bootstrap 与样鞋 API 401，数据库路径 404。
- 系统确认当前有线 IP 为 `192.168.49.194`；服务机访问自身有线地址 health 200/schema21。入口 `http://192.168.49.194:8080/`。本轮未代替同事从另一台电脑登录验收。
- 当前后台运行，电脑重启后仍双击已修复的 `start-flowboard.cmd`。本轮未配置自启，未 commit/push 或修改机器配置。
- 日志：`../flowboard-backups/service-20261109-110917-stdout.log`、对应 `stderr.log`；本机核验资料：`local-test-data/20261109-production-upgrade/{proof,http,lan,launch}.json`。真实数据和派生表指纹保留在 Git 忽略目录。

## Git 交付

用户随后明确调用 `commit-push-pr`，授权本次修复的 Git 交付。已验证账号 `cjzymail-Mc` 为仓库所有者，目标为 `cjzymail-Mc/SSRC-Monday-com:main`，按技能走 main 直接提交路径；提交范围为启动器、部署提示、两项部署回归及 README/STATE/本记录六个文件。复用未变化源码的部署17/17与迁移恢复证据，不重新操作正式服务或数据库；不提交运行库、备份、附件及真实数据派生指纹。具体提交与推送结果以 Git 记录为准。
