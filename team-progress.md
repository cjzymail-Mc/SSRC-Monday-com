# team-progress · 门 4 team-task（feature01 · B-002 九项最小闭环）

> 模式：**B 深度放权**（用户 2026-08-19 第 0 步 AskUserQuestion 拍板）。
> 适配盘点：5/5 yes、0 KO → team lane；选型纠偏检查通过（非单点串行流水线：§8 要求逐项独立负例验收，planner 为持续取证角色；用户 §7 已显式拍板三角色小队）。厚度闸：完整集成立（实际触发：9 项有序检查点+门禁链 B-002→B-003→B-004→B-005 / coder→planner 逐项交棒 / 门 4 跨会话接力）；现有 team-task.md 已实质覆盖完整集七块，未重写。
> 归档检查：根 team-progress.md 原不存在、team-progress/ 内无 NNN 归档 → 跳过归档，本文件为新建。
> 任务定义：repo 根 `team-task.md`（§8 = 本次任务）。门禁：**B-002 九项全绿前禁入 B-003/B-004/B-005**。
> 测试跑法（本机实测）：`python -m unittest discover -s tests -p 'test_timeline.py'`（README L110；本机无 pytest，勿装）。

## 进度日志

### 2026-08-19（建队）
- /team-task 触发流程走完：读 team-task.md → 适配盘点（5/5 yes、0 KO）→ 厚度闸（完整集）→ 归档（跳过）→ 第 0 步 A/B → 用户拍板 **B 深度放权**。
- 基线验证：`python -m unittest discover -s tests -p 'test_timeline.py'` → **21 tests OK**（23s），与 team-task.md §6 工作树快照一致，起点确认。
- 建队：spawn coder / planner / mc-expert 三角色已全部启动（spawn prompt = 短锚+指针；三者第一动作均为完整读 team-task.md）。
- **【用户指令】lead 补读 `--------- ★ 通用指南 ★ ----------/` 两份通用指南**（防漂移补丁指南 2026-08-04 + 验收侧判据手册 2026-08-05），已完整读入并按角色分发：
  - planner ← 验收侧判据手册为操作手册（三硬纪律：字面判据当标尺 / 阳性对照负例真跑 / 签注不许静态冒充 PASS）+ 防漂移指南块⑥⑦（failure_key 累计口径、最终报告三分证据）。
  - coder ← 块⑥⑦（纠偏三问入口、failure_key 口径）+ 验收侧手册（对齐 planner 验收口径：负例真跑真失败、round-trip 真实字节）。
  - mc-expert ← 纪律 3 陪审禁喂框框 + 块⑥扳机清单/§7 触发留痕，其陪审要点须显式引用纪律编号。
