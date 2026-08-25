# B-004 CP4a coder report — stage interval semantic class repair

日期：2026-08-20  
来源：外层 CP4 Chromium 14 条中 13 PASS / 1 FAIL  
failure_key：`CP4_STAGE_INTERVAL_CLASS_MAPPING`（首次）  
结论：**READY_FOR_EXTERNAL_RERUN**

## 根因

服务端和生产枚举一致，均为 `创意 / 设计 / 开发 / 测试 / 量产 / 应用迭代`；生产 `stageClass('设计')` 实际也会生成 `stage-design`。

失败来自 Playwright selector 语义：先得到所有 interval 元素后调用 `intervals.locator('.stage-design')`，会查找这些元素的**后代** `.stage-design`，不会匹配 interval 元素自身的 class，所以真实 DOM 上同元素已有 `timeline-stage stage-design` 时仍返回 0。它不是把设计阶段错映成其它颜色，也不是 fixture 使用了非冻结枚举。

## 修复与加固

- `timeline-ui.js`
  - 六阶段映射从并行数组改为显式冻结字典，中文枚举到 semantic token 一一可读。
  - 每个阶段条同时输出：
    - `data-stage="设计"`（业务语义）；
    - `stage-design`（颜色/形状 semantic class）；
    - 可见 `<b>设计</b>` 与 `aria-label="阶段 设计…"`（文字/无障碍冗余）。
- `tests/test_timeline_e2e.py`
  - 仍严格期待设计条恰好 1 个、量产条恰好 1 个；改用匹配元素自身的复合 selector：
    - `[data-stage-interval][data-stage="设计"].stage-design`
    - `[data-stage-interval][data-stage="量产"].stage-production`
  - 2px 圆角、连续区间文字、node_ids 等原断言保留，未降低期待。
- `tests/timeline_ui.test.js`
  - 新增全部六阶段中文→semantic class 的完整映射断言。
  - 新增 `data-stage + class + aria-label` 三者一致断言。

## 本地结果

- `node --check timeline-ui.js`：PASS
- `node tests/timeline_ui.test.js`：**20/20 PASS**
- `python -X utf8 -m py_compile tests/test_timeline_e2e.py`：PASS
- `git diff --check -- timeline-ui.js tests/timeline_ui.test.js tests/test_timeline_e2e.py`：PASS
- 当前沙箱仍无法启动 Playwright（既有 WinError 5），需沿用外层命令复跑 14 条。

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_timeline_e2e.py'
```

## 指纹

- `timeline-ui.js` `8128E2BF4663C48278F8142ABA961A222EE9B26429A79546079C36EE07DF1FB0`
- `tests/timeline_ui.test.js` `42038F6F94C4D0E00C279A91D20DF35F3A22C311B98AE9499253555210D0F582`
- `tests/test_timeline_e2e.py` `27BEEE103999F633A9FAA86D25BC23982A19291A9CA8FFB5842777E7275B9AED`
- 真实 `flowboard.db` `9C782261E3F0F8ACFD83723EEA15B0FC954B06BF9E0C040335725B2E0268500D`（未写入）

同一 failure_key 未发生第二次失败；等待外层复跑后由 planner 签注。
