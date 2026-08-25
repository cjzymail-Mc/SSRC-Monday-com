# B-004 CP4b coder report — E2E card scope repair

日期：2026-08-20  
failure_key：`CP4A_TEST_CARD_UNDEFINED`（首次；测试问题，非产品问题）  
外部前值：14 条中 13 PASS，唯一 ERROR 为 `NameError: name 'card' is not defined`  
结论：**READY_FOR_EXTERNAL_RERUN**

## 根因与最小修复

CP4a 把阶段语义 selector 改为从 `card` 查询元素自身，但该测试方法只定义了 `intervals`，没有在本地作用域定义 `card`。因此 Python 在浏览器断言前即抛 `NameError`，产品 DOM 没有得到该条验证。

仅修改 `tests/test_timeline_e2e.py::test_timeline_stage_intervals_semantics`：

1. 显式绑定当前项目白卡：`card = page.locator('[data-dashboard-project="{project_id}"]')`。
2. `intervals` 从该卡片作用域取得，避免跨项目误匹配。
3. 设计和量产仍各严格期待 1 个，复合条件未放宽：
   - `data-stage="设计" + stage-design`
   - `data-stage="量产" + stage-production`
4. 保留并加强冻结语义：
   - 可见文字分别为“设计”“量产”；
   - `aria-label` 分别包含“阶段 设计”“阶段 量产”；
   - computed `border-radius` 仍严格为 `2px`；
   - 每个阶段 interval 的 inline width 必须大于 0，维持连续实色条；
   - 全部阶段条可见文字非空；
   - 全部 `node_ids` 非空。

未改生产代码、CSS、B-005、治理文件、`.copilot-*` 或真实数据库，也未在当前沙箱运行浏览器。

## 本地结果

- `node --check timeline-ui.js`：PASS
- `node tests/timeline_ui.test.js`：20/20 PASS
- `python -X utf8 -m py_compile tests/test_timeline_e2e.py`：PASS
- `git diff --check -- tests/test_timeline_e2e.py`：PASS

外层复跑命令：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'
```

## 指纹

- `tests/test_timeline_e2e.py`：`D8DF135DE5BCAA060D50FED439329885DFDE2DC139DDABE0E20261863E883D3C`
- 真实 `flowboard.db`：`9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`（未写入）

同一 failure_key 未发生第二次失败；等待主 agent 外跑并由 planner 签注。
