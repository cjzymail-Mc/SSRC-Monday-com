import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAP = ROOT / "team-progress" / "B-004-coverage-map.md"
E2E = ROOT / "tests" / "test_timeline_e2e.py"

map_text = MAP.read_text(encoding="utf-8")
tree = ast.parse(E2E.read_text(encoding="utf-8"), filename=str(E2E))
actual = sorted({node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")})
references = sorted(set(re.findall(r"`(test_[A-Za-z0-9_]+)`", map_text)))
rows = sorted(set(re.findall(r"^\| (B\d{2}) \|", map_text, re.MULTILINE)))
missing = sorted(set(references) - set(actual))
b36_required = [
    "test_timeline_journey_edit_submit_refresh_undo",
    "test_timeline_journey_dashboards",
    "test_timeline_journey_import_export_reimport",
]

result = {
    "status": "PASS" if len(rows) == 38 and not missing else "REWORK",
    "failure_key": None if not missing else "B004_CP6_COVERAGE_TEST_REFERENCE_MISSING",
    "coverage_rows": len(rows),
    "coverage_ids": rows,
    "referenced_tests": len(references),
    "loadable_e2e_tests": len(actual),
    "resolved_references": sorted(set(references) & set(actual)),
    "missing_references": missing,
    "b36_required": b36_required,
    "b36_missing": sorted(set(b36_required) - set(actual)),
    "positive_control_fake_name_detected": "test_timeline_fake_positive_control" not in actual,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result["status"] == "PASS" else 1)
