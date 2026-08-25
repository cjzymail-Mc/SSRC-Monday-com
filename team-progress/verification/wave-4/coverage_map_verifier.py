# -*- coding: utf-8 -*-
"""Wave-4 rerun of the unchanged wave-3 deterministic verifier logic."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WAVE3 = HERE.parent / "wave-3" / "coverage_map_verifier.py"
TEAM_TASK = REPO / "team-task.md"
EXPECTED_HASHES = {
    "flowboard/timeline.py": "c9bd463da49d5517c7d44f213d929ada5d1d4fb08b7b2a5e36d9b963b75b6e2b",
    "tests/test_timeline.py": "8b30f9536b199f244c00438b706689074af0e403d2016a7905dba46a7a7221cf",
    "team-progress/B-002-coverage-map.md": "092e69c6c4b668c43915fdce30e5368bedb0ae8086e83e9d5771c2c0752da708",
}
EXPECTED_FREEZE = "4a83bfecf75b05c5bdbdc26d41dca7710e2e7867bc590a6a5027fa9fae901070"
CLARIFICATION_MARKERS = [
    "恢复澄清（2026-08-19",
    "范围外条款必须显式标为",
    "`GAP-非九项` 并绑定 B-003 候选去向",
    "删除一条映射",
    "伪造测试名",
]


def load_wave3():
    spec = importlib.util.spec_from_file_location("wave3_coverage_verifier", WAVE3)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load wave-3 verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def enriched_snapshot(core) -> dict:
    snap = core.snapshot()
    snap["team_task_sha256"] = core.sha256(TEAM_TASK)
    task = TEAM_TASK.read_text(encoding="utf-8")
    snap["clarification_markers"] = {
        marker: marker in task for marker in CLARIFICATION_MARKERS
    }
    return snap


def preflight(snapshot: dict) -> dict:
    actual = {key.replace("\\", "/"): value for key, value in snapshot["hashes"].items()}
    return {
        "hashes_match": actual == EXPECTED_HASHES,
        "expected_hashes": EXPECTED_HASHES,
        "actual_hashes": actual,
        "freeze_match": snapshot["freeze_sha256"] == EXPECTED_FREEZE,
        "clarification_complete": all(snapshot["clarification_markers"].values()),
        "team_task_sha256": snapshot["team_task_sha256"],
    }


def main() -> int:
    for path in (str(REPO), str(REPO / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    core = load_wave3()
    start = enriched_snapshot(core)
    start_gate = preflight(start)
    if not all((start_gate["hashes_match"], start_gate["freeze_match"],
                start_gate["clarification_complete"])):
        payload = {"baseline_start": start, "preflight": start_gate, "passed": False}
        (HERE / "coverage_map_verification.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 2

    map_text = core.MAP_PATH.read_text(encoding="utf-8")
    real = core.validate(map_text)

    deletion_lines = map_text.splitlines(keepends=True)
    delete_marker = "| 空 batch/correction 422 |"
    deleted = False
    for index, line in enumerate(deletion_lines):
        if delete_marker in line:
            del deletion_lines[index]
            deleted = True
            break
    deletion = core.validate("".join(deletion_lines)) if deleted else {
        "passed": False, "exit_code": 1,
        "failures": [{"key": "CONTROL_SETUP_FAILED"}],
    }

    original_test = "`test_import_headers_contract_literal`"
    fake_test = "`test_wave4_definitely_missing`"
    fake = core.validate(map_text.replace(original_test, fake_test, 1))
    controls = {
        "delete_one_mapping": {
            "mutated_in_memory_only": True,
            "exit_code": deletion["exit_code"],
            "failure_keys": [item["key"] for item in deletion["failures"]],
            "expected_failure_observed": (
                not deletion["passed"]
                and "MISSING_MAPPING" in [item["key"] for item in deletion["failures"]]
            ),
        },
        "replace_with_missing_test": {
            "mutated_in_memory_only": True,
            "exit_code": fake["exit_code"],
            "failure_keys": [item["key"] for item in fake["failures"]],
            "expected_failure_observed": (
                not fake["passed"]
                and "TEST_NOT_FOUND" in [item["key"] for item in fake["failures"]]
            ),
        },
    }

    end = enriched_snapshot(core)
    end_gate = preflight(end)
    baseline_stable = start == end
    controls_passed = all(item["expected_failure_observed"] for item in controls.values())
    overall_pass = (
        real["passed"] and controls_passed and baseline_stable
        and end_gate["hashes_match"] and end_gate["freeze_match"]
        and end_gate["clarification_complete"]
    )
    payload = {
        "verifier_source": str(WAVE3.relative_to(REPO)),
        "verifier_source_sha256": core.sha256(WAVE3),
        "baseline_start": start,
        "baseline_end": end,
        "preflight_start": start_gate,
        "preflight_end": end_gate,
        "baseline_stable": baseline_stable,
        "real_map": real,
        "positive_controls": controls,
        "controls_passed": controls_passed,
        "overall_pass": overall_pass,
    }
    (HERE / "coverage_map_verification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (HERE / "positive_controls.json").write_text(
        json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    event = {
        "event": "coverage_map_wave4",
        "real_passed": real["passed"],
        "real_exit_code": real["exit_code"],
        "failure_keys": [item["key"] for item in real["failures"]],
        "coverage": real["coverage"],
        "statuses": real["statuses"],
        "tests": {key: value for key, value in real["tests"].items()
                  if key != "load_results"},
        "positive_controls": controls,
        "baseline_stable": baseline_stable,
        "overall_pass": overall_pass,
    }
    (HERE / "run_console.json").write_text(
        json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(event, ensure_ascii=False))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
