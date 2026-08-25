# B-002 九项验收陪审要点（mc-expert · 2026-08-19）

> 归档：lead 落盘（mc-expert 为只读角色）。依据链：KB（reflexes / acceptance-guardrails / acceptance-ladder / MEMORY 索引）+ repo 根 team-task.md §4/§5/§8 + mc-plan/（claude-glm复盘-首次施工失败）2026-08-19-feature01-door4-double-workflow-incident-review.md + 冻结契约原文 feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md §3.7/§3.8/§5/§6/§7.1 + 工作树实证抽查（tests/test_timeline.py、flowboard/timeline.py）。
> lead 复核注：两个关键实证已由 lead 独立 grep 复核属实——「未完成」在 test_timeline.py 实际命中 11 行（445/453/467/472/473/499/556/586/590/616，含 590 行 preview_json 注入与 499 行 helper）；timeline.py:720 `return rows[:1000]` 在。

## 历史参考（共用底座）

- Mc-Expert-repo/reflexes.md 第 28 条「判 done_when 前按字面判据跑阳性对照」——源头是 Mc-emoji double-workflow 首次验收假 PASS。本次门 4 事故是该反射预告的「第二 repo 命中」，两案共同点：测试全绿 + 独立负例才揭穿。
- decisions/acceptance-guardrails.md 三护栏：①期望值只能来自外部真相（红旗 4=代码内 hardcode 期望值回读自证——round-trip 伪造 workbook 的原型）；③审查标准不能被被审查者碰——对应 team-task §4「负例必须来自冻结契约原文或验收方独立构造」。
- references/acceptance-ladder.md：首件挑最难样本、每级只验新增失败模式——第 6 项 round-trip fixture 必须用最难样本。
- 事故复盘 §4/§5 四大反模式：实现/测试同构、round-trip 真实字节被伪造覆盖、改旧测试适配实现、后置验收。

## 九项逐项：风险模式 → 负例必盯断言

**1. xlsx 序列号**：风险=整条序列号分支零测试（已实证零命中）、边界只测越界不测端点、openpyxl 写 datetime 导致整数路径没跑到、`isinstance(x,int)` 吞 float 时间分量。断言：int 正例 18264→1950-01-01、73051→2100-01-01（25569=1970-01-01 基准核算，planner 独立复算）；18263 与 73052 各 422；float cell（如 46234.5）422 且 details 带 row；str 型走文本路径互不串扰。期望值 planner 用 `datetime(1899,12,30)+timedelta(days=n)` 预计算，不得 import 实现的换算函数自证。

**2. 状态三态**：风险=只补三态正例不关旧非法值、「按日期重算」只断言不报错不断言落库结果、非完成态也写 done_at。断言：三态+空独立正例；**「未完成」这个具体旧值必须 422**（事故实现认可的值，锋利负例）；非完成态落库 `done_at IS NULL` 且派生状态=按 server_today 重算的预计算期望（planner 自算）；仅「已完成」写 done_at 非空。

**3. 多行项目聚合**：风险=修复成「同名全部拒」反向过头、两条规则混测 422 因错误理由触发、聚合实现成 upsert 互相覆盖。断言：同名 3 行（不同轨道/日期）→ preview 201、projects 恰 1 个、节点数=行数；commit 后 `COUNT(timeline_nodes)`=行数（防覆盖）；四元组重复第二行 422 且文案含「与第 N 行重复」行号正确；四元组任一不同不得拒；库内已有同名活跃项目→该项目所有行报错、有错不许提交（不得部分导入）。错误断言必须带 code/details 区分拒收理由。

**4. 字段上限**：风险=半边界（只测 501 不测 500 恰接受）、长度按字节不按字符（中文 200 字=600 字节被拒）。断言：节点名/备注各 500 accept+501 reject、项目名 200 accept+201 reject 六方向齐全；边界样本用中文字符串；核对 trim 语义与 §3.6「trim 后 1..200」对齐（导入路径是否同样 trim 低置信，planner 回读 §5.2 原文定）。

**5. 导出边界**：风险=`rows[:1000]` 藏在别处（timeline.py:720 现存）、只断 422 不断 code、产物可再导入没闭环。断言：恰 1000 行导出 200、字节导入新 workspace 成功行数=1000；1001 行→422 且 **code==EXPORT_LIMIT、details 含 total==1001 与 max==1000**；任何路径不得「1001 行返回 200 只带 1000 行」。fixture 生成器保证无重复四元组。

