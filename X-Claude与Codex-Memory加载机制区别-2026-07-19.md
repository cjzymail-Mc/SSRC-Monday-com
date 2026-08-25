# Claude 与 Codex Memory 加载机制区别

> 初稿日期：2026-07-19  
> 最近复核：2026-08-24（按 OpenAI / Anthropic 最新官方文档及当前 Flowboard 工作区复核）  
> 性质：冷启动自足的专题说明；区分官方机制、当前 Flowboard 事实与 Mc-emoji 历史案例。  
> 适用范围：Claude Code 与本机 Codex CLI / TUI。产品仍在快速演进，涉及默认行为时应重新核对文末官方来源。

---

## 更新历史

- **2026-08-24**：官方机制复核仍成立；纠正“当前 repo 自动走 `AGENTS.md → Claude memory`”的过期表述。当前 Flowboard 根 `AGENTS.md` 只存宪法，不含 memory 冷启动指针；repo 内 `.claude/memory/`、`.claude/auto-memory/` 是项目知识目录，不因路径名自动等于 Claude 原生 auto memory。同步更新 Claude 的 `/context` 实载核验口径与 auto memory 四类内容边界；Mc-emoji Plan16 / feature06–07 内容降级为外部历史案例，并补录本机 Codex/Claude 版本与 Memories 实际开关状态。
- **2026-07-21**：feature07 plan03 补录 S-002 / S-003，继续观察，hook 暂不配置（Mc-emoji 历史记录）。

---

## 0. 结论先行

Claude Code 和 Codex 都有“跨会话记住信息”的能力，但不能把它们想成同一套 memory 系统。

最准确的短结论是：

> **Claude Code 原生加载 `CLAUDE.md` 与其原生 auto memory 索引，再按需读取主题正文。Codex 原生加载 `AGENTS.md` 指令链，并可选使用一套独立的 local Memories。两端都不会仅凭目录名自动把对方的 memory 纳入上下文；普通 Markdown 仍可在任务、skill、profile 或明确指针要求时由 agent 按需读取。当前 Flowboard 没有配置 `AGENTS.md → Claude memory` 冷启动链。**

因此：

- “Claude memory 是 harness（宿主执行层）自动加载的”——方向正确；
- “不得不看 / 不得不读”——只适合通俗描述“内容已被宿主注入模型上下文”，不代表模型必然遵守；
- “Codex 完全读不到 Claude memory 文件”——能力层面不成立；Codex 可像读取其他工作区文件一样按需读取。2026-07-19 Mc-emoji 三路实测还证明了显式指针链可工作，但该证据不等于当前 Flowboard 已配置同一链路；
- “Codex 已原生获得与 Claude 完全相同的 memory harness”——不成立；
- “Codex 必须建设复杂的新数据库或 runtime 才能使用 Claude memory”——也不成立；显式按需读取、skill 或薄路由已经能覆盖许多场景；
- 当前诚实定级分三层：**官方原生机制 = 已确认；Mc-emoji 2026-07-19 薄指针实验 = 历史 `PARTIAL`；当前 Flowboard 的 Claude memory 自动跨读 = `NOT_CONFIGURED`（未配置，不等于故障）。**

---

## 1. 先统一几个词

### 1.1 Memory

本文的 memory 泛指跨会话保留、在未来任务中重新使用的规则、经验和工作背景。它至少包括三种不同东西：

1. **持久指令**：如 Claude 的 `CLAUDE.md`、Codex 的 `AGENTS.md`；
2. **经验记忆**：如 Claude auto memory、Codex local Memories；
3. **项目自建知识库**：如本 repo 的 `.claude/memory/`、`.claude/auto-memory/` 与主题正文。它们是否自动加载取决于宿主原生位置、导入或显式路由，不能只看目录名。

这三者的加载时机、控制权和可靠性不同，不能混称“系统会自动记住”。

### 1.2 Harness（宿主执行层）

本文用 harness 指 Claude Code 或 Codex 客户端在模型调用之外负责的确定性工作，例如：

- 发现约定文件；
- 按作用域和优先级拼接内容；
- 把内容送进模型上下文；
- 运行 hooks（钩子）；
- 管理本地 memory 文件与开关。

它与语言模型的区别是：

```text
harness 决定“哪些内容进入上下文”
模型决定“如何理解、是否正确执行这些内容”
```

所以“宿主自动加载”比“提示模型自己记得去搜文件”更可靠，但仍不等于规则被机器强制执行。真正需要机械强制的安全规则应放 sandbox、permission、hook 或 validator，而不是只写在 memory 里。

### 1.3 分层加载

分层加载不是“把所有 memory 全塞进上下文”。理想结构是：

```text
常驻入口 / 薄索引
  → 根据当前任务识别相关主题
  → 按需打开少量主题正文
```

这样既能提高召回率，又避免几十条长经验持续占满上下文。

---

## 2. Claude Code 的原生加载机制

### 2.1 两条互补的官方 memory 通道

Claude Code 官方把跨会话知识分成两类：

