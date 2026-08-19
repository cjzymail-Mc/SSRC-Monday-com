# 门 3 整体评审 · 退回修订台账（历史记录，非实现权威）

> 建立：2026-08-18（评审裁决经 `temp.md` 接力传入本 session）。
> **最终状态：门 3 增量复审 PASS（2026-08-18）**。三单元产品决策蒸馏与初审修订已全部写入 `9-GATE3_TECH_FREEZE.md`；本文只保留评审过程与修法追溯，**不得作为门 4 实现权威**。
> 本台账 = 历史修订工作面：每项含问题、修法提案、处置级别与状态；修订均已落回 `9-GATE3_TECH_FREEZE.md`（增量修订，不重开 D/E/F 拍板）。增量复审与归档均已完成，本文件现为非权威历史记录。
> 评审声明：初审为只读，未改文件未提交；初审时 mc-expert 契约入口缺失，后已修复。2026-08-18 增量陪审成功读取中央 KB 并复核本台账，新增 B3-4/C2 两处纠偏，均已记录于 §3。

## §1 阻断项（门 4 阻断，必须全部闭环）

### B1 · undo 可绕过 initial_date 的 admin-only 权限【陪审】

- **问题**：E4 拍了「有写权限即可撤（不限原 actor）」，undo 反转行级 old/new——若某项目最新批次是 admin 的 `initial_correction`，member 项目创建者 undo 即可把 initial_date 改回去，直接违反 D3/Q21「initial_date 纠正仅限 workspace admin」。
- **候选修法**：
  - (i) 撤销目标批次为 `initial_correction`（或含 field=initial_date 行）时，undo 操作者必须为 workspace admin（403 `ADMIN_REQUIRED`，先例 service.py:2776/2795）；护栏其余不变。
  - (ii) `initial_correction` 批次不进入普通 undo（作为最新批次时 undo 拒绝，专属 409 code）；admin 纠错只可再纠正。
- **倾向 (i)**：保持「提交后一次撤销」语义完整（确认 12/16 窗口不因最后一批是纠正批而消失）；admin 自己仍可撤纠正批。两案在 member 侧效果等价（纠正批成为最新后 member 本就撤不到更早批次——护栏①）。
- 补测试：member undo 含 initial_correction 的最新批次 → 403；admin undo 同批 → 成功（若 (i)）。

### B2 · workspace / project / node 归属校验未锁死【陪审（修法基本机械，错误码细节陪审）】

- **问题**：workspace 批次端点路径带 `{workspace_id}`，但 `_project_access` 只按 project_id 查 membership，未校验项目属于路径 workspace；node_id 也未强制属于当前变更组的 project_id——跨 workspace / 跨项目 ID 注入风险。
- **修法提案**：① `_project_access` 查询加 `AND p.workspace_id=?`（路径参数传入）；路径 workspace 与项目归属不符 → 404（模糊化，不泄露存在性）。② 所有节点读写 `WHERE id=? AND project_id=?`，node_id 不属于该组 project_id → 422 行级（details 带 node_id）或 404（陪审定）。③ 补两组越权测试（路径不符 / node 跨项目注入）。

### B3 · 核心写入契约不完整【陪审】

四个子洞，修法提案：

1. **interval_days 不在请求 schema**：加入 change 行 `set`（`{"interval_days": 12}`，编辑器改间隔的意图字段）；与 `date` 并存时日期优先并覆盖重算间隔（6- 原文已有、冻结版示例漏掉；mainline §4.1「手改间隔触发顺延」的载体）。
2. **done_at 布尔映射**：`true` → done_at=服务器当前时刻（UTC ISO）；`false` → NULL；等值比对（E7b）按布尔语义（true↔非 NULL）。
3. **服务端钳制**：direct 节点日期服务端同样钳制——single 模式钳在同轨前后邻居之间、cascade 模式钳在前驱之后（含同日）；与前端同一规则（E8 意图提交防伪造）；钳制后与提交值不同不报错，以服务端重算为准、响应视图即真相。
4. **同轨同日多节点的稳定顺序**：遵守 UX Q3 已冻结自然序，链序=`date → 节点名称自然序 → id`；id 仅在名称自然序完全相同时作最终兜底。同日相邻间隔=0。服务端钳制以前置事务快照中的链序确定前驱/后邻，再把本批意图合并计算终态，避免用终态反推邻居造成循环定义。

### B4 · 视图返回体装不下「阶段区间列表」【陪审】

- **问题**：§2.4 承诺额外派生阶段区间列表，但正式响应形状只有 nodes[]+segments[]+metrics；segments[] 装链式段还是阶段区间不明。
- **修法提案**：响应显式增加第三数组 **`stage_intervals[]`**：元素 `{track, stage, start_date, end_date, row_index}`（重叠分半/展开拆行的服务端数据源）；`segments[]` 专装链式段（画法 A 语义不变）；两者同派生器产出；§3.1 200 体、§3.3 GET 两端点、409 冲突视图同步加该数组（形状一致）。

