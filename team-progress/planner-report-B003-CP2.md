# B-003 · planner report · CP2（R06–R08）

日期：2026-08-20  
角色：planner（独立验收；未写实现、未改 coder tests）  
范围：`team-task.md` §10 CP2，仅 R06–R08 与绑定的 D-2 HTTP 可观察项。

## 结论

**CP2 PASS。R06、R07、R08 均正式签注 PASS，可进入 CP3。**

| 路由 | 四态签注 | 验收依据 |
|---|---|---|
| R06 `POST .../timeline/batches` | PASS | 独立随机端口/临时库探针通过；成功完整 view、逐路 CSRF、权限、版本、428、3650/3651、多项目原子回滚与零写证据齐全 |
| R07 `POST .../batches/undo` | PASS | 六段路由真实可达；成功完整 view；CSRF、stale、撤 undo、软删项目 404、member 撤 initial-correction 403 与零写证据齐全 |
| R08 `POST .../batches/initial-correction` | PASS | 六段路由真实可达；不钳制/不级联/不改 date、no-op、越界、软删、版本、权限、CSRF 与零写证据齐全 |

本波未发现 `CONFLICT`、`GAP-B003` 或 `OUT_OF_SCOPE` 残项。

## 独立性与证据强度

- planner 自建 `team-progress/verification/B-003-CP2/probe_cp2_http.py`，没有调用 coder 测试方法；R06/R07/R08 分别启动独立的真实 HTTP server、随机端口与临时迁移数据库。
- 负例零写不是只看行数：探针对 `timeline_projects`、`timeline_nodes`、`timeline_change_batches`、`timeline_node_changes` 的排序全行内容计算 SHA-256 状态指纹并前后比较。
- 独立探针补上 coder 组未单独覆盖的“撤 undo 批次”和“member 撤 initial-correction”两项，均得到 `409 UNDO_TARGET_STALE` / `403 ADMIN_REQUIRED` 且状态指纹不变。
- 详细结果见 `team-progress/verification/B-003-CP2/results.md`。

## 动态验收

1. planner 独立探针：R06 12/12、R07 13/13、R08 15/15，exit 0。
2. coder HTTP 全组：7/7，OK。
3. timeline 服务回归：29/29，OK。
4. planner 探针 py_compile：exit 0。

## 指纹与运行库安全

- `server.py`: `5C1DDD81723A27C9644593DF9E659319706D4C24DD2612611A52C6F79BF97DAC`
- `flowboard/timeline.py`: `EDBA2DF03736EB6BFE15DF3D20C7B4A604A92B4E67B2AFBEF6D72D89498BFD6C`
- `tests/test_timeline_http.py`: `AE17DE0EABC692D93B3B641C849851F2804776DAAA2193D2D44AAAF8EC113BF7`
- 真实 `flowboard.db` 前后 SHA-256 均为 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`；446464 bytes；mtime `2026-08-12 14:31:25.4654747`。未迁移、未写入。

## failure_key / 边界

- 首次执行 planner 脚本时因脚本位于子目录、未注入 repo root，出现一次 `ModuleNotFoundError: flowboard`；补齐只属于验收器的 `sys.path` 后通过。这是 probe fixture 问题，不是实现 failure_key。
- 无同一 failure_key 连续两次；不触发熔断。
- 未验收 imports/export/UI；这些仍分别属于 CP3/CP4/B-004。