- **收尾 pin 候选登记**：用户纠正「lead 建队前应主动扫 repo 内通用指南目录（如 --------- ★ 通用指南 ★ ----------/）并入队」——team-task skill 只内置了 KO 指南内容、未含『扫 repo 本地指南』动作。收尾 loop pin 段预判输入。
- **mc-expert 交付九项陪审要点**（全文归档 `team-progress/B-002-验收陪审要点-mc-expert.md`；初始常驻任务，非扳机触发）。两个锋利实证经 lead 独立 grep 复核属实：①test_timeline.py「未完成」命中 11 行（多为合法正例——即事故缺口②本身写进了基线测试）→ 与 §8 第 2 项修复正面相撞；②timeline.py:720 `rows[:1000]` 静默截断仍在。六条整体扳机 + 三条默认落点，采纳情况见自主裁决 #4/#5。
- 【自主裁决 #4】21 测试相撞裁定 → 已下发 coder/planner（详见自主裁决区，**浮给用户**）。
- 【自主裁决 #5】planner 验收证据归档落点 → 已下发 planner。
- **收尾 KB 候选（mc-expert 提出）**：reflexes #28 阳性对照「第二 repo 命中」条件已满足可升正反射；round-trip 伪造字节 = pipeline-self-check-loop 第 5 条第三命中。收尾 loop 处理。
- **planner 备战完成轻报**：①第 9 项骨架落 `team-progress/verification/B-002-coverage-map-骨架.md`（§7.1 十二组+§5.1×4+§5.2×10+§5.3×2+§3.7×2，判据列=契约原文摘句+node id 槽位）；②39 条独立负例探针（wave-1 脚本+证据归档可复跑；序列号期望值 1899-12-30 基准自算、探针自带 xlsx 构造器、round-trip sha256 双侧同一性）；③基线快照（施工中工作树，非签注）36 绿/3 红；④第 6 项 diff 判定：test_group9 已重写为真实字节链路（506/507-508/517/543-545），旧伪造模式已移除。真实 flowboard.db mtime 未动。
- **P0 裁定（自主裁决 #6）**：契约 §5 字面表头「项目名称｜阶段｜轨道｜节点｜日期｜间隔｜状态｜备注」被现实现 422 拒收（`timeline.py:13` IMPORT_HEADERS＝「项目｜轨道｜阶段｜节点｜日期｜状态｜备注｜间隔」，列名+列序双偏）——**裁定并入 B-002 为追加项⑩**，导入期望表头+导出产列表头+报错附件标准表头+受影响测试全部向契约字面收敛（导出物必可再导入，两侧必须同步）。
- **P8b/P8c 归因存疑（lead 复核）**：planner 静态指认 624-627 行互换，但 lead 现读该段为 `created→stamp 软删、deleted→NULL 恢复`，与 E4③ 注释一致、**非互换**（可能为 coder 施工中已改或读档时序差）；动态红仅记「快照时刻观察」，CP2 波次重跑定论，不作为当前事实下发结论。
- **planner 回执**：三裁定全落实——⑩四探针（P0a 契约表头正例/P0b 导出表头逐列比对/P0c 乱序 422/P0d 缺列 422）入册全绿；P8b/P8c 定位型升级后复跑**转绿**（created 反向软删/deleted 反向恢复均正确，证实时序差）；终值 **43 探针全绿 0 FAIL**，仍标「备战基线非签注」。→ 43/43 全绿侧面表明 coder 已深入项 1–8+⑩ 修复施工。
- **coder CP0 产物已落盘**（`team-progress/B-002-coverage-map.md`，报告未到、lead 按「承重靠盘」直接读产物验收）：§7.1 十二组+§5 逐条映射、状态四分级（PASS/GAP-B002/CONFLICT/GAP-非九项）、§C 冲突清单 C1–C4 均为最小收敛修正、§E 计划测试施工图。**lead 复核两点纠偏**：①其 OPEN-1 建议「维持现状列序」已被自主裁决 #6 超越（向契约字面收敛，planner P0a–d 探针证实已实现）；②§E 表缺第 ⑩ 行——CP3 终版须补 ⑩ 具名测试映射并确认表头正/负例以 unittest 形式真实存在（不能只靠 planner 探针）。
- **OPEN-2…OPEN-7 隔离裁定（自主裁决 #7）**：map 挖出的 6 类「GAP-非九项」（断言补强/行级 details 带 row/同名全行报错形态/CSV 提示文案/导出行序含轨道/xlsx-CSV 序列号判定折中）**不进 B-002**，记为 B-003 候选——防「大合同一次铺开」事故模式复发；B-002 范围=九项+⑩。
- **Codex 恢复交付**：补齐 `coder-report-CP2.md` / `coder-report-CP3.md`，冻结实现、测试与 map 哈希；恢复回合项 6/7/8 各 1/1、专项回归 29/29，零实现改动。
- **planner wave-2 正式签注**：修正 wave-1 的提前拦截/任意 422 假绿，独立复跑专项 29/29、范围内探针 40/40、setup/safety 2/2、具名单载 9/9；P3d 明确剔除为 `OUT_OF_SCOPE/B-003`。项 1–8+⑩ PASS。
- **最终陪审首次 NO-GO（custom agent 模拟非原生 mc-expert）**：第 9 项字面要求与自主裁决 #7 的范围隔离未显式消歧，且缺少可失败的 coverage-map 验收器；不采信 map 自述关门。
- **第 9 项最小闭环**：`team-task.md` 追加不回溯的恢复澄清（自主裁决 #8）；planner wave-3 以冻结清单为外部真相，真实 map 因 `OUT_OF_SCOPE_ROUTE_MISSING` REWORK，两个内存阳性对照正确失败；coder 仅补 map §D 的统一 B-003 去向；wave-4 复验 78/78 映射、80/80 状态、29/29 测试引用，真实 map exit 0，删映射/伪造测试名均 exit 1。
- **B-002 正式关闭**：最终复核（custom agent 模拟非原生 mc-expert）给出 **GO / 高置信**；关闭范围仅九项+⑩。八个 `GAP-非九项` 继续作为 B-003 候选，不代表冻结契约全文完成。真实 `flowboard.db` 全程 size/mtime 未变。

