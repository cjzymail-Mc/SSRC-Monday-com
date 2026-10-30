# memory 索引（技术细节 · 按需加载）

- [真浏览器事件序测试坑](browser-event-order-testing.md) — mousedown 隐藏目标会吞 click；合成 .click() 掩盖此 bug，测试须用真实事件序；同族增补：双重渲染竞态、视图切换可见性竞态、hover 显隐命中环（opacity:0+pointer-events:none 锁死 Playwright 物理点击）；focus-within 无 tabindex=纸面通道，须条件性 tabindex（08-26 订正）；重渲染后断言用户可见状态而非 detached、预期 4xx console 游标分段核销（Codex 提案 08-27，10-30 采纳）
- [筛选子集排序合并回完整序列](filtered-subset-order-merge.md) — 筛选/周期视图排序按可见锚点合并回 canonical 全序列提交，防隐藏项丢失/409 错配/排序跳回；业务判断用全量数据集，筛选只作用展示（Codex 提案 08-27，10-30 采纳）
- [保存可靠性三件套](save-conflict-reliability.md) — 409 保留输入、显式确认后重试、绝不自动重试/顺带提交；保存中防重复/防离页；净变更检测；多入口统一语义（卡内指路到实现与回归）
- [真实产物往返验证](roundtrip-real-artifacts.md) — 导入导出往返全程用服务端真实字节+真实分布画像的代表性数据；拿到真实产物后换手工 fixture=最危险假 PASS；往返相等≠备份恢复
- [SQLite 运维手册](sqlite-ops-playbook.md) — 正式/持久库写操作链：备份快照+内容哈希+副本演练+维护锁；软删部分唯一索引 WHERE deleted_at IS NULL；executescript 事务陷阱；OS 文件锁+进程创建时间防 PID 复用；WAL 残留；预览切真实库重定性
- [Windows 测试环境排错](windows-test-env-troubleshooting.md) — 沙箱权限不规避不重试、换仓库内隔离目录复跑同一测试；中文 cp936 编码；daemon 线程退出后再清 SQLite；仓库根 discover；并行核对总数；标注环境条件按需取用
- [决策覆盖留痕](decision-overwrite-trail.md) — 覆盖注记（以注记为准）+追加式留痕+证据目录不覆盖历史轮次+as-built 及时蒸馏防冷会话复活旧入口
- [交互几何计算真源](geometry-truth-source.md) — 布局常量不硬编码、缩放锚点读实时 rect＋已渲染 data 属性；锚点漂移/画布滑走类 bug 的根因族（08-26/27 两实例）
