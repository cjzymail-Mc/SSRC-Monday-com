#!/usr/bin/env python3
"""Run isolated positive controls and database immutability check for CP0."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from verify_b003_cp0 import validate


ROOT = Path(__file__).resolve().parents[3]
MAP = ROOT / "team-progress" / "B-003-coverage-map.md"
TESTS = ROOT / "tests" / "test_timeline.py"
DB = ROOT / "flowboard.db"


def db_snapshot() -> dict:
    stat = DB.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(DB.read_bytes()).hexdigest(),
    }


def main() -> int:
    before = db_snapshot()
    source = MAP.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="flowboard-b003-map-control-") as td:
        temp = Path(td)
        missing_route = temp / "missing-route.md"
        fake_test = temp / "fake-test.md"

        lines = source.splitlines()
        removed = False
        kept = []
        for line in lines:
            if not removed and line.startswith("| 2 | GET | `/api/timeline/projects/{id}`"):
                removed = True
                continue
            kept.append(line)
        missing_route.write_text("\n".join(kept) + "\n", encoding="utf-8")
        fake_test.write_text(
            source.replace(
                "TimelineCoreTests.test_group1_unauthenticated_http_401",
                "TimelineCoreTests.test_http_name_that_does_not_exist",
                1,
            ),
            encoding="utf-8",
        )

        missing_result = validate(missing_route, TESTS)
        fake_result = validate(fake_test, TESTS)

    after = db_snapshot()
    missing_keys = [f["failure_key"] for f in missing_result["failures"]]
    fake_keys = [f["failure_key"] for f in fake_result["failures"]]
    result = {
        "result": "PASS" if "ROUTE_MISSING" in missing_keys and "TEST_NOT_FOUND" in fake_keys and before == after else "REWORK",
        "missing_route_control": {"validator_result": missing_result["result"], "failure_keys": missing_keys},
        "fake_test_control": {"validator_result": fake_result["result"], "failure_keys": fake_keys},
        "flowboard_db_before": before,
        "flowboard_db_after": after,
        "flowboard_db_unchanged": before == after,
        "temporary_inputs_cleaned": True,
    }
    output = ROOT / "team-progress" / "verification" / "B-003-CP0" / "controls-result.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