| 通道 | 谁写 | 典型内容 | 启动行为 |
|---|---|---|---|
| `CLAUDE.md` / `CLAUDE.local.md` / `.claude/rules/` | 用户或团队 | 必须长期携带的项目规则、命令、架构与工作约定 | 宿主按目录与作用域发现并装入上下文 |
| Auto memory | Claude | 用户偏好、用户纠正、不可从代码推导的项目背景、外部参考 | 每次会话加载 `MEMORY.md` 的前 200 行或 25KB，主题正文按需读取 |

Claude 官方明确说：两者都会在每次 conversation（会话）开始时加载（auto memory 关闭时除外）；但它们是 context（上下文），不是 enforced configuration（强制配置）。

### 2.2 `CLAUDE.md` 的层级发现

Claude Code 会从当前工作目录向上发现 `CLAUDE.md` 与 `CLAUDE.local.md`，把发现的内容拼进上下文。越靠近当前工作目录的内容越晚出现。子目录下的 `CLAUDE.md` 不一定在启动时全量加载，而是在 Claude 读取该子目录文件时进入上下文。

此外：

- `CLAUDE.md` 可用 `@path` 导入其他文件；
- 根级 `CLAUDE.md` 在 `/compact` 后会重新读取并注入；
- `/memory` 用于浏览/编辑 memory 位置与切换 auto memory；要确认当前会话**实际加载**了哪些文件，使用 `/context`；
- 可用 `InstructionsLoaded` hook 调试具体加载来源和原因。

### 2.3 Auto memory 的“索引常驻、正文按需”

Claude auto memory 的默认项目位置是：

```text
~/.claude/projects/<project>/memory/
```

其中：

- `MEMORY.md` 是启动层索引与精简摘要；
- 启动时只加载其前 200 行或 25KB，取先达到者；
- `user_role.md`、`feedback_*.md` 等主题文件不会全部在启动时进入上下文；当前格式可用 frontmatter 的 `type` 区分 `user / feedback / project / reference`；
- Claude 在任务需要时通过普通文件工具读取相关主题正文；
- Claude 可在会话中写回 memory；auto memory 默认开启，但可关闭。
- Claude 当前会跳过能从代码库直接推导的架构、文件路径、调试修复，以及 `CLAUDE.md` 已经声明的内容；
- 主会话的 auto memory 不自动传给普通 subagent，fork 继承父上下文；subagent 自有 memory 是另一目录。

这就是本讨论中“Claude 原生分层加载”的核心：

```text
Claude harness
  → 启动自动注入 MEMORY.md 薄索引
  → 模型根据任务线索选择主题
  → 文件工具按需读取正文
```

### 2.4 “不得不读”到底是什么意思

通俗说，Claude 在启动时“绕不开”被装入上下文的索引：不是等模型临时想起来再去找，宿主已经把它送进请求。

但严格说法应是：

> **宿主保证送达上下文，不保证模型百分之百正确理解或执行。**

因此：

- 关键规则应短、明确、无冲突；
- 多步骤流程更适合 skill；
- 路径专属规则更适合 `.claude/rules/`；
- 真正不可违反的操作边界还要靠 permission / sandbox / hook。

---

## 3. Codex 的原生机制

### 3.1 Codex 原生稳定加载的是 `AGENTS.md` 指令链

OpenAI 官方说明，Codex 在每个 run（运行；TUI 通常是一轮新 session）开始时构造 instruction chain（指令链）：

1. 先读 Codex home 下的 `AGENTS.override.md`，没有则读 `AGENTS.md`；
2. 再从项目根走到当前工作目录；
3. 每层优先 `AGENTS.override.md`，其次 `AGENTS.md`，再其次配置的 fallback 文件名；
4. 从根到当前目录依次拼接，越靠近当前目录的内容越晚出现；
5. 默认累计上限由 `project_doc_max_bytes` 控制，官方当前默认 32KiB；
6. 每次新 run 重建指令链，不需要手工清缓存。

这部分是 Codex 自带的 harness 行为。最适合放“每次必须带入”的仓库规则、验证命令、范围与审查要求。

### 3.2 `AGENTS.md` 不会天然递归加载任意 memory 目录

Codex 官方 instruction discovery 只自动识别规定的 `AGENTS.md` / override / fallback 链。普通的：

```text
.claude/auto-memory/MEMORY.md
.claude/auto-memory/*.md
```

不会因为它们存在就自动成为 Codex 的项目 memory。要让 Codex使用它们，至少需要一条入口指令告诉它：

```text
启动时读 MEMORY.md 索引
→ 只打开与当前任务相关的主题正文
```

这仍然比原生注入弱一层：`AGENTS.md` 的送达由 harness 保证，但继续读取 `MEMORY.md` 与主题正文属于 agent 执行指令的工具行为。

### 3.3 Codex 也有自己的 Local Memories，但不是 Claude memory

OpenAI 当前官方文档显示，Codex 有独立的本地 Memories 功能：

- 默认关闭；
- 可通过 `[features] memories = true` 开启；
- 使用独立的 `~/.codex/memories/` generated state（生成态）；
- 可从符合条件的旧 chats 生成本地 memory；
- 可控制未来 chats 是否使用已有 memory、是否贡献新 memory；
- 官方建议把“必须始终生效”的团队规则放 `AGENTS.md` 或受版本控制的文档，不要只依赖 memories；
- 官方不建议把手工编辑生成文件作为主要控制面。

