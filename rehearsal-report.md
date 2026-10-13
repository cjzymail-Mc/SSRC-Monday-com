# rehearsal-report — XY24（2026-10-12）

按《Flowboard 彩排执行指南》（2026-10-12，主控侧经用户转达）执行。数据经 U 盘复制到本机 repo 根目录 `D:\Technique Support\Claude Code Learning\monday-com`（未走 SMB 推送；`monday-com` 共享已建但未用于传输）。早期按原彩排委托书完成的 T0 记录见 `..\Hot-Fix\rehearsal-report.md`。

## 1. 预检（15:30:10）

```
PS> python --version
Python 3.12.2                      # ≥3.10 通过

PS> Test-Path .\server.py, .\index.html, .\local-test-data\flowboard.db
True
True
True

PS> Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
8080: 空闲（查询结果为空）
```

- `local-test-data\flowboard.db` 存在 → 无需执行 `flowboard_dev_seed.py` 播种。

## 2. 防误启动（15:30:27）

根目录存在 `flowboard.db`（U 盘带来的真实库快照）→ 已重命名隔离：

```
PS> Rename-Item .\flowboard.db flowboard-usb-snapshot-DO-NOT-USE.db
重命名完成
根目录 flowboard.db 仍存在: False
快照文件存在: True
```

## 3. 起服（约 15:30:45，后台窗口保持运行）

```
PS> cd "D:\Technique Support\Claude Code Learning\monday-com"
PS> $env:FLOWBOARD_DB="$PWD\local-test-data\flowboard.db"
PS> $env:FLOWBOARD_ATTACHMENT_DIR="$PWD\local-test-data\attachments"
PS> $env:FLOWBOARD_BACKUP_DIR="$PWD\local-test-data\backups"
PS> $env:FLOWBOARD_HOST="0.0.0.0"; $env:FLOWBOARD_PORT="8080"
PS> $env:FLOWBOARD_SECURE_COOKIE=""; $env:FLOWBOARD_INITIAL_PASSWORD="localtest"
PS> python -u server.py

启动输出：
Flowboard running at http://localhost:8080
LAN access: http://192.168.49.194:8080
```

- 防火墙弹窗处理：（待用户确认——见「待补」）

## 4. 本机自检（15:31:52 回报「可联测」）

```
PS> Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/health | Select StatusCode,Content
       200 {"status": "ok", "schema_version": 20}

PS> Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/ | Select StatusCode
       200
```

- 「可联测」时间：**2026-10-12 15:31:52**
- 收到「联测完成」时间：（待填）

## 5. 收尾

（待收到「联测完成」后执行：停服记录退出码、删除 monday-com 共享、删除空目录 C:\Flowboard、完成本报告。）

## 6. 跨机不通排查与根因定位（15:40–16:1x 补记）

- 15:40 用户报跨机访问 `http://192.168.49.194:8080/` 不通。诊断：服务存活（PID 5980，监听 0.0.0.0:8080）、本机经 LAN IP 自检 200、防火墙 4662 条入站规则中无任何 python/8080 规则。
- 15:44 重启服务试图触发「Windows 安全中心警报」弹窗 → 用户确认**从未见到弹窗**。
- 15:53 根因定位：`netsh advfirewall show allprofiles` 显示三个 profile 均为 `BlockInbound,AllowOutbound` 且 **`LocalFirewallRules = N/A (GPO-store only)`**——域 GPO 设置「不应用本地防火墙规则」，弹窗/本机手工加规则均写入本地存储、不生效。12:00:52 的 445 跨子网成功证明 GPO 侧存在文件和打印机共享放行，python/8080 无对应 GPO 规则故被默认丢弃。
- 16:0x 复核：策略读数与 15:53 完全一致（三 profile 均 ON、GPO-store only）；服务仍健康（health 200，schema v20）。
- 16:0x 生效规则枚举尝试（为「换已放行端口」方案提供决策依据），三条免提权通道全部不可行：
  1. `Get-NetFirewallRule -PolicyStore ActiveStore` → 会话工具沙箱故障，不可用；
  2. 注册表 GPO 规则键查询（reg.exe）→ 本机安全策略程序黑名单拦截，按红线不绕过；
  3. `netsh wfp show state`、`gpresult /r /scope:computer` → 均需管理员提权，按红线不提权，记录并停。
