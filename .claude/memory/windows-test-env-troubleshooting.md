---
name: windows-test-env-troubleshooting
description: 中文 Windows+本机沙箱下测试环境四类反复阻塞与标准解法——沙箱权限、编码、进程/文件生命周期、cwd；标注环境条件
type: reference
---

# Windows 测试环境排错（环境条件：中文 Windows + 本机沙箱 + 项目 Python 3.12；换环境部分失效，按条件取用）

- **沙箱/权限阻塞**（node spawn EPERM、Playwright WinError 5、git sh.exe pipe error 5、系统临时目录权限）：识别为环境限制后**不改测试逻辑规避、不在同一受限环境重试**；标准解法 = 仓库内隔离目录 + 项目原有 Python、直接执行自带断言的同一测试模块、或获批后沙箱外复跑同一测试；受限方声明 BLOCKED_DYNAMIC 不申请动态 PASS。（08-20~10-29 约 14 次实证）
- **中文输出编码**：不用 UTF-8 模式强解中文 Windows 工具输出（taskkill cp936 解码崩溃；PowerShell 首次中文输出乱码同因，统一按 UTF-8 处理输出侧）。
- **进程/文件生命周期**：先关闭所有测试上下文、等 daemon 请求线程退出，再清理 SQLite 临时文件——否则 WinError 32 埋掉真实断言失败（清理错误不能遮蔽首因）；进程级初始密码须显式初始化；临时库不覆盖各自附件/备份默认目录。
- **cwd**：统一从仓库根用 discover 模式跑测试/验证器，避免 ModuleNotFoundError 与 loader 误记导入错误（此类预检失误不算产品 failure）。
- **并行拆分**：按同一完整 discovery 清单分互不重叠进程，并核对测试总数未缩减（278 不缩）。

证据：`team-progress/20261029-final-regression-and-delivery.md`、`team-progress/planner-report-B005-CP2.md`、`team-progress/coder-report-B004-CP1.md`。