因此必须区分：

```text
Codex local Memories
≠ Claude auto memory
≠ 本 repo 的 .codex/memory-inbox
```

本 repo 的 `.codex/memory-inbox/` 是项目自建的“Codex 新知识待 Claude 审核”协议，不是 OpenAI 原生 Memories 目录。

**本机现状（2026-08-24）**：Codex CLI 为 `0.149.1`；`~/.codex/config.toml` 未配置
`[features] memories = true`，`~/.codex/memories/` 也不存在，因此当前本机 local Memories 仍处于关闭/未初始化状态。
这只是本机配置事实，不改变 Codex 产品已支持 local Memories 的结论。

### 3.4 Codex hooks 能补强，但不应默认上复杂方案

Codex 支持 `SessionStart` hook。该 hook 可以在 `startup / resume / clear / compact` 时运行脚本，并把 stdout 或 `additionalContext` 加进 developer context（开发者上下文）。所以理论上可以做：

```text
SessionStart hook
  → 读取或生成 memory 路由提示
  → 注入 developer context
```

但它会带来额外工程边界：

- repo hook 需要 trusted project；
- 非托管 hook 需要按当前定义 hash 审核信任；
- 多个匹配 hook 会并发启动；
- hook 必须幂等；
- 单条模型可见输出约 2,500 tokens，超长会截断并落临时文件；
- hook 注入索引不等于主题正文已被正确读取；
- 仍需阳性 / 阴性对照证明真实生效。

所以“Codex 想做得像 Claude，必须依赖更复杂额外工具”只对一半：

- 若目标是**与 Claude harness 尽量同形、自动注入更多上下文**，确实可能需要 hook、路由脚本、原生 Memories 等额外机制；
- 若目标只是**在真实任务里可靠找到相关 Claude 经验**，可以先用 `AGENTS.md → MEMORY.md → 主题正文` 的薄指针，不应直接建设数据库、daemon（常驻进程）、统一 runtime 或迁移系统。

---

## 4. 二者的核心差异对照

| 维度 | Claude Code | Codex |
|---|---|---|
| 原生持久指令入口 | `CLAUDE.md`、`CLAUDE.local.md`、`.claude/rules/` | `AGENTS.md`、`AGENTS.override.md`、fallback 文件 |
| 原生经验 memory | Claude auto memory | Codex local Memories（独立系统、默认关闭） |
| Claude auto-memory 索引 | 启动原生加载 `MEMORY.md` 前 200 行或 25KB | 不天然识别；需 `AGENTS.md` 指针或其他机制 |
| 主题正文 | 需要时按需读取 | 需要时按需读取；若使用 Claude memory，入口是项目自建 |
| “送达模型”强度 | `CLAUDE.md` 与 auto-memory 索引由 Claude harness 自动送达 | `AGENTS.md` 由 Codex harness 自动送达；后续 Claude memory 读取依赖 agent 执行 |
| 是否保证遵守 | 否，仍是上下文 | 否，仍是上下文 |
| 原生存储位置 | `~/.claude/projects/<project>/memory/` | `~/.codex/memories/` |
| 本 repo 项目知识源 | `.claude/auto-memory` / `.claude/memory`（项目约定；不自动等同原生 auto memory） | 可按需读取共享源；新知识先进 `.codex/memory-inbox/` |
| 可选补强 | rules、imports、InstructionsLoaded hook | `SessionStart` hook、原生 Memories、路由脚本 |
| 当前 Flowboard 定级 | 官方机制已确认；repo 内知识目录不是原生加载位置 | 根 `AGENTS.md` 不含跨读指针；Claude memory 自动跨读为 `NOT_CONFIGURED`；local Memories 当前关闭 |

---

## 5. 当前 Flowboard 实际架构与历史案例

### 5.1 当前 Flowboard（2026-08-24）

当前仓库的真实链路是：

```text
Codex harness 自动加载根 AGENTS.md（仓库宪法）
  → 不自动读取 repo 内 .claude/memory 或 .claude/auto-memory
  → 任务、skill、profile 或用户明确要求时，agent 才按需读取相关索引/正文
  → STATE.md 也只在任务需要项目现状时读取
```

核对事实：

- 根 `AGENTS.md` 已于 2026-08-24 精简为宪法层，只声明 memory 的分层与审核边界，不包含冷启动读取清单；
- 当前 repo 没有 `.claude/CLAUDE.md`；
- 默认 Claude 项目 auto-memory 路径 `~/.claude/projects/<本 repo>/memory/` 当前不存在；
- repo 内 `.claude/memory/` 与 `.claude/auto-memory/` 是普通、受版本控制的项目知识目录；没有导入或原生路径映射时，不会被 Claude/Codex 仅凭目录名自动注入；
- 本机 Codex local Memories 未启用，当前 repo 也没有 active `SessionStart` hook。

因此，当前 Flowboard 不再使用旧文所述的“每次启动固定读取两层 memory”机制。需要共享经验时按任务相关性显式读取；必须始终成立的团队规则继续留在 `AGENTS.md` 或受版本控制的契约文档。

