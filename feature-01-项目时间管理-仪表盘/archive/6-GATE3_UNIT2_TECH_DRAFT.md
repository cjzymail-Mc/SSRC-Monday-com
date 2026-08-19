# 门 3 · 单元 ②「原子批量 API」技术方案草案

> 状态：planner 草案 v1（2026-08-18）。**拍板结果（2026-08-18 全项收口，见 `7-GATE3_UNIT2_DECISIONS.md` §0）**：E1=A 单端点单事务、E4=A（护栏四件套 + 写权限可撤 + 跨项目 undo_group 等价确认）、E7b=A、E7c=a（行级区分不动 D5 结构）、E7d=A（钉住+分段平移）；P2=A（E2/E3/E3b/E5/E6/E7a/E8 打包冻结）。§0 速览表状态列为出题时快照，以问卷 §0 确认记录为准。本文件为门 3 收口总固化前的过程稿，届时并入《技术方案冻结版》后归档。**拍板前不编码、不改库的约束继续有效，直至门 3 评审整体通过。**
> 依据：`STATE.md` §2/§5/§7（第 2/7 条归本单元）、`4-GATE3_UNIT1_TECH_DRAFT.md` 头部拍板注记 + §8 预留口、`2-DRAG_TIMELINE_REQUIREMENTS.md` §0、`3-UX_DETAIL_REQUIREMENTS.md` §0（R1）、`5-GATE3_UNIT1_DECISIONS.md` §0（D5/D11/P1）。
> 代码证据均为本次只读勘察核实（文件:行号）；未对运行库做任何写操作。
> 主 Claude 抽查复核（2026-08-18）：require_version=428 VERSION_REQUIRED（service.py:60-63）、batch_tasks 先全检后全写+版本不符 409（service.py:2223-2230）、transaction=BEGIN IMMEDIATE+异常回滚（database.py:25-33）——草案 §1.1/§1.2 承重论据属实。
> 纪律：DRAG 确认 1–24（含覆盖注记）、UX Q1–Q8+R1–R3、单元 ① 全部拍板（D1–D14 + 画法 A 链式 + 阶段区间配套）一律当输入；与冻结条款的出入均已 ⚠️ 显式标注。

---

## §0 决策点速览表

| # | 问题 | 选项 | planner 推荐 | 置信度 | 状态 |
|---|------|------|-------------|--------|------|
| E1 | 批次端点形状 | A workspace 级单端点「POST 一批（可含多项目）」/ B 项目级端点前端循环 / C 行级多请求 | **A**（跨项目单请求单事务） | 高 | 【待拍板】（A/B 差异小，C 被冻结条款强否决） |
| E2 | 并发锚点携带方式 | base_version 逐项目比对，任一不符整批 409 / 行级版本 | **逐项目 base_version**（锚点本身=项目级 version，单元① §8 已锁，本项只定携带与比对细节） | 高 | 建议直接冻结 |
| E3 | 409 返回体 | 只报版本号 / 带服务端最新完整视图 | **带最新完整视图**（nodes[]+segments[]+metrics+version），供前端并排提示 | 高 | 建议直接冻结（DRAG 问卷 Q10 原文直接要求） |
| E3b | 放弃更改的服务端语义 | 纯前端丢弃 / 通知服务端 | **纯前端丢弃，零 API、零批次、零审计** | 高 | 建议直接冻结 |
| E4 | 撤销护栏 | 见 §5：最新批次校验 / actor 限定 / redo / 时限 | **仅可撤各项目最新批次；undo 亦为批次（version+1）；不做 redo；无服务端时限；操作者需项目写权限即可（不限原 actor）** | 中高 | 【待拍板】（actor 限定子项） |
| E5 | `_project_access` 形态 | 见 §6 | **仿 `_board_access` 同构新函数：读=admin+member（viewer 挡读挡写）、写=admin 或 member 且 created_by=自己；单一 403 code 模糊化** | 高 | 建议直接冻结 |
| E6 | 拖拽授权与 API 交互 | 纯前端 vs 逐节点请求 | **拖拽期间零网络请求；【更新日期】才 POST 一批；details_json 记 {mode, magnet}** | 高 | 建议直接冻结 |
| E7a | 新增/删除与修改同批？ | 同一批次 / 分开端点 | **同走一个批次端点**（field 已含 'created'/'deleted'） | 高 | 建议直接冻结 |
| E7b | 空批/等值变更 | 422 / 幂等 200 no-op / 照常建批 | **空变更数组=422（对齐惯例）；等值行剔除后全空=200 no-op 不建批不 +version** | 中高 | 【待拍板】 |
| E7c | ⚠️ 混合批次的 change_kind | a 行级 field 区分+details 记 kinds / b CHECK 加 'mixed' | **a（不动已拍板结构）**；b 趁 v16 未建零成本但属改拍板产物 | 中 | 【待拍板】（R1 与 D5 的交界缺口，必拍） |
| E7d | direct/cascaded 行生成规则 | 见 §8.4（分段平移细则） | **direct 钉住、位移分段传导**（冻结顺延规则的自然推广） | 中高 | 【待拍板】（新细则，需确认） |
| E8 | 提交「意图」还是「结果」 | 意图（direct 变更集，服务端重算级联）/ 结果（整表新值） | **意图**（服务端权威，防作弊/漂移） | 高 | 建议直接冻结 |

