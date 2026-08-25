# coder-report-CP3a（B-002 第 9 项唯一 REWORK）· 2026-08-19

## 1. REWORK 定位与最小处置

- `failure_key`：`OUT_OF_SCOPE_ROUTE_MISSING`
- 原因：coverage map §D 虽已把 D-2 / D-4 / D-5 / D-6 / D-7 标为未关闭的 `GAP-非九项`，但共享标题没有把五项统一、无歧义地路由为 B-003 候选。
- 处置：仅修改 `team-progress/B-002-coverage-map.md` 的 §D 标题并新增一段共享前言，明确五项全部为 `GAP-非九项`、统一路由 B-003 候选、不阻塞 B-002、不代表已实现，也不授权在 B-002 内顺手修复。
- D-2 / D-4 / D-5 / D-6 / D-7 的原有逐项内容全部保留，未逐行重写、未修任何缺口。

## 2. 哈希迁移

- coverage map 旧 SHA256：`d6e8f7356113e9ee8f6aeb9a848dc5c1a713ef9b448d9f0eac1cc28b1477cada`
- coverage map 新 SHA256：`092e69c6c4b668c43915fdce30e5368bedb0ae8086e83e9d5771c2c0752da708`
- `flowboard/timeline.py` 保持：`c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b`
- `tests/test_timeline.py` 保持：`8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf`

CP3/CP2 中绑定的旧 map 哈希由本 CP3a 记录迁移；实现与测试哈希没有变化。

## 3. 改动与验证边界

- 修改：`team-progress/B-002-coverage-map.md` §D 标题/共享前言。
- 新增：`team-progress/coder-report-CP3a.md`。
- 零代码改动、零测试改动；未改 team-task、team-progress.md、`.copilot-*` 或其他文件。
- 本次是 map 路由文字的唯一 REWORK，没有重跑 unittest，也不以 coder 自述替代验收。
- 下一步：等待 planner 使用既有 wave-3 验收器，对新 map 哈希复跑并签注第 9 项。

## 4. 三清单

- 自主裁决：无；严格按 lead 给定的唯一 failure_key 与最小改动范围处置。
- OPEN_BLOCKERS：无 coder 侧阻塞；待 planner wave-3 对新哈希验收。
- PENDING_HUMAN_NONBLOCKING：无。