**6. 真实字节 round-trip（事故核心复发点，最高危）**：风险=原样复发（拿到 export 字节后又手工构造比较文件；test_timeline.py:499 附近「从 nodes 拼 xlsx」helper 形态可疑，diff 其字节来源）、数据太顺等价断言平凡真、「新 workspace」偷换、语义等价只比 COUNT。断言：planner 自己调 export API 取 base64（不经 coder 测试中间变量），断言喂给 preview 的 content_base64 与导出返回值逐字节相等（含 sha256）；round-trip 在全新 workspace；fixture 挑最难样本（多项目、双轨、四态齐全、跨月日期、中文字段、边界长度节点名）；逐节点比对名称/日期/轨道/阶段；既定差异四件显式断言：已完成保留、非完成态 done_at 空按日期重算、interval 忽略但重派生后一致、done_at 只比存在性不比时刻。

**7. 迁移证据**：风险=只断言 backup 存在（事故事实）、内容断言打在迁移后库而非备份本体、幂等只测不报错不测记账条数、测试库路径失守。断言：v15 隔离库造代表存量（users/workspaces/boards/tasks 各≥1+可识别 sentinel 行）再迁移；断言对象=备份快照本体：非空、`user_version==15`、sentinel 在、存量计数与基线一致；重跑 migrate 后 `user_version==16` 且 schema_migrations version=16 行 COUNT==1、五表 COUNT 不变；一次 migrate 后 backups 只多一个 `flowboard-pre-v16-<ts>.db`；全程 tmp 路径+跑完 stat 真实 flowboard.db mtime 仍 2026-08-12。回滚语义：restore 后 `user_version==15` 且数据在（中途失败注入负例构造成本高，降中优先，至少证 restore 侧）。

**8. undo 证据**：风险=零写入断言太窄（只查 nodes 表）、409 因错误理由触发（VERSION_CONFLICT 而非 UNDO_TARGET_STALE）、反向操作做成物理删除。断言：同项目真连续三批（id 严格递增中间无夹杂），撤中间批→409 且 **code==UNDO_TARGET_STALE**，五处零写入：version 不变、batches COUNT 不变、node_changes COUNT 不变、audit_log 无新行、节点表无变更；创建反向→`deleted_at IS NOT NULL` 且行仍在（软删）；删除反向→`deleted_at IS NULL`；原批次及行级记录原样保留（undo 批自身新批次 version+1、undone_batch_id 正确）；廉价负例：对 undo 批再 undo→409。

**9. coverage map**：风险=粒度糊到文件/测试类、SKIP/todo/占位名冒充、只做正向映射藏无锚自造测试。断言：§7.1 十二组+§5 每条规则→具名测试函数（unittest node id 级），名字真实存在、能被 `python -m unittest <nodeid>` 单独加载运行（planner 机械复核逐条或抽样真跑）；不许「计划中/SKIP」字样；对新 Excel 相关测试反向抽查：每条测试能指回某条款，指不回=同构嫌疑名单交 lead。

## 整体扳机条件（出现即点 mc-expert 一次性陪审）

1. coder 提出修改现有 21 个测试任何一个（已实证相撞，lead 已裁定，见 team-progress 自主裁决 #4；若出现裁定范围外的修改仍触发）。
2. 任何一项关闭证据出现 STATIC_ONLY/「静态推断」类签注（B-002 明文禁）。
3. round-trip/迁移类证据再现「拿到真实产物后替换 fixture」或「只查存在不查内容」（信号：diff 测试文件见 export 调用后紧跟 workbook 构造调用）。
4. 同一项第 2 次返工或 §4「连续 2 次失败」熔断触发。
5. **B-002 宣布九项全绿、放行 B-003 之前的最终门**（固定触发）。
6. 冻结契约字面含义争议（如第 4 项 trim、第 7 项回滚证明深度）——低置信裁决点，陪审先出对照再升级用户。

## mc-expert 三条默认落点（lead 裁定采纳情况见 team-progress）

① coverage map 先行或至少并行——planner 现在产出条款清单骨架，coder 边修边填，验收逐条真跑。【lead：已采纳，planner 骨架+coder CP0 对齐】
② 21 测试冲突默认处理——允许且仅允许「向冻结契约收敛」方向修改，三前置：逐条 diff 报 planner 审、team-progress 留痕、禁任何放松方向反向修改；最终解释权归 lead/用户。【lead：已采纳为自主裁决 #4，浮给用户】
③ planner 探针脚本与输出落 team-progress/ 留痕，最终门可复跑。【lead：已采纳为自主裁决 #5，限 team-progress/verification/】

## KB 补洞建议（收尾 loop 处理）

- reflexes.md 第 28 条标「待第二 repo 命中升正反射」，本次门 4 事故条件已满足，可收割升级。
- round-trip 伪造字节覆盖真实产物 = pipeline-self-check-loop SKILL 第 5 条「证据防 probe 后篡改」跨 repo 第三命中，可在该 SKILL 或 KB 索引补实例指针。

## 置信度

第 1/2/3/4/5/6/8/9 项：高（断言点锚定冻结原文+事故八缺口+工作树实证）；第 7 项整体高、回滚语义证明深度中；扳机 1 高（grep 实证）；第 4 项 trim 细节低置信（已注明交 planner 回读原文定）。