- 另导出本地存储全部入站规则（`team-progress\fw-inbound-rules-20261012.txt`，368 条）：启用+放行+带端口的 84 条（含 TCP 445/135/139/3389/2869/10246/10247 等）。**注意**：该清单含不会生效的本地规则（如 v2rayN 自建规则），无法区分 GPO 来源，不能直接作为换端口依据；全清单中无任何 8080/python 规则。
- **结论**：修复只能来自 GPO 侧。建议域管理员在 GPO 为 XY24（或其 OU）加入站放行 TCP 8080（或 python.exe 程序级规则），XY24 侧零改动即可联测；若要走「换已放行端口」路线，须先由域管理员/提权查询 GPO 已放行端口清单。注：走 WLAN 同子网地址（192.168.3.40:8080）同样无效——BlockInbound 对全部 profile 生效，与子网无关，且无任何 8080 放行规则。

### 6.1 陪审复核补记（16:17）——第 6 节结论已部分被推翻，以本节为准

独立陪审复核（注册表直读 + 全规则存储盘点 + 实证）推翻了上面第 6 节的机制归因：

1. **`LocalFirewallRules = N/A (GPO-store only)` 不表示"本地规则不生效"**——该显示仅指此设置项属 GPO 存储、未在本地配置；真正的禁用开关 `AllowLocalFirewallRules` 本机为 NotConfigured（默认合并本地规则）。
2. **GPO 规则存储实测为空**（`HKLM\SOFTWARE\Policies\Microsoft\WindowsFirewall` 无 `FirewallRules` 子键）；若"只有 GPO 规则生效"为真，445 也应被拦。
3. **445 的放行规则 `FPS-SMB-In-TCP-NoScope`（Profile=Domain）位于本地存储且 12:00:52 跨子网实测通** → 本地规则确证生效。故"弹窗/本地加规则是死路、修复只能走 GPO"的结论**作废**。
4. **修正后的修复路径**：本机管理员 PowerShell 运行
   `New-NetFirewallRule -DisplayName "Flowboard 8080 (彩排)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Domain,Private`
   （由机主人工执行；"换已放行端口"方案否决——80/443 在任何存储均无放行。）加规则后仍不通 → 转查 ESET 网络防护（ekrn/ekrnEpfw 运行中，为未排除的第二层闸门，亦为"从未弹窗"的候选解释）。
5. 勘误：第 6 节"4662 条入站规则"实为输出行数（≈367/368 条入站规则）；"reg.exe 被黑名单 → GPO 键不可查"不成立（PowerShell 只读注册表访问畅通，陪审已以此完成核查）。

根因本身不变：Domain profile 默认 BlockInbound + 全存储无 python/8080 放行 → 外部入站被静默丢弃（本机自检走回环豁免）。详见 `..\Hot-Fix\temp.md`（v2）。

## 7. 换端口实测与鞋类系统对照（16:2x 补记）

- 用户指示不纠结 8080、考虑换端口，并提供对照：鞋类管理系统（192.168.49.113，同有线子网，Docker 容器服务 8088/13000）其他电脑访问正常，但从本机访问 8088/13000 同样超时。
- **多端口探针已部署**（`team-progress\port-probe.py`，PID 8108，监听 0.0.0.0 的 554/2869/5357/7250/9955/10246/10247/23554，任意路径应答 `PORT-PROBE <port> OK`，本机 8/8 自检通过；彩排服务 8080 不受影响）：候选取自本地存储中"启用+放行+带端口"的规则端口。待主控侧从其他机器扫描，通则立即把彩排服务切到该端口；全不通则为"GPO 未放行任何通用端口"的铁证。
- **可达性矩阵（16:2x，本机出向实测）**：
  - → 鞋机 192.168.49.113（同 /24 子网）：ping 100% 丢失、445/8088/13000/3389 全部超时，**ARP 无表项（二层无应答）**；
  - → 主控机 xy198 192.168.3.39（WLAN 同子网）：445 OPEN（3389 拒绝=主机在线）；
  - → 域控 192.168.4.25（跨子网 4 跳）：389/445 均 OPEN。
  - 结论：本机出向正常（同 WLAN 子网、跨子网路由均通）；唯独与鞋机二层完全不可达。Windows 防火墙不过滤 ARP，无 ARP 应答指向**接入层端口隔离（或鞋机下线/对端整丢）**，与"8080 被 GPO 防火墙拦截"是两个独立问题。
