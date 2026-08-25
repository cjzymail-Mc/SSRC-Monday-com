# B-003 · coder report · CP1（R01–R05）

日期：2026-08-20  
角色：coder（Codex team-task 恢复施工）  
范围：严格限于 `team-task.md` §10 CP1 / R01–R05。

## 产物

- `server.py`
  - 新增 `GET /api/timeline/projects/{id}`，调用 `TimelineService.get_project()`。
  - 修复 DELETE 项目路由：`project_id` 从 `parts[5]` 取得。
- `flowboard/timeline.py`
  - review 的 `batches[]` 按冻结形状返回 `actor:{id,name}` 与完整 `change_rows[]`。
  - `stage_intervals[].row_index` 按同轨 `(start_date, 首节点id)` 稳定排序、最低可用行号贪心分配。
- `tests/test_timeline_http.py`
  - 4 个随机端口、临时数据库真实 HTTP 测试，覆盖 R01–R05。

## 动态证据

1. `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py' -v`
   - `Ran 4 tests in 7.456s`，`OK`。
   - 实际命中 GET 列表/单项目/review、POST 项目、DELETE 项目。
   - 负例包含 401、viewer/member 403、CSRF 403、重复名称 422、缺版本 428、版本冲突 409、重复删除 404。
2. `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'`
   - `Ran 29 tests in 32.376s`，`OK`。
3. `python -X utf8 -m py_compile server.py flowboard/timeline.py tests/test_timeline_http.py`
   - exit 0。

具名 HTTP 测试：

- `test_r01_r02_list_and_single_get_auth_permissions_and_shapes`
- `test_r03_review_actor_change_rows_metrics_and_overlap_rows`
- `test_r04_create_lifecycle_conflict_csrf_and_viewer`
- `test_r05_delete_path_version_admin_soft_delete_and_repeat`

## 指纹与运行库安全

- `server.py`: `e64f9efa8520f9dfc4d60418b686817364a42b92631acee6d95a3ba4acd8ef14`
- `flowboard/timeline.py`: `edba2df03736eb6bfe15df3d20c7b4a604a92b4e67b2afbef6d72d89498bfd6c`
- `tests/test_timeline_http.py`: `7b5e419591538c1850773ad9c1753b7f0adfe60cec6d7bebacc6b0a1b3c36cec`
- 真实 `flowboard.db`: `9c782261e3f0f8acfd83723eea15b0fc954b06bf9e0c040335725b2e0268500d`，446464 bytes，mtime `2026-08-12 14:31:25`；施工前后 stat 未变化。

## 失败记录 / 剩余风险

- 初次使用模块名运行 unittest 因 `tests` 非 package 而导入失败；改用仓库既定 discover 方式即消失，不属于实现 failure_key。
- 第一轮 HTTP 中 u2/u3 登录失败，根因是 fixture 误把明文写入 `password_hash`；改为复制 u1 的已哈希密码后 4/4 全绿。该 failure_key 未连续发生两次。
- CP1 未触碰 CP2–CP4；11 路由完整关门仍需 planner 独立验收及后续检查点。
