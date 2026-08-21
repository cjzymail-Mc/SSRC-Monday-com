# B-005 CP4 主 Codex 验收报告

日期：2026-08-20
模式：主 Codex 单 session；最终独立签注保留给 CP6。

CP4 验证器一次 exit 0。D1–D4 矩阵已逐行绑定 B-002/B-003/B-004 正式报告、B-004 独立 Chromium stdout、B-005 CP1/CP2/CP3 动态报告和可复跑验证器。

特别纠偏：CP1 的“17 个旧测试 blob 完全相同”已被用户后续授权的 schema v16 最小修正超越。CP4 没有沿用过期口径，而是重新证明：旧文件全在、旧方法 79/79 不变、无 skip，变化精确限定于 8 个 Python 文件的当前 schema/备份前缀常量化，所有历史 version/checksum/数据/FK/integrity/权限断言保留。

范围排除审计也通过：没有暗色运行态/主题切换、周看板、timeline rename/restore、md/json 导入、`project_ids` 导出或冻结外未来业务能力。

证据：

- `team-progress/verification/B-005-CP4/verify_cp4.py`
- `team-progress/verification/B-005-CP4/evidence-matrix.md`
- `team-progress/verification/B-005-CP4/results.md`

**结论：CP4 PASS；允许进入 CP5。**