### 5.2 Mc-emoji Plan16 Wave 0（历史案例，不是当前 repo 证据）

2026-07-19，另一个 Mc-emoji 仓库曾用显式 `AGENTS.md` 指针做 Blind / Negative / Positive 三路隔离对照，工具轨迹显示 Codex 按顺序打开了 `AGENTS.md`、项目 `CLAUDE.md`、memory 索引、相关主题正文与 `STATE.md`，三路均 PASS。

该案例仍能证明：**Codex 可以执行一个明确的项目路由，从普通 Markdown 索引继续读取相关正文。** 但它不能证明当前 Flowboard 已配置同一链路，也不能证明所有 memory、模型、账号和 surface 都稳定召回。原始结论只能保留为历史 `PARTIAL`，不能再写成“本 repo 当前架构”。

### 5.3 当前分层定级

| 层级 | 当前结论 |
|---|---|
| Claude / Codex 官方原生机制 | 已由当前官方文档确认 |
| Mc-emoji 显式薄指针 | 2026-07-19 历史 `PARTIAL`，证明机制可行但不具普遍性 |
| Flowboard 自动跨读 Claude 项目知识 | `NOT_CONFIGURED`，不是失败，也没有当前动态 PASS |
| Flowboard 按任务显式读取 | 可用；本次核对已实际读取 `.claude/*/MEMORY.md` |

---

## 6. 写回机制也不同

### 6.1 Claude

Claude auto memory 可以在会话中自行读写项目 memory，并维护 `MEMORY.md` 与主题正文。项目另有 `$mc-update` 人工审核流程，用于把高价值经验更审慎地固化。

### 6.2 Codex

本 repo 不允许 Codex 直接写 Claude 正式 memory。新知识采用：

```text
Codex 发现可固化经验
  → 写 .codex/memory-inbox/ proposal
  → Claude / $mc-update 审核、去重、裁定
  → accepted 后进入正式 memory 或其他合适落点
```

这不是能力不足导致的临时绕路，而是项目的知识治理边界：

- 正式知识只保留一份；
- 避免两个平台同时改索引造成冲突；
- 让经验通过频次、去重、适用性和人工审核门；
- 记录 producer platform，防止把 Codex-only 事实误写成 shared。

截至 2026-08-24，当前 Flowboard 的 `.codex/memory-inbox/` 已有 schema v2 协议与两份
`proposed / pending` 提案，但尚未标记为 accepted/applied。它证明提案入口已经落地，**不证明当前仓库已完成一次正式消费**；
Mc-emoji 在 2026-07-19 的 `$mc-update` 消费记录只保留为外部历史证据。

---

## 7. 什么时候需要额外工具

### 7.1 当前不需要扩建的情况

当前 Flowboard 没有“每次 Codex 启动都必须消费 Claude 项目知识”的需求。满足以下条件时，保持按需读取即可：

- 硬规则已经留在 `AGENTS.md` 或冻结契约，不依赖 memory 才成立；
- 任务或专家 profile 能在需要时明确指向相关索引/正文；
- 偶发漏召回可由显式提示、skill 或 inbox 兜底；
- 没有重复出现的稳定故障。

此时不要为了架构对称新增：

- Codex 专属 memory 数据库；
- 常驻 daemon；
- 跨平台统一 runtime；
- 全量 memory 注入；
- 复杂自动分类器；
- 仅为证明理论完整性的 hook。

### 7.2 可以重启评估的真实触发器

只有出现以下真实痛点时，再评估补强：

1. 多次任务明确要求读取同一项目知识，Codex 仍稳定漏读相关索引或正文；
2. 不同账号 / 模型 / surface 对同一显式路由表现显著不一致；
3. `/compact`、resume 或切换工作目录后稳定丢失已经明确建立的路由；
4. memory 规模扩大后，索引路由频繁选错；
5. 需要在无模型自主性的前提下机械保证某段上下文被注入。

候选补强顺序应从小到大：

```text
先把硬规则放回 AGENTS.md / 受版本控制契约
→ 把重复流程做成 skill 或明确的任务入口
→ 增加真实任务 fixture
→ 必要时加轻量 resolver
→ 再考虑 SessionStart hook
→ 仅为 Codex 自身跨会话召回时，单独评估 local Memories
```

每次只解决已复现问题，并用盲测 + 负对照 + 正对照验收。

---

## 8. 常见误区

### 误区 1：Claude 自动加载，所以 Claude 一定遵守

错误。自动加载只保证进入上下文，不保证模型百分之百执行。机械红线要靠 hook、permission、sandbox 或 validator。

### 误区 2：Codex 没有 Claude harness，所以完全不能分层使用 Claude memory

错误。Codex 可以按任务或显式路由读取普通 Markdown 索引与正文；Mc-emoji 历史实验已证明这条路径可行。
但当前 Flowboard 没有自动薄指针，不能把历史实验写成当前冷启动保证。

### 误区 3：Codex local Memories 等于 `.claude/auto-memory`

错误。两者是不同产品、不同目录、不同生成与控制机制。

### 误区 4：把 `.claude/auto-memory` 路径写进 `AGENTS.md` 就等于原生注入