---

## §1 代码勘察结论（全部经读码核实）

### 1.1 事务与整批原子性先例

- `transaction(conn)` = `BEGIN IMMEDIATE` + 异常回滚（`flowboard/database.py:25-33`）。BEGIN IMMEDIATE 在事务开始即取写锁，天然串行化写者——「整批全成全败」的机制地基已存在。
- `batch_tasks`（`flowboard/service.py:2196-2266`）：先逐项校验（版本不符在**任何写入之前**抛 409，service.py:2226-2230），后在一个事务内写完全部条目；items 限 1..100（service.py:2200）；`batch_key=secrets.token_hex(12)` 写入每条 details_json（service.py:2242, 2261）——「同键散条」式批次先例。
- `commit_import`（service.py:1388-1447）：两段式（preview 存 `import_batches` → commit 整批单事务）；行级报错 details 带 `row`（从 2 起=数据行号，service.py:1417, 1425, 1428）——timeline 批次的行级报错可直接沿用此格式。

### 1.2 乐观锁 409 模式

- `require_version`：缺 version 抛 **428 VERSION_REQUIRED**（service.py:60-63）——注意不是 422。
- 版本不符抛 **409 VERSION_CONFLICT**：`update_task` 比对（service.py:2171）+ 条件 UPDATE 配 `_conflict`（cursor.rowcount!=1 即 409，service.py:269-272；用法 service.py:2191、1443）。
- `ApiError` 统一形状 `{code, message, details?}`（service.py:34-43）。业务专属 409 code 有先例（`ACTIVE_SUBTASKS`，service.py:2240）。

### 1.3 权限钩子形态

- `_workspace_role`（service.py:177-186）：无 membership → 403 `RESOURCE_FORBIDDEN`「资源不存在或不可访问」；viewer 写 → 403 `READ_ONLY`。**读路径不挡 viewer**。
- `_board_access`（service.py:188-202）：JOIN 查询一次取回对象+角色，403/404 分层，返回 row 给调用方。**现状全库无任何创建者校验**——`_project_access` 是全新钩子（单元① §8 已预告）。
- admin 判定惯例：`_workspace_role(...)!="admin"` → 403 `ADMIN_REQUIRED`（service.py:2776, 2795）。

### 1.4 审计桥接

- `_activity` 一次写三表（activity + audit_log 幂等 + realtime_events，service.py:240-254）。单元① D5 已拍板 timeline **不走 activity/realtime**，只写 audit_log 桥接行；activity 表的 `CHECK(entity_type IN ('board','group','task','comment'))` + `board_id NOT NULL` 已再核实（database.py:323-333）。
- admin 统一审计查询/CSV（service.py:2773-2790）零改造即可见桥接行。

### 1.5 路由与认证

- server.py 手工路由：`parts = path.strip("/").split("/")` + if 链（server.py:148 起）；workspace 级批量端点先例 `POST /api/workspaces/{id}/tasks/batch`（server.py:163-164）。新端点纯增量，无框架约束。
- **401 位置**：`current_user`（server.py:107-111）→ `service.authenticate` 抛 401 `AUTH_REQUIRED`/`SESSION_INVALID`（service.py:135-149）；在 dispatch 内对全部非登录路由统一先调（server.py:142），写方法同时验 CSRF。→ timeline 端点**零额外代码自动获得 401/CSRF 语义**，service 层方法收到的一律是已认证 user——与现有做法一致，无需新决策。

### 1.6 撤销/反向操作先例

