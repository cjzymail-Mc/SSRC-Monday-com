# Flowboard 彩排委托书 — XY24 隔离试运行

- 委托日期：2026-10-12
- 发起方：主控机 `xy198`（192.168.3.39）
- 受托方：XY24（有线 192.168.49.194，候选承载机）
- 执行者：本机上的 AI agent（你），部分步骤需本机人工/管理员配合
- 交付物：本文件同目录下的 `rehearsal-report.md`

## 0. 背景与目标

网络终验已通过（2026-10-12 12:00:52 联测，TCP 445 跨子网对称路径可达）。彩排目标：**用隔离演示数据在 XY24 上跑起完整 Flowboard 服务**，验证「文件推送 → 起服 → 防火墙 → 跨子网访问」全链路。本轮**不涉及任何真实数据**——真实库、附件、备份都留在主控机，不会推送，XY24 也不得另行拉取。

## 1. 本轮授权与红线

**允许（仅限以下）**：
1. 创建 `C:\Flowboard` 目录；
2. 创建名为 `flowboard` 的临时共享（指向 `C:\Flowboard`，Everyone 完全控制）——**仅限彩排窗口，收尾 T5 必须删除**；
3. 运行 Flowboard Python 服务（隔离数据，监听 0.0.0.0:8080）；
4. Windows 防火墙弹窗时人工点击「允许访问」；
5. 生成本报告。

**禁止**：其他任何系统配置更改、安装任何软件、动 C:\ 其他内容、修改域身份/电源计划/网卡。命令权限不足 → 记录并终止对应步骤，不绕过。

## 2. 执行步骤

### T0 前置检查与传输通道（部分需管理员）

```powershell
Get-Date
python --version          # 需 ≥3.10；无 python 或版本不足 → 记录并终止本轮
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue    # 预期为空（端口未被占用）
```

创建目录与临时共享（二选一）：

- agent 若有管理员 PowerShell：

  ```powershell
  New-Item -ItemType Directory -Force C:\Flowboard
  New-SmbShare -Name flowboard -Path C:\Flowboard -FullAccess Everyone
  Get-SmbShare -Name flowboard
  ```

- 无管理员权限 → 请本机人工操作：建 `C:\Flowboard` 文件夹 → 右键「属性 → 共享」→ 添加 Everyone 并给「读/写」权限。

完成后：把 `Get-SmbShare` 结果（或人工操作说明）与时间戳写入报告，**通过用户通知主控侧「共享就绪」**，然后等待推送（T1 期间本机无动作）。

### T1 主控侧推送（XY24 无动作，仅等待）

主控侧将通过 `\\192.168.49.194\flowboard` 推送约 55–60 MB（完整仓库：代码 + `.git` + 演示种子库 `local-test-data\flowboard.db`；**排除**真实库/真实附件/真实备份/`__pycache__`/调试日志）。推送完成主控侧会核验文件数与大小，再通过用户通知本机继续。

### T2 启动服务（普通 PowerShell，保持窗口运行）

```powershell
cd C:\Flowboard
$env:FLOWBOARD_DB="C:\Flowboard\local-test-data\flowboard.db"
$env:FLOWBOARD_ATTACHMENT_DIR="C:\Flowboard\local-test-data\attachments"
$env:FLOWBOARD_BACKUP_DIR="C:\Flowboard\local-test-data\backups"
$env:FLOWBOARD_HOST="0.0.0.0"
$env:FLOWBOARD_PORT="8080"
$env:FLOWBOARD_SECURE_COOKIE=""
$env:FLOWBOARD_INITIAL_PASSWORD="localtest"
python -u server.py
```

- 首次绑定时 Windows 可能弹「Windows 安全中心警报」→ **人工勾选「专用网络」和「域网络」并点「允许访问」**（需管理员确认一次）；未弹窗也如实记录。
- 记录启动输出（监听地址、数据库路径等）。
- 保持服务窗口运行，另开一个窗口做 T3。

### T3 本机自检

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/health | Select-Object StatusCode,Content
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/ | Select-Object StatusCode
```

预期均 200，health 返回 JSON。通过后**通过用户通知主控侧「可联测」**，进入 T4 等待窗口（保持服务运行、机器不睡眠）。

### T4 主控侧联测 + 第三方子网样本（XY24 无动作）

- 主控侧（xy198）访问 `http://192.168.49.194:8080/api/health`；
- 用户另找**其他 WiFi 子网**的同事用浏览器打开 `http://192.168.49.194:8080/`，用 `test / test` 登录，确认能看到演示看板（这一步补齐第三方子网样本）。
- 完成后用户转达「联测完成」。

### T5 收尾（必做）

```powershell
# 在服务窗口 Ctrl+C 停止服务，记录退出码
Remove-SmbShare -Name flowboard -Confirm:$false    # 需管理员；人工操作亦可（右键共享 → 停止共享）
Get-SmbShare -Name flowboard -ErrorAction SilentlyContinue    # 确认已不存在
```

- **保留 `C:\Flowboard` 全部内容**（含彩排数据）待主控侧确认后再议，不删除；
- 完成报告 `rehearsal-report.md`。

## 3. 报告要求

```md
# rehearsal-report — XY24（<日期>）
## T0 前置
- python 版本：
- 8080 占用检查：
- 共享创建方式与 Get-SmbShare 结果：
- 就绪时间戳：
## T2 启动
- 启动输出：
- 防火墙弹窗处理：
## T3 本机自检
- health 状态码与内容：
- 首页状态码：
## T4 联测窗口
- 「可联测」时间：
- 收到「联测完成」时间：
## T5 收尾
- 停服退出码：
- 共享删除确认：
## 异常与权限失败
（无则写「无」）
```

## 4. 协调协议（用户在中转）

1. XY24 完成 T0（共享就绪）→ 用户通知主控侧；
2. 主控侧 robocopy 推送并核验 → 用户通知 XY24 执行 T2；
3. XY24 T3 自检通过 → 用户通知主控侧联测；
4. 主控联测 + 第三方子网样本完成 → 用户通知 XY24 执行 T5 收尾。

任一步失败：如实记录、停止后续步骤、恢复已做的变更（至少停服、删共享），等主控侧判断。

## 5. 结果判读（主控侧负责）

- 全链路通过 = 彩排成功，正式迁移按同一通道执行（数据换成真实库三件套，须另行授权与停服窗口）；
- 任一环节失败 = 记录证据，主控侧诊断后决定下一步，XY24 不自行改配置重试。
