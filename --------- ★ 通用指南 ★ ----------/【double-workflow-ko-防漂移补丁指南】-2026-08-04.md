# double-workflow 防漂移补丁指南（第二次任务 kickoff 前执行）

> 性质：**不改 skill 母本**的开工前操作指南。目标是沿用 monday-com 实战中已验证有价值的“主动纠偏 + 防漂移 + 独立验真”，而不是照抄它的文件布局。
> 适用：目标相对稳定、可拆检查点、需要跨会话接力、最终结果可取证的复杂长链任务。
> 当前依据：monday-com / Flowboard 的 I3→I13 实战、当前 live double-session protocol，以及 2026-08-04 独立复盘。
> 关联复盘：`[feature-07-codex-workshop-Adv]/double-session-长链任务防漂移机制复盘-2026-08-04.md`。

---

## 0. 开工前最短版

第二次任务只做下面五件事：

1. 先查旧 double run 状态；旧 run 未终止时，不覆盖 `temp.md`。
2. 按 §3/§6 把新任务写入 repo 根 `temp.md`，钉死主线、排除项、全局 `done_when`、检查点和证据。
3. 建议先启动 planner 进入预启动监视，再启动 coder；每个角色只能有一个活跃窗口。
4. 每次冷启动、恢复、Consume、新检查点和验收前，执行三条纠偏自问。
5. `mc-expert` 只在重大岔路口触发；planner 最终 PASS 必须独立复验全部 `done_when`。

这五项全部满足才开工。

---

## 1. 这套经验真正包含三道防线

| 防线 | 防什么 | 当前由谁承担 |
|---|---|---|
| **连续性** | compact、中断、跨 session 后丢进度 | double protocol 的冻结任务、state、message snapshot、`temp.md`、Consume/Handoff/Recover |
| **对齐性** | 干着干着换主线、扩大范围、跳过依赖 | 本指南补入初始任务的主线、排除项、完成边界、检查点和纠偏自问 |
| **真实性** | coder 自述完成但产物并未满足要求 | protocol 的 planner 独立取证、替代性复验、REWORK 和最终证据门 |

本指南主要补强第二道，同时把第一、第三道在 kickoff 时接好。不能把 monday-com 的成功简化成“有状态机就够”，也不能把 planner 或测试证据降成可有可无。

monday-com 是一个成功样本：它证明这些机制能共同工作，并实际抓出 I12 cursor 跳跃和 I13 restore 附件丢失；它没有证明所有长任务都必须采用同一文件数、同一检查点数或相同陪审频率。第二次任务应验证机制能否迁移，而不是复刻 I3→I13。

---

## 2. 开工前 GO / NO-GO（可以开工 / 暂不开工）

### 2.1 任务适配性

以下全部为“是”才适合 double-workflow：

- 任务终态相对稳定，可以明确“做完后是什么状态”。
- 能拆成若干有依赖、有验收证据的检查点。
- 条款密集的冻结契约已先整理成**逐条覆盖矩阵**：每条冻结判约映射到检查点、动态正例/负例和真实产物证据位；未映射完不开工。
- 允许范围、禁止动作和人工门边界可以在开工前写清。
- 结果能由代码、文件、测试、查询或其他外部证据验证，而不只靠主观判断。
- coder 与 planner 可以正交分工：一个实施，一个审核；planner 不需要代替 coder 写产物。

以下任一成立则先不开工：

- 仍处于开放探索，目标会随着研究持续变化。
- 有一个会改变范围、架构或交付物的用户决策尚未拍板。
- 任务只能由用户频繁参与才能推进，无法满足中途零普通人工门。
- 旧 run 或旧 Codex Goal 仍活跃且尚未完成合法恢复/收口。

探索型任务若仍想使用这套机制，应先把主线做成**有版本号的当前假设**，并明确什么证据允许升级版本；不要把会演化的目标伪装成永久冻结目标。

### 2.2 旧 run 预检（写新 `temp.md` 之前）

在目标 repo 中执行只读检查：

