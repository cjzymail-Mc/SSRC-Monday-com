import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from .database import connect, transaction, utc_now
from .service import ApiError, reject_unknown, require_int, require_text, validate_choice
from .transfer import MAX_ROWS, XlsxNumericCell, make_xlsx, parse_upload


TRACKS = ("main", "parallel")
STAGES = ("创意", "设计", "开发", "测试", "量产", "应用迭代")
IMPORT_HEADERS = ["项目名称", "阶段", "主线/并行", "节点", "日期", "状态", "备注"]
INTERVAL_IMPORT_HEADERS = ["项目名称", "阶段", "主线/并行", "节点", "日期", "间隔", "状态", "备注"]
LEGACY_IMPORT_HEADERS = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
LEGACY_NO_INTERVAL_IMPORT_HEADERS = ["项目名称", "阶段", "轨道", "节点", "日期", "状态", "备注"]
IMPORT_TRACKS = {"main": "main", "parallel": "parallel", "主线": "main", "并行": "parallel"}
EXPORT_TRACKS = {"main": "主线", "parallel": "并行"}
IMPORT_STATUSES = ("已完成", "未开始", "进行中")
SERIAL_MIN = 18264  # 1950-01-01（1899-12-30 基准，避开 1900 纪元闰年 bug 区）
SERIAL_MAX = 73051  # 2100-01-01
SET_FIELDS = {"date", "interval_days", "done_at", "track", "stage", "name", "remark"}
CREATE_FIELDS = {"track", "stage", "name", "date", "done_at", "remark"}


def _serial_to_date(serial):
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date()


def _natural_key(value):
    return [
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in __import__("re").split(r"(\d+)", value)
        if part
    ]


