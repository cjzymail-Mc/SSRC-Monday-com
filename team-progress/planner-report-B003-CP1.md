# B-003 · planner report · CP1（R01–R05）

日期：2026-08-20  
角色：planner（独立验收；未改实现代码、未改 coder 测试）  
裁定：**PASS，允许交棒 CP2；不代表 B-003 整体关闭。**

## 四态裁定

| 路由 | 状态 | 验收结论 |
|---|---|---|
| R01 `GET /api/workspaces/{id}/timeline` | PASS | 200 形状、created_by、M3/M4/M5、红橙并存、重叠 row_index、401/403 均由独立 HTTP 探针证明 |
| R02 `GET /api/timeline/projects/{id}` | PASS | 200 单项目形状与 R01 派生值一致；membership/viewer 403；软删 404 |
| R03 `GET /api/workspaces/{id}/timeline/review` | PASS | actor/change_rows、最近 50、id DESC、has_more、viewer 403 全部动态通过 |
| R04 `POST /api/workspaces/{id}/timeline/projects` | PASS | 201/created_by；CSRF/viewer/name conflict 专属负例及零写入通过 |
| R05 `DELETE /api/workspaces/{id}/timeline/projects/{project_id}` | PASS | `parts[5]` 路径实命中；admin 软删；403/404/409/428 与零写入通过 |

没有 `REWORK`、`CONFLICT` 或新 `OUT-OF-SCOPE` 项。CP1 未提前签注 R06–R11。

## 独立性与可失败性

- planner 自建 `team-progress/verification/B-003-CP1/probe_cp1_http.py`，没有复用 coder 的断言。
- 所有 HTTP 请求均在 `TemporaryDirectory` 中迁移的新库、`127.0.0.1:0` 随机端口执行。
- review 上限不是静态推断：经 51 次非等值 HTTP 修改加初始批次制造 `>50` 历史，再读取验证。
- R04/R05 的写负例同时比较目标表写入计数/软删计数，避免只看错误码的假绿。
- 证据全文见 `team-progress/verification/B-003-CP1/results.md`。

## 回归与冻结指纹

- coder HTTP：4/4 OK。
- timeline core：29/29 OK。
- py_compile：exit 0。
- `server.py`：`e64f9efa8520f9dfc4d60418b686817364a42b92631acee6d95a3ba4acd8ef14`
- `flowboard/timeline.py`：`edba2df03736eb6bfe15df3d20c7b4a604a92b4e67b2afbef6d72d89498bfd6c`
- `tests/test_timeline_http.py`：`7b5e419591538c1850773ad9c1753b7f0adfe60cec6d7bebacc6b0a1b3c36cec`
- 真实 `flowboard.db` 前后 stat/hash 完全一致。

## 交棒约束

下一棒仅进入 `team-task.md` §10 CP2（R06–R08）。CP1 的通过不授权顺手修改导入、导出、UI、全量回归或 `.copilot-*` 状态。

