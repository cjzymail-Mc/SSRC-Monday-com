# B-003 coder report · CP4 / R11 + D6

日期：2026-08-20  
角色：coder（Codex team agent）  
范围：仅 `team-task.md` §10 CP4；未碰 UI、B-005、task/progress/.copilot。

## 结果

PASS。R11 已收敛为 `POST /api/workspaces/{id}/timeline/export`：统一会话与 CSRF，响应 JSON 含 `content_base64`、`sha256`、文件名和 MIME；sha256 对解码后的真实 XLSX bytes 计算。旧 GET 不再命中，body 的 `project_ids` / `project_id` 均以 `UNKNOWN_FIELD` 拒绝，viewer 为 403。

D6 已关闭：导出固定 8 列、单 sheet；workspace 全部活跃项目按既有项目稳定序分组，每项目内严格 `main → parallel`，轨内沿 `date → 节点名自然序 → id`；间隔逐轨实时派生。超过 1000 行返回 `422 EXPORT_LIMIT`，证据为 1001 行 HTTP 实测。

## 真实往返证据

HTTP R11 导出真实 JSON → base64 解码 → sha256 匹配 → `parse_upload()` 解析单 sheet / 8 列 → 新 workspace 走真实 R09 preview → R10 commit；结果 2 projects / 4 nodes，完成态可导回。

## 修改

- `server.py`：R11 POST JSON 路由、base64/sha256、未知 body 字段封闭。
- `flowboard/timeline.py`：导出按项目分组、轨道冻结序及轨内典范链序生成行。
- `tests/test_timeline_http.py`：新增具名 `test_r11_export_post_json_order_permissions_and_round_trip`，覆盖 GET/CSRF/viewer/扩展字段/JSON hash/XLSX/排序/真实 R09→R10/1001 上限。

## 验证

- HTTP 全组：`python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py'` → **10/10 OK**。
- timeline 全组（含 transfer/1000 边界/round-trip）：`python -X utf8 -m unittest discover -s tests -p 'test_timeline.py'` → **29/29 OK**。
- `python -X utf8 -m py_compile server.py flowboard/timeline.py tests/test_timeline_http.py` → exit 0。
- `git diff --check -- server.py flowboard/timeline.py tests/test_timeline_http.py` → exit 0（仅 Git 的 LF→CRLF 提示）。
- 真实 `flowboard.db`：SHA256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`；446464 bytes；mtime `2026-08-12 14:31:25`，未迁移、未写入。

## 文件哈希（施工后）

- `server.py`: `509862B60E8DB7FAB23F61CC8B67C7E39F87A7148D46C77C489EFFECC9621FD8`
- `flowboard/timeline.py`: `D68FA1BD3797263FEAFDA75BD508F86BFCCB73D603E81681A9AB1D878357A8D5`
- `tests/test_timeline_http.py`: `A8F95CEC755CC9C6CFA79820EA3A2774A9C5FC0F2755CC234622EC9FCF41D432`

## 失败键

- `SERVER_BASE64_LOCAL_SHADOW`：一次。旧 preview 分支的函数内 `import base64` 遮蔽模块导入，首次 R11 成功请求为 500；移除局部 import 后复跑全绿。
- `EXPORT_PROJECT_ORDER_ASSUMPTION`：一次。初测把“项目分组”误写成项目名称自然序，与既有 round-trip 稳定项目序冲突；恢复项目 id 稳定序，只在冻结要求的轨内节点名实施自然序，29/29 复跑确认。
- 单测模块 dotted path 不可导入属于测试命令调用错误，不计实现 failure key；改用仓库既定 discover。

无同一 failure key 连续两次。
