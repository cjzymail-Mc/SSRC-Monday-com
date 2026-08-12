# Flowboard Windows 局域网运维

## 部署边界

使用专用低权限 Windows 账户运行服务，数据库、附件和备份目录仅授予该账户与备份管理员访问权。通过 `FLOWBOARD_DB`、`FLOWBOARD_ATTACHMENT_DIR`、`FLOWBOARD_BACKUP_DIR` 指向三个独立的 NTFS 目录；不要放进 Web 根目录、同步盘或公开共享。局域网入口应由 HTTPS 反向代理终止 TLS，并设置 `FLOWBOARD_SECURE_COOKIE=1`。防火墙只允许受信任子网访问代理端口，不直接暴露 SQLite 或附件目录。

服务探针为 `GET /api/health`，只返回状态和 schema 版本。它不代表备份可恢复；备份校验必须独立执行。

## 备份与保留

在线创建一致性包：

```powershell
python .\flowboard_ops.py --db D:\Flowboard\data\flowboard.db --attachments D:\Flowboard\attachments --backups D:\Flowboard\backups backup
python .\flowboard_ops.py --backups D:\Flowboard\backups list
python .\flowboard_ops.py --backups D:\Flowboard\backups verify D:\Flowboard\backups\flowboard-manual-YYYYMMDD-HHMMSS-ffffff
python .\flowboard_ops.py --backups D:\Flowboard\backups retention --keep 30
```

备份包包含 SQLite 快照、附件副本和带 SHA-256 的 manifest。创建过程会校验数据库、附件大小和摘要；保留命令只删除通过完整校验且名称受控的 Flowboard 包，不触碰其他文件。应把已校验包复制到另一台受控主机或离线介质，并定期在隔离副本上演练恢复。

## 离线恢复演练

恢复没有 HTTP 接口。停止服务并确认没有 `python server.py` 进程使用数据库后，在隔离目录先演练：

```powershell
python .\flowboard_ops.py --db D:\Flowboard-restore-test\flowboard.db --attachments D:\Flowboard-restore-test\attachments --backups D:\Flowboard-restore-test\safety restore D:\Flowboard\backups\flowboard-manual-YYYYMMDD-HHMMSS-ffffff
python .\flowboard_ops.py --backups D:\Flowboard\backups verify D:\Flowboard\backups\flowboard-manual-YYYYMMDD-HHMMSS-ffffff
```

正式恢复前再次停止服务、保存当前库的独立副本，并使用同一命令指向正式路径。工具先校验包并创建 pre-restore 安全备份，再按 DB 与附件各自的交换状态替换；中途失败只撤销已经完成的交换，不会删除尚未移出的当前目录，并清理 stage/old 临时项、释放维护锁。完成后启动服务，检查 `/api/health`、登录、任务数、附件下载、`PRAGMA integrity_check` 与 `PRAGMA foreign_key_check`。

## 回收站永久清理

永久清理只允许管理员对已超过工作区保留期的记录执行。界面先生成带时间和哈希的计划，再要求输入精确确认文字；执行前自动创建并验证 pre-purge 备份，附件先进入隔离区，数据库事务成功后才移除隔离内容。审计日志不会随业务对象清除。不要在生产库上绕过此流程运行手写 DELETE。

## 安全矩阵

| 能力 | viewer | member | admin | 防护 |
|---|---:|---:|---:|---|
| 查看可访问看板/任务 | 是 | 是 | 是 | 工作区与看板 ACL |
| 编辑、批量更新/移动/归档/删除 | 否 | 是 | 是 | CSRF、ACL、逐项 version、单事务 |
| 查看回收站并恢复 | 是 | 是 | 是 | 父资源与 version 校验 |
| 永久清理 | 否 | 否 | 是 | 到期策略、计划哈希、精确确认、预清理备份、审计保留 |
| 创建/列出/校验备份 | 否 | 否 | 是 | 管理员 ACL、受控包名、完整校验 |
| 恢复备份 | 否 | 否 | 离线运维员 | 无 HTTP 路由、维护锁、安全备份、失败回滚 |

## 故障处理

备份或清理报附件摘要不一致时停止相关操作，保留数据库、附件与错误日志，先查明缺失或篡改来源。恢复失败后不要手工混搭数据库和附件时间点；使用工具留下的 pre-restore 包重试。任何目录 junction、符号链接或 reparse point 都不应作为数据库、附件或备份包成员，部署时用 `Get-Item -Force` 检查 `LinkType` 与 `Attributes`。
