# B-003 · coder report · CP2（R06–R08）

日期：2026-08-20  
角色：coder（Codex team-task 恢复施工）  
范围：严格限于 `team-task.md` §10 CP2 / R06–R08；未触碰 imports、export、UI、`.copilot-*`、`team-task.md`、`team-progress.md`。

## 产物

- `server.py`
  - 修复 R07 `POST /api/workspaces/{id}/timeline/batches/undo` 的六段路径判定（`len(parts) == 6`）。
  - 修复 R08 `POST /api/workspaces/{id}/timeline/batches/initial-correction` 的六段路径判定。
- `tests/test_timeline_http.py`
  - 在真实临时数据库、随机端口 HTTP server 上新增 R06–R08 三个具名测试及批次/计数辅助函数。
- `flowboard/timeline.py`
  - CP2 未需修改；沿用 CP1 指纹。

## 具名 HTTP 测试与覆盖

- `test_r06_batch_http_complete_view_csrf_version_atomic_and_interval_bounds`
  - 成功响应完整 `view`；`interval_days=3650` 成功、3651 拒绝。
  - CSRF 403、缺 `base_version` 428、版本冲突 409、viewer 403。
  - no-op 不升版本；跨两项目“第一项有效、第二项冲突”返回 409，四表计数保持不变。
- `test_r07_undo_http_success_csrf_stale_soft_delete_and_zero_write`
  - 创建节点的反向操作为软删除；返回完整 view。
  - CSRF 403 零写；重复/过期撤销 409 零写；已软删项目的最新批次 undo 返回 404 且零写。
- `test_r08_initial_correction_http_noop_no_cascade_permissions_and_invalid_node`
  - correction 可把 `initial_date` 改到当前日期之后，不钳制、不级联、不改变 `date`。
  - CSRF 403；member 对自己创建的项目仍因非 admin 返回 `ADMIN_REQUIRED` 403。
  - 相同值 no-op 不升版本；越界 node 422 零写；软删项目 correction 404 零写。

## 动态证据

1. `python -X utf8 -m unittest discover -s tests -p "test_timeline_http.py"`
   - `Ran 7 tests in 13.664s`，`OK`。
   - R06/R07/R08 的实际 HTTP 日志分别出现 200，以及预期的 403/404/409/422/428。
2. `python -X utf8 -m unittest discover -s tests -p "test_timeline.py"`
   - `Ran 29 tests in 31.934s`，`OK`。
3. `python -m py_compile server.py flowboard/timeline.py tests/test_timeline_http.py`
   - exit 0。
4. `git diff --check -- server.py flowboard/timeline.py tests/test_timeline_http.py`
   - exit 0；仅报告既有 Windows LF→CRLF 提示，无 whitespace error。

## 指纹与运行库安全

CP1 施工报告所载前值 → CP2 后值：

- `server.py`: `e64f9efa8520f9dfc4d60418b686817364a42b92631acee6d95a3ba4acd8ef14` → `5c1ddd81723a27c9644593df9e659319706d4c24dd2612611a52c6f79bf97dac`
- `flowboard/timeline.py`: `edba2df03736eb6bfe15df3d20c7b4a604a92b4e67b2afbef6d72d89498bfd6c` → 同值（CP2 未改）
- `tests/test_timeline_http.py`: `7b5e419591538c1850773ad9c1753b7f0adfe60cec6d7bebacc6b0a1b3c36cec` → `ae17de0eabc692d93b3b641c849851f2804776daaa2193d2d44aaaf8ec113bf7`
- 真实 `flowboard.db`: 前后均为 `9c782261e3f0f8acfd83723eea15b0fc954b06bf9e0c040335725b2e0268500d`，446464 bytes，mtime `2026-08-12 14:31:25`；未迁移、未写入。

## failure_key 与边界

- 首次误用 `python -m unittest tests.test_timeline_http`，因 `tests` 非 package 导入失败；改用仓库既定 discover 命令后正常，不是实现 failure_key。
- HTTP 新测试首轮有两个不同的 fixture/预期问题：日期字面未实际构成 3651 天；member 操作非自己创建的项目先命中 `PROJECT_FORBIDDEN`。分别改为显式 `interval_days=3651`、member 自建项目后命中 `ADMIN_REQUIRED`，复跑全绿。
- 没有同一 failure_key 连续两次；未触发 coder 熔断。
- CP2 只交 coder 证据，不主张 planner 已验收；CP3/CP4 保持未施工。