不等于。`AGENTS.md` 是原生注入，后续 `Get-Content MEMORY.md / 正文` 是 agent 执行指令。两层证据要分开。

### 误区 5：只要上 `SessionStart` hook，就能完全复制 Claude auto memory

错误。hook 只能注入上下文或路由提示，还要处理 trust、幂等、输出上限、主题选择和真实消费验证。

### 误区 6：为了稳定，就该全量加载全部正文

错误。全量注入会浪费上下文并稀释关键规则。正确方向是薄索引 + 任务相关正文。

### 误区 7：单点实测 PASS 等于所有 surface 都稳定

错误。Mc-emoji 当时只有 1 条 memory × 1 模型 × 1 账号 × 1 次三路对照，故历史定级只能是 `PARTIAL`；
当前 Flowboard 则是 `NOT_CONFIGURED`，两者不能混用。

### 误区 8：repo 里叫 `.claude/auto-memory/` 的目录就是 Claude 原生 auto memory

错误。Claude 原生项目 auto memory 默认位于 `~/.claude/projects/<project>/memory/`。repo 内同名或近似命名目录只是普通项目文件，除非被 `CLAUDE.md` 导入、映射到原生位置，或由任务显式读取。

---

## 9. 冷启动操作指南

### 9.1 Claude 新会话

1. 用 `/context` 确认当前会话实际加载的 `CLAUDE.md`、rules 与 auto memory；`/memory` 用于浏览/编辑位置与切换开关；
2. 只有 `/context` 显示进入当前上下文的原生 auto memory 才能视为启动已加载；不要把 repo 内 `.claude/auto-memory/` 的路径名当作加载证据；
3. 碰到项目知识任务时，按显式入口打开 repo 内相关索引与主题正文；
4. 必须机械执行的规则不要只放 memory；
5. 新经验按项目 `$mc-update` / auto-memory 纪律固化。

### 9.2 Codex 新 run

1. 从 repo 根启动；
2. 根 `AGENTS.md` 由 Codex harness 自动注入；只有排查 discovery 时才需要人工核验来源，不必把“再读一遍文件”当作正常启动步骤；
3. 当前任务需要项目现状时读 `STATE.md`，需要历史经验或专家 profile 时再读相关 `.claude/*/MEMORY.md` 与主题正文；
4. 不默认读取不存在的 `.claude/CLAUDE.md`，也不假设 repo 内 `.claude/auto-memory/` 已被原生注入；
5. 若启用 Codex local Memories，用 `/memories` 分别控制本 chat 是否使用旧 memory、是否贡献新 memory；
6. 新 Codex 知识写 `.codex/memory-inbox/`，不直写 Claude 正式 memory；
7. 若怀疑漏载，检查 active instruction sources 与 session 工具轨迹，不凭最终回答猜测。

### 9.3 验证一个 memory 是否真的被加载

不要只问常识题。使用三路对照：

```text
盲测：有项目入口，但 prompt 不泄露正文文件名
负对照：隔离空目录，无项目入口
正对照：显式注入目标 memory
```

最强证据顺序：

1. session 工具轨迹显示打开了具体正文；
2. 回答能说出项目私有正文文件名或私有哨兵；
3. 负对照无法命中该私有指纹；
4. 正对照可以命中。

只答对一般技术事实不够，因为模型可能从训练知识、本机二进制、旧 session 或网络资料得出答案。

---

## 10. 历史附录：Mc-emoji 聊天定位与项目证据

> ⚠️ 本节记录的是 Mc-emoji / feature06–07 在 2026-07-19～21 的历史证据。所列 feature 目录与
> `.claude/CLAUDE.md` 不存在于当前 Flowboard 仓库，不得据此推断当前启动链、任务状态或授权边界。

### 10.1 原始聊天

相关讨论位于 Codex session：

```text
C:\Users\xy198\.codex\sessions\2026\07\18\
rollout-2026-07-18T21-20-31-019f7562-b581-77c2-989f-5c92db173d75.jsonl
```

关键消息约在北京时间 2026-07-18 22:05—22:14，对应 JSONL 第 120、133、159 行附近。核心原话包括：

> Claude 写在 `.claude/auto-memory`、项目规则和 skill 文档里的经验，Codex可以读取并参考。但不会像 Claude 那样自动加载全部相关经验；Codex 需要按索引主动打开。

> Codex 每次启动可靠读取 `AGENTS.md`、Memory 索引和当前状态。根据任务类型，自动打开相关的 Claude memory，而不是把全部 memory 塞进上下文。

> 目标不是复制 Claude 的整套 memory 内部机制，而是：Codex 在实际工作中，能够自动找到并使用正确的 Claude 经验。

注意：“不得不看 / 不得不读”“必须依赖更复杂的额外工具”是对讨论的通俗概括，不是该 session 中找到的逐字原话。

### 10.2 Mc-emoji 当时的权威与实测入口（当前 repo 不可用）

