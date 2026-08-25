# B-003 CP1 planner 独立动态证据

日期：2026-08-20（Asia/Shanghai）  
被验范围：R01–R05；临时数据库、随机端口真实 HTTP。  
探针：`probe_cp1_http.py`（SHA-256 `ebe12e0eb7887045f3195717fb27ea7cd461f2281c59d5da01955199342e2841`）。

## 命令与结果

1. `python -X utf8 team-progress/verification/B-003-CP1/probe_cp1_http.py`
   - exit 0。
   - R01/R02/R03/R04/R05 全部 PASS。
   - review 返回最近 50 条，`has_more=true`；id 严格倒序，50 条均有 `actor` 和非空 `change_rows`。
   - M3 `upcoming` 非空；M4 `overdue_count=2`；M5 `this_week_count=3`，红橙可同时为真；`max(row_index)=1`。
   - 负例均由实际 HTTP status/code 与数据库计数前后相等共同证明零写入。
2. `python -X utf8 -m unittest discover -s tests -p 'test_timeline_http.py' -v`
   - exit 0；Ran 4 tests in 7.361s；OK。
3. `python -X utf8 -m unittest discover -s tests -p 'test_timeline.py' -v`
   - exit 0；Ran 29 tests in 28.480s；OK。
4. `python -X utf8 -m py_compile server.py flowboard/timeline.py tests/test_timeline_http.py team-progress/verification/B-003-CP1/probe_cp1_http.py`
   - exit 0。

## 路由证据

| 路由 | 独立证据 | 结论 |
|---|---|---|
| R01 workspace timeline GET | 200 完整项目形状；created_by；M3/M4/M5；重叠 `row_index=1`；未登录 401；viewer 403 | PASS |
| R02 single project GET | 200 与 R01 同源 metrics/stage_intervals；viewer、非成员 403；软删后 404 | PASS |
| R03 review GET | 200；project filter；最近 50 + has_more；actor/change_rows；viewer 403 | PASS |
| R04 create POST | 201；member created_by；缺 CSRF 403、viewer 403、同名 422，三者项目计数不变 | PASS |
| R05 delete DELETE | 精确命中 `parts[5]`；仅 admin 200 软删；缺 CSRF 403、缺版本 428、冲突 409、创建者 member 403 ADMIN_REQUIRED 均零写入；重复删 404；软删后 R02 404 | PASS |

## 探针施工期纠偏

- `PROBE_FIXTURE_ROW_OVERLAP`：首轮日期未构成同轨区间重叠；调整探针 fixture 后转绿，非产品失败。
- `REVIEW_COUNT_NOOP`：首个等值日期修改按契约不产批；改成 51 次非等值 HTTP 编辑后，50+has_more 转绿，非产品失败。
- `DELETE_MEMBER_FIXTURE`：项目最初由 admin 创建，使 member 先被写权限护栏挡为 PROJECT_FORBIDDEN；改为 member 自建后精确命中 ADMIN_REQUIRED，非产品失败。
- 三个 key 均未连续失败两次。

## 运行库锁

前后完全一致：446464 bytes，mtime `2026-08-12T14:31:25.4654747+08:00`，SHA-256 `9c782261e3f0f8acfd83723eea15b0fc954b06bf9e0c040335725b2e0268500d`。