### B5 · 主线必做能力缺 API 契约（三子项）

- **B5a · admin 纠正 initial_date 端点【陪审】**：提案 `POST /api/workspaces/{id}/timeline/batches/initial-correction`，体 `{project_id, base_version, corrections:[{node_id, initial_date}]}`；单事务、产生 `initial_correction` 批次、version+1；权限仅 admin（403 `ADMIN_REQUIRED`）；node 不存在 404、非法日期 422、版本冲突 409 同 E2/E3；响应同批次端点（view）。
- **B5b · 轻量复盘查询端点【陪审】**（mainline §3.3/§4 必做）：提案 `GET /api/workspaces/{id}/timeline/review?project_ids=1,2`（缺省=全部活跃项目）→ 每项目 `{summary:{direct_edit_total}, nodes:[{node_id, name, track, stage, initial_date, date, delta_days, direct_edit_count}], batches:[{batch_id, change_kind, trigger_source, actor, created_at, change_rows}]}`；权限=读级（member 可看全部、viewer 403）；聚合自 timeline_change_batches/timeline_node_changes/timeline_nodes，零新表。
- **B5c · 项目生命周期：创建/改名/软删【用户已拍板】**（2026-08-18 用户选择 b）：
  - a. v1 项目**只能经 Excel 导入**创建，网页端无新建入口；admin 专属软删端点；不做改名。赌注：想开一个新项目要先造 Excel，日常不便。
  - **b. ✅ 用户拍板：网页端提供「新建项目」**（admin/member 均可，仅输入名称，`created_by=当前操作者` 且不可变，建空项目后在编辑器加节点；viewer 403）；仅 admin 可软删项目；**v1 不做改名**——名称=唯一标识（F2-④=b 用户定调），录错名称走 admin 软删后重建。Excel 导入仍是批量入口。
  - c. 完整 CRUD 含 admin 改名。赌注：唯一标识变迁语义（审计与导入匹配如何跟随）需额外契约，v1 负担最大。

## §2 需同步修正（不单独阻断）

| # | 问题 | 修法 | 级别 |
|---|------|------|------|
| N1 | timeline_import_batches 号称第五表但无完整 DDL（9- §1.5 只有文字描述） | 起草完整 DDL 补入 §1.5（id/workspace_id/created_by/status CHECK('previewed','committed')/preview_json/preview_sha256/created_at/committed_at 等，对齐 import_batches 去 board_id） | 机械 |
| N2 | F2-④=b 后导入只建新项目，「对涉及项目做 base_version 检查」无实际对象 | §3.4/§5.3 与 8- 补丁表述改为：commit 事务内**重新执行文件级+行级校验、名称唯一复查、preview_sha256 一致性比对**（预览被替换/库已变即 409/404），删除 base_version 表述 | 陪审确认表述 |
| N3 | 迁移冒烟写死 4/1/2/2/6 计数 | runbook 改为「迁移前记录存量计数 → 迁移后比对一致」；固定数字仅作测试 fixture | 机械 |
| N4 | §0 行数表述「40 行」与实际不符 | 增量修订时精确清点并改正（评审方计 49，含口径差异——以逐行实数为准） | 机械 |
| N5 | 归档 4/5/6/7/8 后 9-/STATE 溯源路径会失效 | 归档与 9-/STATE/mainline 引用改写已在同一变更完成；10- 已降级 | ✅ 已完成 |
| N6 | 全部产物未 commit（HEAD 仍 2eaa978）、`.copilot-state.json` 仍第一阶段 done | 门 3 已 PASS、归档已完成；当前等待用户显式授权 commit 与新 planner↔coder run | 流程（待用户授权） |
| N7 | 初审时 mc-expert KB 契约入口缺失（PROJECT_MEMORY/SEALED_DECISION_QUERY 等） | 保留为历史记录；2026-08-18 已修复并成功读取中央 KB 完成增量陪审 | 已解决 |

## §3 处置状态（2026-08-18 陪审已回填）

