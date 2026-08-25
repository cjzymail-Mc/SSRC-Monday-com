# B-004 CP3 independent verification results

结论：**PASS**。

## 独立动态门禁

- 生产入口用真实 mouse down/up/contextmenu 与 click 操作；右键菜单严格为四项，remove 为编辑器动作区独立控件。
- 更新按钮只产生 1 次 R06 POST；单一 request 同时含 date、status、create、remove 四类 changes，且 details 精确含 `mode=cascade`、`magnet=standard`、`zoom_band=±10d×8`。
- R07 真实 undo 为 200；临时库恢复原有 4 个活动节点，新建节点被撤销。
- 第二批状态变更提交后刷新生产入口仍存在，证明服务端持久化而非只改 DOM。
- R03 复盘 UI 可见 actor“管理员”和 change_rows 数量。
- R08 管理员纠正成功 200；member 使用自己创建的项目穿过项目写权限后，精确返回 403 / `ADMIN_REQUIRED`，toast 匹配，四表内容 hash 零变化。
- 人工提升项目 version 制造 409：响应携带 server latest view，UI 清空旧草稿并展示最新视图；`timeline_projects`、`timeline_nodes`、`timeline_change_batches`、`timeline_node_changes` 四表逐表内容 hash 均不变。
- 真实 `flowboard.db` 与 `.copilot-state.json`、`.copilot-task.md`、`.copilot-message.md` 的 size/mtime/SHA256 guard 均不变。

独立探针：`probe_cp3_browser.py`。受限沙箱首次启动 Playwright driver 命中 `WinError 5`，按同 key 熔断纪律未重试；主 agent 在沙箱外运行 exit 0。外跑摘录见 `outside-run.txt`。

## 回归

- coder Playwright E2E：6/6，exit 0（沙箱外，21.997s）。
- Node timeline UI：11/11，exit 0。
- HTTP：10/10，exit 0。
- timeline service：29/29，exit 0（38.123s）。
- planner probe `py_compile`：PASS。

## 当前冻结哈希

- `timeline-ui.js`: `E1567EA5513104230386F8512002E14EFEA89F32C4A0D6B2F82CF4F7B68D2B7F`
- `app.js`: `1818D8F380849D97CDD03A6988322B5CF435F2206C41EFA011AED990810283D1`
- `timeline.css`: `767A05675073CAE33558500B3D0B4785D3B911AC5E0941A749E151EA88EBAA9E`
- `tests/timeline_ui.test.js`: `FCE6B9A92C16B915B49F5614C974D2A0D8180D3A63867404FCC6210FBD75A49D`
- `tests/test_timeline_e2e.py`: `33DB8A9DA443DF0E513D637A175B7A35EA0AEBC72A6E4E0F5C633C4BA215C025`
- planner probe: `265326F2B6373618A44A9F63EA9C58C642CEC5B5782F632E308F8DA54E85CE9C`

## 边界

本验收只签 B-004 CP3；不提前签 CP4–CP6，不改实现/coder tests，不推进 double-workflow，不触碰真实库或 `.copilot-*`。
