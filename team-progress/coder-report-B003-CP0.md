# coder report · B-003 CP0 coverage map

> 日期：2026-08-19  
> 角色：coder（静态盘点）  
> 结论：产物已落盘，**等待 planner 独立验收；未宣称 CP0 PASS**。

## 1. 本次产物

- `team-progress/B-003-coverage-map.md`
- `team-progress/coder-report-B003-CP0.md`

本次未修改 `server.py`、`flowboard/timeline.py`、`tests/`、`team-task.md`、`team-progress.md`、B-002 证据或 `.copilot-*`，也未写入真实 `flowboard.db`。

## 2. 输入快照

| 文件 | SHA256 |
|---|---|
| `server.py` | `8bed2b95119aa479b99f34d4727ed558a331c48fa860360e8064fcdbb09b242c` |
| `flowboard/timeline.py` | `c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b` |
| `tests/test_timeline.py` | `8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf` |
| `feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md` | `4a83bfecf75b05c5bdbdc26d41dca7710e2e7867bc590a6a5027fa9fae901070` |
| `team-task.md` | `c35287e9ddb6c84d5b9eda7e55d4466baca0a412a450bef96cb95961c71e99ab` |

## 3. 静态结果

11/11 冻结端点均已逐列登记。状态计数：

- `PASS=0`
- `GAP-B003=7`
- `CONFLICT=4`
- `OUT-OF-SCOPE=0`

`PASS=0` 的原因是当前只有一个 timeline HTTP 测试，而且它只证明路由 1 的未登录 401；其余测试是 service 直调，不能替代冻结要求的 HTTP 黑盒验收。

## 4. 明确 GAP / CONFLICT

### CP1 · 读取与项目生命周期

1. 路由 1 已接线，但仅有未登录 401 HTTP 测试，缺 200/403/响应形状证据。
2. 路由 2 `GET /api/timeline/projects/{id}` 完全没有 server 分支。
3. 路由 3 已接线，但 review `batches[]` 当前返回 `details/change_count`，缺冻结的 `actor/change_rows`。
4. 路由 4 已接线，缺 HTTP 正例、CSRF、viewer 与同名负例。
5. 路由 5 把 `parts[4] == "projects"` 转成 project_id；合法 DELETE 无法到达 service，应使用 `parts[5]`。

### CP2 · 批次写入

6. 路由 6 已接线但没有任何真实 HTTP 正例或写路由负例。
7. 路由 7 undo 的 server 条件写 `len(parts)==5`，实际为 6 段，分支不可达。
8. 路由 8 initial-correction 同样因长度判断不可达。

### CP3 · 导入

9. 路由 9 preview 和路由 10 commit 均把 6 段路径写成 `len==5`，不可达。
10. preview 分支还调用了 server 未导入的 `require_text`；仅修路径长度仍会触发 500。
11. D-4 同名项目全行错误清单、D-5 多 sheet/CSV 提示、D-7 xlsx 数值单元格类型区分均未关闭。
12. commit 当前按 batch 的 workspace/created_by 取数，但没有独立复核提交时仍是 admin/member；HTTP 权限负例缺失。

### CP4 · 导出

13. 冻结路由 11 要求 POST；当前实现为 GET，并额外接受禁止的 `project_ids`。
14. server 向只接收 `(user,workspace_id)` 的 `export_timeline` 多传 `selected`，实际会进入 500。
15. 当前返回原始附件 bytes，不是 base64+sha256 JSON；导出排序也缺轨道维度（D-6）。

### 跨路由证据缺口

16. `tests/test_timeline.py` 唯一 timeline HTTP 用例是 `TimelineCoreTests.test_group1_unauthenticated_http_401`；没有 11 路由成功旅程、写路由 CSRF、权限/版本/原子性 HTTP 负例。

## 5. §D 唯一归属与隔离

- CP1：created_by（合并重复的“组2 created_by”表述）、M3/M5/红橙、重叠 `row_index`、timeline 入口安全界。
- CP2：correction 不钳制/不级联/no-op/越界、软删 correction/undo、member 撤 correction、interval 3650/3651、batch 缺版本 428。
- CP3：D-4、D-5、D-7。
- CP4：D-6。
- B-003 后置：部分唯一索引兜底直触；明确是 backend/data follow-up，不得假记 PASS。
- B-004：UI/浏览器事件序/视觉；B-005：全量回归、文档总收口、Gate 5 交接。

## 6. 动态验证边界

本 CP 按任务要求只做静态映射，未启动 HTTP server、未执行写请求，也未跑动态测试。因此上文的“可达/不可达、签名匹配、形状差异”是代码静态事实；实际状态码、事务零写入、CSRF 和权限组合仍必须由后续 CP 的真实 HTTP 测试及 planner 独立负例确认。

建议 planner 验收时对 coverage map 做两个临时阳性对照：删除任一路由应失败；伪造唯一具名 HTTP 测试名应失败。不要修改正式 map 或测试文件进行该对照。
