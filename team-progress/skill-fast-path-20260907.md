# Git skills 快速路径与按影响验证

日期：2026-09-07。承接 `skill-sync-wip-20260907.md` 的恢复能力。用户明确授权按小团队/学习项目实际成本优化；没有修改产品行为、AGENTS.md、真实数据库或当前仓库 Git 提交状态。

## 已实现

- sync-main 返回明确 mode：unchanged 直接结束，clean 默认不做产品验收，wip 按相关路径/依赖判断检查，recovered 复用刚完成的验证。无冲突不等于接口/行为一定兼容，但不相关变更无需补跑套件。
- unchanged 在本地保护与 fetch/分叉检查后直接返回，不重复枚举相同远端树、恢复检查或清理分支清单。仍保留数据库/敏感路径、旧快照、分叉及进行中 Git 操作保护。
- commit-push-pr 先识别“无未提交工作且无本地独有提交”，此时结束而不做 GitHub 身份/fork 查询、分支、测试或 PR。工作区干净但有本地提交仍会正确进入提交路径。
- 常规提交从四次 fetch 收敛为两次：预检一次、授权后最终刷新一次；摘要阶段不重复 fetch，返回 main 复用最终 OID。`-FetchedMainCommit` 只允许与 `-RequireClean` 配合并匹配当前 origin/main；不匹配/dirty 时拒绝复用，不是通用离线开关。后台 fetch 导致复用失效时仍可走专项恢复。
- 同次调用复用未改变的身份/远端验证；首次/改变 fork setup 单独放入条件引用。不增设账号缓存、计时配置或新的审批框架。
- 两个 skill 明确了 PASS 复用、文档免产品测试、普通修复/冲突按影响补专项、高风险按覆盖缺口扩大验证。已有充分 PASS 不因 SHA、分支切换或无关上游改动失效。外部写授权、主动解决冲突、产品语义不明时的停手机制保留。
- 产品测试与 Git 工具测试分离：工具测试在 `tests/skill_checks/`，无 `__init__.py`，按独立入口运行。README 保留未提交修复可用的产品测试入口，移除全仓递归语法扫描示例。
- 完整检查器仍跑原 Python/Node 产品套件并保留前后真实数据保护。语法输入改为 Git NUL/UTF-8 跟踪源码清单，排除 .agents/ 与 tests/skill_checks/；已跟踪历史源码仍被检查，Python 一次进程检查且不写 pycache。不扫描未跟踪备份/临时源码。

## 验证

| 命令/检查 | 结果 |
| --- | --- |
| `python -B -m unittest discover -s tests/skill_checks -p test_sync_main_skill.py -v -f` | 23 PASS，91.717 秒；session 68420 / chunk 32a1a2，退出 0 |
| `python -B -m unittest discover -s tests/skill_checks -p test_flowboard_checker.py -v -f` | 6 PASS，11.810 秒；独立 agent session 46218 / chunk 8ee3b1，退出 0 |
| 两个 unittest discovery 入口仅加载/枚举，不执行产品测试 | product=184 / skill=29；产品侧无工具测试，工具侧含全部专项，无 FailedTest；chunk 040a40 |
| 两份 skill quick_validate | PASS |
| 两个 PowerShell 脚本 AST 解析 | POWERSHELL_SYNTAX_OK |
| git diff --check | PASS |

23 项 sync 测试保留全部原保护/冲突恢复断言，并新增 clean 无更新、精确复用 fetch 零网络调用、dirty 拒绝复用、已变更/无绑定基线拒绝复用。常规 sync 仍实测一次 fetch。

6 项 checker 测试使用最小临时产品套件和假数据，真实执行被改检查器：Unicode/空格跟踪源、工具及忽略临时源排除、Python/JS 语法负例、已跟踪历史源语法负例、产品断言失败不冒充 PASS，以及断言失败时仍检出假数据库变化。Windows 沙箱不允许 Git/Node 子进程的部分在获准受控执行下完成。未测试真实 GitHub fork/push/PR，未运行真实 Flowboard 产品全量。

独立只读行为试读覆盖四种请求：dirty+unchanged、已有专项 PASS+上游无关文档、clean+local commits、确认后相关函数冲突。没有发现快速路径与保护/授权衔接冲突；该试读不是动态产品验收。

## 被测文件 SHA256

| 文件 | SHA256 |
| --- | --- |
| `.agents/skills/sync-main/scripts/sync-main.ps1` | `D7795DA757F421C8063F7B39229D491EF782D39A8B7C509DC58C38E74D335AD4` |
| `.agents/skills/commit-push-pr/scripts/run-flowboard-checks.ps1` | `814F718B033858043B454DA0E2D80D646339F37D3C7EB27E2395B353740B82F9` |
| `tests/skill_checks/test_sync_main_skill.py` | `54725AEB5F0EC8779F016755568F8B6DBD10EB027A9DB1C42CAA8E2405BE7C3E` |
| `tests/skill_checks/test_flowboard_checker.py` | `36960EF4A813D6B040D247539DAA0ADA698B21E44EEA51AD3245DB0D1EE91439` |

这些测试用于工具改造验收，不是今后每次 sync/提交的必跑步骤。减少两次正常 fetch、消除工具测试与产品测试的默认耦合有明确流程/动态证据；尚无真实网络环境的端到端耗时对比，因此不承诺固定秒数或百分比提速。