- `[feature-06-codex-workshop]/main-plan.md`：feature06 Constitution 与 T4 边界（v1 + rev1 + rev2）；
- `[feature-06-codex-workshop]/plan16-T4-codex-memory-closure.md`：读写两半、R1/R2 候选及停止条件；
- `[feature-06-codex-workshop]/plan16-T4-session交接.md`：Wave 0/2 后的 session 交接锚点；
- `[feature-06-codex-workshop]/output/plan16-t4-memory/wave0-read-positive-control.md`：三路原始实测汇总；
- `[feature-06-codex-workshop]/output/plan16-t4-memory/wave2-run-log.md`：写半边 inbox lane 落地 run 日志；
- `[feature-06-codex-workshop]/output/plan16-t4-memory/wave0-harness.ps1`：可复跑 harness；
- `AGENTS.md`：Mc-emoji 当时的 Codex 启动链与 memory-inbox 硬边界；
- `.claude/auto-memory/MEMORY.md`：Claude memory 薄索引；
- `.codex/memory-inbox/inbox-protocol.md`：Codex 新知识写回协议。

### 10.3 main-plan 在 Wave 0 之后的演进（2026-07-19 同日）

本文件 §5.2 引用的 Wave 0 结论是阶段性快照。Wave 0 出结果当天，main-plan 连续两次据实修订（均为事实性修订，未动 §4 禁区 / §3 真相源 / 终态结构，非 Constitution 重签）：

- **rev1**：§5.1 + §1 T4 表据 Wave 0 实测修正——memory 条数 38→**37**（实测 grep 纠正）；「Codex 完全读不到」被证伪，改为「读半边 PARTIAL（单点）+ 写半边未闭环」。
- **rev2**：Plan16 Wave 2 写半边落地（`/mc-update` inbox lane，候选 D）后，§1 T4 表从「读半边 PARTIAL」→ **「T4 PASS（机制层）」**。用户裁定 A：接受「机制层 PASS」为 T4 闭口（用 fixture 不碰 7 条真 proposed，首次真消费是日常 `/mc-update` 自然发生）。

→ 截至 2026-07-19，**feature06 终态 T2/T3/T4 已全部闭口，仅剩 T1**（补 `$reflect` Codex adapter + 7 skill 各一条阳性 fixture，见 plan17/plan18）。memory 读取这条链「候选 A 够用」由此从「单点 PARTIAL」固化为「T4 闭口依据」，这也是 §12 判定「无新痛点不上 hook」的事实基础。

---

## 11. 官方权威来源

### Anthropic / Claude Code

