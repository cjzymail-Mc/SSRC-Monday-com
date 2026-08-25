# B-003 planner report · CP4 / R11 + D6

日期：2026-08-20  
角色：planner（独立验收；未写实现、未改 coder tests）

## 裁定

**PASS**。CP4 的 R11 与 D6 均满足 `team-task.md` §10；可以进入 CP5 全矩阵验收。

## 逐路四态

| 范围 | 状态 | 独立证据 |
|---|---|---|
| R11 `POST /api/workspaces/{id}/timeline/export` | PASS | 临时 DB + 随机端口真实 HTTP；200 JSON/base64/sha256；8 列单 sheet；workspace 两项目全量；负例、权限、1001 上限均闭合 |
| D6 导出顺序 | PASS | 实际解码行序为项目稳定序 → `main, parallel` → 日期 → 自然名称 → id；`N2/N10` 与同自然键 `Same/same` 均实测 |
| R01/R09/R10 | N/A（CP4 仅作往返依赖） | R11 文件经真实 R09→R10，并由 R01 读回；不重签 CP1/CP3 |
| R02–R08 | N/A | 非 CP4 范围 |

无 `GAP-B003`，无 `CONFLICT`。

## 关键验收事实

- POST 空对象成功；GET 非 200；`project_id` / `project_ids` 扩展均不能成功。
- 缺 CSRF 为 403；viewer 为 403。
- 解码字节 SHA-256 与 JSON 一致，生产解析器确认固定 8 列、单 sheet。
- 严格 workspace 全量导出：两个活跃项目全部出现，不接受项目筛选。
- 1001 行返回 422 `EXPORT_LIMIT`，请求前后节点计数一致，零写入。
- 导出字节在新 workspace 经真实 preview/commit 后，R01 读回 2 projects / 7 nodes。

自然序算法按当前冻结实现明确为：节点名按数字段/非数字段切分；数字段转整数比较，文本段小写比较；自然键相同时以节点 id 升序收尾。轨道冻结顺序为 `main` 后 `parallel`；项目使用活跃项目 id 稳定升序。

## 回归与安全

- coder HTTP：10/10 OK。
- timeline：29/29 OK。
- transfer 定向：4/4 OK。
- `py_compile`：exit 0。
- 真实 `flowboard.db` 前后 hash/stat 不变：`9C782261...8500D`，446464 bytes，mtime UTC `2026-08-12 06:31:25`。

完整命令、探针与哈希见 `team-progress/verification/B-003-CP4/evidence.md`；可复跑验证器为同目录 `verify_cp4.py`。

## Failure key

产品 failure key：无。planner 自身一次 `PLANNER_PYTHONPATH` 与一次 `PLANNER_IMPORT_FIXTURE_DUPLICATE`，均非同键连续失败，且终态复跑全绿。
