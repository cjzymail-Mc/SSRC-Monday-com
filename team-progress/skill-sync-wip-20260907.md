# Git skills 中途同步与主动冲突处理验收

日期：2026-09-07。范围：`.agents/skills/sync-main`、`commit-push-pr` 的同步/冲突衔接，以及对应隔离 Git 测试。未执行当前仓库的 sync、commit、push、PR、部署或真实库操作。

后续优化与当前测试入口见 `skill-fast-path-20260907.md`。下文保留当时的命令、路径和哈希作为历史证据；Git 工具测试已迁至 `tests/skill_checks/`。

## 最终行为

- `sync-main` 支持 main 上未提交改动与远端 main 同时变化：fetch 后固定本次基线，保存命名 stash、不可变 OID、恢复 ref 和 journal，快进 main，再恢复工作区与 index。未跟踪文件一并保护；受保护运行数据不进入快照。没有新远端提交时不创建多余快照。
- 普通冲突由调用 skill 的 agent 主动合并和验证。脚本退出 20 是恢复流程交接，不是任务结束。共享指引涵盖 index patch 提前失败、部分恢复、未跟踪同名冲突、暂存分层与中断续接；`-CompleteRecovery` 检查恢复身份和机械后置条件。
- `commit-push-pr` 主动处理每轮 rebase 冲突并验证双方行为，每次 rebase 前保留恢复引用。远端持续前进不再触发“两轮后等待安静窗口”；按实际已测试基线提交。同范围/目标的兼容合并沿用提交授权，实质变更仍需确认。回到 main 使用 `-RequireClean`。
- 后台 fetch 改变 origin/main 时，可完成本次固定基线的恢复，并单独报告后来观察到的远端 OID。保留旧 stash 及本次恢复 stash/ref，不自动清理。
- 边界：已有本地独有 main 提交、dirty 非 main、受保护路径、无证据可判断的产品语义冲突等仍需单独处理；不能把所有 Git 状态泛称为已支持。

## 可重复验证

命令：

```powershell
python -m unittest discover -s tests -p test_sync_main_skill.py -v -f
```

结果：`Ran 19 tests in 95.416s` / `OK`，退出 0。统一执行 session `8445`，完成输出 chunk `4a81b1`。

真实 Git 操作发生在一次性临时目录中。最终夹具仅将 fetch 的传输参数替换为显式本地 bare 路径；stash、index、merge、冲突和引用读写均为真实 Git，不 mock 其结果。

覆盖：clean 快进、缺少本地 main、dirty 无更新不 stash、部分暂存、Unicode/空格文件名、二进制未跟踪文件、改名/删除、旧快照保留、连续三批远端更新、普通冲突恢复、index 提前失败后的合并、未跟踪同名文件、恢复中后台 fetch、错误 origin、网络失败、dirty 非 main、本地提交分叉、敏感路径、远端引入数据库、ignored 文件碰撞、无关联 unmerged index、错误快照 OID/未解冲突不能完成恢复。

另通过：两份 skill 的 `quick_validate.py`、PowerShell AST 语法解析、`git diff --check`。没有为纯工具改动扩跑产品全量回归。

最终可执行文件/测试 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `.agents/skills/sync-main/scripts/sync-main.ps1` | `7559D974F393BBB8595AA127F2040C87257031C1A7FAE39F020A76324CB2BA2C` |
| `tests/test_sync_main_skill.py` | `EFBF3E72625DCFBFED3B90E53FE6AC7898BD14C97D56F4CC0D74A52F88AE9E90` |

环境说明：沙箱阻止 Git 本地传输启动 sh.exe（signal pipe / Win32 error 5），最终测试在获准的受控执行下完成。早期测试夹具用 `-c remote.origin.url` 覆盖多值 URL 未达到隔离目的，读取了真实 origin 到临时仓库；修正为显式本地路径后才产生以上 PASS。没有真实远端写入。

## 独立行为试做

按 skill-creator 的独立 forward-testing 指引，由另一 agent 在临时 Git 仓库执行：

- sync：同一行的本地 staged `strip`、unstaged `None` 处理与上游 `casefold` 冲突；依指引主动合并，恢复为 `MM normalize.py` 与未跟踪 notes，动态验证三种行为、暂存分层和快照保留。
- submission rebase：上游连续两轮追加压缩空白和下划线转换；两轮均真实产生冲突，解决、continue、验证双方行为，并确认恢复引用及干净 fix 分支。

完成记录：独立 agent `skill_forward_check`，session `80609`，chunk `825b15`，退出 0。关键输出 `SYNC agent resolution PASS`、`REBASE batch 1 PASS`、`REBASE batch 2 PASS`。临时目录已由测试清理；内联脚本保留在工具调用记录。该试做未记录当时文件哈希，不冒充最终哈希绑定审计。

未验证真实 GitHub fork/push/PR；这些外部流程本轮未被执行。脚本机械完成检查不代替 agent 对冲突语义的判断或相关行为测试。

Git 行为依据：[stash 文档](https://git-scm.com/docs/git-stash)（按 OID apply、index 恢复和 untracked 保存）、[merge 文档](https://git-scm.com/docs/git-merge)（fast-forward 与 ignored 文件保护）；实际验收以上述真实 Git 结果为准。