```powershell
$repo = (& git rev-parse --show-toplevel).Trim()
$stateTool = Join-Path $env:USERPROFILE '.agents\double-session-common\double-session-state.ps1'
pwsh -NoProfile -File $stateTool -Action Config
pwsh -NoProfile -File $stateTool -Action Show -ExpectedRepo $repo
```

`Config` 必须先成功；配置缺字段、多字段、越界或格式错误都会让正式入口 fail-loud，应在写任务前修正。`Show` 返回 `STATE_NOT_FOUND` 则按“没有旧 run”处理。

按结果处理：

| live 状态 | 是否可写新任务 | 处理 |
|---|---|---|
| `STATE_NOT_FOUND` | 可以 | 准备新 `temp.md` |
| `done` / `cancelled` | 可以 | 新 `temp.md` 必须非空、内容哈希不同，修改时间晚于旧 state |
| `running` | 不可以 | 回原两个 session 恢复或完成旧 run |
| `paused_budget` | 不可以 | 在原 coder/planner session 显式“继续”或 Continue Goal |
| `wait_human` | 不可以 | 先合法决议旧人工门；`ForceInit` 只用于用户明确替换旧任务，不是常规开工捷径 |

还要确认：

- 没有第二个 coder 或第二个 planner 会竞争同一 repo。
- Codex 窗口没有属于其他 repo/run/role 的 unfinished Goal；不得为图省事清掉仍活跃 double run 的 Goal。
- 不依赖旧聊天或旧工具输出判断状态；以 live protocol、`Show` 和 Goal objective 的绑定为准。

---

## 3. 新任务只需手写一个入口文件

默认只手写目标 repo 根目录的：

```text
temp.md
```

其余文件由状态机管理：

| 文件 | 处理方式 |
|---|---|
| `.copilot-task.md` | coder `Init` 从 `temp.md` 冻结；run 内只读，禁止手改 |
| `.copilot-state.json` | 脚本维护，禁止手改 |
| `.copilot-message.md` | 状态机保存当前交接快照，禁止手改 |
| `double-session-config.json` | 运行参数真相源；除非本轮明确要调参，否则只让 skill 读取校验 |

独立 `PROJECT_MAINLINE.md` 不是禁区，也不是默认必需品。只有当主线需要跨多个任务长期复用、放进 `temp.md` 会明显过重时才单独建立；建立后必须在冻结任务里写明读取时机和冲突优先级。第二次验证默认先把主线直接写进 `temp.md`，减少新机制。

> 本 repo 的“读 temp”命令会执行读取→清空→验空。正式任务写入后，**不要再让普通会话执行“读temp”**；由 double-coder 通过 `Init/Consume` 的受控路径处理。也不要手建或手改 `.copilot-*` 文件。

---

## 3.5 场景二：普通会话手写 v1 合同直供 coder Init

> 适用：你想在**普通会话**（不是 double-planner session）里，让 codex/claude 直接产出一份 coder 能 `Init` 的规范合同，**跳过 planner 的语义 KO**，然后启动 double-coder。
> 若你只想写零散需求让 planner 自动整理成合同，走场景一（§5），不需要本节。

### 唯一权威源（不复制，只指）

v1 合同的**完整字段清单与机械格式**以生产母本为唯一权威源，本指南**不复制**：

```
D:\Downloads\Mc Claude Code Workshop\Mc-Expert-repo\.agents\double-session-common\protocol.md
```

定位其中标题为 **`### DOUBLE_TASK_CONTRACT=v1 机械格式`** 的那一段（行号会随母本改版漂移，以段标题为准）。手写合同必须**照该段字段顺序逐字段抄**。

### ⚠️ 不要把本指南 §4 的「7 块」当合同骨架

这是最常见的致命错配：

