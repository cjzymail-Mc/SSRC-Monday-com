# double-workflow 验收侧判据手册（主 Claude 验收 codex 侧产物时）

> 2026-08-05 立。配套 `double-workflow-防漂移补丁指南-2026-08-04.md`（那份管 **coder/planner 接力侧**，
> 本份管 **主 Claude 验收侧**——两条侧各自缺手册，本份补验收侧）。
>
> 立这份的触发事件：2026-08-04 double-workflow 首次验收（复核 codex 侧 `build-pptx-from-template`
> skill 施工），主 Claude 判「达标」，codex 独立 planner 复跑判「部分达标」，抓出主 Claude 漏看的
> D3 假 PASS + D5 hash 范围不达标。根因：验收侧缺独立判据手册，主 Claude 用「报告结论」当标尺、
> 只静态取证、没构造负例真跑。**本份堵这个方法论缺口。**

## 适用边界

- **适用**：主 Claude（或任意验收方）复核 **codex 侧 / 其他 agent 侧**产的 skill/产物/验收报告时，
  如何独立判 done_when 是否真达标。
- **不适用**：coder/planner 接力内部的验收（走防漂移指南）；批量产线五级排程（走 Mc-Expert-repo
  `references/acceptance-ladder.md`）；自动闭环三护栏（走 `decisions/acceptance-guardrails.md`）。

## 三条硬纪律（按优先级）

### 1. 字面判据当标尺，不用「报告结论」当标尺

判每条 done_when 前，**先拎冻结任务的 done_when 原文判据**，不取验收报告的二手结论、不取印象。

- 反例（本次事故）：D3 原文是「缺锚点、**缺槽位**、输出已存在等场景可靠失败」。主 Claude 用
  「验收报告写 D3 PASS + docstring 写了 fail-protect」当标尺 → 判达标。实际代码 `build_pptx.py`
  只对 anchor 做了 abort，**缺槽位仍 save+exit0**。报告/docstring 是二手，代码是一手，标尺用错。
- 正解：done_when 原文 → 逐条映射到代码行为/可跑负例。

### 2. 阳性对照：构造会失败的输入真跑，看到它真失败

字面判据含「可靠失败 / 失败时 X / 缺 Y 时中止」→ **必须构造「缺 Y」的负例真跑一次**，看到它真的
exit≠0/报错。只静态读到「代码里有 abort 路径」**不算**——abort 路径可能没覆盖所有 Y。

- 反例（本次事故）：主 Claude 静态看到 `build_pptx.py:198-201` 有 anchor 的 `missing_anchors → return 1`，
  就判 D3 fail-protect 达标。**没构造缺槽位负例去跑**，所以没发现 slot/image 路径无 fail-protect。
- 正解：D3 要跑 4 个负例——缺锚点 / 缺槽位 / 缺图片 / 输出已存在——**逐个**看到 exit 1。
- 这条已提案进中央 KB reflexes（见 Mc-Expert-repo inbox `proposal-done-when-sign-needs-positive-control.md`），
  与 `feedback_negative_needs_positive_control` 互补。

### 3. 陪审员独立取证，禁喂已采信结论框框

派 mc-expert/reviewer 陪审时，prompt **只给原始证据（文件路径/行号/事件）+ 待判问题**，
**不列「我已确认 X / 已知问题 Y」**。

- 反例（本次事故）：主 Claude 陪审 prompt 列「D5 report.py 悬空、Pillow 冗余」当已知问题 →
  mc-expert 在主 Claude 的框框里判「达标但补接线」，**漏 D3 假 PASS + D5 hash 范围**。
  已采信结论把陪审员压进「校对模式」（共享盲区）。
- 正解：prompt 只写「读 build_pptx.py / report.py，判 D3/D5 是否字面达标，指出任何不符」，
  不预告你已发现什么。
- 例外：用户拍板的边界约束（「不许改母本」）可写进 prompt，但这是**约束**不是**结论**。
- 这条待 /KB-update 判归属（候选见 Mc-Expert-repo inbox `proposal-jury-prompt-no-feeding-conclusions.md`）。

## 验收流程（按这个顺序，别跳）

1. **取标尺**：读冻结任务/plan 的 done_when 原文（逐条），不读验收报告的自评结论。
2. **静态映射**：逐条把 done_when 判据映射到代码行为/产物字段，标出「代码承诺了 X」。
3. **阳性对照（关键）**：凡「可靠失败」类判据，构造负例真跑，看到真失败。**这是静态陪审替代不了的**。
4. **独立陪审**：派 mc-expert，prompt 只给原始证据+待判问题（纪律 3）。
5. **对照差异**：若验收报告/陪审结论与你的独立复跑结果冲突 → **信独立复跑**（一手 > 二手），
   把差异逐条列给用户，不擅自调和。
6. **签注分级**：逐条标三态——
   - **PASS（本 run 独立证据）**：真跑过、看到对。
   - **仅静态推断**：读了代码但没跑负例。**不许冒充 PASS**，必须标「待动态复跑」。
   - **FAIL/BLOCKED**：真跑看到错/阻断。
7. **后置项单列**：live cutover / 视觉层 / 外发合规等「设计边界外的用户决策」单独列，**不冒充达标**。

## 与防漂移指南的分工

| 侧 | 文件 | 管什么 |
|---|---|---|
| coder/planner 接力 | `double-workflow-防漂移补丁指南-2026-08-04.md` | 双角色怎么接力、防漂移、检查点 |
| **主 Claude 验收**（本份） | 本文件 | 验收方怎么独立判 done_when、避假 PASS |

两侧互补：接力侧保证 codex 产对，验收侧保证主 Claude 判对。本次事故是验收侧缺手册导致判松，
不是接力侧没产对（codex 独立 planner 反而判对了）。

## 复盘锚（本次事故教训，下次验收前回看）

- **D3 假 PASS** 漏判根因：静态看到 anchor 有 abort 就判达标，没跑缺槽位负例。→ 纪律 2。
- **D5 hash 范围** 漏判根因：信了 report.py docstring「绑 contract+tool hashes」，没核 report 实际字段
  （只绑 source/output）。→ 纪律 1（字面判据：D5 要 contract+tool hash，docstring 是二手）。
- **陪审漏 D3/D5** 根因：喂了框框。→ 纪律 3。
- **「学习 repo 宽严」不是漏判挡箭牌**：D3 字面违约跟 repo 宽严无关；repo 宽严只影响「要不要现在修」，
  不影响「达不达标」的判定。

## 成功标准

- 下次主 Claude 验收 codex 侧产物，读本份即可独立复跑 done_when 逐条判据 + 构造负例 + 禁喂框框陪审。
- 不依赖本次对话历史。
- 与防漂移指南、acceptance-ladder、acceptance-guardrails 三份**不重叠**（各管一侧，本份只管验收侧）。
