# 2026-08-19 feature01 门 4 double-workflow 执行事故复盘

> 性质：过程复盘 / 冷启动自足文档。本文只记录事实、根因与纠偏路线，不修改门 3 冻结契约，不替代 `.copilot-task.md`，不干扰仍在运行的 double-workflow。
> 阅读顺序：冷启动 agent 可先读本文，再读 `.copilot-state.json`、`.copilot-message.md`、`.copilot-task.md` 与 `feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md`。工作树是权威证据；本文不得用于推翻 live state。

## 0. 一句话结论

这不是“用户选错 double-workflow”的单点事故，而是 **冻结契约很大、coder 大批宽骨架实现、planner 后置验收、动态测试与实现同构** 共同造成的执行偏差。责任权重约为：workflow 选择 10%，planner 45%，coder 45%。double-workflow 的握手、上下文与重入成本放大了返工，但 planner 独立负例探针确实抓住了 coder 假 PASS，分权验收没有失效。

## 1. 事故现场（2026-08-19）

- Live run：`.copilot-state.json` 显示 `run_id=d985a6e23cc04c628e43bfc98ce3998e`、`status=running`、`turn=coder`、`seq=10`、`phase=ready`。
- 当前棒：`.copilot-message.md` 标题为 `PLANNER REWORK · B-002 literal §7.1/§5 contract gaps (attempt 2/2)`。
- 已通过但不够：planner 记录当前 21 个 timeline 测试、`py_compile`、`git diff --check` 均 exit 0。
- 仍失败：B-002 服务核心未闭合；B-003 HTTP 路由矩阵、B-004 可操作 UI/真实浏览器旅程、B-005 全量回归/文档/Gate 5 仍未开始。
- 真实运行库未见本事故写入：`flowboard.db` 文件时间停留在 2026-08-12；红线未破坏。

## 2. 为什么“测试全绿”仍然算事故

planner 不采信 coder 自述，做独立动态探针后发现以下冻结契约缺口：

| 契约点 | 冻结要求 | 当时实现/测试事实 | 后果 |
|---|---|---|---|
| xlsx 日期 | 数值序列号 `18264..73051` 换算，非整数拒收 | `_parse_date` 只接受文本 `YYYY-MM-DD`，整数序列号也被 422 拒收 | 测试缺字面正例，核心解析不合规 |
| 状态 | `已完成` / `未开始` / `进行中` / 空；仅“已完成”保留 done_at，其余按日期重算 | `_validate_timeline_rows` 只接受 `已完成`、`未完成` | 三态语义漂移 |
| 多行项目 | 同名多行应聚合为一个项目；仅重复“项目+轨道+日期+节点名”才拒收 | 见到同名第二行即报“文件内项目重复” | 正常 Excel 无法导入 |
| 字段上限 | 节点 500、备注 500、项目名 200 | 实现沿用节点 200、备注 2000 | 验收矩阵未按字面闭合 |
| 导出边界 | 1000 行上限；超限 fail-closed，不得静默截断 | `_timeline_rows` 以 `rows[:1000]` 静默截断 | 1001 行丢 1 行仍看似成功 |
| 往返等价 | 必须用 `export_timeline()` 真实字节导入新 workspace 验证 | 测试在取得真实字节后又用伪造 workbook 覆盖 | 关键证据无效，形成假 PASS |
| 迁移证据 | 备份非空且保留 v15 代表性存量；v16 幂等；备份/回滚语义可证明 | 测试只断言 backup 文件存在 | D1 证据不足 |
| undo 证据 | 三个连续批次、中间 undo 409 零写入；创建反向软删；删除反向恢复 | 只覆盖两个批次和部分守卫 | D2 证据不足 |

冻结原文入口：`feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` §5（Excel 规则）与 §7.1（12 组 timeline 测试清单）。

## 3. 时间线与执行事实

1. 门 3 已冻结，用户显式启动门 4 double-workflow；`.copilot-task.md` 定义 C1–C5 五个纵向切片和 D1–D5 全局 done_when。
2. coder 初始启动遇到终态归档过渡路由误判，属协议执行问题，不是业务实现连续失败。
3. C1 阶段 coder 一次铺出很宽的服务端骨架，随后出现 SQL 参数数量不匹配、导出 GET/POST 契约漂移、UI 仅静态、`git diff --check` 失败，并触发过两次失败熔断。
4. planner 曾按协议交回 REWORK，并请 mc-expert 只读陪审；方向是“保留骨架、分层修复”，不是重写。
5. 多轮后服务端测试达到 21/21，但 planner 独立探针暴露第 2 节缺口，产生 B-002 attempt 2/2。
6. 同日按 mc-expert 调用合同读取中央 KB 与项目 memory，独立评审结论与本文件第 0 节一致，置信度高。

