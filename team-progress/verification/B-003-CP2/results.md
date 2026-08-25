# B-003 CP2 独立 HTTP 探针结果

日期：2026-08-20  
执行器：`probe_cp2_http.py`  
环境：R06、R07、R08 各自新建真实临时 SQLite 数据库、随机 HTTP 端口；三套环境互相隔离。

## 结果

| 路由 | checks | 结果 | 关键观测 |
|---|---:|---|---|
| R06 batches | 12 | PASS | 200 完整 view；CSRF 403；缺版本 428；stale 409；viewer 403；3650 接受、3651 拒绝；跨两项目冲突后四张 timeline 表全状态哈希不变 |
| R07 undo | 13 | PASS | 200 完整 view 且 created 节点软删；CSRF 403；stale/撤 undo 均 409；软删项目 404；member 撤 initial-correction 403 `ADMIN_REQUIRED`；所有负例表状态哈希不变 |
| R08 initial-correction | 15 | PASS | 200；不钳制、不级联、不改 current date；CSRF/权限 403；缺版本 428；stale 409；no-op 不升版且零写；越界 422；软删 404；所有负例表状态哈希不变 |

命令：

`python -X utf8 team-progress/verification/B-003-CP2/probe_cp2_http.py`

终值：`status=PASS`, `counts={R06:12,R07:13,R08:15}`，exit 0。HTTP 日志覆盖预期的 200/403/404/409/422/428。

## 回归

- `python -X utf8 -m unittest discover -s tests -p "test_timeline_http.py"` → 7/7，OK（14.371s）。
- `python -X utf8 -m unittest discover -s tests -p "test_timeline.py"` → 29/29，OK（33.315s）。
- `python -m py_compile team-progress/verification/B-003-CP2/probe_cp2_http.py` → exit 0。

## 运行库锁

前后完全一致：

- SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`
- 446464 bytes
- mtime `2026-08-12 14:31:25.4654747`