| | 本指南 §4「7 块」 | 母本 `DOUBLE_TASK_CONTRACT=v1` |
|---|---|---|
| 性质 | **语义辅导**：教你怎么想清楚任务 | **机械格式**：机器校验能识别的合同 |
| 结构 | 任务终态 / 权威源 / done_when / 检查点… 的散文块 | `DOUBLE_TASK_CONTRACT=v1` 标记 + `original_request_json` + sha256 + 固定段顺序 |
| 直接 init | **会拒收**（无 marker、无 sha256、字段名对不上） | 通过 |

§4 帮你**构思任务语义**；要直供 coder Init，必须把 §4 想清楚的内容**翻译进 v1 机械格式骨架**，不是把 §4 原样当合同。

### 4 个机械拒收硬卡点（普通会话 agent 几乎必踩，逐条核对）

这些是状态脚本 `ValidateTask` 的 fail-loud 闸门，命中任一条 → `valid=false` → coder 拒绝 Init：

1. **`original_request_sha256` 算法极易算错**。正确做法：先把用户原始需求写成 `original_request_json`（用户原文做 JSON 字符串转义，单行合法 JSON）→ 脚本会 `ConvertFrom-Json` **解码**这个 JSON → 对**解码后的字符串**算 SHA-256 → 填进 `original_request_sha256`。**不是**对 JSON 字符串本身算、**不是**对 temp.md 全文算。JSON 转义写错会导致解码后字符串变样 → `sha256_mismatch`。
2. **`target_repo` 必须精确等于 coder Init 时传入的 repo 根**。脚本用 `GetFullPath` 规范化后做严格相等比对，大小写不同、尾斜杠、相对路径、多一层都会 `target_repo_mismatch`。用 `(& git rev-parse --show-toplevel).Trim()` 取到的绝对路径最稳。
3. **`runtime` 段三字段都必填**：`planner_runtime` / `review_gate` / `runtime_evidence` 缺一即拒收；`planner_runtime` 只能是这 6 个枚举值之一：`claude-native` / `codex-native` / `codex-glm` / `claude-glm` / `other` / `unknown`。
4. **`planner_runtime` 不是 native 时，`review_gate` 不得填 `planner_only`**。即只要 `planner_runtime` ∈ {`codex-glm`, `claude-glm`, `other`, `unknown`}，`review_gate` 必须填 `planner_plus_mc_expert`，否则 `unknown_or_non_native_requires_double_gate` 拒收。

### runtime 段的安全默认写法（手写时推荐）

手写合同时 planner 和 coder 两端都还没启动，**你无法可靠知道两端真实 model/provider**。安全默认：

```
planner_runtime: unknown
review_gate: planner_plus_mc_expert
runtime_evidence: provider_not_proven
```

**为什么不冲突**：合同里写的 `review_gate` 只被 `ValidateTask` 校验格式合法性；**真正生效的门（effective_review_gate）是 coder Init 时由脚本拿「合同的 `planner_runtime`」+「coder 传入的真实 runtime」现算的，取两端更严者**。手写 `unknown` + 双门保证有效门是双门（偏严、偏安全），绝不会意外降到 `planner_only`。代价仅是「实际两端都 native 时多跑一次 mc-expert 陪审」，对学习 repo 完全可接受。

> 若你**确切知道**两端都是原生模型，可填 `claude-native`/`codex-native` + `planner_only`；不确定就一律 `unknown` + 双门，**别猜 native**。

### 场景二你要自己承担 planner 本会做的语义整理

跳过 planner 等于把「语义 KO」揽到自己身上。 coder 会照你冻结合同的字面跑——若你的 `done_when` 不可外部取证、scope 没收口、检查点缺独立验证命令，coder 照样会跑歪。落笔前用 §2.1（任务适配性）和 §4（7 块心法）把任务想清楚，再翻译进 v1 骨架。

### 场景二操作顺序

1. 按 §2 预检旧 run；旧 run 未终态不得覆盖 `temp.md`。
2. 在目标 repo 根 `temp.md` 写入符合 v1 机械格式的完整合同（照母本段逐字段抄 + 上方 4 硬卡点 + runtime 安全默认）。
3. 启动 double-coder（Claude `/double-coder` / Codex `$double-coder`）；coder 探针会判 `CONTRACT_READY`，复核 `ValidateTask.valid=true` 后直接 `Init`，不碰你的合同内核。
4. planner 后启动时会观察到 state 自动绑定、进入审核循环（参见 §5）。