class TimelineService:
    def __init__(self, db_path):
        self.db_path = db_path

    def _db(self):
        return connect(self.db_path)

    @staticmethod
    def _project_access(conn, user_id, project_id, *, workspace_id=None, write=False, require_active=False, allow_archived=False):
        row = conn.execute(
            """SELECT p.*, wm.role FROM timeline_projects p
               JOIN workspace_memberships wm ON wm.workspace_id=p.workspace_id AND wm.user_id=?
               WHERE p.id=? AND (? IS NULL OR p.workspace_id=?)""",
            (user_id, project_id, workspace_id, workspace_id),
        ).fetchone()
        if not row or row["role"] == "viewer":
            raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
        if write and row["role"] != "admin" and row["created_by"] != user_id:
            raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
        if require_active and row["deleted_at"]:
            raise ApiError(404, "PROJECT_NOT_ACTIVE", "项目当前不可用")
        if write and row["archived_at"] and not allow_archived:
            raise ApiError(409, "PROJECT_ARCHIVED", "项目已归档；请先取消归档再编辑")
        return row

    @staticmethod
    def _workspace_access(conn, user_id, workspace_id):
        role = conn.execute(
            "SELECT role FROM workspace_memberships WHERE workspace_id=? AND user_id=?",
            (workspace_id, user_id),
        ).fetchone()
        if not role or role["role"] == "viewer":
            raise ApiError(403, "PROJECT_FORBIDDEN", "资源不存在或不可访问")
        return role["role"]

    @staticmethod
    def _parse_date(value, field):
        if not isinstance(value, str):
            raise ApiError(422, "VALIDATION_ERROR", f"{field} must be YYYY-MM-DD")
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", f"{field} must be a valid YYYY-MM-DD date")

    @staticmethod
    def _server_today():
        return datetime.now(timezone(timedelta(hours=8))).date()

    def _nodes(self, conn, project_id):
        rows = conn.execute(
            "SELECT * FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL",
            (project_id,),
        ).fetchall()
        return sorted(rows, key=lambda row: (row["date"], _natural_key(row["name"]), row["id"]))

    def _chain(self, nodes, track):
        return [node for node in nodes if node["track"] == track]

    @staticmethod
    def _date(value):
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _view(self, conn, project, *, user_id=None, role=None):
        nodes = self._nodes(conn, project["id"])
        today = self._server_today()
        payloads = []
        intervals = {}
        segments = []
        stage_intervals = []
        for track in TRACKS:
            chain = self._chain(nodes, track)
            previous = None
            for node in chain:
                interval = None if previous is None else (self._date(node["date"]) - self._date(previous["date"])).days
                intervals[node["id"]] = interval
                next_node = chain[chain.index(node) + 1] if chain.index(node) + 1 < len(chain) else None
                segments.append({
                    "track": track,
                    "start_node_id": node["id"],
                    "end_node_id": next_node["id"] if next_node else node["id"],
                    "start_date": node["date"],
                    "end_date": next_node["date"] if next_node else node["date"],
                    "stage": node["stage"],
                })
                previous = node
            runs = []
            for node in chain:
                if not runs or runs[-1][0]["stage"] != node["stage"]:
                    runs.append([])
                runs[-1].append(node)
            for run in runs:
                stage_intervals.append({
                    "track": track,
                    "stage": run[0]["stage"],
                    "start_date": run[0]["date"],
                    "end_date": run[-1]["date"],
                    "row_index": 0,
                    "node_ids": [node["id"] for node in run],
                })
            track_intervals = [item for item in stage_intervals if item["track"] == track]
            row_ends = []
            for item in sorted(track_intervals, key=lambda value: (value["start_date"], value["node_ids"][0])):
                row_index = next((index for index, end_date in enumerate(row_ends) if end_date < item["start_date"]), len(row_ends))
                item["row_index"] = row_index
                if row_index == len(row_ends):
                    row_ends.append(item["end_date"])
                else:
                    row_ends[row_index] = item["end_date"]
        for node in nodes:
            if node["done_at"]:
                status = "已完成"
            else:
                status = "未开始" if self._date(node["date"]) >= today else "进行中"
            payloads.append({
                "id": node["id"],
                "project_id": project["id"],
                "track": node["track"],
                "stage": node["stage"],
                "name": node["name"],
                "date": node["date"],
                "initial_date": node["initial_date"],
                "interval_days": intervals[node["id"]],
                "status": status,
                "done_at": bool(node["done_at"]),
                "remark": node["remark"],
                "version": node["version"],
            })
        started = [node for node in nodes if self._date(node["date"]) <= today]
        current_stage = max((node["stage"] for node in started), key=STAGES.index, default="未开始")
        upcoming_date = min((node["date"] for node in nodes if not node["done_at"] and self._date(node["date"]) >= today), default=None)
        upcoming = [node for node in nodes if not node["done_at"] and node["date"] == upcoming_date] if upcoming_date else []
        upcoming.sort(key=lambda node: (node["date"], STAGES.index(node["stage"]), 0 if node["track"] == "main" else 1, _natural_key(node["name"])))
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        overdue = [node for node in nodes if not node["done_at"] and self._date(node["date"]) < today]
        this_week = [node for node in nodes if not node["done_at"] and week_start <= self._date(node["date"]) <= week_end]
        if role is None and "role" in project.keys():
            role = project["role"]
        archived = bool(project["archived_at"])
        can_manage_archive = bool(user_id and (role == "admin" or project["created_by"] == user_id))
        return {
            "project_id": project["id"],
            "name": project["name"],
            "created_by": project["created_by"],
            "version": project["version"],
            "archived_at": project["archived_at"],
            "archived_by": project["archived_by"],
            "read_only": archived,
            "can_archive": can_manage_archive and not archived,
            "can_unarchive": can_manage_archive and archived,
            "nodes": payloads,
            "segments": segments,
            "stage_intervals": stage_intervals,
            "metrics": {
                "start_date": min((node["date"] for node in nodes), default=None),
                "current_stage": current_stage,
                "upcoming": [{"node_id": node["id"], "name": node["name"], "stage": node["stage"], "track": node["track"], "date": node["date"]} for node in upcoming],
                "overdue_count": len(overdue),
                "this_week_count": len(this_week),
            },
            "server_today": today.isoformat(),
        }

    def _validate_node(self, row, *, create=False):
        allowed = CREATE_FIELDS if create else SET_FIELDS
        reject_unknown(row, allowed)
        track = validate_choice(row.get("track"), "track", set(TRACKS))
        stage = validate_choice(row.get("stage"), "stage", set(STAGES))
        name = require_text(row, "name", max_length=500)
        date = self._parse_date(row.get("date"), "date").isoformat()
        done = row.get("done_at", False)
        if not isinstance(done, bool):
            raise ApiError(422, "VALIDATION_ERROR", "done_at must be boolean")
        remark = require_text({"remark": row.get("remark", "")}, "remark", max_length=500, allow_empty=True)
        return {"track": track, "stage": stage, "name": name, "date": date, "done_at": done, "remark": remark}

    def _insert_node(self, conn, project_id, user_id, values, stamp):
        return conn.execute(
            """INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,done_at,remark,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (project_id, values["track"], values["stage"], values["name"], values["date"], values["date"], utc_now() if values["done_at"] else None, values["remark"], stamp, stamp),
        ).lastrowid

    @staticmethod
    def _audit(conn, workspace_id, user_id, entity_id, action, entity_type="timeline_batch", details=None):
        source_key = f"{action}:{entity_id}"
        if details is not None:
            next_id = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM audit_log").fetchone()[0]
            source_key = f"{source_key}:{next_id}"
        conn.execute(
            """INSERT INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (source_key, workspace_id, user_id, action, "success", entity_type, str(entity_id), json.dumps(details or {}, ensure_ascii=False), utc_now()),
        )

    def _resolve_batch(self, nodes, changes):
        by_id = {node["id"]: node for node in nodes}
        states = {}
        creates = []
        deletes = set()
        for change in changes:
            if not isinstance(change, dict):
                raise ApiError(422, "VALIDATION_ERROR", "change must be an object")
            node_id = change.get("node_id")
            if node_id is not None:
                node_id = require_int(node_id, "node_id", minimum=1)
                if node_id not in by_id:
                    raise ApiError(422, "VALIDATION_ERROR", "节点无效", {"node_id": node_id})
            reject_unknown(change, {"node_id", "set", "create", "remove"})
            if change.get("remove") is not None and not isinstance(change["remove"], bool):
                raise ApiError(422, "VALIDATION_ERROR", "remove must be boolean")
            if node_id is None:
                if "create" not in change:
                    raise ApiError(422, "VALIDATION_ERROR", "change requires node_id or create")
                if not isinstance(change["create"], dict):
                    raise ApiError(422, "VALIDATION_ERROR", "create must be an object")
                values = self._validate_node(change["create"], create=True)
                if "interval_days" in change["create"]:
                    raise ApiError(422, "VALIDATION_ERROR", "create cannot set interval_days")
                creates.append(values)
                continue
            if "create" in change:
                raise ApiError(422, "VALIDATION_ERROR", "node change cannot use create")
            state = states.get(node_id)
            if state is None and node_id not in deletes:
                state = {
                    "track": by_id[node_id]["track"], "stage": by_id[node_id]["stage"], "name": by_id[node_id]["name"],
                    "date": by_id[node_id]["date"], "done": bool(by_id[node_id]["done_at"]), "remark": by_id[node_id]["remark"],
                    "track_changed": False,
                    "date_intent": None,
                    "interval_intent": None,
                }
            if change.get("remove"):
                deletes.add(node_id)
                states[node_id] = None
                continue
            settings = change.get("set")
            if settings is None:
                settings = {}
            if not isinstance(settings, dict):
                raise ApiError(422, "VALIDATION_ERROR", "set must be an object")
            reject_unknown(settings, SET_FIELDS)
            if "interval_days" in settings:
                interval = require_int(settings["interval_days"], "interval_days", minimum=0)
                if interval > 3650:
                    raise ApiError(422, "VALIDATION_ERROR", "interval_days is out of range")
                state["interval_days"] = interval
                state["interval_intent"] = interval
            if "date" in settings:
                state["date"] = self._parse_date(settings["date"], "date").isoformat()
                state["date_intent"] = state["date"]
            for field in ("track", "stage", "name", "remark"):
                if field in settings:
                    if field == "track":
                        state["track"] = validate_choice(settings[field], field, set(TRACKS))
                    else:
                        state[field] = require_text({"value": settings[field]}, "value", max_length=500, allow_empty=field == "remark")
            if "stage" in settings:
                state["stage"] = validate_choice(settings["stage"], "stage", set(STAGES))
            if "track" in settings:
                state["track_changed"] = True
            if "done_at" in settings:
                if not isinstance(settings["done_at"], bool):
                    raise ApiError(422, "VALIDATION_ERROR", "done_at must be boolean")
                state["done"] = settings["done_at"]
            states[node_id] = state
        resolved = []
        for node_id, state in states.items():
            node = by_id[node_id]
            if state is None:
                resolved.append((node, {"_delete": True}))
                continue
            track_changed = state.pop("track_changed")
            interval_intent = state.pop("interval_intent", None)
            date_intent = state.pop("date_intent", None)
            if date_intent is not None:
                state["date"] = date_intent
                state["date_anchor"] = True
            elif interval_intent is not None:
                track = state["track"] if track_changed else node["track"]
                chain = self._chain(nodes, track)
                if track_changed:
                    raise ApiError(422, "VALIDATION_ERROR", "interval_days cannot combine with track change", {"node_id": node_id})
                index = chain.index(node)
                if index == 0:
                    raise ApiError(422, "VALIDATION_ERROR", "节点没有前驱", {"node_id": node_id})
                state["date"] = (self._date(chain[index - 1]["date"]) + timedelta(days=interval_intent)).isoformat()
                state["date_anchor"] = True
            else:
                state["date_anchor"] = False
            resolved.append((node, state))
        return resolved, creates, deletes

    def _parse_import_date(self, value, row_number, file_format):
        """F2-②：文本 YYYY-MM-DD 严格校验；.xlsx 整数序列号 18264..73051 换算；分数/越界行级 422。"""
        if not isinstance(value, str):
            raise ApiError(422, "VALIDATION_ERROR", "date 必须是 YYYY-MM-DD 文本", {"row": row_number})
        if re.fullmatch(r"\d+", value):
            if file_format != "xlsx" or not isinstance(value, XlsxNumericCell):
                suffix = "；在 Excel 中编辑请改用 .xlsx 导入" if file_format == "csv" else ""
                raise ApiError(422, "VALIDATION_ERROR", f"date 必须是有效的 YYYY-MM-DD 日期{suffix}", {"row": row_number})
            serial = int(value)
            if not SERIAL_MIN <= serial <= SERIAL_MAX:
                raise ApiError(422, "VALIDATION_ERROR", f"日期序列号超出 {SERIAL_MIN}..{SERIAL_MAX}（1950–2100）范围", {"row": row_number})
            return _serial_to_date(serial).isoformat()
        if file_format == "xlsx" and isinstance(value, XlsxNumericCell):
            raise ApiError(422, "VALIDATION_ERROR", "Excel 日期序列号必须是整数", {"row": row_number})
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", "date 必须是有效的 YYYY-MM-DD 日期", {"row": row_number})

    def _validate_timeline_rows(self, rows, workspace_names, file_format):
        clean = []
        first_seen = {}
        project_spellings = {}
        workspace_name_keys = {name.casefold() for name in workspace_names}
        conflicts = [
            {"row": row_number, "project": row.get("project")}
            for row_number, row in enumerate(rows, 2)
            if isinstance(row, dict)
            and isinstance(row.get("project"), str)
            and row.get("project").strip().casefold() in workspace_name_keys
        ]
        if conflicts:
            raise ApiError(422, "NAME_CONFLICT", "项目名称唯一：已存在同名项目", {"row": conflicts[0]["row"], "rows": conflicts})
        for row_number, row in enumerate(rows, 2):
            if not isinstance(row, dict):
                raise ApiError(422, "VALIDATION_ERROR", "row must be an object", {"row": row_number})
            try:
                reject_unknown(row, {"project", "track", "stage", "name", "date", "status", "remark"})
                project = require_text({"value": row.get("project")}, "value", max_length=200)
                project_key = project.casefold()
                project = project_spellings.setdefault(project_key, project)
                track = row.get("track")
                track = track.strip() if isinstance(track, str) else track
                if track not in IMPORT_TRACKS:
                    raise ApiError(422, "VALIDATION_ERROR", "track 必须是 主线/并行（兼容 main/parallel）")
                values = {
                    "row": row_number,
                    "project": project,
                    "track": IMPORT_TRACKS[track],
                    "stage": validate_choice(row.get("stage"), "stage", set(STAGES)),
                    "name": require_text({"value": row.get("name")}, "value", max_length=500),
                    "status": None,
                    "remark": require_text({"remark": row.get("remark", "")}, "remark", max_length=500, allow_empty=True),
                }
                status = row.get("status", "")
                status = status.strip() if isinstance(status, str) else status
                if status not in IMPORT_STATUSES and status != "":
                    raise ApiError(422, "VALIDATION_ERROR", "status 必须是 已完成/未开始/进行中 或留空", {"row": row_number})
                values["status"] = status
                values["date"] = self._parse_import_date(row.get("date"), row_number, file_format)
            except ApiError as error:
                if error.status == 422 and error.details is None:
                    error.details = {"row": row_number}
                raise
            key = (project_key, values["track"], values["date"], values["name"])
            if key in first_seen:
                raise ApiError(422, "VALIDATION_ERROR", f"与第 {first_seen[key]} 行重复", {"row": row_number, "duplicate_of": first_seen[key]})
            first_seen[key] = row_number
            clean.append(values)
        return clean

    @staticmethod
    def _group_import_rows(clean):
        groups = {}
        for values in clean:
            groups.setdefault(values["project"], []).append(values)
        return groups

    def create_project(self, user, workspace_id, data):
        reject_unknown(data, {"name"})
        name = require_text(data, "name", max_length=200)
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                if conn.execute("SELECT 1 FROM timeline_projects WHERE workspace_id=? AND name=? COLLATE NOCASE AND deleted_at IS NULL", (workspace_id, name)).fetchone():
                    raise ApiError(422, "NAME_CONFLICT", "项目名称已存在")
                stamp = utc_now()
                try:
                    project_id = conn.execute(
                        "INSERT INTO timeline_projects(workspace_id,name,created_by,created_at,updated_at) VALUES (?,?,?,?,?)",
                        (workspace_id, name, user["id"], stamp, stamp),
                    ).lastrowid
                except sqlite3.IntegrityError as error:
                    raise ApiError(422, "NAME_CONFLICT", "项目名称已存在") from error
                self._audit(conn, workspace_id, user["id"], project_id, "timeline.project_created", "timeline_project")
                return {"project_id": project_id, "name": name, "created_by": user["id"], "version": 1}
        finally:
            conn.close()

    def rename_project(self, user, workspace_id, project_id, data):
        reject_unknown(data, {"name", "base_version"})
        name = require_text(data, "name", max_length=200)
        if "base_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
        base_version = require_int(data["base_version"], "base_version", minimum=1)
        conn = self._db()
        try:
            with transaction(conn):
                project = self._project_access(
                    conn,
                    user["id"],
                    project_id,
                    workspace_id=workspace_id,
                    write=True,
                    require_active=True,
                )
                if project["version"] != base_version:
                    raise ApiError(
                        409,
                        "VERSION_CONFLICT",
                        "项目版本冲突",
                        {"project": self._view(conn, project, user_id=user["id"], role=project["role"])},
                    )
                old_name = project["name"]
                if name == old_name:
                    return self._view(conn, project, user_id=user["id"], role=project["role"])
                if conn.execute(
                    """SELECT 1 FROM timeline_projects
                       WHERE workspace_id=? AND id<>? AND name=? COLLATE NOCASE AND deleted_at IS NULL""",
                    (workspace_id, project_id, name),
                ).fetchone():
                    raise ApiError(422, "NAME_CONFLICT", "项目名称已存在")
                stamp = utc_now()
                try:
                    updated = conn.execute(
                        """UPDATE timeline_projects
                           SET name=?,version=version+1,updated_at=?
                           WHERE id=? AND workspace_id=? AND version=? AND deleted_at IS NULL AND archived_at IS NULL""",
                        (name, stamp, project_id, workspace_id, base_version),
                    )
                except sqlite3.IntegrityError as error:
                    raise ApiError(422, "NAME_CONFLICT", "项目名称已存在") from error
                if updated.rowcount != 1:
                    latest = self._project_access(
                        conn,
                        user["id"],
                        project_id,
                        workspace_id=workspace_id,
                        write=True,
                        require_active=True,
                    )
                    raise ApiError(
                        409,
                        "VERSION_CONFLICT",
                        "项目版本冲突",
                        {"project": self._view(conn, latest, user_id=user["id"], role=latest["role"])},
                    )
                latest = self._project_access(
                    conn,
                    user["id"],
                    project_id,
                    workspace_id=workspace_id,
                    write=True,
                    require_active=True,
                )
                self._audit(
                    conn,
                    workspace_id,
                    user["id"],
                    project_id,
                    "timeline.project_renamed",
                    "timeline_project",
                    {
                        "old_name": old_name,
                        "name": name,
                        "version_before": base_version,
                        "version_after": latest["version"],
                    },
                )
                return self._view(conn, latest, user_id=user["id"], role=latest["role"])
        finally:
            conn.close()

    def list_projects(self, user, workspace_id, archive_state="active"):
        if archive_state not in {"active", "archived"}:
            raise ApiError(422, "VALIDATION_ERROR", "archive_state must be active or archived")
        conn = self._db()
        try:
            role = self._workspace_access(conn, user["id"], workspace_id)
            if archive_state == "archived":
                projects = conn.execute(
                    """SELECT * FROM timeline_projects
                       WHERE workspace_id=? AND deleted_at IS NULL AND archived_at IS NOT NULL
                       ORDER BY archived_at DESC,name COLLATE NOCASE,id""",
                    (workspace_id,),
                ).fetchall()
            else:
                projects = conn.execute(
                    "SELECT * FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY id",
                    (workspace_id,),
                ).fetchall()
            return {
                "archive_state": archive_state,
                "projects": [self._view(conn, project, user_id=user["id"], role=role) for project in projects],
                "server_today": self._server_today().isoformat(),
            }
        finally:
            conn.close()

    def get_project(self, user, project_id):
        conn = self._db()
        try:
            project = self._project_access(conn, user["id"], project_id, require_active=True)
            payload = self._view(conn, project, user_id=user["id"], role=project["role"])
            return payload
        finally:
            conn.close()

    def _set_project_archive(self, user, workspace_id, project_id, data, *, archived):
        reject_unknown(data, {"base_version"})
        if "base_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
        base_version = require_int(data["base_version"], "base_version", minimum=1)
        conn = self._db()
        try:
            with transaction(conn):
                project = self._project_access(
                    conn, user["id"], project_id, workspace_id=workspace_id,
                    require_active=True, allow_archived=True,
                )
                if project["role"] != "admin" and project["created_by"] != user["id"]:
                    raise ApiError(403, "PROJECT_ARCHIVE_FORBIDDEN", "仅管理员或项目创建者可归档或取消归档")
                currently_archived = bool(project["archived_at"])
                if currently_archived == archived or project["version"] != base_version:
                    raise ApiError(
                        409, "ARCHIVE_STATE_CONFLICT", "项目归档状态或版本已变化",
                        {"project": self._view(conn, project, user_id=user["id"], role=project["role"])},
                    )
                stamp = utc_now()
                if archived:
                    cursor = conn.execute(
                        """UPDATE timeline_projects
                           SET archived_at=?,archived_by=?,version=version+1,updated_at=?
                           WHERE id=? AND workspace_id=? AND version=? AND deleted_at IS NULL AND archived_at IS NULL""",
                        (stamp, user["id"], stamp, project_id, workspace_id, base_version),
                    )
                    action = "timeline.project_archived"
                else:
                    cursor = conn.execute(
                        """UPDATE timeline_projects
                           SET archived_at=NULL,archived_by=NULL,version=version+1,updated_at=?
                           WHERE id=? AND workspace_id=? AND version=? AND deleted_at IS NULL AND archived_at IS NOT NULL""",
                        (stamp, project_id, workspace_id, base_version),
                    )
                    action = "timeline.project_unarchived"
                if cursor.rowcount != 1:
                    latest = self._project_access(conn, user["id"], project_id, workspace_id=workspace_id, require_active=True, allow_archived=True)
                    raise ApiError(409, "ARCHIVE_STATE_CONFLICT", "项目归档状态或版本已变化", {"project": self._view(conn, latest, user_id=user["id"], role=latest["role"])})
                latest = self._project_access(conn, user["id"], project_id, workspace_id=workspace_id, require_active=True, allow_archived=True)
                self._audit(
                    conn, workspace_id, user["id"], project_id, action, "timeline_project",
                    {"version_before": base_version, "version_after": latest["version"], "archived_at": latest["archived_at"]},
                )
                return self._view(conn, latest, user_id=user["id"], role=latest["role"])
        finally:
            conn.close()

    def archive_project(self, user, workspace_id, project_id, data):
        return self._set_project_archive(user, workspace_id, project_id, data, archived=True)

    def unarchive_project(self, user, workspace_id, project_id, data):
        return self._set_project_archive(user, workspace_id, project_id, data, archived=False)

    def _archive_bootstrap_snapshot(self, conn, workspace_id, today):
        rows = conn.execute(
            """SELECT p.id project_id,p.name,p.version base_version,MAX(n.date) last_node_date
               FROM timeline_projects p
               JOIN timeline_nodes n ON n.project_id=p.id AND n.deleted_at IS NULL
               WHERE p.workspace_id=? AND p.deleted_at IS NULL AND p.archived_at IS NULL
               GROUP BY p.id,p.name,p.version
               HAVING MAX(n.date) < ?
               ORDER BY p.id""",
            (workspace_id, today),
        ).fetchall()
        candidates = [
            {
                "project_id": row["project_id"],
                "name": row["name"],
                "base_version": row["base_version"],
                "last_node_date": row["last_node_date"],
            }
            for row in rows
        ]
        digest_source = {"workspace_id": workspace_id, "today": today, "candidates": candidates}
        digest = hashlib.sha256(
            json.dumps(digest_source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**digest_source, "candidate_count": len(candidates), "snapshot_sha256": digest}

    def preview_archive_bootstrap(self, user, workspace_id, data):
        reject_unknown(data, set())
        conn = self._db()
        try:
            role = self._workspace_access(conn, user["id"], workspace_id)
            if role != "admin":
                raise ApiError(403, "ADMIN_REQUIRED", "仅管理员可预览首次归档")
            today = self._server_today().isoformat()
            return self._archive_bootstrap_snapshot(conn, workspace_id, today)
        finally:
            conn.close()

    def apply_archive_bootstrap(self, user, workspace_id, data):
        reject_unknown(data, {"today", "candidates", "snapshot_sha256"})
        today = require_text(data, "today", max_length=10)
        self._parse_date(today, "today")
        snapshot_sha256 = require_text(data, "snapshot_sha256", max_length=64)
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256):
            raise ApiError(422, "VALIDATION_ERROR", "snapshot_sha256 must be lowercase SHA-256")
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            raise ApiError(422, "VALIDATION_ERROR", "candidates must be an array")
        submitted = []
        for row in candidates:
            if not isinstance(row, dict):
                raise ApiError(422, "VALIDATION_ERROR", "candidate must be an object")
            reject_unknown(row, {"project_id", "name", "base_version", "last_node_date"})
            submitted.append({
                "project_id": require_int(row.get("project_id"), "project_id", minimum=1),
                "name": require_text(row, "name", max_length=200),
                "base_version": require_int(row.get("base_version"), "base_version", minimum=1),
                "last_node_date": self._parse_date(row.get("last_node_date"), "last_node_date").isoformat(),
            })
        conn = self._db()
        try:
            with transaction(conn):
                role = self._workspace_access(conn, user["id"], workspace_id)
                if role != "admin":
                    raise ApiError(403, "ADMIN_REQUIRED", "仅管理员可执行首次归档")
                if conn.execute(
                    "SELECT 1 FROM audit_log WHERE workspace_id=? AND action_code='timeline.archive_bootstrap_completed' AND outcome='success'",
                    (workspace_id,),
                ).fetchone():
                    raise ApiError(409, "ARCHIVE_BOOTSTRAP_ALREADY_COMPLETED", "该工作区已完成首次归档")
                server_today = self._server_today().isoformat()
                latest = self._archive_bootstrap_snapshot(conn, workspace_id, server_today)
                if today != server_today or submitted != latest["candidates"] or snapshot_sha256 != latest["snapshot_sha256"]:
                    raise ApiError(409, "ARCHIVE_BOOTSTRAP_SNAPSHOT_CHANGED", "日期候选已变化，请重新预览", {"preview": latest})
                stamp = utc_now()
                for row in submitted:
                    updated = conn.execute(
                        """UPDATE timeline_projects
                           SET archived_at=?,archived_by=?,version=version+1,updated_at=?
                           WHERE id=? AND workspace_id=? AND version=? AND deleted_at IS NULL AND archived_at IS NULL""",
                        (stamp, user["id"], stamp, row["project_id"], workspace_id, row["base_version"]),
                    )
                    if updated.rowcount != 1:
                        raise ApiError(409, "ARCHIVE_BOOTSTRAP_SNAPSHOT_CHANGED", "日期候选已变化，请重新预览", {"preview": self._archive_bootstrap_snapshot(conn, workspace_id, server_today)})
                    self._audit(
                        conn, workspace_id, user["id"], row["project_id"], "timeline.project_archived", "timeline_project",
                        {"source": "archive_bootstrap", "version_before": row["base_version"], "version_after": row["base_version"] + 1, "archived_at": stamp},
                    )
                self._audit(
                    conn, workspace_id, user["id"], workspace_id, "timeline.archive_bootstrap_completed", "workspace",
                    {"candidate_count": len(submitted), "snapshot_sha256": snapshot_sha256, "today": today},
                )
                return {"workspace_id": workspace_id, "today": today, "archived_count": len(submitted), "snapshot_sha256": snapshot_sha256}
        finally:
            conn.close()

    def delete_project(self, user, workspace_id, project_id, data):
        reject_unknown(data, {"base_version"})
        if "base_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
        version = require_int(data.get("base_version"), "base_version", minimum=1)
        conn = self._db()
        try:
            with transaction(conn):
                project = self._project_access(conn, user["id"], project_id, workspace_id=workspace_id, write=True, require_active=True)
                if project["role"] != "admin":
                    raise ApiError(403, "ADMIN_REQUIRED", "仅管理员可删除项目")
                if project["version"] != version:
                    raise ApiError(409, "VERSION_CONFLICT", "项目版本冲突", {"server_version": project["version"]})
                stamp = utc_now()
                deleted_at = stamp
                cursor = conn.execute(
                    "UPDATE timeline_projects SET deleted_at=?,deleted_by=?,version=version+1,updated_at=? WHERE id=? AND version=?",
                    (deleted_at, user["id"], stamp, project_id, version),
                )
                if cursor.rowcount != 1:
                    raise ApiError(409, "VERSION_CONFLICT", "项目版本冲突", {"server_version": project["version"]})
                self._audit(conn, workspace_id, user["id"], project_id, "timeline.project_deleted", "timeline_project")
                return {"project_id": project_id, "version": version + 1, "deleted_at": deleted_at}
        finally:
            conn.close()

    def submit_batches(self, user, workspace_id, data):
        reject_unknown(data, {"requests"})
        requests = data.get("requests")
        if not isinstance(requests, list) or not requests or len(requests) > 20:
            raise ApiError(422, "VALIDATION_ERROR", "requests must contain 1..20 projects")
        conn = self._db()
        try:
            with transaction(conn):
                contexts = []
                for request in requests:
                    if not isinstance(request, dict):
                        raise ApiError(422, "VALIDATION_ERROR", "request must be an object")
                    reject_unknown(request, {"project_id", "base_version", "trigger_source", "details", "changes"})
                    project_id = require_int(request.get("project_id"), "project_id", minimum=1)
                    if "base_version" not in request:
                        raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
                    base_version = require_int(request.get("base_version"), "base_version", minimum=1)
                    project = self._project_access(conn, user["id"], project_id, workspace_id=workspace_id, write=True, require_active=True)
                    if project["version"] != base_version:
                        raise ApiError(409, "VERSION_CONFLICT", "批量提交存在版本冲突，整批未写入", {"conflicts": [{
                            "project_id": project_id,
                            "submitted_version": base_version,
                            "server_version": project["version"],
                            "view": self._view(conn, project),
                        }]})
                    changes = request.get("changes")
                    if not isinstance(changes, list) or not changes or len(changes) > 200:
                        raise ApiError(422, "VALIDATION_ERROR", "changes must contain 1..200 rows")
                    details = request.get("details", {})
                    if not isinstance(details, dict):
                        raise ApiError(422, "VALIDATION_ERROR", "details must be an object")
                    reject_unknown(details, {"mode", "magnet", "zoom_band", "historical_correction"})
                    mode = validate_choice(details.get("mode", "cascade"), "mode", {"single", "cascade"})
                    trigger = validate_choice(request.get("trigger_source", "editor"), "trigger_source", {"editor", "drag"})
                    contexts.append((project, changes, mode, trigger, details))
                results = []
                for project, changes, mode, trigger, details in contexts:
                    result = self._apply_one_batch(conn, user, workspace_id, project, changes, mode, trigger, details)
                    results.append(result)
                return {"results": results}
        finally:
            conn.close()

    def _apply_one_batch(self, conn, user, workspace_id, project, changes, mode, trigger, details):
        snapshot = list(self._nodes(conn, project["id"]))
        resolved, creates, deletes = self._resolve_batch(snapshot, changes)
        final_states = {}
        for node, state in resolved:
            if state.get("_delete"):
                final_states[node["id"]] = None
                continue
            current = {
                "track": node["track"], "stage": node["stage"], "name": node["name"], "date": node["date"],
                "done": bool(node["done_at"]), "remark": node["remark"],
            }
            current.update({key: value for key, value in state.items() if key in current})
            current["date_anchor"] = state["date_anchor"]
            current["explicit"] = True
            final_states[node["id"]] = current

        by_id = {node["id"]: node for node in snapshot}
        for node in snapshot:
            if node["id"] in final_states:
                continue
            final_states[node["id"]] = {
                "track": node["track"], "stage": node["stage"], "name": node["name"], "date": node["date"],
                "done": bool(node["done_at"]), "remark": node["remark"], "date_anchor": False, "explicit": False,
            }
        for node_id, state in final_states.items():
            if state is None or not state["date_anchor"]:
                continue
            node = by_id[node_id]
            track = state["track"]
            chain = self._chain(snapshot, track)
            index = next((position for position, candidate in enumerate(chain) if candidate["id"] == node_id), None)
            if index is None:
                raise ApiError(422, "VALIDATION_ERROR", "节点无效", {"node_id": node_id})
            desired = self._date(state["date"])
            lower = self._date(chain[index - 1]["date"]) if index else None
            lower_bound = lower + timedelta(days=1) if lower is not None and trigger == "drag" else lower
            if mode == "cascade" or trigger == "drag":
                state["date"] = (max(desired, lower_bound) if lower_bound else desired).isoformat()
            else:
                upper = self._date(chain[index + 1]["date"]) if index + 1 < len(chain) else None
                if lower is not None:
                    desired = max(desired, lower)
                if upper is not None:
                    desired = min(desired, upper)
                state["date"] = desired.isoformat()

        if mode == "cascade":
            for track in TRACKS:
                shift = 0
                for node in self._chain(snapshot, track):
                    state = final_states.get(node["id"])
                    if state is None:
                        continue
                    if state.get("date_anchor"):
                        shift = (self._date(state["date"]) - self._date(node["date"])).days
                        continue
                    state["date"] = (self._date(node["date"]) + timedelta(days=shift)).isoformat()

        if trigger == "drag":
            for track in TRACKS:
                previous = None
                collision_active = False
                for node in self._chain(snapshot, track):
                    state = final_states.get(node["id"])
                    if state is None:
                        continue
                    if previous is not None and collision_active:
                        minimum = previous + timedelta(days=1)
                        if self._date(state["date"]) < minimum:
                            state["date"] = minimum.isoformat()
                    if state.get("date_anchor"):
                        collision_active = True
                    previous = self._date(state["date"])

        has_direct_edit = bool(creates)
        has_status_toggle = False
        for node in snapshot:
            state = final_states.get(node["id"])
            if state is None:
                has_direct_edit = True
                continue
            has_direct_edit = has_direct_edit or any(
                node[field] != state[field]
                for field in ("track", "stage", "name", "date", "remark")
            )
            has_status_toggle = has_status_toggle or bool(node["done_at"]) != state["done"]
        if not has_direct_edit and not has_status_toggle:
            return {"project_id": project["id"], "version": project["version"], "no_op": True, "view": self._view(conn, project)}

        stamp = utc_now()
        kinds = []
        if has_direct_edit:
            kinds.append("direct_edit")
        if has_status_toggle:
            kinds.append("status_toggle")
        change_kind = "direct_edit" if has_direct_edit else "status_toggle"
        batch_id = conn.execute(
            """INSERT INTO timeline_change_batches(project_id,actor_user_id,change_kind,trigger_source,project_version_before,project_version_after,details_json,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (project["id"], user["id"], change_kind, trigger, project["version"], project["version"] + 1, json.dumps({**details, "mode": mode, "kinds": kinds}, ensure_ascii=False), stamp),
        ).lastrowid
        for node in snapshot:
            state = final_states.get(node["id"])
            if state is None:
                conn.execute("UPDATE timeline_nodes SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=?", (stamp, user["id"], stamp, node["id"]))
                conn.execute("INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,NULL,'deleted')", (batch_id, node["id"], "direct", "deleted"))
                continue
            if all(
                node[field] == state[field]
                for field in ("track", "stage", "name", "date", "remark")
            ) and bool(node["done_at"]) == state["done"]:
                continue
            old_done = bool(node["done_at"])
            new_done = state["done"]
            for field, old, new in (
                ("track", node["track"], state["track"]),
                ("stage", node["stage"], state["stage"]),
                ("name", node["name"], state["name"]),
                ("date", node["date"], state["date"]),
                ("remark", node["remark"], state["remark"]),
            ):
                if old != new:
                    role = "direct" if (field != "date" or state["date_anchor"]) else "cascaded"
                    conn.execute("INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,?,?)", (batch_id, node["id"], role, field, str(old), str(new)))
            if old_done != new_done:
                conn.execute("INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,?,?)", (batch_id, node["id"], "direct", "done_at", str(old_done), str(new_done)))
            conn.execute(
                "UPDATE timeline_nodes SET track=?,stage=?,name=?,date=?,done_at=?,remark=?,version=version+1,updated_at=? WHERE id=?",
                (state["track"], state["stage"], state["name"], state["date"], utc_now() if new_done else None, state["remark"], stamp, node["id"]),
            )
        for values in creates:
            node_id = self._insert_node(conn, project["id"], user["id"], values, stamp)
            conn.execute("INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,NULL,?)", (batch_id, node_id, "direct", "created", json.dumps(values, ensure_ascii=False)))
        cursor = conn.execute("UPDATE timeline_projects SET version=version+1,updated_at=? WHERE id=? AND version=?", (stamp, project["id"], project["version"]))
        if cursor.rowcount != 1:
            raise ApiError(409, "VERSION_CONFLICT", "项目版本冲突")
        self._audit(conn, workspace_id, user["id"], batch_id, "timeline.batch_committed")
        fresh = conn.execute("SELECT * FROM timeline_projects WHERE id=?", (project["id"],)).fetchone()
        return {"project_id": project["id"], "batch_id": batch_id, "version": fresh["version"], "view": self._view(conn, fresh)}

    def undo_batches(self, user, workspace_id, data):
        reject_unknown(data, {"batch_ids"})
        batch_ids = data.get("batch_ids")
        if not isinstance(batch_ids, list) or not 1 <= len(batch_ids) <= 20:
            raise ApiError(422, "VALIDATION_ERROR", "batch_ids must contain 1..20 items")
        clean = []
        for batch_id in batch_ids:
            value = require_int(batch_id, "batch_id", minimum=1)
            if value in clean:
                raise ApiError(422, "VALIDATION_ERROR", "duplicate batch_id")
            clean.append(value)
        conn = self._db()
        try:
            with transaction(conn):
                targets = []
                for batch_id in clean:
                    row = conn.execute(
                        """SELECT b.*,p.workspace_id FROM timeline_change_batches b
                           JOIN timeline_projects p ON p.id=b.project_id WHERE b.id=?""",
                        (batch_id,),
                    ).fetchone()
                    if not row or row["workspace_id"] != workspace_id:
                        raise ApiError(404, "TIMELINE_BATCH_NOT_FOUND", "撤销批次不存在")
                    latest = conn.execute("SELECT MAX(id) FROM timeline_change_batches WHERE project_id=?", (row["project_id"],)).fetchone()[0]
                    if latest != batch_id or row["change_kind"] == "undo":
                        raise ApiError(409, "UNDO_TARGET_STALE", "撤销目标已过期")
                    project = self._project_access(conn, user["id"], row["project_id"], workspace_id=workspace_id, write=True, require_active=True)
                    if row["change_kind"] == "initial_correction" and project["role"] != "admin":
                        raise ApiError(403, "ADMIN_REQUIRED", "仅管理员可撤销初始日期纠正")
                    targets.append((project, row))
                undo_group = hashlib.sha256(",".join(map(str, clean)).encode()).hexdigest()
                results = []
                stamp = utc_now()
                for project, row in targets:
                    changes = conn.execute("SELECT * FROM timeline_node_changes WHERE batch_id=? ORDER BY id", (row["id"],)).fetchall()
                    undo_id = conn.execute(
                        """INSERT INTO timeline_change_batches(project_id,actor_user_id,change_kind,trigger_source,project_version_before,project_version_after,undone_batch_id,details_json,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (project["id"], user["id"], "undo", "undo", project["version"], project["version"] + 1, row["id"], json.dumps({"undo_group": undo_group}, ensure_ascii=False), stamp),
                    ).lastrowid
                    for change in changes:
                        old = change["old_value"]
                        new = change["new_value"]
                        if change["field"] in ("created", "deleted"):
                            # E4③：'created' 反向=软删该节点；'deleted' 反向=恢复 deleted_at=NULL
                            reverse_soft_delete = change["field"] == "created"
                            conn.execute(
                                "UPDATE timeline_nodes SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=?",
                                (stamp if reverse_soft_delete else None, user["id"] if reverse_soft_delete else None, stamp, change["node_id"]),
                            )
                        elif change["field"] == "done_at":
                            old_done = old == "True"
                            conn.execute("UPDATE timeline_nodes SET done_at=?,updated_at=?,version=version+1 WHERE id=?", (utc_now() if old_done else None, stamp, change["node_id"]))
                        elif change["field"] == "track":
                            conn.execute("UPDATE timeline_nodes SET track=?,updated_at=?,version=version+1 WHERE id=?", (old, stamp, change["node_id"]))
                        elif change["field"] == "stage":
                            conn.execute("UPDATE timeline_nodes SET stage=?,updated_at=?,version=version+1 WHERE id=?", (old, stamp, change["node_id"]))
                        elif change["field"] == "name":
                            conn.execute("UPDATE timeline_nodes SET name=?,updated_at=?,version=version+1 WHERE id=?", (old, stamp, change["node_id"]))
                        elif change["field"] == "date":
                            conn.execute("UPDATE timeline_nodes SET date=?,updated_at=?,version=version+1 WHERE id=?", (old, stamp, change["node_id"]))
                        elif change["field"] == "initial_date":
                            conn.execute("UPDATE timeline_nodes SET initial_date=?,updated_at=?,version=version+1 WHERE id=?", (old, stamp, change["node_id"]))
                        elif change["field"] == "remark":
                            conn.execute("UPDATE timeline_nodes SET remark=?,updated_at=?,version=version+1 WHERE id=?", (old, stamp, change["node_id"]))
                        conn.execute(
                            "INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,?,?)",
                            (undo_id, change["node_id"], "direct", change["field"], new, old),
                        )
                    cursor = conn.execute("UPDATE timeline_projects SET version=version+1,updated_at=? WHERE id=? AND version=?", (stamp, project["id"], project["version"]))
                    if cursor.rowcount != 1:
                        raise ApiError(409, "VERSION_CONFLICT", "项目版本冲突")
                    self._audit(conn, workspace_id, user["id"], undo_id, "timeline.batch_undone")
                    fresh = conn.execute("SELECT * FROM timeline_projects WHERE id=?", (project["id"],)).fetchone()
                    results.append({"project_id": project["id"], "batch_id": undo_id, "version": fresh["version"], "view": self._view(conn, fresh)})
                return {"results": results}
        finally:
            conn.close()

    def initial_correction(self, user, workspace_id, data):
        reject_unknown(data, {"project_id", "base_version", "corrections"})
        project_id = require_int(data.get("project_id"), "project_id", minimum=1)
        if "base_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
        base_version = require_int(data.get("base_version"), "base_version", minimum=1)
        corrections = data.get("corrections")
        if not isinstance(corrections, list) or not corrections or len(corrections) > 200:
            raise ApiError(422, "VALIDATION_ERROR", "corrections must contain 1..200 rows")
        conn = self._db()
        try:
            with transaction(conn):
                project = self._project_access(conn, user["id"], project_id, workspace_id=workspace_id, write=True, require_active=True)
                if project["role"] != "admin":
                    raise ApiError(403, "ADMIN_REQUIRED", "仅管理员可纠正初始日期")
                if project["version"] != base_version:
                    raise ApiError(409, "VERSION_CONFLICT", "项目版本冲突", {"server_version": project["version"]})
                nodes = {node["id"]: node for node in self._nodes(conn, project_id)}
                resolved = []
                seen = set()
                for row in corrections:
                    if not isinstance(row, dict):
                        raise ApiError(422, "VALIDATION_ERROR", "correction must be an object")
                    reject_unknown(row, {"node_id", "initial_date"})
                    node_id = require_int(row.get("node_id"), "node_id", minimum=1)
                    if node_id not in nodes or node_id in seen:
                        raise ApiError(422, "VALIDATION_ERROR", "节点无效", {"node_id": node_id})
                    seen.add(node_id)
                    date = self._parse_date(row.get("initial_date"), "initial_date").isoformat()
                    if nodes[node_id]["initial_date"] != date:
                        resolved.append((nodes[node_id], date))
                if not resolved:
                    return {"results": [{"project_id": project_id, "version": project["version"], "no_op": True, "view": self._view(conn, project)}]}
                stamp = utc_now()
                batch_id = conn.execute(
                    """INSERT INTO timeline_change_batches(project_id,actor_user_id,change_kind,trigger_source,project_version_before,project_version_after,details_json,created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (project_id, user["id"], "initial_correction", "admin", base_version, base_version + 1, json.dumps({"historical_correction": True}, ensure_ascii=False), stamp),
                ).lastrowid
                for node, date in resolved:
                    conn.execute("INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,?,?)", (batch_id, node["id"], "direct", "initial_date", node["initial_date"], date))
                    conn.execute("UPDATE timeline_nodes SET initial_date=?,updated_at=?,version=version+1 WHERE id=?", (date, stamp, node["id"]))
                cursor = conn.execute("UPDATE timeline_projects SET version=version+1,updated_at=? WHERE id=? AND version=?", (stamp, project_id, base_version))
                if cursor.rowcount != 1:
                    raise ApiError(409, "VERSION_CONFLICT", "项目版本冲突")
                self._audit(conn, workspace_id, user["id"], batch_id, "timeline.initial_corrected")
                fresh = conn.execute("SELECT * FROM timeline_projects WHERE id=?", (project_id,)).fetchone()
                return {"results": [{"project_id": project_id, "batch_id": batch_id, "version": fresh["version"], "view": self._view(conn, fresh)}]}
        finally:
            conn.close()

    def review(self, user, workspace_id, project_ids=None):
        conn = self._db()
        try:
            self._workspace_access(conn, user["id"], workspace_id)
            selected = set(project_ids or [])
            projects = conn.execute("SELECT * FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY id", (workspace_id,)).fetchall()
            payload = []
            for project in projects:
                if selected and project["id"] not in selected:
                    continue
                nodes = self._nodes(conn, project["id"])
                counts = dict(conn.execute(
                    """SELECT c.node_id,COUNT(*) FROM timeline_node_changes c
                       JOIN timeline_change_batches b ON b.id=c.batch_id
                       WHERE b.project_id=? AND b.change_kind='direct_edit' AND c.change_role='direct' AND c.field='date'
                       GROUP BY c.node_id""",
                    (project["id"],),
                ).fetchall())
                history = conn.execute(
                    """SELECT b.id,b.change_kind,b.trigger_source,b.actor_user_id,u.name actor_name,
                       b.created_at,b.details_json
                       FROM timeline_change_batches b JOIN users u ON u.id=b.actor_user_id
                       WHERE b.project_id=? ORDER BY b.id DESC LIMIT 51""",
                    (project["id"],),
                ).fetchall()
                payload.append({
                    "project_id": project["id"],
                    "name": project["name"],
                    "version": project["version"],
                    "summary": {"direct_edit_total": sum(counts.values())},
                    "nodes": [{
                        "node_id": node["id"], "name": node["name"], "track": node["track"], "stage": node["stage"],
                        "initial_date": node["initial_date"], "date": node["date"],
                        "delta_days": (self._date(node["date"]) - self._date(node["initial_date"])).days,
                        "direct_edit_count": counts.get(node["id"], 0),
                    } for node in nodes],
                    "batches": [{
                        "batch_id": row["id"], "change_kind": row["change_kind"], "trigger_source": row["trigger_source"],
                        "actor": {"id": row["actor_user_id"], "name": row["actor_name"]},
                        "created_at": row["created_at"],
                        "change_rows": [{
                            "node_id": change["node_id"], "node_name": change["node_name"],
                            "change_role": change["change_role"], "field": change["field"],
                            "old_value": change["old_value"], "new_value": change["new_value"],
                        } for change in conn.execute(
                            """SELECT c.node_id,n.name node_name,c.change_role,c.field,c.old_value,c.new_value
                               FROM timeline_node_changes c JOIN timeline_nodes n ON n.id=c.node_id
                               WHERE c.batch_id=? ORDER BY c.id""", (row["id"],)).fetchall()],
                    } for row in history[:50]],
                    "has_more": len(history) > 50,
                })
            return {"projects": payload, "server_today": self._server_today().isoformat()}
        finally:
            conn.close()

    def _timeline_rows(self, user, workspace_id):
        conn = self._db()
        try:
            self._workspace_access(conn, user["id"], workspace_id)
            projects = conn.execute("SELECT * FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY id", (workspace_id,)).fetchall()
            rows = []
            today = self._server_today()
            for project in projects:
                nodes = self._nodes(conn, project["id"])
                for track in TRACKS:
                    for node in self._chain(nodes, track):
                        status = "已完成" if node["done_at"] else ("未开始" if self._date(node["date"]) >= today else "进行中")
                        rows.append([project["name"], node["stage"], EXPORT_TRACKS[node["track"]], node["name"], node["date"], status, node["remark"]])
            if len(rows) > MAX_ROWS:
                raise ApiError(422, "EXPORT_LIMIT", "导出行数超过上限", {"total": len(rows), "max": MAX_ROWS})
            return rows
        finally:
            conn.close()

    def export_timeline(self, user, workspace_id):
        return make_xlsx(IMPORT_HEADERS, self._timeline_rows(user, workspace_id), sheet="Timeline")

    def preview_import(self, user, workspace_id, filename, raw):
        try:
            parsed = parse_upload(filename, raw)
        except Exception as error:
            raise ApiError(422, getattr(error, "code", "IMPORT_INVALID"), str(error), getattr(error, "details", None))
        supported_headers = (IMPORT_HEADERS, INTERVAL_IMPORT_HEADERS, LEGACY_IMPORT_HEADERS, LEGACY_NO_INTERVAL_IMPORT_HEADERS)
        if parsed["headers"] not in supported_headers:
            raise ApiError(422, "IMPORT_HEADERS_MISMATCH", f"Excel 表头不匹配，标准表头：{'｜'.join(IMPORT_HEADERS)}", {"headers": IMPORT_HEADERS})
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                names = {row[0] for row in conn.execute("SELECT name FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL", (workspace_id,))}
                columns = {header: index for index, header in enumerate(parsed["headers"])}
                track_header = "主线/并行" if "主线/并行" in columns else "轨道"
                rows = [
                    {
                        "project": row[columns["项目名称"]],
                        "stage": row[columns["阶段"]],
                        "track": row[columns[track_header]],
                        "name": row[columns["节点"]],
                        "date": row[columns["日期"]],
                        "status": row[columns["状态"]],
                        "remark": row[columns["备注"]],
                    }
                    for row in parsed["rows"]
                ]
                clean = self._validate_timeline_rows(rows, names, parsed["format"])
                preview = json.dumps(clean, ensure_ascii=False)
                stamp = utc_now()
                batch_id = conn.execute(
                    """INSERT INTO timeline_import_batches(workspace_id,filename,file_format,content_sha256,preview_json,status,created_by,created_at)
                       VALUES (?,?,?,?,?,'previewed',?,?)""",
                    (workspace_id, filename, parsed["format"], hashlib.sha256(raw).hexdigest(), preview, user["id"], stamp),
                ).lastrowid
                warnings = ["状态将按日期重算，仅『已完成』保留"]
                if parsed["format"] == "xlsx" and len(parsed.get("sheets", [])) > 1:
                    warnings.append("仅导入第一个 sheet")
                return {
                    "batch_id": batch_id, "format": parsed["format"], "row_count": len(clean),
                    "projects": [{"name": name, "node_count": len(group)} for name, group in self._group_import_rows(clean).items()],
                    "warnings": warnings,
                }
        finally:
            conn.close()

    def commit_import(self, user, workspace_id, data):
        reject_unknown(data, {"batch_id"})
        batch_id = require_int(data.get("batch_id"), "batch_id", minimum=1)
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                batch = conn.execute("SELECT * FROM timeline_import_batches WHERE id=? AND workspace_id=? AND created_by=?", (batch_id, workspace_id, user["id"])).fetchone()
                if not batch:
                    raise ApiError(404, "TIMELINE_IMPORT_BATCH_NOT_FOUND", "导入批次不存在")
                if batch["status"] == "committed":
                    raise ApiError(409, "TIMELINE_IMPORT_ALREADY_COMMITTED", "导入批次已提交")
                rows = [{key: row[key] for key in ("project", "track", "stage", "name", "date", "status", "remark")} for row in json.loads(batch["preview_json"])]
                names = {row[0] for row in conn.execute("SELECT name FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL", (workspace_id,))}
                clean = self._validate_timeline_rows(rows, names, batch["file_format"])
                stamp = utc_now()
                projects_created = 0
                nodes_created = 0
                for name, group in self._group_import_rows(clean).items():
                    project_id = conn.execute(
                        "INSERT INTO timeline_projects(workspace_id,name,created_by,created_at,updated_at) VALUES (?,?,?,?,?)",
                        (workspace_id, name, user["id"], stamp, stamp),
                    ).lastrowid
                    timeline_batch = conn.execute(
                        """INSERT INTO timeline_change_batches(project_id,actor_user_id,change_kind,trigger_source,project_version_before,project_version_after,details_json,created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (project_id, user["id"], "direct_edit", "import", 1, 1, json.dumps({"file_sha256": batch["content_sha256"]}, ensure_ascii=False), stamp),
                    ).lastrowid
                    for values in group:
                        node_id = self._insert_node(conn, project_id, user["id"], {"track": values["track"], "stage": values["stage"], "name": values["name"], "date": values["date"], "done_at": values["status"] == "已完成", "remark": values["remark"]}, stamp)
                        conn.execute("INSERT INTO timeline_node_changes(batch_id,node_id,change_role,field,old_value,new_value) VALUES (?,?,?,?,NULL,?)", (timeline_batch, node_id, "direct", "created", json.dumps(values, ensure_ascii=False)))
                        nodes_created += 1
                    self._audit(conn, workspace_id, user["id"], timeline_batch, "timeline.batch_committed")
                    projects_created += 1
                updated = conn.execute("UPDATE timeline_import_batches SET status='committed',version=version+1,committed_at=? WHERE id=? AND status='previewed'", (stamp, batch_id))
                if updated.rowcount != 1:
                    raise ApiError(409, "TIMELINE_IMPORT_ALREADY_COMMITTED", "导入批次已提交")
                return {"batch_id": batch_id, "projects": projects_created, "nodes": nodes_created}
        finally:
            conn.close()

    @staticmethod
    def _tag_row(conn, workspace_id, tag_id):
        tag = conn.execute(
            "SELECT * FROM timeline_tags WHERE id=? AND workspace_id=? AND deleted_at IS NULL",
            (tag_id, workspace_id),
        ).fetchone()
        if not tag:
            raise ApiError(404, "TIMELINE_TAG_NOT_FOUND", "标签不存在或已删除")
        return tag

    @staticmethod
    def _tag_payload(conn, tag):
        count = conn.execute(
            "SELECT COUNT(*) FROM timeline_project_tags pt JOIN timeline_projects p ON p.id=pt.project_id "
            "WHERE pt.tag_id=? AND pt.deleted_at IS NULL AND p.deleted_at IS NULL AND p.archived_at IS NULL",
            (tag["id"],),
        ).fetchone()[0]
        return {"tag_id": tag["id"], "name": tag["name"], "version": tag["version"], "project_count": count}

    def _tag_membership_view(self, conn, workspace_id, tag):
        rows = conn.execute(
            """SELECT p.id project_id,p.name,
                      CASE WHEN pt.id IS NULL THEN 0 ELSE 1 END included
               FROM timeline_projects p
               LEFT JOIN timeline_project_tags pt
                 ON pt.project_id=p.id AND pt.tag_id=? AND pt.deleted_at IS NULL
               WHERE p.workspace_id=? AND p.deleted_at IS NULL AND p.archived_at IS NULL
               ORDER BY p.id""",
            (tag["id"], workspace_id),
        ).fetchall()
        payload = [{"project_id": row["project_id"], "name": row["name"]} for row in rows]
        return {
            "tag": self._tag_payload(conn, tag),
            "included": [item for item, row in zip(payload, rows) if row["included"]],
            "excluded": [item for item, row in zip(payload, rows) if not row["included"]],
        }

    def list_tags(self, user, workspace_id):
        conn = self._db()
        try:
            role = self._workspace_access(conn, user["id"], workspace_id)
            tags = conn.execute(
                "SELECT * FROM timeline_tags WHERE workspace_id=? AND deleted_at IS NULL ORDER BY name COLLATE NOCASE,id",
                (workspace_id,),
            ).fetchall()
            all_count = conn.execute(
                "SELECT COUNT(*) FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL AND archived_at IS NULL", (workspace_id,)
            ).fetchone()[0]
            mine_count = conn.execute(
                "SELECT COUNT(*) FROM timeline_projects WHERE workspace_id=? AND created_by=? AND deleted_at IS NULL AND archived_at IS NULL",
                (workspace_id, user["id"]),
            ).fetchone()[0]
            uncategorized_count = conn.execute(
                """SELECT COUNT(*) FROM timeline_projects p
                   WHERE p.workspace_id=? AND p.deleted_at IS NULL AND p.archived_at IS NULL
                     AND NOT EXISTS(SELECT 1 FROM timeline_project_tags pt
                                    WHERE pt.project_id=p.id AND pt.deleted_at IS NULL)""",
                (workspace_id,),
            ).fetchone()[0]
            archived_count = conn.execute(
                "SELECT COUNT(*) FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL AND archived_at IS NOT NULL",
                (workspace_id,),
            ).fetchone()[0]
            return {
                "role": role,
                "virtual": [
                    {"context_type": "all", "name": "全部", "project_count": all_count},
                    {"context_type": "mine", "name": "我的项目", "project_count": mine_count},
                    {"context_type": "uncategorized", "name": "未分类", "project_count": uncategorized_count},
                    {"context_type": "archived", "name": "已归档项目", "project_count": archived_count},
                ],
                "tags": [self._tag_payload(conn, tag) for tag in tags],
            }
        finally:
            conn.close()

    def create_tag(self, user, workspace_id, data):
        reject_unknown(data, {"name"})
        name = require_text(data, "name", max_length=80)
        if name.casefold() in {"全部".casefold(), "我的项目".casefold(), "未分类".casefold(), "已归档项目".casefold()}:
            raise ApiError(409, "TAG_NAME_CONFLICT", "该名称为系统标签")
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                if conn.execute(
                    "SELECT 1 FROM timeline_tags WHERE workspace_id=? AND name=? COLLATE NOCASE AND deleted_at IS NULL",
                    (workspace_id, name),
                ).fetchone():
                    raise ApiError(409, "TAG_NAME_CONFLICT", "标签名称已存在")
                stamp = utc_now()
                tag_id = conn.execute(
                    "INSERT INTO timeline_tags(workspace_id,name,created_by,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (workspace_id, name, user["id"], stamp, stamp),
                ).lastrowid
                tag = self._tag_row(conn, workspace_id, tag_id)
                self._audit(conn, workspace_id, user["id"], tag_id, "timeline.tag_created", "timeline_tag", {"name": name, "version": 1})
                return self._tag_payload(conn, tag)
        finally:
            conn.close()

    def rename_tag(self, user, workspace_id, tag_id, data):
        reject_unknown(data, {"name", "base_version"})
        name = require_text(data, "name", max_length=80)
        if "base_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
        base_version = require_int(data["base_version"], "base_version", minimum=1)
        if name.casefold() in {"全部".casefold(), "我的项目".casefold(), "未分类".casefold(), "已归档项目".casefold()}:
            raise ApiError(409, "TAG_NAME_CONFLICT", "该名称为系统标签")
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                tag = self._tag_row(conn, workspace_id, tag_id)
                if tag["version"] != base_version:
                    raise ApiError(409, "TAG_VERSION_CONFLICT", "标签版本冲突", {"tag": self._tag_payload(conn, tag)})
                if tag["name"] == name:
                    return self._tag_payload(conn, tag)
                if conn.execute(
                    "SELECT 1 FROM timeline_tags WHERE workspace_id=? AND id<>? AND name=? COLLATE NOCASE AND deleted_at IS NULL",
                    (workspace_id, tag_id, name),
                ).fetchone():
                    raise ApiError(409, "TAG_NAME_CONFLICT", "标签名称已存在")
                stamp = utc_now()
                updated = conn.execute(
                    "UPDATE timeline_tags SET name=?,version=version+1,updated_at=? WHERE id=? AND version=? AND deleted_at IS NULL",
                    (name, stamp, tag_id, base_version),
                )
                if updated.rowcount != 1:
                    latest = self._tag_row(conn, workspace_id, tag_id)
                    raise ApiError(409, "TAG_VERSION_CONFLICT", "标签版本冲突", {"tag": self._tag_payload(conn, latest)})
                latest = self._tag_row(conn, workspace_id, tag_id)
                self._audit(conn, workspace_id, user["id"], tag_id, "timeline.tag_renamed", "timeline_tag", {"old_name": tag["name"], "name": name, "version": latest["version"]})
                return self._tag_payload(conn, latest)
        finally:
            conn.close()

    def delete_tag(self, user, workspace_id, tag_id, data):
        reject_unknown(data, {"base_version"})
        if "base_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_version is required")
        base_version = require_int(data["base_version"], "base_version", minimum=1)
        conn = self._db()
        try:
            with transaction(conn):
                role = self._workspace_access(conn, user["id"], workspace_id)
                if role != "admin":
                    raise ApiError(403, "ADMIN_REQUIRED", "仅管理员可删除标签")
                tag = self._tag_row(conn, workspace_id, tag_id)
                if tag["version"] != base_version:
                    raise ApiError(409, "TAG_VERSION_CONFLICT", "标签版本冲突", {"tag": self._tag_payload(conn, tag)})
                stamp = utc_now()
                conn.execute(
                    "UPDATE timeline_tags SET deleted_at=?,deleted_by=?,version=version+1,updated_at=? WHERE id=? AND version=?",
                    (stamp, user["id"], stamp, tag_id, base_version),
                )
                conn.execute(
                    "UPDATE timeline_project_tags SET deleted_at=?,removed_by=?,version=version+1,updated_at=? WHERE tag_id=? AND deleted_at IS NULL",
                    (stamp, user["id"], stamp, tag_id),
                )
                context_ids = [row[0] for row in conn.execute(
                    "SELECT id FROM timeline_order_contexts WHERE tag_id=? AND deleted_at IS NULL", (tag_id,)
                )]
                if context_ids:
                    marks = ",".join("?" for _ in context_ids)
                    conn.execute(f"UPDATE timeline_order_items SET deleted_at=?,updated_at=? WHERE context_id IN ({marks}) AND deleted_at IS NULL", (stamp, stamp, *context_ids))
                conn.execute(
                    "UPDATE timeline_order_contexts SET deleted_at=?,updated_at=? WHERE tag_id=? AND deleted_at IS NULL",
                    (stamp, stamp, tag_id),
                )
                self._audit(conn, workspace_id, user["id"], tag_id, "timeline.tag_deleted", "timeline_tag", {"name": tag["name"], "version": base_version + 1})
                return {"tag_id": tag_id, "version": base_version + 1, "deleted_at": stamp}
        finally:
            conn.close()

    def get_tag_projects(self, user, workspace_id, tag_id):
        conn = self._db()
        try:
            self._workspace_access(conn, user["id"], workspace_id)
            tag = self._tag_row(conn, workspace_id, tag_id)
            return self._tag_membership_view(conn, workspace_id, tag)
        finally:
            conn.close()

    def set_tag_project(self, user, workspace_id, tag_id, project_id, data, *, included):
        reject_unknown(data, {"base_tag_version"})
        if "base_tag_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_tag_version is required")
        base_version = require_int(data["base_tag_version"], "base_tag_version", minimum=1)
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                tag = self._tag_row(conn, workspace_id, tag_id)
                if tag["version"] != base_version:
                    raise ApiError(409, "TAG_VERSION_CONFLICT", "标签版本冲突", {"view": self._tag_membership_view(conn, workspace_id, tag)})
                project = self._project_access(conn, user["id"], project_id, workspace_id=workspace_id, require_active=True)
                if project["archived_at"]:
                    raise ApiError(409, "PROJECT_ARCHIVED", "项目已归档；请先取消归档再修改标签")
                relation = conn.execute(
                    "SELECT * FROM timeline_project_tags WHERE project_id=? AND tag_id=? AND deleted_at IS NULL",
                    (project_id, tag_id),
                ).fetchone()
                if bool(relation) == included:
                    return self._tag_membership_view(conn, workspace_id, tag)
                stamp = utc_now()
                if included:
                    was_uncategorized = not conn.execute(
                        "SELECT 1 FROM timeline_project_tags WHERE project_id=? AND deleted_at IS NULL", (project_id,)
                    ).fetchone()
                    relation_id = conn.execute(
                        """INSERT INTO timeline_project_tags(workspace_id,project_id,tag_id,created_by,created_at,updated_at)
                           VALUES (?,?,?,?,?,?)""",
                        (workspace_id, project_id, tag_id, user["id"], stamp, stamp),
                    ).lastrowid
                    if was_uncategorized:
                        conn.execute(
                            """UPDATE timeline_order_items SET deleted_at=?,updated_at=?
                               WHERE project_id=? AND deleted_at IS NULL AND context_id IN (
                                   SELECT id FROM timeline_order_contexts
                                   WHERE workspace_id=? AND context_type='uncategorized' AND deleted_at IS NULL
                               )""",
                            (stamp, stamp, project_id, workspace_id),
                        )
                    action = "timeline.tag_project_added"
                else:
                    relation_id = relation["id"]
                    conn.execute(
                        "UPDATE timeline_project_tags SET deleted_at=?,removed_by=?,version=version+1,updated_at=? WHERE id=? AND deleted_at IS NULL",
                        (stamp, user["id"], stamp, relation_id),
                    )
                    conn.execute(
                        """UPDATE timeline_order_items SET deleted_at=?,updated_at=?
                           WHERE project_id=? AND deleted_at IS NULL AND context_id IN (
                               SELECT id FROM timeline_order_contexts
                               WHERE workspace_id=? AND context_type='tag' AND tag_id=? AND deleted_at IS NULL
                           )""",
                        (stamp, stamp, project_id, workspace_id, tag_id),
                    )
                    action = "timeline.tag_project_removed"
                updated = conn.execute(
                    "UPDATE timeline_tags SET version=version+1,updated_at=? WHERE id=? AND version=? AND deleted_at IS NULL",
                    (stamp, tag_id, base_version),
                )
                if updated.rowcount != 1:
                    latest = self._tag_row(conn, workspace_id, tag_id)
                    raise ApiError(409, "TAG_VERSION_CONFLICT", "标签版本冲突", {"view": self._tag_membership_view(conn, workspace_id, latest)})
                latest = self._tag_row(conn, workspace_id, tag_id)
                self._audit(conn, workspace_id, user["id"], relation_id, action, "timeline_project_tag", {"tag_id": tag_id, "project_id": project_id, "tag_version": latest["version"]})
                return self._tag_membership_view(conn, workspace_id, latest)
        finally:
            conn.close()

    def _order_scope(self, conn, user_id, workspace_id, context_type, tag_id, *, include_archived=False):
        archive_filter = "" if include_archived else " AND archived_at IS NULL"
        project_archive_filter = "" if include_archived else " AND p.archived_at IS NULL"
        if context_type == "mine":
            rows = conn.execute(
                f"SELECT id FROM timeline_projects WHERE workspace_id=? AND created_by=? AND deleted_at IS NULL{archive_filter} ORDER BY id",
                (workspace_id, user_id),
            ).fetchall()
        elif context_type == "all":
            rows = conn.execute(
                f"SELECT id FROM timeline_projects WHERE workspace_id=? AND deleted_at IS NULL{archive_filter} ORDER BY id", (workspace_id,)
            ).fetchall()
        elif context_type == "uncategorized":
            rows = conn.execute(
                f"""SELECT p.id FROM timeline_projects p WHERE p.workspace_id=? AND p.deleted_at IS NULL{project_archive_filter}
                   AND NOT EXISTS(SELECT 1 FROM timeline_project_tags pt WHERE pt.project_id=p.id AND pt.deleted_at IS NULL)
                   ORDER BY p.id""",
                (workspace_id,),
            ).fetchall()
        else:
            self._tag_row(conn, workspace_id, tag_id)
            rows = conn.execute(
                f"""SELECT p.id FROM timeline_projects p JOIN timeline_project_tags pt ON pt.project_id=p.id
                   WHERE p.workspace_id=? AND p.deleted_at IS NULL{project_archive_filter} AND pt.tag_id=? AND pt.deleted_at IS NULL ORDER BY p.id""",
                (workspace_id, tag_id),
            ).fetchall()
        return [row["id"] for row in rows]

    @staticmethod
    def _order_context(conn, user_id, workspace_id, context_type, tag_id):
        return conn.execute(
            """SELECT * FROM timeline_order_contexts
               WHERE workspace_id=? AND user_id=? AND context_type=?
                 AND ((? IS NULL AND tag_id IS NULL) OR tag_id=?) AND deleted_at IS NULL""",
            (workspace_id, user_id, context_type, tag_id, tag_id),
        ).fetchone()

    def _order_view(self, conn, user_id, workspace_id, context_type, tag_id):
        scope = self._order_scope(conn, user_id, workspace_id, context_type, tag_id)
        context = self._order_context(conn, user_id, workspace_id, context_type, tag_id)
        stored = []
        if context:
            stored = [row["project_id"] for row in conn.execute(
                "SELECT project_id FROM timeline_order_items WHERE context_id=? AND deleted_at IS NULL ORDER BY position,id",
                (context["id"],),
            )]
        scope_set = set(scope)
        ordered = [project_id for project_id in stored if project_id in scope_set]
        seen = set(ordered)
        ordered.extend(project_id for project_id in scope if project_id not in seen)
        return {"context_type": context_type, "tag_id": tag_id, "order_version": context["version"] if context else 0, "project_ids": ordered}

    @staticmethod
    def _validate_order_context(context_type, tag_id):
        if context_type not in {"mine", "all", "uncategorized", "tag"}:
            raise ApiError(422, "VALIDATION_ERROR", "context_type is invalid")
        if context_type == "tag":
            return require_int(tag_id, "tag_id", minimum=1)
        if tag_id is not None:
            raise ApiError(422, "VALIDATION_ERROR", "tag_id is only valid for tag context")
        return None

    def get_personal_order(self, user, workspace_id, context_type, tag_id=None):
        tag_id = self._validate_order_context(context_type, tag_id)
        conn = self._db()
        try:
            self._workspace_access(conn, user["id"], workspace_id)
            return self._order_view(conn, user["id"], workspace_id, context_type, tag_id)
        finally:
            conn.close()

    def put_personal_order(self, user, workspace_id, data):
        reject_unknown(data, {"context_type", "tag_id", "base_order_version", "project_ids"})
        context_type = data.get("context_type")
        tag_id = self._validate_order_context(context_type, data.get("tag_id"))
        if "base_order_version" not in data:
            raise ApiError(428, "VERSION_REQUIRED", "base_order_version is required")
        base_version = require_int(data["base_order_version"], "base_order_version", minimum=0)
        project_ids = data.get("project_ids")
        if not isinstance(project_ids, list) or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in project_ids):
            raise ApiError(422, "VALIDATION_ERROR", "project_ids must be positive integer ids")
        if len(project_ids) != len(set(project_ids)):
            raise ApiError(422, "VALIDATION_ERROR", "project_ids must not contain duplicates")
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_access(conn, user["id"], workspace_id)
                latest = self._order_view(conn, user["id"], workspace_id, context_type, tag_id)
                if latest["order_version"] != base_version:
                    raise ApiError(409, "ORDER_VERSION_CONFLICT", "个人排序版本冲突", {"order": latest})
                if set(project_ids) != set(latest["project_ids"]) or len(project_ids) != len(latest["project_ids"]):
                    raise ApiError(409, "ORDER_SCOPE_CHANGED", "项目集合已变化", {"order": latest})
                stamp = utc_now()
                context = self._order_context(conn, user["id"], workspace_id, context_type, tag_id)
                if context:
                    context_id = context["id"]
                    active_scope = set(latest["project_ids"])
                    underlying_scope = set(self._order_scope(
                        conn, user["id"], workspace_id, context_type, tag_id, include_archived=True
                    ))
                    existing = conn.execute(
                        "SELECT id,project_id,position FROM timeline_order_items WHERE context_id=? AND deleted_at IS NULL ORDER BY position,id",
                        (context_id,),
                    ).fetchall()
                    hidden = underlying_scope - active_scope
                    submitted_iter = iter(project_ids)
                    merged = []
                    for item in existing:
                        project_id = item["project_id"]
                        if project_id in hidden:
                            merged.append(project_id)
                        elif project_id in active_scope:
                            merged.append(next(submitted_iter))
                    merged.extend(submitted_iter)
                    merged_set = set(merged)
                    obsolete = [item["id"] for item in existing if item["project_id"] not in merged_set]
                    if obsolete:
                        marks = ",".join("?" for _ in obsolete)
                        conn.execute(
                            f"UPDATE timeline_order_items SET deleted_at=?,updated_at=? WHERE id IN ({marks}) AND deleted_at IS NULL",
                            (stamp, stamp, *obsolete),
                        )
                    retained = {item["project_id"]: item["id"] for item in existing if item["project_id"] in merged_set}
                    if retained:
                        marks = ",".join("?" for _ in retained)
                        conn.execute(
                            f"UPDATE timeline_order_items SET position=position+1000000,updated_at=? WHERE id IN ({marks})",
                            (stamp, *retained.values()),
                        )
                    for position, project_id in enumerate(merged):
                        item_id = retained.get(project_id)
                        if item_id:
                            conn.execute(
                                "UPDATE timeline_order_items SET position=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                                (position, stamp, item_id),
                            )
                        else:
                            conn.execute(
                                "INSERT INTO timeline_order_items(context_id,project_id,position,created_at,updated_at) VALUES (?,?,?,?,?)",
                                (context_id, project_id, position, stamp, stamp),
                            )
                    updated = conn.execute(
                        "UPDATE timeline_order_contexts SET version=version+1,updated_at=? WHERE id=? AND version=?",
                        (stamp, context["id"], base_version),
                    )
                    if updated.rowcount != 1:
                        raise ApiError(409, "ORDER_VERSION_CONFLICT", "个人排序版本冲突", {"order": self._order_view(conn, user["id"], workspace_id, context_type, tag_id)})
                    next_version = base_version + 1
                else:
                    context_id = conn.execute(
                        """INSERT INTO timeline_order_contexts(workspace_id,user_id,context_type,tag_id,version,created_at,updated_at)
                           VALUES (?,?,?,?,1,?,?)""",
                        (workspace_id, user["id"], context_type, tag_id, stamp, stamp),
                    ).lastrowid
                    next_version = 1
                    conn.executemany(
                        "INSERT INTO timeline_order_items(context_id,project_id,position,created_at,updated_at) VALUES (?,?,?,?,?)",
                        [(context_id, project_id, position, stamp, stamp) for position, project_id in enumerate(project_ids)],
                    )
                self._audit(conn, workspace_id, user["id"], context_id, "timeline.personal_order_changed", "timeline_order_context", {"context_type": context_type, "tag_id": tag_id, "version": next_version, "project_count": len(project_ids)})
                return {"context_type": context_type, "tag_id": tag_id, "order_version": next_version, "project_ids": project_ids}
        finally:
            conn.close()