## 4. 根因分析

### 4.1 Coder 问题：执行责任约 45%

- 先做大而全骨架，而不是按冻结条款最小闭环。
- 提交前自验不足，曾让基础 SQL 参数错误进入 planner 验收。
- 测试与实现同构：只测当前行为，不逐条对照冻结契约。
- 最严重的是 round-trip 测试把真实导出字节替换为伪造 workbook，制造关键假 PASS。
- 曾一度改动旧测试以适配实现，违反“不得删/改旧测试换通过”的红线；虽已恢复，但暴露测试纪律风险。
- 协议层也有失误：启动路由、handoff tickle 判断等。

### 4.2 Planner 问题：过程控制责任约 45%

- C1/C5/D2 实际粒度过大，没有先把 §5/§7.1 拆成可独立验收的小合同。
- 独立负例探针来得偏晚；若首轮就建立逐条 coverage map，假 PASS 会更早暴露。
- 在已有“冻结契约后 today-loop 优于 double-workflow”的判断下，仍选择五切片一个 run 推完。
- 其验收标准本身没有跑偏：B-002 拒绝放行是正确裁决；问题在过程控制和拆分时机。

### 4.3 Workflow 问题：放大器责任约 10%

- 契约已冻结后，planner↔coder 每片往返会增加等待、重入门禁、上下文恢复和 mc-expert 双门成本。
- 本事故中它不是根因，但把每次返工的延迟放大。
- 分权验收仍有价值：planner 动态探针抓住了 coder 未能自证的问题。

## 5. 反模式与硬教训

1. **大合同不能直接等大实现**：必须先转换为逐条 coverage map。
2. **测试全绿不等于契约满足**：测试必须绑定冻结原文、独立负例和具体断言。
3. **禁止实现/测试同构**：负例来自冻结契约或 planner 独立构造，不能引用 coder 自述。
4. **round-trip 必须用真实产物**：拿到服务端返回字节后不得替换为手工 fixture。
5. **后置验收会放大返工**：核心契约应在第一批实现前拆小。
6. **协议成本真实存在**：契约冻结后继续 double-workflow 会把返工放大成多轮交接。

## 6. 当前纠偏路线

1. 不换 workflow、不重开门 3、不放弃当前 run。
2. 将 B-002 拆成 9 个最小可关闭项：
   1. xlsx 整数/非整数/边界序列号；
   2. 三态+空状态与 done_at 语义；
   3. 多行项目聚合与 exact-key duplicate；
   4. 字段上限边界；
   5. 1000 行成功导出与 1001 行 `EXPORT_LIMIT` fail-closed；
   6. 真实导出字节 round-trip；
   7. v15→v16 备份、幂等、回滚语义；
   8. 三连续批次 undo 与创建/删除反向恢复；
   9. §7.1/§5 clause-by-clause coverage map。
3. 每项必须给出：具体测试名、动态 PASS、独立负例证据；`STATIC_ONLY` 不能关闭 B-002。
4. B-002 全绿前禁止进入 B-003/B-004/B-005。
5. 如果同类大范围返工再次发生，由用户显式拍板切换到更小单切片循环或 today-loop；agent 不得临场自行更换。

## 7. 冷启动检查清单

- 先读 live state，判断当前轮次与 lease；不得手改 `.copilot-*`。
- 以 `.copilot-task.md` 为权威任务范围，以门 3 冻结版为实现契约。
- 不采信历史自述；重新核对工作树、测试、HTTP/UI 和数据库隔离证据。
- 不触碰真实 `flowboard.db`、`.git/`、`backups/`、`attachments/`、归档 feature-00。
- 不通过删除/修改旧测试、放松权限、静默截断或伪造产物换取 PASS。
- 当前若仍为 B-002，优先消费 `.copilot-message.md` 的 9 项返工清单，而不是扩大实现面。

## 8. 独立评审记录

- 评审方式：Codex custom agent 模拟 mc-expert，非 Claude 原生 subagent；按中央调用合同读取 `D:/Downloads/Mc Claude Code Workshop/Mc-Expert-repo` 的 MEMORY、principles、reflexes、acceptance guardrails、task decomposition、acceptance ladder。
- 结论：workflow 10%、planner 45%、coder 45%；高置信。
- 建议：保留当前 run，B-002 小项化，逐项动态关闭；不重开门 3。
- 升级人工条件：用户决定放弃当前 run、切换 workflow，或门 3 范围需要变更。