---

## 4. `temp.md` 必须包含的 7 块

总体原则：全局完成边界写“结果状态”，检查点写“依赖与局部验收”，不要把微观实现步骤钉死，让 coder 在冻结边界内自主选择最可逆路线。

### 块① 任务终态

一句话说明做完后世界是什么状态，不写“重构、实现、优化”等动作词。

- 差：重构 X 模块。
- 好：X 模块保持既有兼容性，指定场景全部可用，回归测试和文档证据一致。

### 块② 权威源、主线与范围

必须同时写：

- 目标 repo 绝对路径和冷启动必读文件。
- 冲突优先级：用户最新明确指令 > repo 硬规则/已封决策 > 本冻结任务 > 检查点计划 > 历史说明。
- **本轮做什么**：1–3 句话。
- **明确不做什么**：逐项列排除项，和“做什么”同等重要。
- 允许写路径、只读路径、禁止路径；已有用户改动如何处理。

### 块③ 全局 `done_when`

每条必须是可取证的结果属性，并写验证方式：

```text
- [ ] D1: <结果>（验证：<命令/文件/查询及预期>）
- [ ] D2: <结果>（验证：<命令/文件/查询及预期>）
- [ ] D3: 排除项未被扩入（验证：逐项核对块②）
- [ ] D4: 文档、实现与实际证据一致（验证：交叉核对）
```

单个检查点通过不等于全局完成。只有 planner 对全部全局 `done_when` 独立取证后，才能最终 `Done`。

### 块④ 检查点路线

复杂任务必须列检查点；每项至少包含：

```text
C1: <检查点名称>
  depends_on: <前置；没有写 none>
  scope: <本检查点覆盖什么>
  local_done_when: <局部结果属性>
  evidence: <planner 可独立复验的方式>
  novelty: <是否引入新 schema/契约/核心配置/跨模块边界>
  expert_review: <required/skip + 原因>
```

`evidence` 不得只写“运行相关测试 / 代码已实现 / 文档已更新”。它必须指向能关闭条款的具体证据：冻结原文、planner 独立构造的正例或负例、命名的动态测试/断言/查询，以及 round-trip/export/import/migration 类验收所需的真实返回产物。测试全绿、静态映射和 coder 自述都不能关闭条款；实现和测试同构时，以独立负例为准。

检查点只负责分段推进，不得自行扩大块②范围或降低块③的全局完成边界。当前入口必须明确；planner 通过当前检查点但全局未完成时，应把下一检查点交回 coder，而不是提前 `Done`。

### 块⑤ 红线、禁止动作和人工门

- 四红线：销毁性不可逆 / 对外交付明文合规 / 同一失败两次熔断 / 推翻已封决策。
- 本项目禁止动作：例如删除、force push、改外部母本、触碰敏感目录或改变既有数据。
- 授权模式：确认本任务适合深度授权 B；范围内普通可逆判断由两角色自主推进并留痕。
- 哪些权限/外部动作已前置授权，哪些必须进入 `PENDING_HUMAN_NONBLOCKING`。
- 什么会阻断 `done_when`，不能伪装成“收尾再说”。

同一失败两次必须按 protocol 的 `failure_key` 机械累计：只有两个独立 coder→planner 失败交接才算两次；同一回合内的短暂重试不算。

### 块⑥ 主动纠偏与陪审触发器

要求 coder/planner 在以下入口重锚：冷启动、恢复、每次 Consume 后、制定/调整计划、新检查点开始、关键交棒和准备验收。

每次回答三问：

1. 当前动作明确服务哪个检查点、哪个未满足的 `done_when`？如果映射不上，立即停下回看主线。
2. 当前方案是否把“明确不做”或范围外优化偷偷变成必做？
3. 正准备声称“已完成”的内容，实际实现、文档和可复验证据是否一致？