## 当前现状
- **B-002**：**CLOSED**（项 1–9+⑩ 全部正式 PASS；证据链 wave-2→wave-3 REWORK→CP3a→wave-4→最终陪审 GO）。
- **B-003**：**CLOSED**（CP0–CP5 全部正式 PASS；11/11 HTTP 成功路径、8/8 写路由 CSRF、权限/版本/软删/竞态/错误 method 与六表零写入证据齐全）。
- **coder**：B-003 终态 coverage map 已收口为 11/11 PASS，并保留 CP0 的 7 GAP/4 CONFLICT 历史快照。
- **planner**：CP1–CP5 逐波独立签注；最终同一隔离库、随机端口完成 11/11 路由关门。
- **mc-expert**：B-004 拆分陪审为 GO / 高置信；角色为 Codex custom agent 模拟，非 Claude 原生 mc-expert。
- **lead**：已关闭 B-003，当前程序计数器移至 **B-004 可操作 UI 与真实浏览器旅程**。

## 下一步
- 先做 B-004 CP0 coverage map；不先铺 UI 实现。
- CP1–CP5 逐切片完成生产入口、编辑器、提交/撤销、双仪表盘、Excel UI；关键点击必须跑真实 `mousedown→mouseup→click` 事件序并做吞 click 阳性对照。
- CP6 独立复跑三条完整 Chromium 旅程；全仓历史回归、文档总收口和 Gate 5 留 B-005。

## 卡点
- 无

## 自主裁决(B)

