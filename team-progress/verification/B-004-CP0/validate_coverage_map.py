from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_IDS = [f"B{i:02d}" for i in range(1, 39)]
LEGAL = {"PASS", "GAP-B004", "CONFLICT", "OUT-OF-SCOPE"}
CP_BY_ID = {
    **{f"B{i:02d}": "CP1" for i in range(1, 6)},
    **{f"B{i:02d}": "CP2" for i in range(6, 15)},
    **{f"B{i:02d}": "CP3" for i in range(15, 22)},
    **{f"B{i:02d}": "CP4" for i in range(22, 30)},
    **{f"B{i:02d}": "CP5" for i in range(30, 36)},
    "B36": "CP6",
    "B37": "CP3",
    "B38": "CP5",
}

SEMANTIC_KEYS = {
    "B37": (
        ("`create`",), ("新增节点",),
        ("`remove`",), ("软删节点",), ("不得硬删",),
        ("batch",), ("刷新",),
    ),
    "B38": (
        ("1.5MB",), ("12MB",), ("1000",), ("10k",),
        ("公式",), ("宏",), ("外链",), ("严格",), ("8 列",),
        ("不进入 preview/commit",),
    ),
}


def existing_test_names() -> set[str]:
    names: set[str] = set()
    for p in (ROOT / "tests").glob("test*.py"):
        names.update(re.findall(r"\bdef\s+(test_[A-Za-z0-9_]+)\s*\(", p.read_text(encoding="utf-8")))
    node = ROOT / "tests" / "timeline_ui.test.js"
    if node.exists():
        names.update(re.findall(r"\btest\s*\(\s*['\"]([^'\"]+)", node.read_text(encoding="utf-8")))
    return names


def validate(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines():
        m = re.match(r"^\| (B\d{2}) \|(.+)\|$", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 6:
            continue
        ident, clause, entry, evidence, status, slot = cells
        rows[ident] = {"clause": clause, "entry": entry, "evidence": evidence, "status": status, "slot": slot}

    errors: list[str] = []
    ids = sorted(rows)
    missing = [x for x in EXPECTED_IDS if x not in rows]
    extra = [x for x in ids if x not in EXPECTED_IDS]
    if missing:
        errors.append("MISSING_MAPPING:" + ",".join(missing))
    if extra:
        errors.append("EXTRA_MAPPING:" + ",".join(extra))

    tests = existing_test_names()
    counts = {s: 0 for s in sorted(LEGAL)}
    for ident, row in rows.items():
        status = row["status"]
        if status not in LEGAL:
            errors.append(f"ILLEGAL_STATUS:{ident}:{status}")
            continue
        counts[status] += 1
        slot = row["slot"]
        cps = re.findall(r"\bCP[1-6]\b", slot)
        if len(cps) != 1 or cps[0] != CP_BY_ID.get(ident):
            errors.append(f"CP_OWNERSHIP:{ident}:{cps}")
        named = re.findall(r"`(test_[A-Za-z0-9_]+)`", slot)
        if not named:
            errors.append(f"FUTURE_SLOT_MISSING:{ident}")
        if status == "PASS":
            absent = [n for n in named if n not in tests]
            if absent:
                errors.append(f"TEST_NOT_FOUND:{ident}:{','.join(absent)}")
        elif named and any(n in tests for n in named):
            errors.append(f"NONPASS_REFERENCES_EXISTING_TEST:{ident}")

        if ident in SEMANTIC_KEYS:
            clause = row["clause"]
            for alternatives in SEMANTIC_KEYS[ident]:
                if not any(key in clause for key in alternatives):
                    errors.append(f"SEMANTIC_KEY_MISSING:{ident}:{'/'.join(alternatives)}")

    if counts["PASS"] != 0:
        errors.append(f"STATIC_ONLY_AS_PASS:{counts['PASS']}")
    return {"ok": not errors, "row_count": len(rows), "status_counts": counts, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("map", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = validate(args.map)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