发现偏离时，先在冻结范围内调整方案或返工，并记录到 `AUTONOMOUS_DECISIONS`；需要改变冻结范围时不得自行实施，按 protocol 交给 planner 归并。

`mc-expert` 按当前 live protocol 的风险扳机调用：

- 重大技术选型；
- 修改核心配置、agent、skill 或已封决策相关文件；
- 拆分任务前；
- 第一次实质失败后，准备第二次尝试前；
- 高风险、低置信或验证未闭的关键交棒前。

**不要把“每个检查点都叫一次架构预审”写成机械指标。** monday-com 的 I3→I13 每个检查点都包含新 schema 或同级核心契约，因此逐检查点预审有合理性；第二次任务若只是沿用已经审过的重复模式、没有新契约或新风险，可以不叫。22 次（coder 20 + planner 2）是实战观察值，不是配额。

planner 只有在自己检查文件、差异、测试并做过替代性复验后，仍遇到重大、高影响且多种解释都获证据支持的低置信判断，才调用 `mc-expert`；普通缺证据直接要求 coder 补证或 REWORK。

### 块⑦ 交接与最终证据口径

要求每次交接至少能回答：

- 当前检查点和对应全局 `done_when`。
- 实际改动、实际运行的验证及证据路径。
- 三条纠偏自问的结论；是否沿用了既有已审模式。
- `AUTONOMOUS_DECISIONS`、`PENDING_HUMAN_NONBLOCKING`、`OPEN_BLOCKERS` 的累计状态。
- 若失败：稳定 `failure_key`、本轮实质方案、未满足项和下一次验收方式。

最终报告必须区分：协议设计保证、实际执行证据、尚未独立复跑的历史记录。不要把“文件里写 PASS”当成这次 session 已重新验证。

---

## 5. kickoff 操作顺序

1. **先做 §2 预检**；旧 run 不是 `STATE_NOT_FOUND|done|cancelled` 就停止新任务开工。
2. **按 §4/§6 完成 `temp.md`**；人工通读一次，确认没有未拍板的范围分叉。
3. **最后写入 repo 根 `temp.md` 并验非空**；它必须比旧终态更新且内容不同。写入后不再用普通“读temp”路径读取。
4. **启动两个原生窗口**：建议先 planner、后 coder。planner 会进入预启动监视，coder 随后通过 skill 自动 `Init` 并冻结任务；不要手调状态脚本抢跑。
5. **入口**：Claude 使用 `/double-planner` + `/double-coder`；Codex 使用 `$double-planner` + `$double-coder`。同一 run 不得启动第二个同角色窗口。
6. **运行中少干预**：普通判断由 coder/planner 按冻结契约自主处理。预算暂停时在原两个 session 显式“继续”或 Continue Goal；不要另开窗口、猜 token 或随意清 Goal。
7. **只在合法人工门介入**：planner 呈出 `wait_human` 及允许决议后再操作；非阻塞事项留到最终汇总。
8. **以 planner `Done` 为终态**：必须附全部全局 `done_when` 的独立证据和未关闭人工事项，不以单个检查点 PASS 代替。

---

## 6. 最小可用 `temp.md` 模板