| 项 | 处置 | 状态 |
|---|------|------|
| B1 | 陪审定稿=**(i) admin 门槛**（判定键=change_kind='initial_correction' 即完备；403 ADMIN_REQUIRED；整 undo 零写入） | ✅ mc-expert 陪审定稿（高） |
| B2 | 陪审定稿=路径 workspace 不符、项目不存在、无权访问统一 **403 PROJECT_FORBIDDEN**（折进 _project_access 查询自然落 not row，零新分支）；node 跨项目注入 **422 行级**；分层规则入 §3.5（顶层 project 访问失败→403；undo/import batch 等操作对象查无→404；变更行内 node 引用无效/越界→422） | ✅ mc-expert 陪审定稿并经增量陪审消歧（高） |
| B3 | 四子项全部定稿：interval_days 入 set（整数 0..3650，仅已存在节点，create 行 422，无前驱 422，date 优先）/ done_at true→服务器当前 UTC ISO、false→NULL、非布尔 422、create 行可选携带 / 服务端钳制按 details.mode（single=同轨前后邻居间、cascade=前驱之后含同日；**邻居取前置事务快照链序**，再合并本批意图计算终态；钳制结果=现值走 E7b 剔除；editor 缺省 mode=cascade）/ 链序遵守 UX Q3：`(track, date, 节点名称自然序, id)`，id 仅作同名最终兜底；M3 展示排序仍按其独立契约 | ✅ mc-expert 陪审定稿并经增量陪审按既有用户冻结项纠偏（高） |
| B4 | 陪审定稿=`stage_intervals[]`，元素 `{track, stage, start_date, end_date, row_index, node_ids}`（node_ids 必带——悬浮/点击穿透，防客户端重推导）；row_index=同轨内重叠区间拆分行号（按 start_date、首节点 id 序贪心分配最低空闲行，确定性钉死）；segments[] 专装链式段、stage_intervals[] 专装阶段合并游程，同派生器一次遍历产出，三处响应（200/GET/409）同步加 | ✅ mc-expert 陪审定稿（中高） |
| B5a | 陪审定稿=**corrections 数组多节点同批**（≤200、空 422；系统性录错一次纠正）；initial_date **完全自由仅历法校验不钳制**（历史记录字段不进日期链，纠正零级联）；node 不存在/不属于该项目 → **422 行级**（否决台账 404，同 B2 分层）；补 E7b 等值豁免；重复 node_id 422；响应同批次端点 view，nodes[] 统一含 initial_date | ✅ mc-expert 陪审定稿（高） |
| B5b | 陪审定稿=读级权限正确（member 全员、viewer 403）；**不带 base_version**（summary 带当前 version 供判陈旧）；项目与节点汇总完整返回、不分页；仅历史 `batches` 明细封顶最近 50 批+`has_more`，并写全 actor/change_rows 元素 schema（audit 先例 service.py:2773-2784 同款；续载游标留未来） | ✅ mc-expert 陪审定稿（中高；主 Claude 接受 audit 先例+无界增长论证） |
| B5c | **b：网页新建 + admin 软删 + v1 不改名**；admin/member 可新建，created_by=当前操作者且不可变，viewer 403；仅 admin 可软删 | ✅ 用户拍板（2026-08-18） |
| N1/N3/N4 | 完整导入 DDL / 动态迁移计数 / §0 精确计数 | ✅ 已写入 9- |
| N5 | 归档移动与引用同步 | ✅ 已完成；4/5/6/7/8 在 archive/，10- 已降级 |
| N2 | 陪审定稿=删 base_version 正确；**并删 preview_sha256 比对表述**（commit 不重收文件、无可比对象；不靠 sha256——状态机 404/409 管提交资格、事务内重校验 422 管内容仍合法：名称唯一复查+行级校验对 preview_json 重放，序=状态机在前重校验在后） | ✅ mc-expert 陪审定稿（高） |
| N6 | commit / 新 run 流程 | 已定，须用户显式授权 |
| N7 | mc-expert KB 契约入口 | ✅ 已修复并完成增量陪审 |

**共性修订两条（随修订一并落 9-，陪审提出）**：C1 = §1.2 initial_date 注释「成员不可见不可改」改写为「编辑器不展示（UX 层）；复盘语境全员可见」——消除与 STATE §4 复盘全员可见的互咬；C2 = §3.5 加分层规则一句「顶层 project 不存在/跨 workspace/无权统一 → 403 PROJECT_FORBIDDEN；undo/import batch 等操作对象查无 → 404 专属 code；变更行内 node_id 无效/越界 → 422 行级」——防 G3 与 B2 裁决日后被误读为矛盾。

修订执行序：**B5c 已由用户拍板=b** → **B/N/C 已全量写入 9-** → 增量复审 CONDITIONAL PASS（补 require_active 与 undo 计数）→ 最终点检 **PASS** → N5 归档与引用同步已完成。commit / 新 run 仍须用户显式授权（N6）。

## §4 最终增量复审记录

- 首轮增量复审确认 B1–B5/N1–N4/C1–C2 主体闭环，另抓到两处局部阻断：软删项目访问路径未逐处显式 `require_active=True`；复盘直接修改次数未排除 undo 反向日期行。
- 最小修订已写入 9-：batch/undo/initial-correction/单项目 GET/项目 DELETE 全部强制 active；`direct_edit_count` 限定为 `batch.change_kind='direct_edit' AND row.change_role='direct' AND field='date'`，并补软删隔离与 undo 不虚增测试。
- mc-expert 最终逐项取证结论：**PASS，高置信；门 3 技术契约可以关闭**。N5 已执行；未 commit，未激活新 run。
