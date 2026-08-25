# B-003 CP0 planner 独立验收报告

> 验收日期：2026-08-20  
> 角色：planner（只验收，不写实现代码）  
> 结论：**PASS**

## 1. 签注范围

本报告只签注 `team-task.md` §10.2 的 **CP0 · coverage map**。它证明 B-003 的施工盘面完整、可机器复验，不代表任一路由已经通过动态 HTTP 验收，也不授权跳过 CP1–CP5。

四态正式结论：

| 验收项 | 结论 | 证据 |
|---|---|---|
| 冻结路由集合 | PASS | method/path 与 §10.1 精确相等，11/11，无缺项、无扩展 |
| 逐路由字段与归属 | PASS | 每行均登记成功状态、请求/响应、认证/CSRF、权限/错误、server 接线、service、HTTP 测试栏、四态、唯一 CP |
| 当前具名 HTTP 测试验真 | PASS | map 当前只引用 `TimelineCoreTests.test_group1_unauthenticated_http_401`；AST 在 `tests/test_timeline.py` 中找到真实 test method |
| 删除路由阳性对照 | PASS | 隔离临时副本删除 R02 后 validator=`REWORK`，failure_key=`ROUTE_MISSING`（并伴随 `ROUTE_COUNT`） |
| 伪造测试名阳性对照 | PASS | 隔离临时副本替换现存测试名后 validator=`REWORK`，failure_key=`TEST_NOT_FOUND` |
| 运行库安全 | PASS | 前后 size/mtime_ns/SHA256 完全一致 |

## 2. 口径裁定

CP0 验收的是 coverage map 是否如实登记“现状 + 缺口 + 后续 CP”，不是要求 CP1–CP4 的未来 HTTP 测试槽位提前存在。因此当前只有一个真实 HTTP 测试引用不构成 CP0 失败；其余路由明确标为 `GAP-B003` 或 `CONFLICT`，并绑定 CP1–CP4，符合 §10 的有序施工门禁。

map 当前静态状态汇总为：`PASS=0 / GAP-B003=7 / CONFLICT=4 / OUT-OF-SCOPE=0`。这里的 `PASS=0` 是路由实现状态，不与本报告的“CP0 coverage map PASS”冲突。

## 3. 可复跑证据

- 验收器：`team-progress/verification/B-003-CP0/verify_b003_cp0.py`
- 阳性对照与数据库保护：`team-progress/verification/B-003-CP0/run_controls.py`
- 真实输入结果：`team-progress/verification/B-003-CP0/real-result.json`
- 阳性对照结果：`team-progress/verification/B-003-CP0/controls-result.json`

复跑命令：

```powershell
python -X utf8 team-progress/verification/B-003-CP0/verify_b003_cp0.py team-progress/B-003-coverage-map.md --json team-progress/verification/B-003-CP0/real-result.json
python -X utf8 team-progress/verification/B-003-CP0/run_controls.py
```

输入 SHA256：

| 文件 | SHA256 |
|---|---|
| `team-task.md` | `c35287e9ddb6c84d5b9eda7e55d4466baca0a412a450bef96cb95961c71e99ab` |
| `team-progress/B-003-coverage-map.md` | `d2463e95ae0a58ed402b16a55c753fdd68922c177a86c21a84e3221c2f351b9c` |
| `team-progress/verification/B-003-route-matrix-skeleton.md` | `790fa4dbc75e79db3f6698b37d81466991965f8bc89ff0fcd8f5d018abd855b1` |
| `server.py` | `8bed2b95119aa479b99f34d4727ed558a331c48fa860360e8064fcdbb09b242c` |
| `flowboard/timeline.py` | `c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b` |
| `tests/test_timeline.py` | `8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf` |

真实 `flowboard.db` 前后均为：size `446464`，mtime_ns `1786516285465474700`，SHA256 `9c782261e3f0f8acfd83723eea15b0fc954b06bf9e0c040335725b2e0268500d`。

## 4. 下一棒边界

**允许进入 CP1（R01–R05）**。CP1 必须完成实现、真实 HTTP 正例和 planner 独立负例后再签；本报告不得被引用为任何 R01–R05 动态 PASS，也不得提前铺 CP2–CP4。
