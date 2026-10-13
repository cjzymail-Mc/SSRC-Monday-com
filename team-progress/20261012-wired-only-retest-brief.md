# XY24 纯有线复测委托 — 消除回程近路的终验

- 委托日期：2026-10-12
- 发起方：主控机 `xy198`（192.168.3.39）
- 受托方：本机 XY24（有线 192.168.49.194，候选承载机）
- 执行者：本机上的 AI agent（你）
- 交付物：本文件同目录下的 `wired-only-retest-report.md`

## 0. 背景（为什么复测）

首轮联测（本机有线 IP 192.168.49.194:445，跨子网 TCP）成功，但当时本机**双网卡同时在线**：WLAN（192.168.3.40）恰好与主控机同处 192.168.3.0/24，测试的回程包可能走了 WLAN 近路，样本不纯净。本轮**临时禁用 WLAN、仅保留有线**，由主控侧再次联测。回程只剩「本机网关 192.168.49.252 → 核心 → 主控机 NAT」一条路——成功即证明真正的对称跨子网路径可达。

## 1. 本轮授权与红线

**本轮新增授权（仅此一项）**：允许临时禁用并恢复名为 `WLAN` 的网络适配器（或物理拔插 USB 无线网卡）。测试结束后**必须**恢复。

其余继续遵守上轮红线：

- 除上述 WLAN 禁用/恢复外，**只读诊断**，不改任何其他配置（IP/DNS/防火墙/电源/服务/域身份）、不安装软件、不重启。
- 命令权限不足：记录失败信息即可终止对应步骤，不提权、不绕道、不换方式。
- 报告为唯一写操作（本文件同目录）。输出乱码不影响判定，原样粘贴。

## 2. 执行步骤

### T0 基线

```powershell
Get-Date
Get-NetAdapter | Format-Table Name,InterfaceDescription,Status,MacAddress
```

### T1 禁用 WLAN（二选一，方式 A 优先）

- **方式 A（免权限，优先）**：人工拔下 USB 无线网卡（Realtek 8811CU），等待约 5 秒。
- **方式 B（需管理员 PowerShell）**：

  ```powershell
  Disable-NetAdapter -Name "WLAN" -Confirm:$false
  ```

- 若方式 B 权限不足且方式 A 无法执行：记录后**终止本轮**，不要尝试其他办法。

### T2 验证纯有线状态（关键证据）

```powershell
Get-Date
Get-NetAdapter | Format-Table Name,InterfaceDescription,Status
Get-NetIPConfiguration | ForEach-Object { [PSCustomObject]@{InterfaceAlias=$_.InterfaceAlias; IPv4=($_.IPv4Address.IPAddress -join ","); Gateway=($_.IPv4DefaultGateway.NextHop -join ","); DNS=($_.DNSServer.ServerAddresses -join ",")} } | Format-List
route print -4
Test-NetConnection 192.168.4.25 -Port 389 -WarningAction SilentlyContinue | Select-Object RemoteAddress,RemotePort,TcpTestSucceeded
```

验收标准（全部满足才算就绪）：

1. WLAN 状态为 Disconnected / 已从列表消失；仅「以太网」有 IPv4 **192.168.49.194**；
2. `route print -4` 活动路由中**不存在** 192.168.3.0/24 的 on-link 路由（这是本轮的核心证据，整段粘贴）；
3. 389 直连域控仍成功（有线独立可用）。

### T3 通知联测（进入等待窗口）

- 在报告「联测窗口」一节写入就绪时间戳（T2 的 Get-Date）。
- **保持开机、不睡眠**，等待用户转达「联测完成」后再执行 T4。等待期间不执行其他操作。

### T4 恢复 WLAN（必做，即使联测失败）

- 方式 A：插回 USB 无线网卡；方式 B：

  ```powershell
  Enable-NetAdapter -Name "WLAN" -Confirm:$false
  ```

- 恢复后验证并粘贴：

  ```powershell
  Get-Date
  Get-NetAdapter | Format-Table Name,InterfaceDescription,Status
  Get-NetIPConfiguration | ForEach-Object { [PSCustomObject]@{InterfaceAlias=$_.InterfaceAlias; IPv4=($_.IPv4Address.IPAddress -join ","); Gateway=($_.IPv4DefaultGateway.NextHop -join ",")} } | Format-List
  ```

- 验收：WLAN 恢复 Up 并重新获得 192.168.3.x 地址。

## 3. 报告要求

写入同目录 `wired-only-retest-report.md`：

```md
# wired-only-retest-report — XY24（<日期>）
## T0 基线
<原始输出>
## T1 禁用方式
<方式 A / 方式 B / 终止原因>
## T2 纯有线验证
<原始输出；route print 活动路由段整段粘贴>
- 是否确认无 192.168.3.0/24 路由：
- 389 结果：
## 联测窗口
- 就绪时间戳：
- 收到「联测完成」时间：
## T4 恢复
<原始输出>
- WLAN 是否恢复 Up 并拿回 192.168.3.x：
## 异常与权限失败
（无则写「无」）
```

## 4. 协调协议（用户在中转）

1. XY24 agent 完成 T2 → 报告写入就绪时间 → 用户告知主控侧「开始联测」；
2. 主控侧（xy198）执行联测（预告：`Test-NetConnection 192.168.49.194 -Port 445`），回报结果；
3. 用户向 XY24 转达「联测完成」→ agent 执行 T4 恢复并完成报告。

窗口应控制在 15 分钟内，避免机器闲置入睡。

## 5. 结果判读（主控侧负责，本机不下结论）

- 445 通 = 纯净对称跨子网路径可达，**终验通过**，方案 1a 网络条件成立；
- 445 不通 = 如实记录失败，主控侧转入彩排路线（隔离数据起 HTTP 监听），本机**不要**自行加监听或改防火墙。
