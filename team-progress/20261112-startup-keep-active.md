# 2026-11-12 启动器自动防锁屏

状态：实现及定向自动验证通过；尚未执行连续超过 10 分钟的离机锁屏观察。下次运行 `start-flowboard.cmd` 生效，本轮没有重启正式服务、写正式数据库、修改系统策略或执行仓库 commit/push。

## 用户范围与本机诊断

- 用户提供 `do_not_sleep_Num.py`，要求解析原理并集成到现有 CMD；随后明确目标是避免自动锁屏后需要密码，不只是避免电脑睡眠。
- 原脚本用 PyAutoGUI 模拟一次 Num Lock，等待 1 秒再按一次还原，等待 55 秒后循环；缺包时自动 pip 安装。原文件保留，未修改或运行。
- 只读检查显示当前电源计划的交流/直流自动息屏和睡眠超时均为 0（从不）；用户屏保策略有 `ScreenSaverIsSecure=1`、`ScreenSaveTimeOut=600`，更符合用户描述。`SPI_GETBLOCKSENDINPUTRESETS=False`，本机会接受模拟输入重置屏保计时。
- `SetThreadExecutionState` 只能阻止空闲睡眠，不能停止屏保，故没有将首版仅防睡眠的实现当作最终交付。

## 实现

- `start-flowboard.cmd` 继续调用 `flowboard_deploy.py start`，调用方式不变。后者健康检查成功后启动桌面活动保持，并在等待服务进程期间每 50 秒刷新一次；没有新建常驻子程序或线程。
- `flowboard/desktop_activity.py` 使用 Python 标准库 ctypes 调用 Windows `SendInput`，把两次完整 Num Lock 按下/释放放在同一批次，避免原脚本两次按键间 1 秒状态改变。按住 Shift/Ctrl/Alt/Win/Num Lock 时跳过。部分输入成功时仅补发一次剩余事件；失败明确警告。
- 成功显示 `[OK] Automatic lock prevention active`；输入被桌面/系统策略阻止时提示警告，恢复后报告成功，服务继续运行。
- 同时通过 `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` 辅助防止空闲睡眠，在相同线程退出作用域时恢复此前请求。正常退出、Ctrl+C、子进程异常或启动失败均清理；系统会在线程退出后释放请求。
- `--check`、数据库检查失败、占用端口和重复启动拒绝均不启用这些功能。手动 Win+L 仍可锁屏，不实现自动解锁。模拟输入也可能延后自动息屏。
- 不改电源计划、注册表、登录密码或锁屏策略，不安装 PyAutoGUI，不读取或改写真实业务数据。README 已更新使用说明。

## 验证

- `test_deployment_power.py`：12/12 PASS，覆盖原生 Windows 线程状态获取/还原、正常退出、Ctrl+C、启动失败、服务异常、`--check`、API 失败降级、50 秒等待到期继续保持以及服务退出停止。
- `test_desktop_activity.py`：7/7 PASS，覆盖双击事件顺序、修饰键保护、部分发送补全、失败警告与恢复、屏保策略禁止时不发送、非 Windows 不调用。首次新测试有 list/tuple 类型比较错误，已按同一事件内容修正，未改变行为断言。
- `test_deployment.py`：17/17 PASS，39.521 秒。实际 CMD 隔离库启动、health/schema、权限负例、旧锁恢复、重复启动拒绝、更新后启动及既有备份/迁移回归均通过；本次扩充检查启动状态提示与 `--check` 无副作用。
- 本机原生输入验证：沙箱内 `SendInput` 接受 0/4 个事件；在获准的桌面会话中执行一组双按键成功，64 位 INPUT 为 40 字节，最后输入 tick 从 18426937 更新到 18427968，核验时空闲时长为 203ms，Num Lock 状态始终为 1。证明输入计时重置且数字键盘状态保持；没有将这次短测宣称为 10 分钟离机验收。
- Python 语法检查及 `git diff --check` PASS。日志/原生证据在忽略目录 `local-test-data/20261112-startup-awake/`。已有用户文件 `do_not_sleep_Num.py` 保持原样。

## 依据

- [Microsoft：SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)：一批输入顺序插入，不与用户输入交错；可能受权限隔离限制。
- [Microsoft：SystemParametersInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfoa)：`SPI_GETBLOCKSENDINPUTRESETS` 可查询模拟输入是否允许重置屏保计时。
- [Microsoft：SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate)：系统使用请求不阻止屏保或用户手动睡眠。

## 后续：用户授权直接关闭本机自动屏保

用户随后要求取消600秒屏保限制、不需要自动锁屏。只读 `gpresult` 确认该电脑加入公司域，用户侧已应用屏保相关域GPO，本地组策略为空。因此没有将直接删改域注册表值当作永久取消上游策略。

- 已先备份本机相关用户设置、策略值及系统实际生效值，文件位于忽略目录 `local-test-data/20261112-startup-awake/screensaver-before-20261112-133801.json`。
- 按用户授权调用 `SystemParametersInfoW(SPI_SETSCREENSAVEACTIVE, FALSE, NULL, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)`，关闭当前账户自动屏保并持久保存。
- 操作后及另一个新进程回读确认：`ScreenSaveActive=0`、系统 `SPI_GETSCREENSAVEACTIVE=FALSE`，已立即生效。
- 域策略的600秒超时、恢复密码要求及屏保文件值保持原样；关闭屏保使该屏保计时不再触发。永久删除域规则须由域管理员修改策略源；未来域策略若重新启用屏保可能恢复原行为。
- 本次修改属于后续用户明确授权的系统偏好操作，覆盖前段“本轮没有修改系统设置”的范围口径；未改登录密码、电源计划或正式服务。原 CMD 防锁屏实现仍保留。
