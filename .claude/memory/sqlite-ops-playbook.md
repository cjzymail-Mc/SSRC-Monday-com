---
name: sqlite-ops-playbook
description: SQLite 正式/持久库写操作与迁移操作链——备份快照、内容哈希、副本演练、维护锁、启动锁、WAL 残留、预览重定性；按需读
type: reference
---

# SQLite 运维手册（适用范围 = 正式库/持久演示库与正式迁移；一次性临时测试库不强制此链，2026-10-30 评审限定）

- **写前写后证据链**：写前 SQLite backup API 一致快照 + 完整性/外键检查；写后表级/全量内容哈希前后对比证明只动预期数据；核对一律 mode=ro 只读投影 + before/after JSON 证据。
- **正式迁移链**：ro 快照 → 副本演练（升级/回退/幂等/全表指纹）→ 机器可读报告等用户授权 → 维护锁内执行 → 备份恢复实测 + 启动器 --check 通过才收口（09-30 v20 实例；换机迁移先用隔离数据彩排全链路）。
- **软删表唯一性**：UNIQUE(col, deleted_at) 因 NULL 语义不约束活跃行；用部分唯一索引 WHERE deleted_at IS NULL + 服务端校验双保险；大小写不敏感唯一是同类盲区（08-28 上线审计才暴露）。
- **executescript() 陷阱**：隐式提交绕过外层事务，DDL 中途失败留半表；DDL 走统一事务封装；此类事务性缺陷只有故障注入能暴露，修复后用 authorizer 阳性对照（08-20 codex 故障注入发现）。
- **跨进程启动锁**：不能只写 PID 标记文件——持锁进程 os._exit(0) 异常退出残留假锁；用 OS 文件锁互斥、随进程退出自动释放，Windows 下比对进程创建时间防 PID 复用；归属不明一律保守拒绝（10-13，15/15 部署单测含异常退出恢复/PID 复用负例）。
- **WAL 备份残留**：对 WAL 库做备份读取会残留空 WAL/SHM：隔离副本 checkpoint + 关闭连接后消除；静态副本用 immutable=1 只读检查，正式库保持普通只读连接。
- **预览入口重定性**：production-preview 一旦切真实库，保存即写生产数据，每轮重申；自动化一律临时库；双入口并存用独立 cookie 隔离会话；仅监听 127.0.0.1；切回演示先核验并停止当前进程。

证据：`team-progress/20260930-team-member-order.md`、`team-progress/20261013-deployment-restart.md`、`team-progress/codex-report-B005-CP3.md`、`team-progress/20261009-production-preview-switch.md`。
