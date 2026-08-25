# B-004 CP6a coder report — 终态 coverage 可追溯与三条完整旅程

日期：2026-08-20  
planner 前值：CP6 wave 1 REWORK  
failure_key：`B004_CP6_COVERAGE_TEST_REFERENCE_MISSING`（首次）  
结论：**READY_FOR_EXTERNAL_RERUN**；未发现需要修改生产的产品缺陷。

## 1. 终态 coverage 修正

逐条审计 `tests/test_timeline_e2e.py` 当前 21 条真实 Chromium 用例后确认，CP1–CP5 采用了按波次聚合的真实旅程，CP0 map 却仍把施工前未来槽位当作终态引用；25 个名字因此不可加载。已有聚合测试具备实际语义，不应复制成空 alias。

`team-progress/B-004-coverage-map.md` 本次处理：

- B 表、CP0a 增补、初始 GAP/CONFLICT、当时“未来槽位”名称和 CP0 指纹全部保留为历史事实；未来槽位仅改用 `<code data-historical-slot>` 标识，避免被关门 validator 误认为当前可执行引用。
- 新增 §H“CP6 终态真实 E2E 可追溯表”，逐行登记 B01–B38 当前实际可加载方法和语义说明。
- 对 B01–B35/B37/B38，只有现有测试语义精确覆盖时才复用实际方法；一个聚合旅程覆盖多条条款时复用同名，没有创建 alias、test 互调或 skip。
- B04/B05 审计发现原 CP1 聚合测试证据不够精确，直接在原真实旅程补实质断言：
  - 第二真实浏览器会话保持 stale single-project UI；第一会话软删后，第二会话物理进入 editor，真实单项目 GET 返回 404，toast 可见、预期 console 精确核销。
  - 项目 input `maxlength=200`；带空格同名创建经过前端 trim 后真实 POST 422 `NAME_CONFLICT`，toast/console/四表 hash 零写均验。

关门义务按 B01–B35/B37/B38 37 行 + B36 三旅程共 40 项全部有真实引用。planner 原 validator 实际输出：

- `status=PASS`
- `coverage_rows=38`
- `referenced_tests=24`
- `loadable_e2e_tests=24`
- `missing_references=[]`
- `b36_missing=[]`
- positive-control fake name 仍未被当成实际测试

唯一引用数从施工前计划名的 40 降为 24，是因为 validator 去重且 prompt 明确允许一个语义充分的真实聚合测试覆盖多行；不是丢失条款。B01–B38 表仍逐行闭合。

## 2. B36 三条新隔离库完整旅程

新增三个精确名称，均在自己的随机端口/临时 DB 中完整执行，不调用其他 `test_*`：

### `test_timeline_journey_edit_submit_refresh_undo`

- 真实入口与 editor 点击；节点真实右键 → “已完成” → 本地 1 项草稿。
- 物理提交，精确观察单次 R05 200、草稿归零、服务端完整 view 刷新、DB `done_at` 与非 undo batch。
- 物理 undo，精确观察 R06 200、DB `done_at` 回滚与 `change_kind='undo'/undone_batch_id`。
- 页面刷新后重新真实进入 editor，确认撤销结果持久且 undo 入口生命周期消失；网络计数、console/pageerror 门保持。

### `test_timeline_journey_dashboards`

- 真实进入 single：方向 A 双轨、今日文字/日期、阶段 interval、overlap 展开。
- 真实 node 右键四项 controller 并选择 done，确认只读提示。
- 真实切 all、选择 overdue 排序、多选筛选重渲染；以 `elementFromPoint(...).closest(node)` 复核物理 hit，再用共享右键 controller。
- 从 single 起点到 all 终点网络请求数不增，四表 hash 完全不变，console/pageerror 全零。

### `test_timeline_journey_import_export_reimport`

- workspace 1 真实 file chooser 上传 XLSX → R09 201 → 物理 R10 201 → UI/四表变化。
- 物理 R11 POST、消费服务端真实 bytes/SHA-256、真实 browser download。
- 独立用户 workspace 2 将刚下载文件经真实 chooser 再上传 → R09 201 → 物理 R10 201。
- 精确回读目标 DB 项目/node 顺序及既定状态差异（仅已完成保留）；两端 route/status、hash、console/pageerror 门完整。

E2E 从 21 条增加至 **24 条**；未使用 `self.test_*`、skip、空壳包装、mock fetch、handler 直调或 `set_content`。

## 3. 本地验证

- `python team-progress/verification/B-004-CP6/validate_terminal_coverage.py`：**PASS**（38/38 rows，24/24 unique refs loadable，missing 0，B36 missing 0）
- `node tests/timeline_ui.test.js`：**24/24 PASS**
- `python -m py_compile tests/test_timeline_e2e.py`：PASS
- `git diff --check -- tests/test_timeline_e2e.py team-progress/B-004-coverage-map.md`：PASS
- `rg self.test_|skip`：无命中
- E2E AST 具名测试计数：24
- 按指令 worker 未运行浏览器；完整 24 条交主 agent 沙箱外运行。

外跑命令：

```powershell
python -m unittest discover -s tests -p test_timeline_e2e.py
```

## 4. 指纹与边界锁

- `tests/test_timeline_e2e.py` SHA-256：`D1C4BA3D51001847AA6D5A81E87697E4CE497E03784EE86F870D52696C20CA6E`
- `team-progress/B-004-coverage-map.md` SHA-256：`6E079AD021F0219897DD5DB1CB1B59F5F123F171919FB261EE4372E29A3F4BE3`
- 真实 `flowboard.db`：446,464 bytes，mtime `2026-08-12 14:31:25`，SHA-256 `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`。
- `.copilot-task.md/.copilot-state.json/.copilot-message.md` mtime 保持 `2026-08-19 09:48:23 / 14:00:55 / 13:57:38`。

未进入 B-005，未改生产、planner validator、CP0–CP5 报告、治理、`.copilot-*` 或真实数据库。