- **给 IT/域管理员的比对清单**（按用户建议方向整理）：
  1. 并排比对两台服务器的**生效防火墙策略**（XY24 为 GPO-store only）：重点看鞋机侧放行规则是 Docker/程序级还是端口级、远程地址是否按源子网限定——这直接回答"为何 Docker 能通、Python 不能通"；
  2. 核查 XY24 有线接入口的**交换机端口隔离/私有 VLAN** 配置（解释同子网 49.113 二层黑洞）；
  3. 若比对后确认 XY24 仅缺入站放行：GPO 加一条 TCP 8080（或任一端口）入站规则即可，XY24 侧零改动。

## 异常与权限失败

- T0：New-SmbShare 权限失败（详见 ..\Hot-Fix\rehearsal-report.md）。
- 15:40 起：跨机不通，根因为域 GPO 防火墙策略（见第 6 节），非应用故障。
- 16:0x：生效防火墙规则枚举受权限/安全策略限制（reg.exe 黑名单、WFP/gpresult 需提权），按红线停止，未提权未绕过。

## 待补

- ~~防火墙弹窗是否出现~~ 已确认：用户从未见到弹窗（原因存疑：通知抑制或 ESET 前置拦截；~~GPO 不应用本地规则~~ 的解释已被 6.1 节陪审复核推翻）。
- ~~本机管理员加 TCP 8080 入站放行（见 6.1 节命令，机主人工执行）后，重新联测并补记「联测完成」时间。~~ 后续用户已报告跨机访问成功，当前无需据此继续修改防火墙；见第 8 节。

## 8. 当前会话补记：跨机访问成功与正式切换准备（2026-10-12）

- 用户已确认其它电脑成功打开 `http://192.168.49.194:8080/`。来源电脑、网段及登录操作未提供；本条仅确认该访问路径成功，不推断全公司可达或恢复原因。
- 本轮只读复核：8080 仍由 PID5980 监听 `0.0.0.0`；本机回环及有线 IP 的 health 均 200、schema20。运行时防火墙 COM 接口及 netsh 显示开启、Domain 默认入站阻断；ActiveStore 查询则返回关闭，与运行时读数不一致，不能凭其中一个读数断定用户关闭防火墙或认定具体拦截根因。本轮没有改规则或机器配置。
- 旧材料的“只能由 GPO 修复”和“候选端口全不通即证明只能 GPO”不作为后续部署依据。用户报告实际访问成功后，本轮停止扩展这条排查路径。
- 当前 8080 仍连接演示库，尚未切正式数据。用户确认 U 盘正式快照是最新数据、复制后无人修改。
- 17:27 已完成正式快照的一致备份与隔离恢复验证：v20、integrity ok、外键违规 0，46 张表及 schema 哈希相同，附件记录/文件均为 0，源库逻辑内容未变。备份 `backups/flowboard-before-xy24-cutover-20261012-092742-402502`；证据 `team-progress/20261012-xy24-deployment-preflight-20261012-172742.json`。
- 根正式 `flowboard.db` 尚未创建，未执行正式服务切换。临时探针及共享收尾尚未执行；正式切换和机器级收尾需按用户本轮明确授权落实。

## 9. 正式数据安装与8080启动（2026-10-13 09:20）

- 用户已明确授权“执行正式数据安装并启动8080”，按已核验计划执行；网络排查和彩排阶段结束，当前已启用正式数据。
- 正式数据与配置保存在仓库父目录：`flowboard-data/flowboard.db`、`flowboard-data/attachments`、`flowboard-host.json`，本机备份及服务日志位于 `flowboard-backups`。
- 安装前后全部46张表及schema哈希一致；启动前后业务数据哈希一致，原账号密码不变。v20无需schema升级，25活跃项目、7原账号，附件0。
- 后台监督PID9348、服务PID288，监听0.0.0.0:8080；有线IP192.168.49.194，入口 `http://192.168.49.194:8080/`。两地址health与首页200、未登录bootstrap401、数据库与README404及静态资源比对通过。
- 当前技术启动完成，另一台电脑用原账号登录打开真实项目待用户确认。未配置开机自启，重启电脑后需运行 `start-flowboard.cmd`。临时共享等旧彩排收尾不因本次启动授权而自动扩大为机器配置操作。
- 证据 `team-progress/20261013-production-release.json`；本节覆盖上文旧的“尚未正式切换/8080仍为演示库”状态。

## 10. 办公室正式访问验收（2026-10-13）

用户明确确认：原账号登录成功、真实项目正常，办公室同事经不同路由器均能访问，有线服务机未连接Wi-Fi。当前办公室访问与正式项目验收通过；不推断尚未测试的全公司网段。第9节的待确认状态已完成。数据库派生的校验记录、启动日志及本机配置仅保留本机，不随Git发布。