- [How Claude remembers your project](https://code.claude.com/docs/en/memory)：`CLAUDE.md`、auto memory、加载范围、200 行 / 25KB 索引上限、主题正文按需读取、`/context` 实载核验、`/memory` 管理与 compaction 行为。
- [Explore the context window](https://code.claude.com/docs/en/context-window)：会话开始前进入上下文的 `CLAUDE.md`、auto memory、skills 等内容。

### OpenAI / Codex

- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)：Codex 启动时的全局 / 项目 / 嵌套指令发现链、优先级、32KiB 默认上限与每 run 重建行为。
- [Memories](https://learn.chatgpt.com/docs/customization/memories)：Codex 独立 local Memories、默认关闭、存储位置、生成与使用控制，以及“强制团队规则应放 AGENTS.md”的边界。
- [Hooks](https://learn.chatgpt.com/docs/hooks)：`SessionStart`、trust、并发、模型可见输出上限与 additional context 行为。

### 资料取得说明

- 2026-08-24 通过当前官方页面重新核对：Codex `AGENTS.md`、Memories、Hooks 三页与 Claude Code memory 页均可直接取得；上述官方机制仍成立；
- 本机核对版本为 Codex CLI `0.149.1`、Claude Code `2.1.215`；Flowboard 当前未启用 Codex local Memories，也没有 repo-local `SessionStart` hook；
- 2026-07-19 尝试通过 OpenAI Codex manual helper 获取当前 manual，因代理对 `developers.openai.com/codex/codex-manual.md` 的 HEAD 请求返回 HTTP 403 未成功；
- 随后按 `openai-docs` 技能规定，改用 OpenAI Developer Docs MCP 直接获取上述三个官方页面正文；
- Claude 机制通过 Anthropic 官方 `code.claude.com` 页面核对；
- Mc-emoji 历史结论受当时 Plan16 三路实测约束；Flowboard 当前结论以 2026-08-24 的仓库与本机核对为准。官方能力、本机配置和跨 repo 历史案例分开标注，不互相替代。

---

## 12. 历史附录：Codex memory hook 是否超出 Mc-emoji feature06 范围

> 本节回答一个高频问题：「为了让 Codex 像 Claude harness 一样自动加载 memory，上 Codex `SessionStart` hook——这算不算超出 feature06 main-plan §4 禁区？」
> 判定方式：逐条对照 main-plan §4 禁区原文 + §5 T4 边界（2026-07-19 核对 main-plan v1 + rev1/rev2）。
> **适用性注记（2026-08-24）**：这是 Mc-emoji 已封计划的历史范围裁定，不是当前 Flowboard 的授权依据。Flowboard 若未来需要 hook，必须以届时用户指令、当前 `AGENTS.md` 与独立方案重新判断。

### 12.1 逐条对照 §4 禁区

| main-plan §4 禁区 | Codex memory hook 撞不撞 | 判定 |
|---|---|---|
| ① deterministic runtime（mode gate / failcount journal / halt ledger） | 不撞——SessionStart hook 只注入上下文，不做计数/熔断 | — |
| ② promotion tool / apply transaction | 不撞——注入不等于 memory 晋升事务 | — |
| ③ `.ai/knowledge/` 知识治理系统 | 不撞 | — |
| ④ hook shared core（双端 hook 注册壳抽共享判定） | **部分相关**——单端 Codex `SessionStart` hook 本身**不是**「双端 shared core」；但 §4 第 4 条的精神是「只在真实重复同步痛点时才抽 hook 共享」。且 §4 安全例外只对 delete/overwrite guard 放宽，**memory 注入 hook 不享安全例外** | ⚠️ 不直接撞第 4 条字面，但落在其约束范围内 |
| ⑤ 跨 repo 产品化 / marketplace | 不撞 | — |
| ⑥ Scheduled / 崩溃恢复 / 网络中断同-run 恢复 | 不撞——SessionStart 是会话级一次性，不是后台定时 | — |

### 12.2 但撞了 main-plan 的「已封决策」边界（这才是真红线）

- main-plan **§5.2** 把 Codex 启动钩子列为 **T4 memory 闭环的候选机制 B**，并明文「由专门 sub-plan 实测」。
- Plan16 Wave 0（2026-07-19）实测选的是**候选 A**（`AGENTS.md` 指针），三路对照 PASS、定级 PARTIAL。
- main-plan **rev1**（2026-07-19）据此把 §5.1 从「Codex 完全读不到」改为「读半边 PARTIAL」；**rev2** 同日确认 T4 在机制层闭口、**接受候选 A 够用**。

→ **现在再上 hook = 在没有新痛点的前提下，推翻 Wave 0 已封的「候选 A 足够」结论**。这撞：
- main-plan §4.1「触碰禁区 = 命中即停（4 红线第 4 条：推翻已封决策）」；
- §7.3 反「为理论完整性建 hook / runtime」（「留给后续 plan 实现」类措辞 = 命中即停）；
- AGENTS.md memory 边界「memory follows the repo」「新 Codex 知识必须经 `.codex/memory-inbox`」——hook 注入若绕过这条协议直写，也越界。

### 12.3 三层精确结论

1. **不是绝对禁区**：§4 第 4 条禁的是「双端 hook shared core」，不是「单端 Codex SessionStart hook 本身」。memory 注入 hook 在文字上没被判死刑。
2. **当前禁止做**：因为 Wave 0 已实证候选 A 够用、定级 PARTIAL；无真实痛点就上 hook = 撞 §4 第 4 条精神 + §7.3 反过度工程 + 推翻已封决策。
3. **重启条件**（满足才可走专门 sub-plan + 用户批准 + 三路对照验收）：
   - 多次新 Codex session 读了 `AGENTS.md` 仍不读 `MEMORY.md`；
   - 不同账号 / 模型 / surface 对同一启动链表现显著不一致；
   - `/compact` / resume / 切工作目录后稳定丢入口；
   - memory 规模扩大后索引路由频繁选错；
   - 需要在无模型自主性的前提下机械保证某段上下文被注入。

### 12.4 一句话裁定

> **Mc-emoji 当时的裁定是：Codex memory hook 不超「绝对禁区」，但超「已封决策的边界」；除非有 §12.3 真实痛点 + 新 sub-plan + 用户显式批准 + 三路对照验收，否则不动 hook。该仓库当时继续使用 `AGENTS.md` 薄指针。此裁定不自动适用于当前 Flowboard。**

---

## 13. 最终裁定卡

以后再讨论这个主题，默认采用以下口径：

```text
Claude：
  原生 harness 自动加载 CLAUDE.md + auto-memory 薄索引；
  主题正文按需读取；送达上下文 ≠ 强制遵守。

Codex：
  原生 harness 自动加载 AGENTS.md 指令链；
  原生 local Memories 是另一套、默认关闭的系统；
  不天然加载 Claude auto-memory。

Flowboard（2026-08-24）：
  根 AGENTS.md 只存宪法，不含 Claude memory 冷启动指针；
  repo 内 .claude/memory 与 .claude/auto-memory 是项目知识目录，按任务读取；
  本机 Codex local Memories 未启用，repo-local SessionStart hook 未配置；
  新 Codex 知识经 .codex/memory-inbox → $mc-update 审核后固化。

Mc-emoji 历史案例：
  2026-07-19 显式 AGENTS.md 薄指针三路单点实测成立；
  只保留为历史 PARTIAL，不外推为 Flowboard 当前机制或产品普遍保证。
```

---

## 14. 历史附录：2026-07-21 Mc-emoji plan03 多信号观察

> 本节保留当时信号台账供追溯；当前 Flowboard 不存在所述 feature07 plan03，不能把 `WAIT_SIGNAL` 或其候选修复视为本仓库现状。

### 14.1 本次完成内容

feature07 plan03 继续承担 Codex memory 路由的观察台账。本轮没有修改正式 Memory、skill、reviewer、settings、hook 或中央 KB，只完成以下 repo-local 记录：

1. 在 `[feature-07-codex-workshop-Adv]/plan03-Codex-memory路由信号观察与升级门.md` 补录 S-002 / S-003；
2. 在 plan03 §2 问题模型新增一层：`.agents/` runtime binding 是否可发现并在动作前激活；
3. 同步更新 `STATE.md` 的活跃 plan 摘要、变更日志和更新时间；
4. plan03 状态继续保持 `WAIT_SIGNAL`，没有把“信号数量增加”自动解释成施工授权。

当前台账：

| 信号 | 状态 | 定性 |
|---|---|---|
| S-001 · skill-bound proposal 错路由到中央 KB 直接修改 | `CONFIRMED_SINGLE_SAMPLE` | 已读索引但没激活 junction / KB 正文，主 agent 与 mc-expert 都给出错误写入入口 |
| S-002 · `$free` discovery 表面与磁盘实际不一致 | `REPORTED` | skill discovery 与 memory 动作激活的混合型信号；尚未独立复现 |
| S-003 · 调用 mc-expert 前未激活 runtime binding 与路由记忆 | `REPORTED` | 第二次清晰路由复发；与 S-002 来自同一连续会话，尚非跨 session 复现 |

### 14.2 当前问题已经从“加载没加载”细分为六层

```text
AGENTS.md 是否由 harness 加载
  → MEMORY.md 索引是否被读取
  → 相关 memory 正文是否按任务语义激活
  → `.agents/` runtime binding 是否在动作前激活
  → adapter 是否把知识边界落实成硬门
  → reviewer 是否收到同一边界且不扩大权限
```

S-001 和 S-003 主要落在“正文 / runtime binding 未在动作前激活，导致路由选错”；S-002 还混有 skill discovery 表面与磁盘实际不一致。它们不能被笼统写成“Codex 完全没有加载 memory”。

### 14.3 为什么现在仍不配置 hook

当前多条信号说明“无任何真实痛点”的旧状态已经结束，但尚不能证明全局 memory 加载层失效：

- S-001 / S-003 的主要问题是任务路由和 runtime binding 激活，不是 `AGENTS.md` 或 `MEMORY.md` 完全没读；
- S-002 是混合型，尚未确认是系统性 discovery 缺陷还是单次 surface 差异；
- S-002 / S-003 都是会话自报，尚缺跨 session、跨模型或跨 surface 的独立复现；
- 更窄的候选修复仍存在：adapter 源归属硬门、reviewer 调用合同、索引触发词和 runtime binding 冷启动入口；
- hook 只能增强机械注入，不能自动保证模型选择了正确正文，也不能替代 adapter 的确定性硬门。

因此当前裁决保持：

> **继续观察并记录信号；plan03 保持 `WAIT_SIGNAL`；memory-load hook 继续 `NO-GO`。**

### 14.4 继续观察哪些信号

后续重点记录以下证据，并区分事实、假设与是否独立复现：

1. **跨 session 复发**：新 Codex session 已读启动链，仍在相似任务中不打开相关 memory 正文或 runtime binding；
2. **跨模型 / 账号 / surface 不一致**：同一 repo、同一任务，在不同模型、账号、TUI / App / CLI 上出现稳定差异；
3. **compact / resume 丢入口**：压缩、恢复或切换工作目录后，之前已激活的知识边界稳定丢失；
4. **索引规模导致频繁选错**：memory 增长后，多次选择错误正文或漏掉明确相关正文；
5. **skill discovery 冲突复现**：Available skills 清单与实际 user-scope adapter 状态再次不一致，并导致错误判断；
6. **runtime binding 重复漏读**：涉及 reviewer、fallback、权限或熔断时，再次未读 `.agents/codex-runtime-bindings.md` 就选择错误路线；
7. **窄修后仍复发**：未来若 adapter 硬门、reviewer 合同或索引触发词已经修复，同型错误仍然出现；
8. **出现机械注入刚需**：某段上下文必须不依赖模型判断而稳定送达，否则会造成确定性错误或安全风险。

每条新信号继续写入 feature07 plan03，并至少记录：session / model / surface、预期、实际、证据路径、是否与既有信号同根、是否独立复现。

### 14.5 什么时候才重新评估并配置 hook

hook 不是按“累计到第 N 条”自动启动。满足以下组合后，才进入专门规划：

1. 出现上节至少一类稳定证据，尤其是跨 session / 模型 / surface 复发、compact / resume 丢入口，或窄修后仍复发；
2. 已确认故障位于“上下文机械送达 / 加载”层，而不是只需 adapter 硬门或调用合同即可解决；
3. 用户明确把 plan03 从 `WAIT_SIGNAL` 切换到 `READY_TO_PLAN`；
4. 新 plan 重新核对当时 Codex 官方 hook 能力、事件名、trust、输出上限和幂等边界；
5. 先做隔离 PoC（概念验证），用盲测 + 负对照 + 正对照证明 hook 真实送达且不会全量灌入无关 memory；
6. 用户再明确批准具体 settings / hook 写入范围，之后才配置 live hook。

在 Mc-emoji 当时的 plan03 条件满足前，路径仍是：

```text
AGENTS.md 薄入口
  → MEMORY.md 索引
  → 任务相关正文 / runtime binding
  → adapter 硬门与 reviewer 合同
  → plan03 持续记录真实信号
```