```markdown
# 任务：<一句话标题>

## ① 任务终态
<做完后的状态；不要只写动作>

## ② 权威源、主线与范围
- repo：<绝对路径>
- 冷启动必读：<文件清单>
- 冲突优先级：用户最新指令 > repo 硬规则/已封决策 > 本任务 > 检查点计划 > 历史说明
- 本轮做：<1–3 句>
- 明确不做：
  - <排除项 1>
  - <排除项 2>
- 允许写：<路径/文件>
- 只读：<路径/文件>
- 禁止：<路径/动作>
- 保留现有用户改动，不回退与本任务无关的工作树变化。

## ③ 全局 done_when（全部满足才可 Done）
- [ ] D1: <结果>（验证：<方式及预期>）
- [ ] D2: <结果>（验证：<方式及预期>）
- [ ] D3: 排除项未被扩入（验证：逐项核对 ②）
- [ ] D4: 文档、实现与证据一致（验证：交叉核对）

## ④ 检查点路线
- C1: <名称>
  - depends_on: none
  - scope: <范围>
  - local_done_when: <局部结果>
  - evidence: <独立复验方法>
  - novelty: <新 schema/契约/核心配置/跨模块边界；没有写 none>
  - expert_review: <required/skip + 原因>
- C2: <名称>
  - depends_on: C1
  - scope: <范围>
  - local_done_when: <局部结果>
  - evidence: <独立复验方法>
  - novelty: <...>
  - expert_review: <required/skip + 原因>
- 当前入口：C1

## ⑤ 红线、禁止动作与人工门
- 四红线：销毁性不可逆 / 对外交付明文合规 / 同一失败两次 / 推翻已封决策
- 授权模式：深度授权 B；范围内普通可逆判断自主推进并记录
- 本项目禁止：<列举>
- 已授权权限动作：<没有写 none>
- 后置人工事项：<哪些进入 PENDING_HUMAN_NONBLOCKING>
- 阻断 done_when 的事项不得后置伪装完成。

## ⑥ 主动纠偏与 mc-expert
在冷启动、恢复、每次 Consume、新检查点、关键交棒和验收前回答：
1. 当前动作服务哪个检查点、哪个未满足 done_when？映射不上就停下重锚。
2. 是否把“明确不做”或范围外优化偷偷变成必做？
3. 正准备声称完成的内容，实际实现、文档和证据一致吗？

mc-expert 只在这些扳机调用：重大选型 / 核心配置-agent-skill-已封决策 / 拆任务前 / 第一次实质失败后准备第二次尝试 / 高风险低置信或验证未闭的关键交棒。
重复采用已审模式、普通机械改动、仅缺证据：不调用；后者由 planner 直接要求补证或 REWORK。

## ⑦ 交接与最终证据
每次交接写：当前检查点与 done_when 映射 / 实际改动 / 实际验证与证据路径 / 纠偏结论 / 是否复用已审模式 / AUTONOMOUS_DECISIONS / PENDING_HUMAN_NONBLOCKING / OPEN_BLOCKERS。
失败时另写：failure_key / 本轮实质方案 / 未满足项 / 下一次取证与验收方式。
planner 只有对全部全局 done_when 独立取证后才能 Done。
```

---

## 7. 第二次任务结束后要记录什么

这次是差异样本，不只记录“最终 PASS”。至少记录：

- 任务类型、检查点数、运行时长、compact/恢复次数。
- 每次 `mc-expert` 的触发原因，以及哪些重复检查点明确跳过陪审。
- 实际发生的漂移苗头、由哪条重锚问题纠正。
- planner 独立发现的问题、REWORK 次数和最终证据。
- 是否出现旧 run、Goal 绑定、预算暂停或人工门恢复问题。
- 哪些字段有用、哪些只是增加读取负担。

第二次仍顺利，不等于立即把模板全量固化进 skill；应先比较两个任务的共同机制和差异，再决定是否升级母本。

---

## 8. 边界

- 本指南不修改 double-coder、double-planner 或公共 protocol。
- `temp.md` 是本次任务的冻结输入与运行时接力槽，不是普通草稿缓存；开工后只由协议路径消费。
- 状态文件保存业务现场，但 Codex Goal/Claude loop 还保存调度绑定；恢复必须回原 session，并先读 live skill/protocol 后对账。
- planner 是真实性证据门，不意味着所有项目都必须增加更多 reviewer；double-workflow 已有 planner 时，不再自动加第二轮独立 reviewer。
- `mc-expert` 是岔路口顾问，不是每检查点打卡项；频率由新颖性、风险、失败和低置信决定。
- 如果第二次任务的目标持续演化或结果不可客观取证，应换工作流或先收敛任务，不要靠加更多文件掩盖不适配。

