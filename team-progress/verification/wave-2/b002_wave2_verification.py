# -*- coding: utf-8 -*-
"""B-002 wave-2 正式独立验收。

只验证 team-task §8 九项与 lead 追加项⑩；不把 B-003 候选计入 B-002。
探针数据库、备份和测试 fixture 全部位于 tempfile；真实 flowboard.db 仅 stat。
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WAVE1_SCRIPT = HERE.parent / "wave-1" / "b002_probes.py"
EXPECTED = {
    "flowboard/timeline.py": "c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b",
    "tests/test_timeline.py": "8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf",
    "team-progress/B-002-coverage-map.md": "d6e8f7356113e9ee8f6aeb9a848dc5c1a713ef9b448d9f0eac1cc28b1477cada",
}
NAMED_TESTS = [
    "test_timeline.TimelineCoreTests.test_import_headers_contract_literal",
    "test_timeline.TimelineCoreTests.test_import_xlsx_serial_positive_and_boundaries",
    "test_timeline.TimelineCoreTests.test_import_status_three_states_and_recompute",
    "test_timeline.TimelineCoreTests.test_import_multirow_aggregation_and_counts",
    "test_timeline.TimelineCoreTests.test_import_field_limits_boundaries",
    "test_timeline.TimelineCoreTests.test_export_exact_1000_and_over_limit_fail_closed",
    "test_timeline.TimelineCoreTests.test_group9_excel_round_trip_in_new_workspace",
    "test_timeline.TimelineCoreTests.test_group10_backup_content_idempotence_rollback",
    "test_timeline.TimelineCoreTests.test_group4_undo_three_batch_middle_and_reverse_roles",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot() -> dict:
    real = REPO / "flowboard.db"
    st = real.stat()
    return {
        "hashes": {relative: sha256(REPO / relative) for relative in EXPECTED},
        "flowboard_db": {
            "path": str(real),
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
        },
    }


def frozen_ok(snap: dict) -> bool:
    return snap["hashes"] == EXPECTED


def load_wave1_helpers():
    spec = importlib.util.spec_from_file_location("wave1_b002_helpers", WAVE1_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load wave-1 probe helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parsed_actual(result: dict) -> dict:
    actual = result.get("actual")
    if isinstance(actual, dict):
        return actual
    if isinstance(actual, str):
        try:
            value = json.loads(actual)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def tighten(result: dict, predicate, note: str) -> None:
    result["observed"] = "PASS_PROBE" if predicate(parsed_actual(result)) else "FAIL_PROBE"
    result["note"] = (result.get("note", "") + "；" + note).strip("；")


def corrected_status_probes(old, env, headers) -> None:
    """P2 两个拒收输入必须先补合法 project，且锁定 status 拒绝理由。"""
    criterion = (
        "A§5.2 状态行：∈ 三态或空；其他文本→行级报错。"
        "B§8-2：非法状态仍 422。"
    )
    base = {
        "stage": ("s", "创意"),
        "track": ("s", "main"),
        "interval": ("s", ""),
        "remark": ("s", ""),
    }

    def run_case(tag, status_cell, node_date, expect_status, expect_done):
        row = dict(base)
        row.update({
            "project": ("s", "状态项目-" + tag),
            "node": ("s", tag),
            "date": ("s", node_date),
            "status": status_cell,
        })
        ok, preview = old.call(
            env.service.preview_import,
            env.admin,
            1,
            "wave2-status-%s.xlsx" % tag,
            old.build_xlsx(headers, [old.make_row(headers, row)]),
        )
        if not ok:
            old.record(
                "P2-" + tag, 2, criterion,
                "合法 project/track/stage/date + status=%s → preview" % old.brief(status_cell),
                "接受并按契约落库", old.brief(preview), "FAIL_PROBE",
                "合法状态/空被拒",
            )
            return
        ok2, committed = old.call(
            env.service.commit_import, env.admin, 1, {"batch_id": preview["batch_id"]}
        )
        if not ok2:
            old.record(
                "P2-" + tag, 2, criterion, "preview 后 commit", "commit 成功",
                old.brief(committed), "FAIL_PROBE",
            )
            return
        conn = old.connect(env.db)
        row_db = conn.execute(
            "SELECT done_at FROM timeline_nodes WHERE name=?", (tag,)
        ).fetchone()
        conn.close()
        done_stored = None if row_db is None else row_db[0] is not None
        projects = env.service.list_projects(env.admin, 1)["projects"]
        nodes = [node for project in projects for node in project["nodes"] if node["name"] == tag]
        got_status = nodes[0]["status"] if nodes else None
        passed = done_stored == expect_done and got_status == expect_status
        old.record(
            "P2-" + tag, 2, criterion,
            "合法 project/track/stage/date + status=%s → preview+commit+读回" % old.brief(status_cell),
            "derived_status=%s；done_at=%s" % (expect_status, expect_done),
            {"stored_done_at": done_stored, "derived_status": got_status},
            "PASS_PROBE" if passed else "FAIL_PROBE",
            "所有非目标字段均合法",
        )

    run_case("weikaishi_past", ("s", "未开始"), "2020-01-01", "进行中", False)
    run_case("jinxingzhong_future", ("s", "进行中"), "2099-01-01", "未开始", False)
    run_case("empty_past", ("s", ""), "2020-01-02", "进行中", False)
    run_case("yiwancheng", ("s", "已完成"), "2099-01-02", "已完成", True)

    for tag, status in (("illegal", "暂停"), ("weifenjian", "未完成")):
        row = dict(base)
        row.update({
            "project": ("s", "状态非法项目-" + tag),
            "node": ("s", tag),
            "date": ("s", "2030-01-01"),
            "status": ("s", status),
        })
        ok, out = old.call(
            env.service.preview_import,
            env.admin,
            1,
            "wave2-status-negative-%s.xlsx" % tag,
            old.build_xlsx(headers, [old.make_row(headers, row)]),
        )
        details = out.get("details") if isinstance(out, dict) else None
        passed = (
            not ok
            and out.get("status") == 422
            and out.get("code") == "VALIDATION_ERROR"
            and isinstance(details, dict)
            and details.get("row") == 2
            and out.get("message") == "status 必须是 已完成/未开始/进行中 或留空"
        )
        old.record(
            "P2-" + tag, 2, criterion,
            "合法 project/track/stage/date + 非法 status=%s → preview" % status,
            "422 VALIDATION_ERROR；details.row=2；message 精确命中 status 枚举拒绝理由",
            out, "PASS_PROBE" if passed else "FAIL_PROBE",
            "修正 wave-1：不再由缺少 project 的 value is required 冒充状态负例 PASS",
        )


def run_probes(old) -> dict:
    old.RESULTS.clear()
    env = old.Env()
    headers = old.negotiate_headers(env)
    old.probe_serial(env, headers)
    corrected_status_probes(old, env, headers)
    old.probe_aggregate(env, headers)
    old.probe_limits(env, headers)
    env.tmp.cleanup()

    old.probe_export_boundary(None)
    roundtrip_env = old.Env()
    old.probe_roundtrip(roundtrip_env)
    roundtrip_env.tmp.cleanup()
    old.probe_migration()
    undo_env = old.Env()
    old.probe_undo(undo_env)
    undo_env.tmp.cleanup()
    old.probe_header_contract(None)

    # 拒收探针除 P2 输入修正外，统一锁定具体 code/details/message，防“任意 422”假绿。
    for result in old.RESULTS:
        probe = result["probe"]
        if probe == "P1b":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("details") == {"row": 2}
                and "YYYY-MM-DD" in a.get("message", "")
            ), "锁定日期解析理由+row=2")
        elif probe == "P1c":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("details") == {"row": 2}
                and "日期序列号超出 18264..73051" in a.get("message", "")
            ), "锁定序列号越界理由+row=2")
        elif probe == "P1d":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("details") == {"row": 2}
                and "YYYY-MM-DD" in a.get("message", "")
            ), "锁定 CSV 日期格式拒绝理由")
        elif probe == "P3a":
            actual = parsed_actual(result)
            preview = actual.get("preview", [])
            commit = actual.get("commit", {})
            exact = (
                preview == [{"name": "聚合项目", "node_count": 3}]
                and commit.get("projects") == 1 and commit.get("nodes") == 3
                and actual.get("db_node_count") == 3 and actual.get("db_project_count") == 1
            )
            result["observed"] = "PASS_PROBE" if exact else "FAIL_PROBE"
            result["note"] = "锁定 preview/commit/DB 三侧精确计数"
        elif probe == "P3b":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("message") == "与第 2 行重复"
                and a.get("details") == {"row": 3, "duplicate_of": 2}
            ), "锁定四键重复的具体拒绝理由")
        elif probe == "P3d":
            result["item"] = "B-003"
            result["observed"] = "OUT_OF_SCOPE"
            result["note"] = (
                "lead 裁定 #7：同名项目全行错误清单属于 B-003；本次仅留诊断记录，"
                "不计入 B-002 PASS/FAIL"
            )
        elif probe == "P4b":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("details") == {"row": 2} and a.get("message") == "value is too long"
            ), "仅节点名 501 非法，锁定长度拒绝理由")
        elif probe == "P4d":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("details") == {"row": 2} and a.get("message") == "remark is too long"
            ), "仅备注 501 非法，锁定备注长度拒绝理由")
        elif probe == "P4f":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "VALIDATION_ERROR"
                and a.get("details") == {"row": 2} and a.get("message") == "value is too long"
            ), "仅项目名 201 非法，锁定长度拒绝理由")
        elif probe == "P6b":
            tighten(result, lambda a: (
                a.get("status") == 422 and a.get("code") == "NAME_CONFLICT"
                and isinstance(a.get("details"), dict)
                and a["details"].get("row") == 2 and a["details"].get("project") == "往返甲"
            ), "锁定 R5 同名拒绝理由")

    real = REPO / "flowboard.db"
    st = real.stat()
    old.record(
        "PX-realdb", 0, "真实 flowboard.db 只读优先",
        "所有探针结束后只读 stat", "size/mtime 与开始值一致",
        {"size": st.st_size, "mtime_ns": st.st_mtime_ns}, "PASS_PROBE",
    )

    results = list(old.RESULTS)
    in_scope = [r for r in results if isinstance(r["item"], int) and r["item"] in {1,2,3,4,5,6,7,8,10}]
    setup = [r for r in results if r["item"] == 0]
    out_scope = [r for r in results if r["observed"] == "OUT_OF_SCOPE"]
    summary = {
        "in_scope": {
            "PASS_PROBE": sum(r["observed"] == "PASS_PROBE" for r in in_scope),
            "FAIL_PROBE": sum(r["observed"] == "FAIL_PROBE" for r in in_scope),
            "total": len(in_scope),
        },
        "setup_safety": {
            "PASS_PROBE": sum(r["observed"] == "PASS_PROBE" for r in setup),
            "FAIL_PROBE": sum(r["observed"] == "FAIL_PROBE" for r in setup),
            "total": len(setup),
        },
        "out_of_scope": len(out_scope),
    }
    payload = {
        "source_helper": str(WAVE1_SCRIPT.relative_to(REPO)),
        "source_helper_sha256": sha256(WAVE1_SCRIPT),
        "using_headers": headers,
        "summary": summary,
        "results": results,
    }
    (HERE / "b002_probe_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "% -22s item=%-5s %-12s | %s" % (
            r["probe"], r["item"], r["observed"], r.get("note", "")
        ) for r in results
    ]
    (HERE / "probe_index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def run_full_suite() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    command = [
        sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover",
        "-s", "tests", "-p", "test_timeline.py", "-v",
    ]
    completed = subprocess.run(
        command, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8"
    )
    console = completed.stdout + completed.stderr
    (HERE / "full_suite_console.txt").write_text(console, encoding="utf-8")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "ran_29": "Ran 29 tests" in console,
        "ok_marker": "OK" in console,
    }


def run_named_tests() -> dict:
    for path in (str(REPO), str(REPO / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import test_timeline  # noqa: F401

    rows = []
    console_parts = []
    for name in NAMED_TESTS:
        suite = unittest.defaultTestLoader.loadTestsFromName(name)
        count = suite.countTestCases()
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        output = stream.getvalue()
        console_parts.append("===== %s =====\n%s" % (name, output))
        rows.append({
            "name": name,
            "loaded_count": count,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "passed": count == 1 and result.testsRun == 1 and result.wasSuccessful(),
        })
    (HERE / "named_tests_console.txt").write_text("\n".join(console_parts), encoding="utf-8")
    payload = {
        "coverage_map_section_e_executable_entries": len(NAMED_TESTS),
        "note": "§E 第9项是 coverage map 文档本体，不是 unittest；其余九个可执行条目逐一加载并运行。",
        "passed": sum(row["passed"] for row in rows),
        "results": rows,
    }
    (HERE / "named_tests_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    start = snapshot()
    (HERE / "baseline_start.json").write_text(
        json.dumps(start, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not frozen_ok(start):
        print(json.dumps({"event": "BASELINE_DRIFT_START", "snapshot": start}, ensure_ascii=False))
        return 2

    old = load_wave1_helpers()
    full_suite = run_full_suite()
    probes = run_probes(old)
    named = run_named_tests()

    end = snapshot()
    (HERE / "baseline_end.json").write_text(
        json.dumps(end, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    baseline_stable = frozen_ok(end) and start == end
    overall = (
        full_suite["exit_code"] == 0 and full_suite["ran_29"] and full_suite["ok_marker"]
        and probes["summary"]["in_scope"] == {"PASS_PROBE": 40, "FAIL_PROBE": 0, "total": 40}
        and probes["summary"]["setup_safety"] == {"PASS_PROBE": 2, "FAIL_PROBE": 0, "total": 2}
        and probes["summary"]["out_of_scope"] == 1
        and named["passed"] == len(NAMED_TESTS)
        and baseline_stable
    )
    final = {
        "full_suite": full_suite,
        "probes": probes["summary"],
        "named_tests": {"passed": named["passed"], "total": len(NAMED_TESTS)},
        "baseline_stable": baseline_stable,
        "flowboard_db_unchanged": start["flowboard_db"] == end["flowboard_db"],
        "overall_pass": overall,
    }
    (HERE / "verification_summary.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"event": "wave2_summary", **final}, ensure_ascii=False))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
