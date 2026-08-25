"""Import a real timeline workbook into Flowboard's isolated trial DB.

The source workbook is opened through ``zipfile`` only and is never written.
Generated files are prefixed with ``测试数据-`` and the database target defaults
to the same %TEMP% database used by ``start-gate5-trial.cmd``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS}
TEST_PREFIX = "[真实表] "
OUTPUT_XLSX = "测试数据-Flowboard标准时间表.xlsx"
OUTPUT_MANIFEST = "测试数据-提取清单.json"


STRUCTURED_SECTIONS = {
    "26Q4（8项+1同步）": [
        {"project_col": 5, "node_header": 2, "start": 3, "end": 30, "fallback": "2025-11-01"},
    ],
    "27Q1-Q4（7项+3同步）": [
        {"project_col": 6, "node_header": 3, "start": 4, "end": 22, "fallback": "2025-08-01"},
        {"project_col": 6, "node_header": 26, "start": 27, "end": 56, "fallback": "2025-12-01"},
        {"project_col": 6, "node_header": 60, "start": 61, "end": 72, "fallback": "2026-01-01"},
        {"project_col": 6, "node_header": 76, "start": 77, "end": 84, "fallback": "2026-03-01"},
        {"project_col": 6, "node_header": 88, "start": 89, "end": 98, "fallback": "2026-04-01"},
        {"project_col": 6, "node_header": 102, "start": 103, "end": 118, "fallback": "2026-06-01"},
        {"project_col": 6, "node_header": 125, "start": 126, "end": 133, "fallback": "2026-08-01"},
    ],
    "28Q1-28Q2": [
        {"project_col": 6, "node_header": 3, "start": 4, "end": 7, "fallback": "2026-06-01"},
    ],
    "26Q2": [
        {"project_col": 3, "node_header": 2, "start": 3, "end": 14, "fallback": "2025-10-01"},
    ],
}


def source_workbook(folder: Path) -> Path:
    files = [path for path in folder.glob("*.xlsx") if not path.name.startswith("测试数据-")]
    if len(files) != 1:
        raise RuntimeError(f"expected one source workbook, found {len(files)}")
    return files[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def column_index(reference: str) -> int:
    match = re.match(r"[A-Z]+", reference)
    if not match:
        raise ValueError(f"invalid cell reference: {reference}")
    value = 0
    for letter in match.group(0):
        value = value * 26 + ord(letter) - 64
    return value


def cell_value(cell: ET.Element, shared: list[str]):
    cell_type = cell.attrib.get("t")
    value_node = cell.find("m:v", NS)
    raw = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s":
        if not raw:
            return ""
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    if cell_type == "inlineStr":
        inline = cell.find("m:is", NS)
        return "" if inline is None else "".join(node.text or "" for node in inline.iter(f"{{{MAIN_NS}}}t"))
    if cell_type == "b":
        return raw == "1"
    return raw


def read_workbook(path: Path) -> list[dict]:
    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")) for item in root]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        sheets: list[dict] = []
        for sheet in workbook.find("m:sheets", NS):
            target = targets[sheet.attrib[f"{{{REL_NS}}}id"]].lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            root = ET.fromstring(archive.read(target))
            rows: list[dict] = []
            for row in root.findall(".//m:sheetData/m:row", NS):
                cells: dict[int, object] = {}
                for cell in row.findall("m:c", NS):
                    index = column_index(cell.attrib["r"])
                    value = cell_value(cell, shared)
                    if value not in (None, "") or cell.find("m:f", NS) is not None:
                        cells[index] = value
                if cells:
                    rows.append({"row": int(row.attrib["r"]), "cells": cells})
            dimension = root.find("m:dimension", NS)
            sheets.append(
                {
                    "name": sheet.attrib["name"],
                    "dimension": dimension.attrib.get("ref") if dimension is not None else None,
                    "rows": rows,
                }
            )
        return sheets


def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def project_key(value: str) -> str:
    # Source sheets alternate between "项目(负责人)" and "项目 负责人".
    # Ignore spacing/punctuation while retaining letters, digits and CJK text.
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value), flags=re.UNICODE).casefold()


def serial_date(value) -> str | None:
    text = clean_text(value)
    if not re.fullmatch(r"\d+(?:\.0+)?", text):
        return None
    serial = int(float(text))
    if serial < 18264 or serial > 73051:
        return None
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()


def stage_for(text: str) -> str:
    if any(word in text for word in ("试穿", "报告", "测试")):
        return "测试"
    if any(word in text for word in ("量产", "下单", "订货", "转色", "配色到样")):
        return "量产"
    if any(word in text for word in ("草图", "图纸", "转图", "AI", "ai", "设计", "配色趋势")):
        return "设计"
    return "开发"


def track_for(text: str) -> str:
    return "parallel" if any(word in text for word in ("鞋底", "木模", "模具", "试穿", "报告", "中底", "开底")) else "main"


def new_project(name: str, source: str) -> dict:
    return {"name": clean_text(name), "sources": {source}, "nodes": [], "node_keys": set(), "fallback_nodes": 0}


def add_project(projects: OrderedDict, name: str, source: str) -> dict:
    name = clean_text(name)
    key = project_key(name)
    if key not in projects:
        projects[key] = new_project(name, source)
    else:
        projects[key]["sources"].add(source)
    return projects[key]


def add_node(project: dict, *, date: str, name: str, status: str, remark: str, fallback: bool = False) -> None:
    node_name = clean_text(name)[:500] or "源表节点"
    track = track_for(node_name + remark)
    key = (track, date, node_name)
    if key in project["node_keys"]:
        return
    project["node_keys"].add(key)
    project["nodes"].append(
        {
            "stage": stage_for(node_name + remark),
            "track": track,
            "name": node_name,
            "date": date,
            "status": status,
            "remark": clean_text(remark)[:500],
        }
    )
    if fallback:
        project["fallback_nodes"] += 1


def is_anchor(cells: dict, project_col: int) -> bool:
    name = clean_text(cells.get(project_col))
    if not name or any(token in name for token in ("实际", "调整", "款项")):
        return False
    if name in {"冬季版", "功能定版已结束款项"}:
        return False
    return any(clean_text(cells.get(column)) for column in range(1, project_col))


def structured_remark(sheet: str, cells: dict, project_col: int) -> str:
    labels = ["状态", "工厂", "货号", "底模号", "楦头号"] if project_col == 6 else ["工厂", "货号", "底模号", "楦头号"]
    values = []
    for column in range(1, project_col):
        value = clean_text(cells.get(column))
        if value:
            label = labels[column - 1] if column - 1 < len(labels) else f"字段{column}"
            values.append(f"{label}:{value}")
    return f"源工作表:{sheet}" + ("; " + "; ".join(values) if values else "")


def extract_structured(sheet: dict, projects: OrderedDict) -> None:
    by_row = {row["row"]: row["cells"] for row in sheet["rows"]}
    for config in STRUCTURED_SECTIONS[sheet["name"]]:
        anchors = [
            row_number
            for row_number in range(config["start"], config["end"] + 1)
            if is_anchor(by_row.get(row_number, {}), config["project_col"])
        ]
        for anchor_index, row_number in enumerate(anchors):
            block_end = anchors[anchor_index + 1] - 1 if anchor_index + 1 < len(anchors) else config["end"]
            block = [by_row.get(number, {}) for number in range(row_number, block_end + 1)]
            base = block[0]
            project = add_project(projects, base[config["project_col"]], sheet["name"])
            remark = structured_remark(sheet["name"], base, config["project_col"])
            headers = by_row.get(config["node_header"], {})
            before = len(project["nodes"])
            for column, raw_header in sorted(headers.items()):
                if column <= config["project_col"]:
                    continue
                header = clean_text(raw_header)
                if not header or any(word in header for word in ("备注", "预留", "款项")):
                    continue
                candidates = []
                for offset, cells in enumerate(block):
                    date = serial_date(cells.get(column))
                    if not date:
                        continue
                    labels = " ".join(clean_text(value) for value in cells.values())
                    priority = 2 if "实际" in labels else (1 if "调整" in labels else 0)
                    candidates.append((priority, offset, date))
                if not candidates:
                    continue
                priority, _, date = max(candidates)
                add_node(
                    project,
                    date=date,
                    name=header,
                    status="已完成" if priority == 2 else "未开始",
                    remark=remark,
                )
            if len(project["nodes"]) == before:
                add_node(
                    project,
                    date=config["fallback"],
                    name="源表占位节点",
                    status="未开始",
                    remark=f"{remark}; 原表该项目未提供可识别的 Excel 日期序列,仅用于仪表盘测试",
                    fallback=True,
                )


DATE_TOKEN = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])[./](3[01]|[12]\d|0?[1-9])(?![.\d])")


def narrative_year(sheet_name: str, row_number: int, month: int) -> int:
    if sheet_name.startswith("26年"):
        return 2025
    if row_number <= 15 and month >= 10:
        return 2025
    return 2026


def narrative_project_name(value: object) -> str | None:
    name = clean_text(value)
    if not name or name == "/" or name.startswith(("QD-", "QR-")):
        return None
    if "专项产品" in name or "进度状况" in name:
        return None
    if re.fullmatch(r"\d{4}-\d{4}", name) or re.match(r"^\d{2}年.*项目$", name):
        return None
    return name


def dates_in_text(text: str, sheet_name: str, row_number: int) -> list[str]:
    result = []
    for match in DATE_TOKEN.finditer(text):
        month, day = int(match.group(1)), int(match.group(2))
        try:
            value = datetime(narrative_year(sheet_name, row_number, month), month, day).date().isoformat()
        except ValueError:
            continue
        if value not in result:
            result.append(value)
    return result


def extract_narrative(sheet: dict, projects: OrderedDict) -> None:
    current_fallback = "2025-11-07"
    for row in sheet["rows"]:
        row_number = row["row"]
        cells = row["cells"]
        first = clean_text(cells.get(1))
        if re.fullmatch(r"\d{4}-\d{4}", first):
            current_fallback = "2026-01-04"
            continue
        if re.match(r"^\d{2}年.*项目$", first):
            current_fallback = "2026-04-20"
            continue
        name = narrative_project_name(cells.get(1))
        if not name:
            continue
        project = add_project(projects, name, sheet["name"])
        before = len(project["nodes"])
        for column in sorted(column for column in cells if column > 1):
            text = clean_text(cells[column])
            if not text or text == "/":
                continue
            dates = dates_in_text(text, sheet["name"], row_number)
            if not dates:
                continue
            for date in dates:
                node_text = next(
                    (clean_text(line) for line in str(cells[column]).splitlines() if date[5:].replace("-", ".") in line),
                    clean_text(str(cells[column]).splitlines()[0]),
                )
                done = any(word in node_text for word in ("已", "完成", "结束", "通过", "签开", "到达", "送达", "确认"))
                add_node(
                    project,
                    date=date,
                    name=node_text,
                    status="已完成" if done else "进行中",
                    remark=f"源工作表:{sheet['name']}; {text}",
                )
        if len(project["nodes"]) == before:
            add_node(
                project,
                date=current_fallback,
                name="专项进展占位节点",
                status="未开始",
                remark=f"源工作表:{sheet['name']}; 原表保留了项目名称但未提供可识别的节点日期,仅用于仪表盘测试",
                fallback=True,
            )


def extract_projects(sheets: list[dict]) -> OrderedDict:
    projects: OrderedDict[str, dict] = OrderedDict()
    for sheet in sheets:
        if sheet["name"] in STRUCTURED_SECTIONS:
            extract_structured(sheet, projects)
        elif "专项现况进展记录" in sheet["name"]:
            extract_narrative(sheet, projects)
    for project in projects.values():
        project["nodes"].sort(key=lambda node: (node["date"], node["track"], node["name"]))
    return projects


def import_rows(projects: OrderedDict, *, only_names: set[str] | None = None) -> list[list[str]]:
    rows = []
    for project in projects.values():
        output_name = TEST_PREFIX + project["name"]
        if only_names is not None and output_name not in only_names:
            continue
        for node in project["nodes"]:
            rows.append(
                [output_name, node["stage"], node["track"], node["name"], node["date"], "", node["status"], node["remark"]]
            )
    return rows


def ensure_trial_db(repo_root: Path, trial_db: Path) -> None:
    if not trial_db.exists():
        source_db = repo_root / "flowboard.db"
        if not source_db.is_file():
            raise RuntimeError(f"real database not found for isolated copy: {source_db}")
        trial_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_db, trial_db)
    from flowboard.database import migrate

    migrate(trial_db)


def active_names(db_path: Path, workspace_id: int) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL", (workspace_id,)
            )
        }
    finally:
        connection.close()


def project_ids(db_path: Path, workspace_id: int) -> dict[str, int]:
    connection = sqlite3.connect(db_path)
    try:
        return {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name,id FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL", (workspace_id,)
            )
        }
    finally:
        connection.close()


def seed_trial(repo_root: Path, trial_db: Path, projects: OrderedDict) -> dict:
    ensure_trial_db(repo_root, trial_db)
    from flowboard.timeline import IMPORT_HEADERS, TimelineService
    from flowboard.transfer import make_xlsx

    user = {"id": "u1"}
    workspace_id = 1
    service = TimelineService(trial_db)
    desired = {TEST_PREFIX + project["name"] for project in projects.values()}
    existing = active_names(trial_db, workspace_id)
    missing = desired - existing
    result = {"projects_created": 0, "nodes_created": 0, "projects_reused": len(desired - missing)}
    if missing:
        raw = make_xlsx(IMPORT_HEADERS, import_rows(projects, only_names=missing), sheet="Timeline")
        preview = service.preview_import(user, workspace_id, OUTPUT_XLSX, raw)
        committed = service.commit_import(user, workspace_id, {"batch_id": preview["batch_id"]})
        result.update({"projects_created": committed["projects"], "nodes_created": committed["nodes"]})

    ids = project_ids(trial_db, workspace_id)
    tags = {item["name"]: item for item in service.list_tags(user, workspace_id)["tags"]}
    memberships_added = 0
    sources = {source for project in projects.values() for source in project["sources"]}
    for source_name in sorted(sources):
        tag_name = source_name[:80]
        tag = tags.get(tag_name)
        legacy_name = f"真实表·{source_name}"[:80]
        if not tag and legacy_name in tags:
            legacy = tags[legacy_name]
            tag = service.rename_tag(
                user,
                workspace_id,
                legacy["tag_id"],
                {"name": tag_name, "base_version": legacy["version"]},
            )
            tags.pop(legacy_name)
            tags[tag_name] = tag
        if not tag:
            tag = service.create_tag(user, workspace_id, {"name": tag_name})
            tags[tag_name] = tag
        view = service.get_tag_projects(user, workspace_id, tag["tag_id"])
        included = {item["project_id"] for item in view["included"]}
        version = view["tag"]["version"]
        for project in projects.values():
            if source_name not in project["sources"]:
                continue
            project_id = ids[TEST_PREFIX + project["name"]]
            if project_id in included:
                continue
            view = service.set_tag_project(
                user,
                workspace_id,
                tag["tag_id"],
                project_id,
                {"base_tag_version": version},
                included=True,
            )
            version = view["tag"]["version"]
            included.add(project_id)
            memberships_added += 1
    result["tag_count"] = len(sources)
    result["tag_memberships_added"] = memberships_added
    return result


def inspect(path: Path) -> None:
    sheets = read_workbook(path)
    payload = {
        "source": path.name,
        "size": path.stat().st_size,
        "sheets": [
            {"name": sheet["name"], "dimension": sheet["dimension"], "nonempty_rows": len(sheet["rows"])} for sheet in sheets
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true", help="print source workbook metadata only")
    parser.add_argument("--extract-only", action="store_true", help="generate the standard workbook without seeding")
    parser.add_argument("--trial-db", type=Path, help="override the isolated trial database path")
    args = parser.parse_args()

    folder = Path(__file__).resolve().parent
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    source = source_workbook(folder)
    source_hash_before = sha256(source)
    if args.inspect:
        inspect(source)
        return 0

    sheets = read_workbook(source)
    projects = extract_projects(sheets)
    if not projects:
        raise RuntimeError("no projects extracted")

    from flowboard.timeline import IMPORT_HEADERS
    from flowboard.transfer import make_xlsx

    rows = import_rows(projects)
    standard_xlsx = make_xlsx(IMPORT_HEADERS, rows, sheet="Timeline")
    output_xlsx = folder / OUTPUT_XLSX
    output_xlsx.write_bytes(standard_xlsx)
    trial_db = (args.trial_db or Path(tempfile.gettempdir()) / "flowboard-gate5-trial" / "flowboard-trial.db").resolve()
    import_result = None if args.extract_only else seed_trial(repo_root, trial_db, projects)
    source_hash_after = sha256(source)
    if source_hash_after != source_hash_before:
        raise RuntimeError("source workbook hash changed unexpectedly")

    manifest = {
        "source": source.name,
        "source_size": source.stat().st_size,
        "source_sha256_before": source_hash_before,
        "source_sha256_after": source_hash_after,
        "source_unchanged": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "standard_workbook": output_xlsx.name,
        "project_count": len(projects),
        "node_count": len(rows),
        "fallback_node_count": sum(project["fallback_nodes"] for project in projects.values()),
        "projects": [
            {
                "name": TEST_PREFIX + project["name"],
                "node_count": len(project["nodes"]),
                "source_sheets": sorted(project["sources"]),
                "fallback_node_count": project["fallback_nodes"],
            }
            for project in projects.values()
        ],
        "trial_db": None if args.extract_only else str(trial_db),
        "import_result": import_result,
    }
    (folder / OUTPUT_MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: manifest[key] for key in ("source_unchanged", "project_count", "node_count", "fallback_node_count", "trial_db", "import_result")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