| # | 决策点 | 候选项 | 选了哪个 | 依据 | 置信度 |
|---|---|---|---|---|---|
| 1 | coverage map（§8 第 9 项）落点 | team-progress/ vs mc-plan/ vs repo 根 | `team-progress/B-002-coverage-map.md` | 门 4 team 产物自包含；untracked 目录、不碰契约文件，最易回滚 | 高 |
| 2 | coder 检查点分批 | 一次性交九项 vs 分 CP | CP0 map→CP1 项1–5→CP2 项6–8→CP3 回归 | 事故红线「先 coverage map 再动手」+ 分批交棒防验收后置；1–5 为 Excel/preview 层、6–8 为 round-trip/迁移/undo 层，天然两组 | 高 |
| 3 | 测试运行器 | 安装 pytest vs 沿用 unittest discover | 沿用 `python -m unittest discover` | README L110 既定跑法、test 文件本就是 unittest 风格；装新依赖属扩实现面 | 高 |
| 4 | §8「现有 21 测试不得删改」与第 2 项修复相撞（「未完成」正例 11 行=事故缺口②写进了基线） | 禁改保基线 vs 允许「向冻结契约收敛」方向修改 | **允许收敛方向修改**：fixture 改三态合法值，或反手改成「未完成→422」负例；三前置=逐条 diff 报 planner 审 / team-progress 留痕 / 禁任何向实现放松断言的反向修改 | mc-expert 默认方案（历史成功率最高：§4 事故红线原意是「不删改**换 PASS**」，收敛修改不买 PASS、反手改负例反而加强）；diff 逐条可回滚 | 高（**待用户复盘确认项**） |
| 5 | planner 负例证据落点 | 仅系统临时目录 vs 归档进 team-progress | 执行仍在临时目录（零副作用不变）；每波次后探针脚本+关键输出归档 `team-progress/verification/wave-{N}/` | mc-expert 建议③：最终门可复跑、不依赖对话记忆；不动工作树交付物正本 | 高 |
| 6 | P0 表头契约偏差归属（planner 新发现） | 并入 B-002 追加项 vs 另案后置 | **并入 B-002 为追加项⑩**：导入期望表头+导出产列表头+IMPORT_HEADERS_MISMATCH 报错附件+受影响测试，全部向契约字面 8 列收敛（项目名称｜阶段｜轨道｜节点｜日期｜间隔｜状态｜备注） | 与事故八缺口同类（契约字面 vs 实现），第 9 项 §5.1 表头行不修则 coverage map 带已知 FAIL 无法关闭；§3.7「导出物必可再导入」要求两侧同步改；最小收敛修复非扩实现面 | 高（**待用户复盘确认项**：九项门禁扩为十项） |
| 7 | coverage map 挖出的 OPEN-2…7 六类字面缺口归属 | 顺手修进 B-002 vs 隔离给 B-003 | **隔离出 B-002、记 B-003 候选**；B-002 范围钉死=九项+⑩，map 只负责暴露不负责顺手修 | §8 门禁本意「最小闭环」；事故复盘教训=「大批宽骨架+后置验收」与范围蔓延互为因果；OPEN 项均已留痕可排序 | 高 |
| 8 | 第 9 项字面要求与 #7 范围隔离冲突 | 把全部 GAP 拉回 B-002 vs 静默按 map 自述关门 vs 追加可追溯澄清 | **追加恢复澄清**：全条款须登记；B-002/PASS 项绑定具名测试，GAP-非九项绑定 B-003 去向；补独立验收器和两类阳性对照 | 最终陪审首次 NO-GO；既不扩大 B-002，也不静默移动 done_when；改动可追溯、最易回滚 | 高 |
| 9 | CP1 的行级 `details.row` 与 #7 隔离交叠 | 回滚统一补强 vs 保留并焊死边界 | **保留**为 B-002 行级 422 共用错误元数据补强；不授权同名全行清单/CSV 提示/导出轨道排序 | 第 1 项字面要求行级 422；附加诊断信息不放松校验，回滚反而扩大改动面；mc-expert 恢复陪审高置信建议 | 高 |

## OPEN_BLOCKERS
- 无

## PENDING_HUMAN_NONBLOCKING
- 自主裁决 #4：允许既有测试向冻结契约收敛修改（未删除测试、未放松断言）；待用户收尾复盘确认。
- 自主裁决 #6：契约字面表头并入追加项⑩；待用户收尾复盘确认。

## 收尾复盘位（正常收尾时填写；字段来自防漂移指南 §7 + 验收侧手册复盘锚）
- 漂移苗头与纠正来源（含被哪条重锚问题/哪份指南纪律纠正）：
- mc-expert 触发/跳过记录（每次触发原因；跳过陪审的检查点及理由——重复已审模式/普通机械改动/仅缺证据不叫）：
- planner 独立发现的问题数 / REWORK 次数 / 最终证据：
- 熔断计数（failure_key 机械累计：两个独立失败交接才算 2 次，同回合短暂重试不算）：
- 最终交付证据三分：协议设计保证 / 本 run 实际执行证据 / 尚未独立复跑的历史记录：
- 后置项单列（live/视觉/外发/真实库类用户决策，不冒充达标）：