- 全库（flowboard/*.py）搜索 undo/revert/rollback/reverse：**无任何业务级撤销先例**（命中仅为排序 reverse、sqlite rollback、路径反转）。undo 是全新能力，无既有模式可套，但批次表已留 `undone_batch_id`（单元① D5）。

### 1.7 冻结条款原文引用与核对（本单元的语义地基）

1. **DRAG §0 确认 5**（`2-DRAG_TIMELINE_REQUIREMENTS.md:17`）：
   > 「批量提交只允许全成或全败：任一项目发生并发冲突时，整批不写入，全部草稿保留并提示冲突。」
   核对结论：整批=**跨项目**整批（与确认 4 连读），任一项目冲突 → 整个请求零写入。E1/E2/E3 直接服务此条。
2. **DRAG 问卷 Q10**（同文件 :244-252，确认句 :250）：
   > 「已确认：选择 A。任一冲突导致整批不写入。」推荐原文：「全批拒绝覆盖，原始数据一项都不写；**保留本地草稿，展示服务端最新日期并让用户重新确认**。」
   核对结论：409 返回体**必须携带服务端最新视图**（E3 的直接依据）。
   ⚠️ **编号歧义申报**：任务书所指「确认 10」若按 §0 序号是「已完成历史节点可拖动、标记【历史日期修正】」（:29，对应问卷 Q6）——那是变更类型/标记语义（见 §7），不是并发语义；多人并发的产品语义在**问卷 Q10 + §0 确认 5**。两条原文均已引用核对，未重开任何一条。
3. **DRAG §0 确认 4**（:16）：「全项目仪表盘允许累计多个项目的草稿；【更新日期】一次提交当前页面全部待更新项目。」→ E1 必须单请求多项目。
4. **DRAG §0 确认 12/16/17**（:31/:54/:55）：提交后一次撤销=新反向审计批次、不删不篡改原记录；有效至页面刷新或下一次编辑开始（**不设固定倒计时**）；跨项目撤销**整批回滚**、「审计记一条反向批次」。
   ⚠️ 与单元① 表结构的字面出入：批次表为每项目一行，跨项目撤销必然产生 **N 行 undo 批次**，与「一条反向批次」字面不符。语义等价处理：一次 undo 请求 = 一个 `undo_group` token 写入各行 details_json（E4），审计呈现为一次操作一组批次。此为表述级出入，非语义重开，随 E4 一并拍板确认。
5. **UX R1**（`3-UX_DETAIL_REQUIREMENTS.md:26`）：「右键【已完成/未完成】切换与日期**共用同一草稿批次**——一次【更新日期】提交、【放弃更改】回滚、提交后一次撤销；**审计区分修改类型**。」→ 引出 E7c 缺口（批次级 change_kind 单值 vs 混合批次）。
6. **mainline §4.1（mainline-feature01.md:72）**：「…顺延一直影响到项目末节点，后续各段间隔保持不变，**保存后提供一次撤销**」——编辑器保存同样有撤销，与拖拽同构；**PHASE2 §12.4**（`1-PHASE2_REQUIREMENTS_DRAFT.md:1004-1007`）：「新节点可填写日期或间隔…**保存时**节点按日期升序自动排列」——编辑器存在「保存」动作。→ E7a（增删改同批）的需求侧依据。
7. **DRAG §6**（:460-469）：「草稿保存在纯前端内存…」「批量更新 API、并发版本号和事务边界」明确留给技术阶段——本草案即其答案，未越权。

---

## §2 E1 · 批次端点形状

### 选项

- **A（推荐）workspace 级单端点**：`POST /api/workspaces/{id}/timeline/batches`，请求体携带 1..N 个项目的变更组，单事务整批提交。路由形态对齐 `tasks/batch` 先例（server.py:163-164）。
- B 项目级端点（`POST /api/timeline/projects/{id}/batches`）+ 前端循环调用：赌注=无法实现确认 5 的「整批不写入」（部分项目已写入后另一项目 409，要么接受部分成功【违约】、要么前端补偿回滚【需撤销链，复杂且留脏批次】）。
- C 行级多请求（仿 update_task 逐节点 PATCH）：直接违反「未点击【更新日期】不改写原始数据」（DRAG §1 第 6 条）与确认 3/5，强否决。

### 请求体草案（A 形态）

```json
POST /api/workspaces/1/timeline/batches
{
  "requests": [
    {
      "project_id": 3,
      "base_version": 7,
      "trigger_source": "drag",
      "details": {"mode": "cascade", "magnet": "standard"},
      "changes": [
        {"node_id": 41, "set": {"date": "2026-09-02"}},
        {"node_id": 42, "set": {"done_at": true}},
        {"node_id": 41, "set": {"stage": "测试", "track": "main", "name": "B2", "remark": "..."}},
        {"create": {"track": "main", "stage": "开发", "name": "B3", "date": "2026-09-10", "remark": ""}},
        {"node_id": 43, "remove": true}
      ]
    }
  ]
}
```

- 同一 node_id 可出现多行（最终值语义，DRAG 确认 3 的服务端版：按序应用、以最后为准）；服务端合并后再算级联。
- `interval_days` 作为编辑器改间隔的意图字段与 `date` 并存时按冻结规则**日期优先**（STATE §2「两者同时改则日期优先并覆盖重算间隔」）。
- `reject_unknown` 白名单不含 created_by/initial_date（单元① D3 三重锁第①重，惯例 service.py:78-81）。
- 防呆上限对齐惯例：`requests` ≤ 20 项目、每项目 `changes` ≤ 200 行（batch_tasks 限 100 的同类做法，service.py:2200）；超限 422。

### 返回体（200）

```json
{
  "results": [
    {"project_id": 3, "batch_id": 118, "version": 8,
     "view": {"nodes": [...], "segments": [...], "metrics": {...}}}
  ]
}
```

- `view` 由单元① 拍板的**服务端唯一派生器**产出（D11/D13：nodes[]+segments[]+M1–M5），前端提交后整视图刷新，零客户端重算。
- 量级：10 项目 × 数十节点 ≈ 数十 KB JSON，局域网无压力。

### 推荐：A，置信度高

理由：确认 4/5 冻结了「跨项目一次提交、整批全成全败」，只有单请求单事务能一字不差兑现；A 同时让 undo 的「整批对称」（确认 17）有天然的请求边界。

风险与回退：单端点承载全部变更类型，请求体分支多——用 changes 数组的统一行结构（如上）而非分类型子端点控制复杂度；若编码期发现分支失控，拆分点在 service 层内部函数，端点形状不必变。

---

## §3 E2 · 并发锚点

**锚点本身已由单元① §8 锁定**（timeline_projects.version 每批 +1，批次表存 before/after），本节只定携带与比对，不重开行级 vs 项目级。

- **提交**：每项目带 `base_version`；服务端在事务内逐项目比对 `timeline_projects.version != base_version` → **整个请求 409，零写入**（比对在写入前，仿 batch_tasks service.py:2226-2230 的「先全检后全写」）。项目 version 用条件 UPDATE `SET version=version+1 WHERE id=? AND version=?` + `_conflict` 兜底（service.py:1443 模式）——双保险防同事务内漏比对。
- **undo**：等价锚 = 「目标批次仍是该项目最新批次」（见 §5），不单独送 base_version（送 batch_id 即可，语义更强且防 ABA）。

**与 DRAG 确认 5 的语义核对**：项目级锚点在「同项目两处不相干编辑同时提交」时也会 409（行级锚点不会）——但这正是冻结语义：「任一项目发生并发冲突时整批不写入 + 展示服务端最新日期让用户重新确认」。产品把冲突定义为**项目级**事件，技术锚点与之一一对应，无出入。

**15 人 × 10 项目冲突概率评估**：
- 每项目潜在写者 = created_by 本人 + admin ≈ 2 人（member 只能写自己的项目，STATE §5）。
- 冲突窗口 = 从前端取得 base_version（页面加载）到提交，含草稿保留期。分钟级窗口下，按每项目日均个位数次提交估算，冲突为**周级罕见事件**；但确认 7/8 允许草稿跨视图/跨筛选长期保留（小时级窗口），冲突率抬升至「可感知」。
- 结论：可接受——冲突成本已被冻结语义压低（草稿不丢、整批拒绝、重新确认即重试），无需悲观锁或行级细化。缓解手段是产品层的（提交前可查看受影响项目），不是技术层的。

风险与回退：若上线后冲突频率惹怨，升级路径是「409 视图并排 + 一键以我的草稿重放」（纯前端重试流），锚点契约不变。

---

## §4 E3 · 409 冲突返回体与前端策略

### 选项

- 只报版本号（`{conflicts:[{project_id, server_version}]}`）：实现最小，但前端无法执行 Q10 拍板的「展示服务端最新日期并让用户重新确认」——没有数据可展示。
- **带服务端最新完整视图（推荐）**：

```json
409 {"error": {"code": "VERSION_CONFLICT", "message": "批量提交存在版本冲突，整批未写入",
       "details": {"conflicts": [
          {"project_id": 3, "submitted_version": 7, "server_version": 9,
           "view": {"nodes": [...], "segments": [...], "metrics": {...}}}]}}}
```

- 只含**冲突项目**的视图（未冲突项目零写入、草稿全保留，无需服务端数据；前端并排「我的草稿 vs 服务端最新」时草稿本来就在本地）。view 复用同一派生器全量产出——代码零分叉，避免「简版视图」第二套实现。

### 「放弃更改=纯前端丢弃」的确认（E3b）

确认：**放弃是纯前端动作——零 API 调用、不产生批次、不写任何审计**。依据：DRAG §3「草稿不应写入正式活动记录」（:124）；审计只记「已提交的批次」（含 undo 批次）。服务端对「曾有过什么草稿」永远不知情。此条建议直接冻结，置信度高。

推荐置信度高（Q10 原文 :250 直接要求「展示服务端最新日期」）。风险与回退：409 体较大（含全视图）——局域网 + 单位数项目冲突，无实际压力；极端时前端可只渲染 nodes[]。

---

## §5 E4 · 撤销护栏

### 方案（逐条）

1. **仅可撤销「该项目最新批次」**：undo 请求 `POST /api/workspaces/{id}/timeline/batches/undo`，体 `{"batch_ids": [118, 119]}`（前端原样送回提交响应里的 batch_id 集合）。服务端校验：每个 batch_id 必须是其所属项目 `MAX(id)` 的批次，**任一不满足 → 整个 undo 409（code `UNDO_TARGET_STALE`，专属 409 code 有先例 service.py:2240），零写入**——与确认 17「整批回滚」对称。
2. **undo 本身也是批次**：`change_kind='undo'`、`undone_batch_id` 指向被撤批次、`trigger_source='undo'`；逐行生成反向变更（node_changes 的 old/new 互换；'created' 的反向=软删该节点、'deleted' 的反向=恢复 deleted_at=NULL）。原批次行原样保留（确认 12「不删除或篡改原提交记录」）。
3. **version 继续 +1**：单元① §8 已锁（每批 +1），undo 不例外——被撤效果回去了，但 version 单调递增，保证「被撤批次不再是最新」由 undo 批次本身占据，天然封死重复撤销。
4. **不做 redo**：undo 批次不可再被撤（目标批次 `change_kind='undo'` → 拒绝）。核对：全部冻结条款（确认 12/16/17、STATE、mainline）**无任何 redo 表述**（已搜索），且确认 16「有效至页面刷新或下一次编辑开始」的窗口语义与 redo 互斥。建议直接冻结「不做 redo」，置信度高。
5. **无服务端时限**：确认 16 选 A 明确「不设固定倒计时」——撤销入口的消失由**前端**控制（刷新/新编辑开始），服务端只守「最新批次」护栏。前端窗口关闭后 API 层面理论可撤，但无入口即无操作；与冻结条款一致，不额外加时限。
6. **跨项目「一条反向批次」的表述对齐**：一次 undo 请求 = 每项目一行 undo 批次 + 同一 `details_json.undo_group` token。⚠️ 字面与确认 17「审计记一条反向批次」不完全一致（那里按单项目语境表述），语义等价（一次操作、一组对称批次），请随本节一并确认。
7. **操作者权限（E4 唯一真正的开放子项）**：推荐 undo 需对涉及项目的**写权限**即可（§6 的 `_project_access(write=True)`），不限定为原批次 actor。理由：「最新批次」护栏已把可撤窗口锁死在「提交后无人动过」，误撤面极小；admin 全权本就覆盖；member 撤 admin 刚在自己项目提交的批次在归属语义上成立。备选：仅原 actor 或 admin——更紧，但引入「owner 看着 admin 改错却不能撤」的死角。置信度中高，【待拍板】。

### 与已冻结条款的关系核对

- R1「提交后一次撤销」：由 1+3 联合实现——每次提交后其批次即为最新批次，可撤一次；用户再提交新批次后，旧批次不再是最新，撤销窗口自动转移给新批次。**无需额外状态位**。
- DRAG 确认 16 的「下一次编辑开始」：前端在用户开始新草稿时撤掉撤销入口；服务端无需感知「编辑开始」。自洽。

风险与回退：undo 的反向行生成依赖 node_changes 的 old/new 完整性——若被撤批次含 'created' 行且该节点后续又被**其他批次**改动，则该批次早已不是最新、根本轮不到撤，护栏闭环。唯一残余风险是实现 bug，靠测试锁定（构造三连批次撤中间批次必败）。

---

## §6 E5 · 权限钩子 `_project_access`

### 形态（仿 `_board_access` 同构不同表，service.py:188-202）

```python
def _project_access(self, conn, user_id, project_id, *, write=False, require_active=False):
    row = conn.execute(
        """SELECT p.*, wm.role FROM timeline_projects p
           JOIN workspace_memberships wm ON wm.workspace_id=p.workspace_id AND wm.user_id=?
           WHERE p.id=?""", (user_id, project_id)).fetchone()
    if not row or row["role"] == "viewer":          # Q18-B：viewer 连看都不行（挡读挡写）
        raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
    if write and row["role"] != "admin" and row["created_by"] != user_id:
        raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
    if require_active and row["deleted_at"]:
        raise ApiError(404, "PROJECT_NOT_ACTIVE", "项目当前不可用")
    return row
```

- **读**：admin+member 开放（STATE §5「查看对所有注册成员开放」）；**viewer 挡读挡写**（DRAG Q18 选 B：「viewer 连看都不行」）。⚠️ 与 `_workspace_role` 现行为不同（那里读不挡 viewer，service.py:184 只挡写）——本钩子语义**收紧**，依据即 Q18-B 拍板，非笔误。
- **写**：admin 全改；member 仅 `created_by=自己`。created_by 不可变由 D3 三重锁兜底。
- **403 返回体**：单一 code `PROJECT_FORBIDDEN` + 模糊文案「资源不存在或不可访问」——对齐现有惯例（service.py:183/197 的存在性模糊化，不泄露项目是否存在）；专属 code 便于 audit 排障（`BOARD_FORBIDDEN` 先例，service.py:197）。写路径不区分「存在但无权/不存在」。
- **401**：路由层统一处理（§1.5），timeline 零额外代码；service 方法假定已认证 user——现状做法，照搬。
- **服务端执行**：每次 batch/undo 事务内对**每个**涉及项目逐一 `_project_access(write=True)`——任一 403 整批拒绝（全成全败对权限同样成立）。

风险与回退：无实质风险（新表新钩子，零回归面）。测试锁定三条：member 改他人项目 403、viewer 读 403、未登录 401。

---

## §7 E6 · 拖拽授权与 API 交互（确认型）

- **右键四项菜单 + 双模式拖拽 + 磁吸 + 放大带 = 全部纯前端实现**：授权（右键解锁→拖→松手上锁）、单节点档前后钳制（R3）、顺延档前驱钳制（DRAG 确认 2）、1 日吸附（标准档）、±10 天 ×8 放大带——全部在浏览器内完成，**拖拽期间零网络请求**。依据：STATE §7 第 7 条「解锁授权纯前端，提交一批变更走一个接口」；DRAG §1 第 6 条「未点击【更新日期】时原始数据必须保持不变」。
- 唯一的 API 触点：点击红色【更新日期】→ `POST .../timeline/batches`（§2）。数据来源为页面加载时的视图（单元① 契约），timeline 不接入 realtime_events（D5 拍板不写该表），无轮询。
- **批次 details_json 记录**：`{"mode": "single"|"cascade", "magnet": "standard"|"strong", "zoom_band": "±10d×8"}`（magnet 默认 standard；强档参数留集成验收）。`trigger_source='drag'`。
- 编辑器来源批次 `trigger_source='editor'`；状态切换行以 `field='done_at'` 落行级审计（R1「审计区分修改类型」，详见 E7c）。
- 拖动**已完成节点**（DRAG §0 确认 10 / 问卷 Q6）：仍是改当前 `date`，属于 `direct_edit` 批次 + details 标 `{"historical_correction": true}` 供前端「明确标记为【历史日期修正】」。⚠️ 概念澄清：这与单元① 的 `initial_correction`（admin 例外入口改 **initial_date**）是**两个不同概念**，后者走独立端点（单元① D3 第③重），不在本端点白名单内。两者同名易混，实现时以字段为准（date vs initial_date）。

建议直接冻结，置信度高。

---

## §8 E7 · 批次内容的边界

### 8.1 新增/删除与修改同批（E7a）

**同走一个批次端点**：`changes` 数组内 `create`/`remove` 与 `set` 混排（§2 请求体）。依据：单元① node_changes.field CHECK 已含 `'created'/'deleted'`（D5 拍板时即预留）；PHASE2 §12.4 编辑器「保存时」统一生效；R1 精神（同批多类型一次提交）。删除=软删（deleted_at/deleted_by，红线「删除优先软删除」），**不移动其他日期，只重算该轨合并间隔**（STATE §2 冻结规则，间隔是派生值无需落库操作）。建议直接冻结，置信度高。

### 8.2 空批/等值变更（E7b）

- 请求体 `changes` 为空数组/缺省 → **422**（对齐 `update_task`「没有可更新字段」service.py:2156、`batch_tasks`「changes cannot be empty」service.py:2213 的既有惯例）。
- 变更存在但逐行比对后**全部与现状等值**（new==old）→ **200 幂等 no-op**：等值行剔除、不建批次、version 不变、返回当前视图 + `"no_op": true`。理由：复盘的「直接修改次数」不能被空转批次污染（STATE §4），且用户端「点了更新但内容没变」不该被报错吓到。
- 部分等值 → 正常建批，等值行不产生 node_changes 行。
- 置信度中高，【待拍板】（422 vs 400 vs 200 的口味题，推荐已给）。

### 8.3 ⚠️ 混合批次的 change_kind（E7c，本草案最重要的新发现）

R1 冻结「状态切换与日期修改共用同一草稿批次…审计区分修改类型」；但单元① D5 拍板的批次表 `change_kind` 是**批次级单值** CHECK（`'direct_edit'|'status_toggle'|'initial_correction'|'undo'`）——一次提交里既有改日期又有点【已完成】时，批次级单值装不下两种类型。**这是 R1 与 D5 的交界缺口，单元① 出题时未覆盖，必须本单元补拍**：

- **a（推荐）不动表结构**：批次级 `change_kind` 记主类型（含日期修改即 `direct_edit`；纯状态切换批次才记 `status_toggle`）；「审计区分修改类型」由**行级**承载——node_changes 的 `field` 列已天然区分（`date` 行=日期修改、`done_at` 行=状态切换，D5 拍板的 field CHECK 本来就两者皆有）；批次级可查询性补 `details_json.kinds: ["direct_edit","status_toggle"]`。查询「某项目状态切换历史」= `EXISTS(node_changes WHERE field='done_at')`，可行。先例：batch_tasks 的 batch_key 即走 details_json（service.py:2242）。
- **b 改 CHECK 加 'mixed'**：v16 尚未建表（已核实代码库零 timeline 表），此刻加值零迁移成本，语义最直白；但严格说是修改 D5 已拍板产物，须用户显式点头。

推荐 a（不动任何已拍板结构、行级粒度本就是审计的真实需求粒度），置信度中，【待拍板】。

### 8.4 direct/cascaded 行生成规则（E7d，配合 §9）

服务端重算级联后写行：

- 用户显式提交的变更（含 create/remove）→ `change_role='direct'` 行；
- 顺延算法自动平移的**非 direct** 节点 → `change_role='cascaded'` 行（只记 date 前后值，间隔随日期可推导，D5 已定不单存）；
- **同批多 direct 的分段平移细则**：链 A→B→C→D，同批 direct 改 B 和 C。规则=**direct 节点钉住自己的新日期；每个非 direct 节点跟随其最近上游 direct 节点的位移整体平移**（B 段位移 δB=B′−B 作用于 B 与 C 之间的非 direct 节点；δC=C′−C 作用于 C 之后）——即「后续整体平移、间隔保持」在多锚点下的自然推广：每两个 direct 锚点之间的相对间隔不变。⚠️ 此细则是冻结顺延规则（单 direct 情形）的**新增推广**，无冻结条款直接覆盖，置信度中高，【待拍板】确认。
- 一个节点既被 direct 又被级联覆盖时：**direct 绝对优先**（用户明确给的值就是终值），级联跳过该行、从它重新分段。

### 8.5 批内跨项目

每项目一个变更组=一个批次行；项目之间无任何联动计算（双轨规则都在项目内）。

---

## §9 E8 · 级联顺延的服务端重算

### 选项

- **意图（推荐）**：前端只提交「改了什么」（direct 变更集：node_id + 新 date / interval_days / done_at / create / remove）。服务端在事务内按冻结规则重算级联（改 B 只顺延本轨后续、间隔保持、日期优先覆盖间隔、删除只重算间隔、钳制边界）、生成 cascaded 行、落库、返回完整视图。
- 结果（前端送整表新值）：服务端退化为校验器。赌注：①顺延规则在前端 mock 已实现一遍，结果提交=两套实现永久并存，漂移无人裁判；②「结果」可被构造（绕过钳制、伪造顺延范围），权限红线「服务端执行」的精神被架空；③请求体从「几个 direct」膨胀为「全项目节点」。

### 推荐：意图，置信度高

理由：D11/D13 已冻结「派生指标与段派生的唯一实现位置=服务端」，顺延算法与派生器同源同层，意图提交让「读视图」和「写重算」共享同一套轨道/间隔/状态函数，单一实现原则一贯到底；前端预览（mock 已演示的顺延反馈）只是**预测**，提交后以服务端返回视图为准刷新——预测错了会被纠正，权威永远在一处。

风险与回退：前后端预测不一致的瞬间存在（如钳制边界差一天）——产品语义兜底：提交后立即以返回视图渲染（E1 返回体已定）；工程兜底：顺延算法写成纯函数 + 与前端共享同一组测试用例（编码期落测试）。回退到「结果提交」的代价是放弃服务端权威，不建议。

---

## §10 单元 ③ 的接口预留

本单元拍板后**锁定**：

1. 端点契约：`POST /api/workspaces/{id}/timeline/batches` + `POST .../batches/undo` 的请求/响应/错误码全集（含 409 两种形态、403 `PROJECT_FORBIDDEN`、422 行级 details 带 row/node_id）。
2. 意图提交模型 + 顺延算法的服务端实现规格（分段平移细则若拍板则一并锁定）。
3. `_project_access` 形态与权限错误码。
4. 只读视图形状（E1 返回体的 view 结构即页面初始加载的视图结构，GET 端点形状随实现期落，无新决策）。

留口不锁：

- v16 迁移 runbook、备份执行序、第一阶段回归清单最终形态（单元 ③ 主项；表结构本身已由单元 ① 锁定）。
- Excel 导入：复用 `import_batches` 两段式骨架（service.py:1346/1388-1447 先例），commit 时产生 `trigger_source='import'` 的 timeline 批次——导入与手工编辑在审计层同构，具体列映射细则归单元 ③。
- 深色主题范围（仅仪表盘 vs 全站）、磁吸强档参数（集成验收）。
- 若 E7c 拍 a：复盘页对 `details_json.kinds` / `undo_group` 的查询呈现方式（呈现层，不回改结构）。

---

## §11 不改变的事实（已冻结清单，本草案一律当输入）

- **单元 ① 全部拍板**：D1=A 新专表 / D2=A 独立项目实体 / D3 service 三重锁不用触发器 / D4=done_at / D5 批次专表+direct·cascaded 行角色+audit_log 桥接（不走 activity/realtime）/ D6 / D7 / D8 / D9 / D10=本周窗口 / D11 实时计算服务端唯一实现 / D12=B / D13 nodes[]+segments[] 双份+可切换段算法 / D14 Asia/Shanghai；画法=A 链式 + 服务端同派生阶段区间列表配套。
- **DRAG Q1–Q22 全部确认 + 2026-08-18 覆盖注记**：尤其确认 3（连续拖动最终草稿为准）、确认 4/5（跨项目整批全成全败）、确认 8（离开拦截）、确认 10/Q6（已完成节点可拖+历史日期修正标记）、确认 11（提交无二次确认）、确认 12/16/17（一次撤销/反向批次/不删原记录/无倒计时/整批回滚）、确认 2+R3（钳制边界）、权限契约 18–24（admin 全改/member 仅 created_by=自己/查看全员不含 viewer/created_by 永不可改/initial_date 纠正仅 admin/导入 created_by=导入者）。
- **UX Q1–Q8 + R1–R3**：R1 状态切换与日期共用草稿批次、一次提交/一次回滚/一次撤销/审计区分类型；R2 双仪表盘同菜单；R3 单节点档双向钳制。
- **业务模型**：六阶段固定、单日里程碑、双轨独立日期链、日期优先、删除只重算间隔、三态状态派生、排序不改数据。
- **工程/流程红线**：服务端执行权限、迁移前备份可恢复、不破坏第一阶段数据、软删除优先、检查点五件套、门 3 期间不编码不碰运行库、冻结决策变更须用户显式拍板。

---

**planner 附注（低置信度项申报）**：E4-7（undo 操作者是否限原 actor，中高）、E7b（空批 422/幂等的口味，中高）、E7c（混合批次 change_kind 的 a/b，**中，R1×D5 交界缺口，必须拍**）、E7d（分段平移细则，中高，冻结规则的新推广）——以上建议交 mc-expert 陪审或用户拍板；其余高置信项可随草案一并过，但均已在 §0 标注状态，不构成既成事实。另申报两处表述级出入（非语义重开）：确认 17「一条反向批次」在 per-project 批次表下的 N 行等价处理（§5-6）、任务书「确认 10」的编号歧义（§1.7-2）。

---

**勘察涉及文件（本次全部只读）**：feature01 目录下 STATE.md / 1-/2-/3-/4-/5- 六份文档（局部）、`flowboard/service.py`、`flowboard/database.py`、`server.py`。
