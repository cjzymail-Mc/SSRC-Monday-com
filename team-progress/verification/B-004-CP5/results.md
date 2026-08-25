# B-004 CP5 independent verification results

结论：**PASS**。B30–B35、B38 全部关闭，允许进入 CP6。

## R09 / R10 与错误呈现

- planner 自行生成 OOXML/CSV bytes，通过生产 file chooser 上传；未调用 coder test helper。
- R09 成功返回 201，UI 显示 row/project/node summary 与 warnings。
- R10 仅发送 `{batch_id}`，返回 201 后重新 GET timeline；完成状态回读证明只有“已完成”保留，进行中被重算。
- 同名项目的全部冲突行 2/4 均在 `details.rows` 和 UI 表格呈现；重复、阶段枚举、日期错误也都有行级可操作信息。
- 每个 422 都独立核对 response code、恰一条预期 Chromium 422 console、pageerror 零增量；commit 保持禁用、R10 请求数不增、四张 timeline 表 hash 不变。
- 多 sheet 只读第一 sheet 并提示；CSV 数字日期提示改用 `.xlsx`；状态重算提示可见。

## R11 与跨 workspace 往返

- 导出严格为 POST，返回真实 JSON `content_base64 + sha256`。
- 服务端 sha256、Python 独立 hashlib、浏览器 WebCrypto 三者一致；浏览器实际下载 bytes 与服务端 base64 解码 bytes 完全相等。
- 真实下载文件在新 workspace 经 file chooser 重新上传，R09→R10 均为 201；随后 R01 回读包含原项目/节点语义与已导入项目/节点语义。

## B38 文件安全

- 1000 数据行且单格恰 10k 的合法 XLSX preview 成功。
- 九类真实文件负例全部 422：1.5MB 文件、12MB 解压、1001 行、10001 字符、公式、宏、外链、严格八列表头错序/名称、重复表头。
- 所有拒绝均禁用 commit、无 R10、四表内容 hash 零变化。

## 浏览器硬门与隔离

- 所有按钮使用 scroll → fresh box → viewport assert → 真实 mouse down/up；file chooser 使用真实选择器流程。
- bad/good swallowed-click canary 正确区分。首轮 canary 无固定 hit box 且断言无 detail，记为 `CP5_PLANNER_CANARY_HITBOX_DIAGNOSTIC` fixture；固定独立 hit box 后复跑全绿，不计产品 failure。
- console/pageerror 最终全零；真实 `flowboard.db` 与 `.copilot-*` 指纹不变。

## 当前哈希与回归

- `app.js`: `FF3BF78E18DE54C62AB81B95E144CD409F127D5053E9D3F9A976218D9C4D4C47`
- `timeline-ui.js`: `436167262465366B97EAD535FA0C3E6B9AB6C98712CA949EEFA299854F15071C`
- `timeline.css`: `48C749FD2FB8D478614970DB7DB7A89FD2300E3603A17C2C9B36A8F78D74D278`
- `tests/timeline_ui.test.js`: `1F64BE20DD97289007EE32A3D9CDEA3000D2A86868733E97A8405C96B798E6F2`
- `tests/test_timeline_e2e.py`: `559DB55B627223F1FA3CB3564A34542F600C7B0A109F77BBA5C383709ED463B9`
- planner probe: `B3CE3F9C28546CA5DDD2056C47877D880580655D36A7FF6C4A3315CF14BA688B`
- coder E2E 21/21、Node 24/24、HTTP 10/10、timeline 29/29，全绿。

本签注不提前验收 CP6，不触碰 B-005、发布、commit 或真实库迁移。
