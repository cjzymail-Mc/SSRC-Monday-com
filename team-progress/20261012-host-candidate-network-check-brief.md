# 候选主机网络环境测试委托 — Flowboard 跨子网迁移评估

- 委托日期：2026-10-12
- 发起方：主控机 `xy198`（192.168.3.39，WiFi 子网 192.168.3.0/24，网关 192.168.3.1）
- 受托方：本机（候选承载 Flowboard 的有线电脑）
- 执行者：本机上的 AI agent（你）
- 交付物：**本文件同目录**下的 `network-check-report.md`

## 0. 背景（为什么做这个测试）

Flowboard 是一个内部协作看板服务，当前跑在主控机上。主控机挂在一个部门 WiFi 路由器（192.168.3.1，做 NAT）下面，导致只有同子网电脑能访问。公司是 AD 域 `qdsports.local`，域控在 192.168.4.x / 192.168.34.x（服务器区），全公司任何子网都能访问域控。

计划：把 Flowboard 迁到一台位于核心/服务器区（或至少不被 NAT 隔离的网段）的电脑上，实现全公司可达。**本机是候选主机，本测试只采集证据，判定由主控侧完成。**

合格判据（供理解，不需你下结论）：

1. 本机所在子网能被公司其他子网主动访问（不被部门路由器 NAT 挡住）；
2. 参考信号：IP 是否在 192.168.4.x / 192.168.34.x、DNS 是否指向域控、到域控是否 1–2 跳直达。

## 1. 执行红线（必须遵守）

- **只读诊断**：只运行第 2 节列出的命令；不运行其他有副作用的命令。
- **禁止**：修改 IP/DNS/网关、增删防火墙规则、安装任何软件、启停任何服务、重启机器、修改电源计划、更改域成员身份。
- 唯一允许的写操作：在本文件所在目录创建并写入 `network-check-report.md`。
- 命令因权限不足失败（如"拒绝访问"）：把失败和错误信息记入报告即可，**不要提权重试、不要换方式绕过**。
- 命令输出出现中文乱码不影响判定，原样贴入报告。
- 无需管理员权限，普通 PowerShell 即可。

## 2. 测试步骤

每一步都记录：执行时间、命令原文、完整原始输出。

### T1 网络身份

```powershell
Get-Date
hostname
(Get-CimInstance Win32_ComputerSystem) | Select-Object Name,Domain
Get-NetIPConfiguration | Format-List InterfaceAlias,InterfaceDescription,IPv4Address,IPv4DefaultGateway,DNSServer
Get-NetConnectionProfile | Format-List InterfaceAlias,NetworkCategory,IPv4Connectivity
```

关注：IPv4 出现在哪块网卡（有线「以太网」还是「WLAN」）、IP/掩码、默认网关、DNS 是否为 192.168.4.x。

### T2 到域控的路径与连通性

```powershell
tracert -d 192.168.4.25
Test-NetConnection 192.168.4.25 -Port 389 -WarningAction SilentlyContinue | Select-Object RemoteAddress,RemotePort,TcpTestSucceeded
nltest /dsgetdc:qdsports.local
```

关注：tracert 第 1 跳是 192.168.x.1 这类部门路由器，还是核心设备地址；到 192.168.4.25 的总跳数。

### T3 承载条件盘点（只读，为后续迁移参考）

```powershell
Get-NetTCPConnection -LocalPort 445 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
powercfg /a
```

可选（若提示权限不足，跳过并记录）：

```powershell
Get-NetFirewallPortFilter -Protocol TCP | Where-Object {$_.LocalPort -eq 445} | Get-NetFirewallRule | Select-Object DisplayName,Enabled,Action,Profile
```

### T4 收尾

```powershell
Get-Date
```

## 3. 报告要求

把结果写入本文件同目录的 `network-check-report.md`，按下述结构（原始输出粘贴进对应小节，不要截断）：

```md
# network-check-report — <主机名>（<执行日期时间>）

## T1 网络身份
<原始输出>
- 活动网卡（有线/无线）：
- IPv4 / 掩码：
- 默认网关：
- DNS：
- NetworkCategory：

## T2 域控路径
<tracert / Test-NetConnection / nltest 原始输出>
- 第 1 跳：
- 到 192.168.4.25 总跳数：

## T3 承载条件
<原始输出>
- 445 是否监听：
- powercfg 摘要（本机当前允许的睡眠/休眠状态）：

## 异常与权限失败
（无则写「无」）

## 自查表（只勾选）
- [ ] IPv4 位于 192.168.4.x / 192.168.34.x
- [ ] DNS 指向 192.168.4.x
- [ ] tracert 到 192.168.4.25 全程 ≤2 跳
- [ ] 445 在监听

## 待主控侧联测
- 本机 IPv4：<填>
- 本机保持开机不休眠直至主控侧联测完成：<是 / 预计休眠时间>
```

## 4. 主控侧联测（预告，本机不要执行）

报告完成后，主控机会从 192.168.3.39（不同子网）对本机 IP 执行 `Test-NetConnection <IP> -Port 445`。**在此之前本机保持开机、不进入休眠。**若联测失败，主控侧会另发「彩排」指令（在本机用隔离数据临时起 HTTP 监听再测），本次不要自行尝试。

## 5. 已知参考信息（主控侧 2026-10-12 实测）

- 主控机：xy198，WiFi 接入，192.168.3.39/24，网关/DNS = 192.168.3.1
- 主控机 → 域控路径：192.168.3.1 → 192.168.49.252 → 172.31.100.254 → 192.168.34.252 → 192.168.4.25（4 跳，出站方向正常）
- 域内已知设备：PDC 192.168.4.6、DC3 192.168.4.25、DC4 192.168.4.3、DC5 192.168.4.4、DC8 192.168.34.3、DC10 192.168.34.25、NAS 192.168.4.55
- 病灶证据：主控机 8080 服务同子网可访问、跨子网不可达（NAT 假设的来源）
