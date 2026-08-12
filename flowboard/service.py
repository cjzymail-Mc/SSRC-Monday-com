import base64
import csv
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import unicodedata
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

from .database import connect, transaction, utc_now
from .security import new_token, token_hash, verify_password
from .advanced import FormulaError, evaluate as evaluate_formula, references as formula_references
from .transfer import TransferError, infer_columns, make_csv, make_xlsx, parse_upload
from .schedule import MAX_SCHEDULE_TASKS, SCALES, ScheduleError, critical_path, parse_day, project as project_schedule
from .aggregation import AggregationError, MAX_WIDGET_TASKS, aggregate as aggregate_rows, aggregate_value, validate_spec as validate_aggregation_spec
from .operations import OperationsError, create_backup, list_backups, verify_backup


COLORS = {"purple", "orange", "green", "blue"}
STATUSES = {"待开始", "进行中", "审核中", "已完成"}
PRIORITIES = {"高", "中", "低"}
ENTITY_TYPES = {"board", "group", "task", "comment"}
FIELD_TYPES = {"text", "number", "status", "person", "date", "checkbox", "tags", "link",
               "timeline", "rating", "file", "email", "phone", "relation", "mirror", "formula"}
READ_ONLY_FIELD_TYPES = {"mirror", "formula"}
COMMAND_ACTION = {"archive": "archived", "unarchive": "unarchived", "restore": "restored"}


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details

    def payload(self):
        error = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


def require_object(value, name="request body"):
    if not isinstance(value, dict):
        raise ApiError(400, "INVALID_REQUEST", f"{name} must be a JSON object")
    return value


def require_int(value, name, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(422, "VALIDATION_ERROR", f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ApiError(422, "VALIDATION_ERROR", f"{name} is out of range")
    return value


def require_version(data):
    if "version" not in data:
        raise ApiError(428, "VERSION_REQUIRED", "操作必须提供 version")
    return require_int(data["version"], "version", minimum=1)


def require_text(data, key, *, max_length=500, allow_empty=False):
    value = data.get(key)
    if not isinstance(value, str):
        raise ApiError(422, "VALIDATION_ERROR", f"{key} must be text")
    value = value.strip()
    if not value and not allow_empty:
        raise ApiError(422, "VALIDATION_ERROR", f"{key} is required")
    if len(value) > max_length:
        raise ApiError(422, "VALIDATION_ERROR", f"{key} is too long")
    return value


def reject_unknown(data, allowed):
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ApiError(422, "UNKNOWN_FIELD", "请求包含未知字段", {"fields": unknown})


def validate_choice(value, name, choices):
    if not isinstance(value, str) or value not in choices:
        raise ApiError(422, "VALIDATION_ERROR", f"{name} is invalid")
    return value


def validate_due(value):
    if not isinstance(value, str) or len(value) > 10:
        raise ApiError(422, "VALIDATION_ERROR", "due is invalid")
    if value == "未设置":
        return value
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ApiError(422, "VALIDATION_ERROR", "due must be 未设置 or YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", "due is not a valid date")
    return value


class FlowboardService:
    def __init__(self, db_path):
        self.db_path = db_path
        self.attachment_root = Path(os.getenv("FLOWBOARD_ATTACHMENT_DIR", str(Path(db_path).parent / "flowboard-attachments"))).resolve()
        self.backup_root = Path(os.getenv("FLOWBOARD_BACKUP_DIR", str(Path(db_path).parent / "backups"))).resolve()

    def _db(self):
        return connect(self.db_path)

    # Authentication -----------------------------------------------------
    def login(self, username, password):
        conn = self._db()
        try:
            user = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
            if not user or not verify_password(password, user["password_hash"]):
                raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
            token, csrf = new_token(), new_token()
            expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(timespec="seconds")
            with transaction(conn):
                conn.execute("DELETE FROM sessions WHERE expires_at<=?", (utc_now(),))
                conn.execute(
                    "INSERT INTO sessions(token_hash,csrf_token,user_id,created_at,expires_at) VALUES (?,?,?,?,?)",
                    (token_hash(token), csrf, user["id"], utc_now(), expires),
                )
                for membership in conn.execute("SELECT workspace_id FROM workspace_memberships WHERE user_id=?",(user["id"],)):
                    conn.execute("""INSERT INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",(f"login:{secrets.token_hex(16)}",membership[0],user["id"],"auth.login","success","user",user["id"],"{}",utc_now()))
            return token, csrf, self._public_user(user)
        finally:
            conn.close()

    def authenticate(self, token):
        if not token:
            raise ApiError(401, "AUTH_REQUIRED", "请先登录")
        conn = self._db()
        try:
            row = conn.execute(
                """SELECT s.csrf_token,s.expires_at,u.* FROM sessions s JOIN users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1""",
                (token_hash(token), utc_now()),
            ).fetchone()
            if not row:
                raise ApiError(401, "SESSION_INVALID", "登录已过期，请重新登录")
            return dict(row)
        finally:
            conn.close()

    def logout(self, token):
        conn = self._db()
        try:
            with transaction(conn):
                session=conn.execute("SELECT user_id FROM sessions WHERE token_hash=?",(token_hash(token),)).fetchone()
                if session:
                    for membership in conn.execute("SELECT workspace_id FROM workspace_memberships WHERE user_id=?",(session[0],)):
                        conn.execute("""INSERT INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?)""",(f"logout:{secrets.token_hex(16)}",membership[0],session[0],"auth.logout","success","user",session[0],"{}",utc_now()))
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
        finally:
            conn.close()

    @staticmethod
    def verify_csrf(user, supplied):
        if not supplied or supplied != user["csrf_token"]:
            raise ApiError(403, "CSRF_INVALID", "请求校验失败，请刷新后重试")

    @staticmethod
    def _public_user(user):
        return {key: user[key] for key in ("id", "username", "name", "avatar", "avatar_class")}

    def session_info(self, user):
        return {"user": self._public_user(user), "csrf_token": user["csrf_token"]}

    # Authorization and query helpers ----------------------------------
    def _workspace_role(self, conn, user_id, workspace_id, *, write=False):
        row = conn.execute(
            "SELECT role FROM workspace_memberships WHERE workspace_id=? AND user_id=?",
            (workspace_id, user_id),
        ).fetchone()
        if not row:
            raise ApiError(403, "RESOURCE_FORBIDDEN", "资源不存在或不可访问")
        if write and row["role"] == "viewer":
            raise ApiError(403, "READ_ONLY", "只读成员不能修改数据")
        return row["role"]

    def _board_access(self, conn, user_id, board_id, *, write=False, require_active=False):
        row = conn.execute(
            """SELECT b.*,wm.role,
                      EXISTS(SELECT 1 FROM board_memberships bm WHERE bm.board_id=b.id AND bm.user_id=?) listed
               FROM boards b JOIN workspace_memberships wm ON wm.workspace_id=b.workspace_id AND wm.user_id=?
               WHERE b.id=?""",
            (user_id, user_id, board_id),
        ).fetchone()
        if not row or (row["access_type"] == "private" and row["role"] != "admin" and not row["listed"]):
            raise ApiError(403, "BOARD_FORBIDDEN", "资源不存在或不可访问")
        if write and row["role"] == "viewer":
            raise ApiError(403, "READ_ONLY", "只读成员不能修改数据")
        if require_active and (row["deleted_at"] or row["archived_at"]):
            raise ApiError(404, "BOARD_NOT_ACTIVE", "看板当前不可用")
        return row

    def _group_context(self, conn, user_id, group_id, *, write=False, require_active=False):
        row = conn.execute(
            """SELECT g.*,b.workspace_id,b.access_type,b.version board_version,
                      b.deleted_at board_deleted_at,b.archived_at board_archived_at
               FROM groups_ g JOIN boards b ON b.id=g.board_id WHERE g.id=?""",
            (group_id,),
        ).fetchone()
        if not row:
            raise ApiError(403, "RESOURCE_FORBIDDEN", "资源不存在或不可访问")
        self._board_access(conn, user_id, row["board_id"], write=write)
        if require_active and (
            row["deleted_at"] or row["archived_at"] or row["board_deleted_at"] or row["board_archived_at"]
        ):
            raise ApiError(404, "GROUP_NOT_ACTIVE", "分组当前不可用")
        return row

    def _task_context(self, conn, user_id, task_id, *, write=False, require_active=False):
        row = conn.execute(
            """SELECT t.*,g.board_id,g.version group_version,g.deleted_at group_deleted_at,
                      g.archived_at group_archived_at,b.workspace_id,b.version board_version,b.deleted_at board_deleted_at,
                      b.archived_at board_archived_at
               FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
               WHERE t.id=?""",
            (task_id,),
        ).fetchone()
        if not row:
            raise ApiError(403, "RESOURCE_FORBIDDEN", "资源不存在或不可访问")
        self._board_access(conn, user_id, row["board_id"], write=write)
        if require_active and any(
            row[key]
            for key in ("deleted_at", "archived_at", "group_deleted_at", "group_archived_at", "board_deleted_at", "board_archived_at")
        ):
            raise ApiError(404, "TASK_NOT_ACTIVE", "任务当前不可用")
        return row

    @staticmethod
    def _activity(conn, board_id, entity_type, entity_id, user_id, action_code, details=None, task_id=None):
        if entity_type not in ENTITY_TYPES:
            raise ValueError("invalid activity entity")
        cursor=conn.execute(
            """INSERT INTO activity(board_id,task_id,entity_type,entity_id,user_id,action_code,details_json,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (board_id, task_id, entity_type, entity_id, user_id, action_code, json.dumps(details or {}, ensure_ascii=False), utc_now()),
        )
        activity_id=cursor.lastrowid
        workspace_id=conn.execute("SELECT workspace_id FROM boards WHERE id=?",(board_id,)).fetchone()[0]
        stamp=utc_now()
        conn.execute("""INSERT OR IGNORE INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",(f"activity:{activity_id}",workspace_id,user_id,action_code,"success",entity_type,str(entity_id),json.dumps(details or {},ensure_ascii=False),stamp))
        conn.execute("""INSERT OR IGNORE INTO realtime_events(event_key,workspace_id,board_id,task_id,actor_user_id,action_code,created_at)
            VALUES (?,?,?,?,?,?,?)""",(f"activity:{activity_id}",workspace_id,board_id,task_id,user_id,action_code,stamp))

    @staticmethod
    def _activity_payload(rows):
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except (TypeError, ValueError):
                item["details"] = {}
                item.pop("details_json", None)
            result.append(item)
        return result

    @staticmethod
    def _conflict(cursor, message):
        if cursor.rowcount != 1:
            raise ApiError(409, "VERSION_CONFLICT", message)

    def _field_payloads(self, conn, board_id, *, include_deleted=False, user_id=None):
        fields = []
        rows = conn.execute(
            f"""SELECT * FROM field_definitions WHERE board_id=? {' ' if include_deleted else 'AND deleted_at IS NULL'}
               ORDER BY deleted_at IS NOT NULL,sort_order,id""", (board_id,)
        ).fetchall()
        for row in rows:
            item = dict(row)
            item["config"] = json.loads(item.pop("config_json") or "{}")
            template_unbound=item["field_type"]=="relation" and not item["is_active"] and item["config"].get("template_unbound") is True
            if user_id and item["field_type"] in {"relation","mirror"} and not template_unbound:
                target_id=item["config"].get("target_board_id")
                if item["field_type"]=="mirror":
                    relation=conn.execute("SELECT config_json FROM field_definitions WHERE id=?",(item["config"].get("relation_field_id"),)).fetchone()
                    target_id=json.loads(relation["config_json"]).get("target_board_id") if relation else None
                try:self._board_access(conn,user_id,target_id,require_active=True)
                except ApiError:
                    item["config"]={"unavailable":True};item["diagnostic"]={"code":"FIELD_SOURCE_UNAVAILABLE","message":"字段来源不可访问"}
            item["options"] = [dict(option) for option in conn.execute(
                """SELECT * FROM field_options WHERE field_id=? AND deleted_at IS NULL
                   ORDER BY sort_order,id""", (row["id"],)
            )]
            fields.append(item)
        return fields

    @staticmethod
    def _task_values(conn, task_id):
        values = {}
        for row in conn.execute(
            """SELECT v.*,f.field_type FROM task_field_values v
               JOIN field_definitions f ON f.id=v.field_id WHERE v.task_id=?""", (task_id,)
        ):
            kind = row["field_type"]
            if kind in {"status"}: value = row["option_id"]
            elif kind in {"text", "email", "phone"}: value = row["text_value"]
            elif kind in {"number", "rating"}: value = row["number_value"]
            elif kind in {"timeline", "file"}:
                try: value = json.loads(row["text_value"])
                except (TypeError, json.JSONDecodeError): value = {"diagnostic":"VALUE_INVALID"}
            elif kind == "person": value = row["user_id"]
            elif kind == "date": value = row["date_value"]
            elif kind == "checkbox": value = bool(row["boolean_value"])
            elif kind == "link": value = {"url": row["link_url"], "label": row["link_label"] or ""}
            else: continue
            values[str(row["field_id"])] = value
        tag_rows = conn.execute(
            "SELECT field_id,option_id FROM task_field_tag_values WHERE task_id=? ORDER BY field_id,sort_order,option_id",
            (task_id,),
        ).fetchall()
        for row in tag_rows:
            values.setdefault(str(row["field_id"]), []).append(row["option_id"])
        for row in conn.execute("SELECT field_id,raw_value,reason FROM legacy_task_field_values WHERE task_id=?", (task_id,)):
            values[str(row["field_id"])] = {"legacy_raw": row["raw_value"], "reason": row["reason"]}
        return values

    def _advanced_values(self, conn, user_id, task, values):
        from .query import active_task_sql
        fields={row["id"]:row for row in conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND deleted_at IS NULL AND is_active=1",(task["board_id"],))}
        diagnostics={}; resolving=set()
        def resolve(field_id):
            key=str(field_id)
            if key in values: return values[key]
            field=fields.get(field_id)
            if not field: return None
            if field_id in resolving:
                diagnostics[key]={"code":"FIELD_CYCLE","message":"字段依赖循环"};return None
            resolving.add(field_id)
            try:
                config=json.loads(field["config_json"] or "{}")
                if field["field_type"]=="relation":
                    self._board_access(conn,user_id,config.get("target_board_id"),require_active=True)
                    rows=conn.execute(f"""SELECT r.id relation_id,r.version relation_version,t.id,t.title,t.version,g.board_id
                        FROM task_relation_values r JOIN tasks t ON t.id=r.target_task_id JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
                        WHERE r.field_id=? AND r.source_task_id=? AND r.deleted_at IS NULL
                        AND {active_task_sql('t','g','b')} ORDER BY r.id""",(field_id,task["id"])).fetchall()
                    visible=[]
                    for row in rows:
                        try:self._board_access(conn,user_id,row["board_id"],require_active=True)
                        except ApiError:continue
                        visible.append(dict(row))
                    values[key]=visible
                elif field["field_type"]=="mirror":
                    relation_id=config.get("relation_field_id");source_id=config.get("source_field_id")
                    related=resolve(relation_id) if isinstance(relation_id,int) else []
                    if str(relation_id) in diagnostics: raise ApiError(403,"FIELD_SOURCE_UNAVAILABLE","字段来源不可访问")
                    mirrored=[]
                    for target in related or []:
                        target_task=self._task_context(conn,user_id,target["id"],require_active=True)
                        target_values=self._task_values(conn,target["id"])
                        mirrored.append(target_values.get(str(source_id)))
                    values[key]=mirrored
                    if not related: diagnostics[key]={"code":"MIRROR_EMPTY","message":"关系为空或来源不可访问"}
                elif field["field_type"]=="formula":
                    expression=config.get("expression","")
                    refs=formula_references(expression)
                    context={ref:resolve(ref) for ref in refs}
                    if any(str(ref) in diagnostics for ref in refs): raise FormulaError("FORMULA_SOURCE_UNAVAILABLE")
                    values[key]=evaluate_formula(expression,context)
            except (ApiError, FormulaError, TypeError, ValueError, json.JSONDecodeError) as error:
                code=str(error) if isinstance(error,FormulaError) else "FIELD_SOURCE_UNAVAILABLE"
                diagnostics[key]={"code":code,"message":"字段暂时无法计算"};values[key]=None
            finally: resolving.discard(field_id)
            return values.get(key)
        for field_id,field in fields.items():
            if field["field_type"] in {"relation","mirror","formula"}: resolve(field_id)
        backlinks=[]
        for row in conn.execute(f"""SELECT r.id relation_id,r.version relation_version,r.source_task_id task_id,t.title,
                f.id field_id,f.name field_name,f.config_json,g.board_id
            FROM task_relation_values r JOIN field_definitions f ON f.id=r.field_id
            JOIN tasks t ON t.id=r.source_task_id JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
            WHERE r.target_task_id=? AND r.deleted_at IS NULL AND f.deleted_at IS NULL AND f.is_active=1
            AND {active_task_sql('t','g','b')}""",(task["id"],)):
            try:
                if not json.loads(row["config_json"]).get("bidirectional"): continue
                self._board_access(conn,user_id,row["board_id"],require_active=True)
                item=dict(row);item.pop("config_json",None);backlinks.append(item)
            except (ApiError,ValueError,json.JSONDecodeError): continue
        task["relation_backlinks"]=backlinks
        return diagnostics

    def _write_field_value(self, conn, task, field, value):
        field_id, kind = field["id"], field["field_type"]
        conn.execute("DELETE FROM task_field_values WHERE task_id=? AND field_id=?", (task["id"], field_id))
        conn.execute("DELETE FROM task_field_tag_values WHERE task_id=? AND field_id=?", (task["id"], field_id))
        if value is None or value == "":
            conn.execute("DELETE FROM legacy_task_field_values WHERE task_id=? AND field_id=?", (task["id"], field_id)); return
        columns, args = "", ()
        if kind == "text":
            if not isinstance(value, str) or len(value) > 10000: raise ApiError(422,"VALIDATION_ERROR","文本字段值无效")
            columns, args = "text_value", (value,)
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int,float)): raise ApiError(422,"VALIDATION_ERROR","数字字段值无效")
            columns, args = "number_value", (value,)
        elif kind == "checkbox":
            if not isinstance(value, bool): raise ApiError(422,"VALIDATION_ERROR","复选框字段值无效")
            columns, args = "boolean_value", (int(value),)
        elif kind == "date":
            value = validate_due(value)
            if value == "未设置": return
            columns, args = "date_value", (value,)
        elif kind == "person":
            if not isinstance(value, str): raise ApiError(422,"VALIDATION_ERROR","人员字段值无效")
            self._validate_owner(conn, task["workspace_id"], value); columns, args = "user_id", (value,)
        elif kind == "link":
            if not isinstance(value, dict) or set(value)-{"url","label"}: raise ApiError(422,"VALIDATION_ERROR","链接字段值无效")
            url, label = value.get("url"), value.get("label", "")
            if not isinstance(url,str) or not re.match(r"^https?://",url) or len(url)>2000 or not isinstance(label,str) or len(label)>500: raise ApiError(422,"VALIDATION_ERROR","链接字段值无效")
            columns, args = "link_url,link_label", (url,label)
        elif kind == "email":
            if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",value): raise ApiError(422,"VALIDATION_ERROR","邮箱字段值无效")
            columns,args="text_value",(value,)
        elif kind == "phone":
            if not isinstance(value,str) or len(value)>40 or not re.fullmatch(r"[0-9+() .-]{3,40}",value): raise ApiError(422,"VALIDATION_ERROR","电话字段值无效")
            columns,args="text_value",(value,)
        elif kind == "rating":
            maximum=json.loads(field["config_json"] or "{}").get("max",5)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 or value>maximum: raise ApiError(422,"VALIDATION_ERROR","评分字段值无效")
            columns,args="number_value",(value,)
        elif kind == "timeline":
            if not isinstance(value,dict) or set(value)!={"start","end"}: raise ApiError(422,"VALIDATION_ERROR","时间线字段值无效")
            start,end=validate_due(value["start"]),validate_due(value["end"])
            if start=="未设置" or end=="未设置" or start>end: raise ApiError(422,"VALIDATION_ERROR","时间线范围无效")
            columns,args="text_value",(json.dumps({"start":start,"end":end},ensure_ascii=False),)
        elif kind == "file":
            if not isinstance(value,dict) or set(value)-{"name","size","media_type","attachment_id"}: raise ApiError(422,"VALIDATION_ERROR","文件元数据无效")
            name=value.get("name");size=value.get("size");media=value.get("media_type","")
            if not isinstance(name,str) or not name or len(name)>255 or "/" in name or "\\" in name or isinstance(size,bool) or not isinstance(size,int) or not 0<=size<=100_000_000 or not isinstance(media,str) or len(media)>100: raise ApiError(422,"VALIDATION_ERROR","文件元数据无效")
            if value.get("attachment_id") is not None: raise ApiError(422,"ATTACHMENT_NOT_READY","二进制附件将在 I11 接入")
            columns,args="text_value",(json.dumps({"name":name,"size":size,"media_type":media},ensure_ascii=False),)
        elif kind in READ_ONLY_FIELD_TYPES or kind=="relation":
            raise ApiError(422,"FIELD_READ_ONLY","关系、镜像和公式字段使用专用接口或为只读")
        elif kind in {"status","tags"}:
            if kind=="status":
                if isinstance(value,bool) or not isinstance(value,int): raise ApiError(422,"VALIDATION_ERROR","状态字段必须是单个选项 ID")
                option_ids=[value]
            else:
                option_ids=value
                if not isinstance(option_ids,list) or any(isinstance(v,bool) or not isinstance(v,int) for v in option_ids): raise ApiError(422,"VALIDATION_ERROR","标签字段必须是选项 ID 数组")
                if len(option_ids)!=len(set(option_ids)): raise ApiError(422,"DUPLICATE_OPTION","标签选项不可重复")
            for order, option_id in enumerate(option_ids):
                option=conn.execute("SELECT 1 FROM field_options WHERE id=? AND field_id=? AND is_active=1 AND deleted_at IS NULL",(option_id,field_id)).fetchone()
                if not option: raise ApiError(422,"INVALID_OPTION","字段选项无效")
                if kind=="tags": conn.execute("INSERT INTO task_field_tag_values VALUES (?,?,?,?)",(task["id"],field_id,option_id,order))
            if kind=="tags": return
            columns,args="option_id",(option_ids[0],)
        else: raise ApiError(422,"VALIDATION_ERROR","字段类型不受支持")
        placeholders=','.join('?' for _ in args)
        conn.execute(f"INSERT INTO task_field_values(task_id,field_id,{columns}) VALUES (?,?,{placeholders})",(task["id"],field_id,*args))
        conn.execute("DELETE FROM legacy_task_field_values WHERE task_id=? AND field_id=?",(task["id"],field_id))

    @staticmethod
    def _task_depth(conn, task_id):
        depth, seen, current = 1, set(), task_id
        while current is not None:
            if current in seen: raise ApiError(409,"HIERARCHY_CYCLE","任务层级存在循环")
            seen.add(current)
            row=conn.execute("SELECT parent_id FROM tasks WHERE id=?",(current,)).fetchone()
            if not row or row["parent_id"] is None: return depth
            depth += 1; current=row["parent_id"]
        return depth

    @staticmethod
    def _subtree_height(conn, task_id):
        row=conn.execute("""WITH RECURSIVE tree(id,depth) AS (
            SELECT ?,1 UNION ALL SELECT t.id,tree.depth+1 FROM tasks t JOIN tree ON t.parent_id=tree.id)
            SELECT COALESCE(MAX(depth),1) height FROM tree""",(task_id,)).fetchone()
        return row["height"]

    def _validate_parent(self, conn, task, parent_id):
        if parent_id is None: return None
        if parent_id==task["id"]: raise ApiError(422,"HIERARCHY_SELF","任务不能成为自己的父任务")
        parent=conn.execute("""SELECT t.*,g.board_id FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
            WHERE t.id=? AND t.deleted_at IS NULL AND t.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL
            AND b.deleted_at IS NULL AND b.archived_at IS NULL""",(parent_id,)).fetchone()
        if not parent or parent["board_id"]!=task["board_id"]: raise ApiError(422,"HIERARCHY_PARENT_INVALID","父任务必须是同一看板的活跃任务")
        ancestor=parent_id
        while ancestor is not None:
            if ancestor==task["id"]: raise ApiError(422,"HIERARCHY_CYCLE","不能把任务挂到自己的后代下")
            row=conn.execute("SELECT parent_id FROM tasks WHERE id=?",(ancestor,)).fetchone();ancestor=row["parent_id"] if row else None
        if self._task_depth(conn,parent_id)+self._subtree_height(conn,task["id"])>3: raise ApiError(422,"HIERARCHY_DEPTH","任务层级最多 3 层")
        return parent

    def _relation_summary(self, conn, task_id):
        descendants=conn.execute("""WITH RECURSIVE tree(id) AS (
            SELECT id FROM tasks WHERE parent_id=? AND deleted_at IS NULL AND archived_at IS NULL
            UNION ALL SELECT t.id FROM tasks t JOIN tree ON t.parent_id=tree.id
            WHERE t.deleted_at IS NULL AND t.archived_at IS NULL)
            SELECT id,status FROM tasks WHERE id IN (SELECT id FROM tree)""",(task_id,)).fetchall()
        total=len(descendants);completed=sum(1 for row in descendants if row["status"]=="已完成")
        direct=conn.execute("SELECT status FROM tasks WHERE parent_id=? AND deleted_at IS NULL AND archived_at IS NULL",(task_id,)).fetchall();direct_total=len(direct);direct_completed=sum(1 for row in direct if row["status"]=="已完成")
        predecessors=[dict(row) for row in conn.execute("""SELECT d.id dependency_id,d.version dependency_version,
            p.id,p.title,p.status,p.due,p.version predecessor_task_version FROM task_dependencies d JOIN tasks p ON p.id=d.predecessor_id JOIN groups_ g ON g.id=p.group_id JOIN boards b ON b.id=g.board_id
            WHERE d.successor_id=? AND d.deleted_at IS NULL AND p.deleted_at IS NULL AND p.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL AND b.deleted_at IS NULL AND b.archived_at IS NULL
            ORDER BY d.id""",(task_id,)).fetchall()]
        blocked=[item for item in predecessors if item["status"]!="已完成"]
        children=[dict(row) for row in conn.execute("""SELECT t.id,t.title,t.status,t.version,t.group_id,t.subtask_order
            FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE t.parent_id=? AND t.deleted_at IS NULL AND t.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL ORDER BY t.subtask_order,t.id""",(task_id,)).fetchall()]
        return {"depth":self._task_depth(conn,task_id),"children":children,
                "progress":{"mode":"recursive","completed":completed,"total":total,"percent":round(completed*100/total) if total else None,
                    "direct":{"completed":direct_completed,"total":direct_total,"percent":round(direct_completed*100/direct_total) if direct_total else None}},
                "predecessors":predecessors,"blocked":bool(blocked),"blocked_by":blocked}

    def _enrich_task(self, conn, task):
        task["relations"]=self._relation_summary(conn,task["id"])
        return task

    # Read models --------------------------------------------------------
    def list_boards(self, user, workspace_id, state="active"):
        if state not in {"active", "archived"}:
            raise ApiError(422, "VALIDATION_ERROR", "state is invalid")
        conn = self._db()
        try:
            self._workspace_role(conn, user["id"], workspace_id)
            lifecycle = "b.deleted_at IS NULL AND b.archived_at IS NULL" if state == "active" else "b.deleted_at IS NULL AND b.archived_at IS NOT NULL"
            return [dict(row) for row in conn.execute(
                f"""SELECT b.*,wm.role current_role FROM boards b
                    JOIN workspace_memberships wm ON wm.workspace_id=b.workspace_id AND wm.user_id=?
                    WHERE b.workspace_id=? AND {lifecycle} AND
                    (b.access_type='open' OR wm.role='admin' OR EXISTS(
                       SELECT 1 FROM board_memberships bm WHERE bm.board_id=b.id AND bm.user_id=?))
                    ORDER BY b.id""",
                (user["id"], workspace_id, user["id"]),
            )]
        finally:
            conn.close()

    def bootstrap(self, user, board_id=None):
        conn = self._db()
        try:
            memberships = conn.execute(
                "SELECT workspace_id,role FROM workspace_memberships WHERE user_id=? ORDER BY workspace_id",
                (user["id"],),
            ).fetchall()
            if not memberships:
                raise ApiError(403, "RESOURCE_FORBIDDEN", "资源不存在或不可访问")
            workspace_id = memberships[0]["workspace_id"]
            boards = self.list_boards(user, workspace_id, "active")
            if board_id is None:
                board_id = boards[0]["id"] if boards else None
            members = [self._public_user(row) for row in conn.execute(
                """SELECT u.* FROM users u JOIN workspace_memberships wm ON wm.user_id=u.id
                   WHERE wm.workspace_id=? AND u.is_active=1 ORDER BY u.name""", (workspace_id,)
            )]
            if board_id is None:
                return {"workspace_id": workspace_id, "boards": boards, "board": None, "groups": [], "members": members, "current_user": self._public_user(user), "capabilities": {"write": memberships[0]["role"] != "viewer","role":memberships[0]["role"],"admin":memberships[0]["role"]=="admin"}}
            board = self._board_access(conn, user["id"], board_id, require_active=True)
            groups = []
            for group in conn.execute(
                """SELECT * FROM groups_ WHERE board_id=? AND deleted_at IS NULL AND archived_at IS NULL
                   ORDER BY sort_order,id""", (board_id,)
            ):
                tasks = [dict(task) for task in conn.execute(
                    """SELECT t.*,u.name owner,u.avatar,u.avatar_class FROM tasks t LEFT JOIN users u ON u.id=t.owner_id
                       WHERE t.group_id=? AND t.deleted_at IS NULL AND t.archived_at IS NULL ORDER BY t.sort_order,t.id""",
                    (group["id"],),
                )]
                for task in tasks:
                    task["board_id"] = board_id
                    task["field_values"] = self._task_values(conn, task["id"])
                    task["field_diagnostics"] = self._advanced_values(conn,user["id"],task,task["field_values"])
                    self._enrich_task(conn,task)
                groups.append({**dict(group), "tasks": tasks})
            payload = dict(board)
            payload["current_role"] = payload.pop("role")
            payload.pop("listed", None)
            view_state=self.list_views(user,board_id)
            return {"workspace_id": workspace_id, "boards": boards, "board": payload, "groups": groups,
                    "fields": self._field_payloads(conn, board_id,user_id=user["id"]),
                    "deleted_fields": [field for field in self._field_payloads(conn,board_id,include_deleted=True,user_id=user["id"]) if field["deleted_at"]],
                    "saved_views":view_state["views"],"effective_default_view_id":view_state["effective_default_id"], "members": members,
                    "current_user": self._public_user(user), "capabilities": {"write": board["role"] != "viewer","role":board["role"],"admin":board["role"]=="admin"}}
        finally:
            conn.close()

    def task_detail(self, user, task_id):
        conn = self._db()
        try:
            task = self._task_context(conn, user["id"], task_id, require_active=True)
            collaboration_role=self._workspace_role(conn,user["id"],task["workspace_id"])
            item = dict(task)
            item["field_values"] = self._task_values(conn, task_id)
            item["field_diagnostics"] = self._advanced_values(conn,user["id"],item,item["field_values"])
            self._enrich_task(conn,item)
            item["fields"] = self._field_payloads(conn, task["board_id"],user_id=user["id"])
            item["comments"] = []
            for row in conn.execute("""SELECT c.*,u.name user_name FROM comments c JOIN users u ON u.id=c.user_id
                   WHERE c.task_id=? ORDER BY c.id""", (task_id,)):
                comment=dict(row); comment["body"]=None if comment["deleted_at"] else comment["body"]
                comment["mentions"]=[dict(x) for x in conn.execute("SELECT target_key,user_id,mention_type FROM comment_mentions WHERE comment_id=? ORDER BY id",(comment["id"],))]
                comment["can_edit"]=not comment["deleted_at"] and comment["user_id"]==user["id"] and collaboration_role!="viewer"
                comment["can_delete"]=not comment["deleted_at"] and collaboration_role!="viewer" and (comment["user_id"]==user["id"] or collaboration_role=="admin")
                item["comments"].append(comment)
            item["attachments"]=[]
            for row in conn.execute("SELECT id,uploader_id,original_name,content_type,size_bytes,sha256,preview_kind,version,created_at FROM attachments WHERE task_id=? AND deleted_at IS NULL ORDER BY id",(task_id,)):
                attachment=dict(row);attachment["download_url"]=f"/api/attachments/{row['id']}/content";attachment["preview_url"]=f"/api/attachments/{row['id']}/content?preview=1" if row["preview_kind"]!="none" else None;attachment["can_delete"]=collaboration_role!="viewer" and (row["uploader_id"]==user["id"] or collaboration_role=="admin");item["attachments"].append(attachment)
            subscription=conn.execute("SELECT state,source,version FROM task_subscriptions WHERE task_id=? AND user_id=?",(task_id,user["id"])).fetchone();item["subscription"]={"subscribed":bool(subscription and subscription["state"]=="following"),"state":subscription["state"] if subscription else "none","source":subscription["source"] if subscription else None,"version":subscription["version"] if subscription else 0}
            item["activity"] = self._activity_payload(conn.execute(
                """SELECT a.*,u.name user_name FROM activity a LEFT JOIN users u ON u.id=a.user_id
                   WHERE a.task_id=? ORDER BY a.id DESC LIMIT 100""", (task_id,)
            ).fetchall())
            return item
        finally:
            conn.close()

    def group_detail(self, user, group_id):
        conn = self._db()
        try:
            group = self._group_context(conn, user["id"], group_id, require_active=True)
            item = dict(group)
            item["tasks"] = [dict(row) for row in conn.execute(
                """SELECT * FROM tasks WHERE group_id=? AND deleted_at IS NULL
                   ORDER BY archived_at IS NOT NULL,sort_order,id""", (group_id,)
            )]
            return item
        finally:
            conn.close()

    def archived(self, user, board_id):
        conn = self._db()
        try:
            self._board_access(conn, user["id"], board_id, require_active=True)
            groups = [dict(row) for row in conn.execute("SELECT * FROM groups_ WHERE board_id=? AND deleted_at IS NULL AND archived_at IS NOT NULL ORDER BY sort_order,id", (board_id,))]
            tasks = [dict(row) for row in conn.execute(
                """SELECT t.*,g.name group_name FROM tasks t JOIN groups_ g ON g.id=t.group_id
                   WHERE g.board_id=? AND t.deleted_at IS NULL AND t.archived_at IS NOT NULL ORDER BY t.id""", (board_id,)
            )]
            return {"groups": groups, "tasks": tasks}
        finally:
            conn.close()

    def trash(self, user, workspace_id):
        conn = self._db()
        try:
            role = self._workspace_role(conn, user["id"], workspace_id)
            if role == "viewer":
                raise ApiError(403, "READ_ONLY", "只读成员不能管理回收站")
            visible = "(b.access_type='open' OR ?='admin' OR EXISTS(SELECT 1 FROM board_memberships bm WHERE bm.board_id=b.id AND bm.user_id=?))"
            boards = [dict(row) for row in conn.execute(f"SELECT b.* FROM boards b WHERE b.workspace_id=? AND b.deleted_at IS NOT NULL AND {visible} ORDER BY b.deleted_at DESC", (workspace_id, role, user["id"]))]
            groups = [dict(row) for row in conn.execute(f"""SELECT g.*,b.name board_name,b.deleted_at parent_deleted_at FROM groups_ g JOIN boards b ON b.id=g.board_id
                WHERE b.workspace_id=? AND g.deleted_at IS NOT NULL AND {visible} ORDER BY g.deleted_at DESC""", (workspace_id, role, user["id"]))]
            tasks = [dict(row) for row in conn.execute(f"""SELECT t.*,g.name group_name,g.deleted_at group_deleted_at,b.name board_name,b.deleted_at board_deleted_at
                FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
                WHERE b.workspace_id=? AND t.deleted_at IS NOT NULL AND {visible} ORDER BY t.deleted_at DESC""", (workspace_id, role, user["id"]))]
            for item in groups:
                item["restorable"] = not bool(item["parent_deleted_at"])
                item["blocked_by"] = "board" if item["parent_deleted_at"] else None
            for item in tasks:
                blocked = "board" if item["board_deleted_at"] else ("group" if item["group_deleted_at"] else None)
                item["restorable"], item["blocked_by"] = blocked is None, blocked
            retention=conn.execute("SELECT trash_retention_days FROM workspaces WHERE id=?",(workspace_id,)).fetchone()[0]
            now=datetime.now(timezone.utc)
            for collection in (boards,groups,tasks):
                for item in collection:
                    deleted=datetime.fromisoformat(item["deleted_at"]);expires=deleted+timedelta(days=retention);item["purge_after"]=expires.isoformat(timespec="seconds");item["purge_eligible"]=expires<=now
            return {"boards": boards, "groups": groups, "tasks": tasks,"retention_days":retention}
        finally:
            conn.close()

    @staticmethod
    def _marks(values):return ','.join('?' for _ in values)

    def _trash_plan(self,conn,workspace_id,as_of):
        workspace=conn.execute("SELECT trash_retention_days FROM workspaces WHERE id=?",(workspace_id,)).fetchone()
        if not workspace:raise ApiError(404,"WORKSPACE_NOT_FOUND","工作区不存在")
        cutoff=(as_of-timedelta(days=workspace["trash_retention_days"])).isoformat(timespec="seconds")
        boards=[row[0] for row in conn.execute("SELECT id FROM boards WHERE workspace_id=? AND deleted_at IS NOT NULL AND deleted_at<=? ORDER BY id",(workspace_id,cutoff))]
        groups=[row[0] for row in conn.execute("SELECT g.id FROM groups_ g JOIN boards b ON b.id=g.board_id WHERE b.workspace_id=? AND g.deleted_at IS NOT NULL AND g.deleted_at<=?"+(f" AND g.board_id NOT IN ({self._marks(boards)})" if boards else "")+" ORDER BY g.id",(workspace_id,cutoff,*boards))]
        all_groups=set(groups)
        if boards:all_groups.update(row[0] for row in conn.execute(f"SELECT id FROM groups_ WHERE board_id IN ({self._marks(boards)})",boards))
        tasks=set()
        if all_groups:tasks.update(row[0] for row in conn.execute(f"SELECT id FROM tasks WHERE group_id IN ({self._marks(all_groups)})",tuple(all_groups)))
        args=[workspace_id,cutoff]
        exclusions=""
        if all_groups:exclusions=f" AND t.group_id NOT IN ({self._marks(all_groups)})";args.extend(all_groups)
        roots=[row[0] for row in conn.execute("SELECT t.id FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id WHERE b.workspace_id=? AND t.deleted_at IS NOT NULL AND t.deleted_at<=?"+exclusions+" ORDER BY t.id",args)]
        tasks.update(roots)
        frontier=list(roots)
        while frontier:
            children=[row[0] for row in conn.execute(f"SELECT id FROM tasks WHERE parent_id IN ({self._marks(frontier)})",frontier) if row[0] not in tasks];tasks.update(children);frontier=children
        task_ids=sorted(tasks);group_ids=sorted(all_groups);attachment_rows=[]
        if task_ids:attachment_rows=[dict(row) for row in conn.execute(f"SELECT id,storage_name,size_bytes,sha256 FROM attachments WHERE task_id IN ({self._marks(task_ids)}) ORDER BY id",task_ids)]
        payload={"workspace_id":workspace_id,"as_of":as_of.isoformat(timespec="seconds"),"cutoff":cutoff,"retention_days":workspace["trash_retention_days"],"boards":sorted(boards),"groups":group_ids,"tasks":task_ids,"attachments":[row["id"] for row in attachment_rows]}
        plan_hash=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest();count=len(boards)+len(group_ids)+len(task_ids)
        return {**payload,"plan_hash":plan_hash,"confirmation":f"PURGE {count} ITEMS","counts":{"boards":len(boards),"groups":len(group_ids),"tasks":len(task_ids),"attachments":len(attachment_rows)},"attachment_rows":attachment_rows}

    def trash_purge_preview(self,user,workspace_id):
        conn=self._db()
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
            plan=self._trash_plan(conn,workspace_id,datetime.now(timezone.utc));plan.pop("attachment_rows",None);return plan
        finally:conn.close()

    def trash_purge(self,user,workspace_id,data):
        reject_unknown(data,{"as_of","plan_hash","confirmation"})
        if not all(isinstance(data.get(key),str) and data[key] for key in ("as_of","plan_hash","confirmation")):raise ApiError(422,"VALIDATION_ERROR","清理确认参数不完整")
        try:as_of=datetime.fromisoformat(data["as_of"])
        except ValueError:raise ApiError(422,"VALIDATION_ERROR","as_of 无效")
        if as_of.tzinfo is None:raise ApiError(422,"VALIDATION_ERROR","as_of 必须包含时区")
        now=datetime.now(timezone.utc)
        if as_of>now+timedelta(seconds=5) or now-as_of>timedelta(minutes=15):raise ApiError(409,"PURGE_PLAN_EXPIRED","清理预览已过期")
        conn=self._db();quarantine=None;moved=[]
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
            plan=self._trash_plan(conn,workspace_id,as_of)
            if not secrets.compare_digest(plan["plan_hash"],data["plan_hash"]):raise ApiError(409,"PURGE_PLAN_CHANGED","回收站内容已变化，请重新预览")
            if not secrets.compare_digest(plan["confirmation"],data["confirmation"]):raise ApiError(422,"PURGE_CONFIRMATION_INVALID","永久清理确认短语不匹配")
            backup_root=Path(os.getenv("FLOWBOARD_BACKUP_DIR",str(Path(self.db_path).resolve().parent/"backups"))).resolve();safety=create_backup(self.db_path,self.attachment_root,backup_root,label="pre-purge")
            if plan["attachment_rows"]:
                quarantine=self.attachment_root.parent/f".{self.attachment_root.name}.purge-{uuid.uuid4().hex}";quarantine.mkdir(parents=True)
                for row in plan["attachment_rows"]:
                    source=(self.attachment_root/row["storage_name"]).resolve()
                    if source.parent!=self.attachment_root or not source.is_file():raise ApiError(409,"ATTACHMENT_STORAGE_INVALID","附件存储不完整，已拒绝清理")
                    target=quarantine/row["storage_name"];os.replace(source,target);moved.append((source,target))
            with transaction(conn):
                refreshed=self._trash_plan(conn,workspace_id,as_of)
                if refreshed["plan_hash"]!=plan["plan_hash"]:raise ApiError(409,"PURGE_PLAN_CHANGED","回收站内容已变化，请重新预览")
                task_ids=plan["tasks"];board_ids=plan["boards"];group_ids=plan["groups"]
                def delete_where(table,column,ids):
                    if ids:conn.execute(f"DELETE FROM {table} WHERE {column} IN ({self._marks(ids)})",ids)
                comment_ids=[row[0] for row in conn.execute(f"SELECT id FROM comments WHERE task_id IN ({self._marks(task_ids)})",task_ids)] if task_ids else []
                attachment_ids=plan["attachments"]
                for table,column,ids in (("collaboration_events","attachment_id",attachment_ids),("collaboration_events","comment_id",comment_ids),("collaboration_events","task_id",task_ids),("notifications","comment_id",comment_ids),("notifications","task_id",task_ids),("realtime_events","task_id",task_ids),("task_dependencies","predecessor_id",task_ids),("task_dependencies","successor_id",task_ids),("task_relation_values","source_task_id",task_ids),("task_relation_values","target_task_id",task_ids),("comment_mentions","comment_id",comment_ids),("comment_versions","comment_id",comment_ids),("comments","id",comment_ids),("attachments","id",attachment_ids),("task_subscriptions","task_id",task_ids),("task_field_tag_values","task_id",task_ids),("task_field_values","task_id",task_ids),("legacy_task_field_values","task_id",task_ids),("activity","task_id",task_ids)):
                    delete_where(table,column,ids)
                if task_ids:
                    depth={task_id:self._task_depth(conn,task_id) for task_id in task_ids}
                    for task_id in sorted(task_ids,key=lambda value:depth[value],reverse=True):conn.execute("DELETE FROM tasks WHERE id=?",(task_id,))
                for table,column in (("collaboration_events","board_id"),("notifications","board_id"),("realtime_events","board_id"),("dashboard_sources","board_id"),("saved_views","board_id"),("import_batches","board_id"),("board_memberships","board_id"),("activity","board_id")):
                    delete_where(table,column,board_ids)
                if board_ids:
                    conn.execute(f"UPDATE board_templates SET source_board_id=NULL WHERE source_board_id IN ({self._marks(board_ids)})",board_ids)
                    field_ids=[row[0] for row in conn.execute(f"SELECT id FROM field_definitions WHERE board_id IN ({self._marks(board_ids)})",board_ids)]
                    delete_where("field_options","field_id",field_ids);delete_where("field_definitions","id",field_ids)
                delete_where("groups_","id",group_ids);delete_where("boards","id",board_ids)
                conn.execute("INSERT INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",(f"purge:{plan['plan_hash']}",workspace_id,user["id"],"trash.purged","success",None,plan["plan_hash"],json.dumps({"counts":plan["counts"],"safety_backup":Path(safety).name}),utc_now()))
            if quarantine:shutil.rmtree(quarantine)
            return {"purged":True,"counts":plan["counts"],"safety_backup":Path(safety).name,"audit_retained":True}
        except Exception:
            for source,target in reversed(moved):
                if target.exists():source.parent.mkdir(parents=True,exist_ok=True);os.replace(target,source)
            if quarantine and quarantine.exists():shutil.rmtree(quarantine,ignore_errors=True)
            raise
        finally:conn.close()

    def activity(self, user, board_id, task_id=None):
        conn = self._db()
        try:
            self._board_access(conn, user["id"], board_id, require_active=True)
            clause, args = ("a.task_id=?", (task_id,)) if task_id else ("a.board_id=?", (board_id,))
            rows = conn.execute(f"""SELECT a.*,u.name user_name FROM activity a LEFT JOIN users u ON u.id=a.user_id
                WHERE {clause} ORDER BY a.id DESC LIMIT 200""", args).fetchall()
            return self._activity_payload(rows)
        finally:
            conn.close()

    # Unified queries and saved views ----------------------------------
    @staticmethod
    def _normalize_query(conn,board_id,payload):
        from .query import QueryValidationError, normalize_query
        try: return normalize_query(conn,board_id,payload)
        except QueryValidationError as error: raise ApiError(422,"QUERY_INVALID",error.message,error.details)

    def query_tasks(self,user,board_id,data):
        from .query import apply_python_query
        conn=self._db()
        try:
            self._board_access(conn,user["id"],board_id,require_active=True)
            normalized,where,where_args,order,order_args,limit,offset=self._normalize_query(conn,board_id,data)
            referenced=[]
            def collect(node):
                if isinstance(node,dict):
                    field=node.get("field")
                    if isinstance(field,dict) and field.get("kind")=="dynamic": referenced.append(field.get("id"))
                    for child in node.get("children",[]): collect(child)
            collect(normalized["filter"])
            referenced.extend(item.get("field",{}).get("id") for item in normalized["sort"] if item.get("field",{}).get("kind")=="dynamic")
            active_fields={row["id"]:dict(row) for row in conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND deleted_at IS NULL AND is_active=1",(board_id,))}
            checked=set()
            def check_source(field_id):
                if field_id in checked:return
                checked.add(field_id);field=active_fields.get(field_id)
                if not field:return
                try:config=json.loads(field["config_json"] or "{}")
                except (TypeError,json.JSONDecodeError):return
                if field["field_type"]=="relation":
                    try:self._board_access(conn,user["id"],config.get("target_board_id"),require_active=True)
                    except ApiError: raise ApiError(403,"FIELD_SOURCE_FORBIDDEN","字段来源不可访问")
                elif field["field_type"]=="mirror":check_source(config.get("relation_field_id"))
                elif field["field_type"]=="formula":
                    try:
                        for dependency in formula_references(config.get("expression","")):check_source(dependency)
                    except FormulaError:return
            for field_id in referenced:check_source(field_id)
            derived_ids={row["id"] for row in conn.execute("SELECT id FROM field_definitions WHERE board_id=? AND field_type IN ('mirror','formula')",(board_id,))}
            if derived_ids.intersection(referenced):
                fields=active_fields
                option_orders={row["id"]:row["sort_order"] for row in conn.execute("SELECT id,sort_order FROM field_options WHERE field_id IN (SELECT id FROM field_definitions WHERE board_id=? AND deleted_at IS NULL)",(board_id,))}
                user_names={row["id"]:row["name"] for row in conn.execute("SELECT id,name FROM users")}
                candidate_count=conn.execute("""SELECT COUNT(*) FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?
                    AND g.deleted_at IS NULL AND g.archived_at IS NULL AND t.deleted_at IS NULL AND t.archived_at IS NULL""",(board_id,)).fetchone()[0]
                if candidate_count>2000 or candidate_count*max(1,len(derived_ids.intersection(referenced)))>10000: raise ApiError(422,"QUERY_LIMIT","派生字段查询超出安全上限")
                rows=conn.execute("""SELECT t.*,g.name group_name,g.sort_order group_sort_order FROM tasks t JOIN groups_ g ON g.id=t.group_id
                    WHERE g.board_id=? AND g.deleted_at IS NULL AND g.archived_at IS NULL AND t.deleted_at IS NULL AND t.archived_at IS NULL
                    ORDER BY g.sort_order,t.sort_order,t.id LIMIT 2000""",(board_id,)).fetchall()
                tasks=[]
                for row in rows:
                    task=dict(row);task["board_id"]=board_id;task["field_values"]=self._task_values(conn,task["id"]);task["field_diagnostics"]=self._advanced_values(conn,user["id"],task,task["field_values"]);self._enrich_task(conn,task);tasks.append(task)
                tasks=apply_python_query(tasks,normalized["filter"],normalized["sort"],fields,option_orders=option_orders,user_names=user_names)
                total=len(tasks);return {"query":normalized,"tasks":tasks[offset:offset+limit],"total":total,"limit":limit,"offset":offset}
            base="""FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
                    WHERE b.id=? AND b.deleted_at IS NULL AND b.archived_at IS NULL
                    AND g.deleted_at IS NULL AND g.archived_at IS NULL
                    AND t.deleted_at IS NULL AND t.archived_at IS NULL AND """+where
            total=conn.execute("SELECT COUNT(*) "+base,(board_id,*where_args)).fetchone()[0]
            rows=conn.execute("SELECT t.*,g.name group_name,g.sort_order group_sort_order "+base+f" ORDER BY {order} LIMIT ? OFFSET ?",(board_id,*where_args,*order_args,limit,offset)).fetchall()
            tasks=[]
            for row in rows:
                task=dict(row);task["board_id"]=board_id;task["field_values"]=self._task_values(conn,task["id"]);task["field_diagnostics"]=self._advanced_values(conn,user["id"],task,task["field_values"]);self._enrich_task(conn,task);tasks.append(task)
            return {"query":normalized,"tasks":tasks,"total":total,"limit":limit,"offset":offset}
        finally: conn.close()

    @staticmethod
    def _view_payload(row, *, current_user=None, role=None):
        item=dict(row)
        diagnostics=[]
        for source,target in (("filter_json","filter"),("sort_json","sort"),("visible_fields_json","visible_fields"),("column_order_json","column_order"),("presentation_json","presentation")):
            raw=item.pop(source)
            try: item[target]=json.loads(raw)
            except (TypeError,json.JSONDecodeError):
                item[target]={"op":"and","children":[]} if target=="filter" else ({"version":1} if target=="presentation" else [])
                diagnostics.append({"code":"VIEW_JSON_INVALID","message":f"{source} 不是有效 JSON"})
        owner=current_user and item["owner_id"]==current_user
        item["can_update"]=bool(owner if item["scope"]=="personal" else role!="viewer")
        item["can_delete"]=item["can_update"]
        item["can_set_default"]=item["can_update"]
        item["blocked"]=bool(diagnostics);item["diagnostics"]=diagnostics
        return item

    def _view_context(self,conn,user,view_id,*,write=False):
        row=conn.execute("SELECT v.*,b.workspace_id FROM saved_views v JOIN boards b ON b.id=v.board_id WHERE v.id=? AND v.deleted_at IS NULL",(view_id,)).fetchone()
        if not row: raise ApiError(403,"VIEW_FORBIDDEN","视图不存在或不可访问")
        board=self._board_access(conn,user["id"],row["board_id"],require_active=True)
        if row["scope"]=="personal" and row["owner_id"]!=user["id"]: raise ApiError(403,"VIEW_FORBIDDEN","视图不存在或不可访问")
        if write and ((row["scope"]=="personal" and row["owner_id"]!=user["id"]) or (row["scope"]=="shared" and board["role"]=="viewer")): raise ApiError(403,"READ_ONLY","没有权限修改该视图")
        return row,board

    def _validate_view_config(self,conn,board_id,data):
        query={"version":1,"filter":data.get("filter",{"op":"and","children":[]}),"sort":data.get("sort",[])}
        normalized,*_=self._normalize_query(conn,board_id,query)
        visible=data.get("visible_fields",[]);columns=data.get("column_order",["title",*visible])
        if not isinstance(visible,list) or any(isinstance(v,bool) or not isinstance(v,int) for v in visible) or len(visible)!=len(set(visible)): raise ApiError(422,"VIEW_INVALID","visible_fields 无效")
        if not isinstance(columns,list) or any(not (v=="title" or isinstance(v,int) and not isinstance(v,bool)) for v in columns) or len(columns)!=len(set(columns)): raise ApiError(422,"VIEW_INVALID","column_order 无效")
        field_rows=conn.execute("SELECT id,field_type FROM field_definitions WHERE board_id=? AND deleted_at IS NULL AND is_active=1",(board_id,)).fetchall();valid={row["id"] for row in field_rows};types={row["id"]:row["field_type"] for row in field_rows}
        if not set(visible)<=valid or not {v for v in columns if v!="title"}<=valid: raise ApiError(422,"VIEW_INVALID","视图引用了不可用字段")
        if set(columns)!={"title",*visible} or len(columns)!=len(visible)+1: raise ApiError(422,"VIEW_INVALID","column_order 必须完整排列标题和可见字段")
        view_type=data.get("view_type","table");presentation=data.get("presentation",{"version":1})
        if not isinstance(presentation,dict) or presentation.get("version")!=1: raise ApiError(422,"VIEW_INVALID","presentation 版本无效")
        allowed={"table":{"version","widths","frozen_columns"},"kanban":{"version","group_field_id"},"calendar":{"version","date_field_id"},"timeline":{"version","source","scale","show_dependencies","baseline"},"gantt":{"version","source","scale","show_dependencies","show_critical_path","baseline"},"chart":{"version","chart_type","dimension","series","metric","date_bucket","top_n","null_policy"}}[view_type]
        if set(presentation)-allowed: raise ApiError(422,"VIEW_INVALID","presentation 含未知字段")
        if view_type=="table":
            widths=presentation.get("widths",{});frozen=presentation.get("frozen_columns",[]);keys={str(v) for v in columns}
            if not isinstance(widths,dict) or any(str(k) not in keys or isinstance(v,bool) or not isinstance(v,int) or not 80<=v<=600 for k,v in widths.items()): raise ApiError(422,"VIEW_INVALID","列宽无效")
            if not isinstance(frozen,list) or frozen!=columns[:len(frozen)]: raise ApiError(422,"VIEW_INVALID","冻结列必须是列顺序前缀")
            presentation={"version":1,"widths":{str(k):v for k,v in widths.items()},"frozen_columns":frozen}
        elif view_type=="kanban":
            field_id=presentation.get("group_field_id")
            if field_id not in valid or types.get(field_id) not in {"status","person"}: raise ApiError(422,"VIEW_INVALID","Kanban 分组字段无效")
            presentation={"version":1,"group_field_id":field_id}
        elif view_type=="calendar":
            field_id=presentation.get("date_field_id")
            if field_id not in valid or types.get(field_id) not in {"date","timeline"}: raise ApiError(422,"VIEW_INVALID","日历日期字段无效")
            presentation={"version":1,"date_field_id":field_id}
        elif view_type=="chart":
            catalog={("core","status"):"status",("core","priority"):"priority",("core","owner_id"):"person",("core","due"):"date",("core","start_date"):"date",("core","board"):"board"};catalog.update({("dynamic",field_id):kind for field_id,kind in types.items()})
            try:validate_aggregation_spec(presentation,[catalog])
            except AggregationError as error:raise ApiError(422,error.code,error.message,error.details)
        else:
            source=presentation.get("source",{"kind":"fixed"});scale=presentation.get("scale","week");show_dependencies=presentation.get("show_dependencies",view_type=="gantt");baseline=presentation.get("baseline","disabled")
            if source!={"kind":"fixed"}:
                if not isinstance(source,dict) or set(source)!={"kind","id"} or source.get("kind")!="dynamic" or source.get("id") not in valid or types.get(source.get("id")) not in {"date","timeline"}:raise ApiError(422,"VIEW_INVALID","排期日期来源无效")
            if scale not in SCALES:raise ApiError(422,"VIEW_INVALID","排期刻度无效")
            if not isinstance(show_dependencies,bool) or baseline!="disabled":raise ApiError(422,"VIEW_INVALID","排期展示配置无效")
            presentation={"version":1,"source":source,"scale":scale,"show_dependencies":show_dependencies,"baseline":"disabled"}
            if view_type=="gantt":
                show_critical=presentation.get("show_critical_path",data.get("presentation",{}).get("show_critical_path",True))
                if not isinstance(show_critical,bool):raise ApiError(422,"VIEW_INVALID","关键路径配置无效")
                presentation["show_critical_path"]=show_critical
        return normalized["filter"],normalized["sort"],visible,columns,presentation

    def list_views(self,user,board_id):
        conn=self._db()
        try:
            board=self._board_access(conn,user["id"],board_id,require_active=True)
            rows=conn.execute("""SELECT * FROM saved_views WHERE board_id=? AND deleted_at IS NULL
                AND (scope='shared' OR owner_id=?) ORDER BY scope,name,id""",(board_id,user["id"])).fetchall()
            views=[self._view_payload(row,current_user=user["id"],role=board["role"]) for row in rows]
            for view in views:
                if view["blocked"]: continue
                try:
                    self._validate_view_config(conn,board_id,view);view["blocked"]=False;view["diagnostics"]=[]
                except ApiError as error:
                    view["blocked"]=True;view["diagnostics"]=[{"code":error.code,"message":error.message,"details":error.details}]
            personal=next((v for v in views if v["scope"]=="personal" and v["is_default"]),None);shared=next((v for v in views if v["scope"]=="shared" and v["is_default"]),None)
            return {"views":views,"effective_default_id":(personal or shared or {}).get("id"),"synthetic_default":not(personal or shared)}
        finally: conn.close()

    def create_view(self,user,board_id,data):
        reject_unknown(data,{"name","scope","view_type","filter","sort","visible_fields","column_order","presentation","is_default"})
        name=require_text(data,"name",max_length=120);scope=validate_choice(data.get("scope","personal"),"scope",{"personal","shared"});view_type=validate_choice(data.get("view_type","table"),"view_type",{"table","kanban","calendar","timeline","gantt","chart"});is_default=data.get("is_default",False)
        if not isinstance(is_default,bool): raise ApiError(422,"VIEW_INVALID","is_default 必须是布尔值")
        conn=self._db()
        try:
            with transaction(conn):
                board=self._board_access(conn,user["id"],board_id,require_active=True)
                if scope=="shared" and board["role"]=="viewer": raise ApiError(403,"READ_ONLY","只读成员不能创建共享视图")
                filter_ast,sorts,visible,columns,presentation=self._validate_view_config(conn,board_id,{**data,"view_type":view_type})
                if is_default:
                    args=(board_id,user["id"]) if scope=="personal" else (board_id,)
                    clause="board_id=? AND owner_id=? AND scope='personal'" if scope=="personal" else "board_id=? AND scope='shared'"
                    conn.execute(f"UPDATE saved_views SET is_default=0,version=version+1,updated_at=? WHERE {clause} AND is_default=1 AND deleted_at IS NULL",(utc_now(),*args))
                stamp=utc_now();cursor=conn.execute("""INSERT INTO saved_views(board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,presentation_json,is_default,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",(board_id,user["id"],scope,view_type,name,json.dumps(filter_ast,ensure_ascii=False),json.dumps(sorts,ensure_ascii=False),json.dumps(visible),json.dumps(columns),json.dumps(presentation),int(is_default),stamp,stamp))
            return {"id":cursor.lastrowid,"version":1}
        finally: conn.close()

    def update_view(self,user,view_id,data):
        reject_unknown(data,{"version","name","filter","sort","visible_fields","column_order","presentation","is_default"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                row,board=self._view_context(conn,user,view_id,write=True);current=self._view_payload(row)
                merged={"view_type":row["view_type"],"filter":data.get("filter",current["filter"]),"sort":data.get("sort",current["sort"]),"visible_fields":data.get("visible_fields",current["visible_fields"]),"column_order":data.get("column_order",current["column_order"]),"presentation":data.get("presentation",current["presentation"])}
                filter_ast,sorts,visible,columns,presentation=self._validate_view_config(conn,row["board_id"],merged);name=require_text({"name":data.get("name",row["name"])},"name",max_length=120);is_default=data.get("is_default",bool(row["is_default"]))
                if not isinstance(is_default,bool): raise ApiError(422,"VIEW_INVALID","is_default 必须是布尔值")
                if is_default and not row["is_default"]:
                    if row["scope"]=="personal": conn.execute("UPDATE saved_views SET is_default=0,version=version+1,updated_at=? WHERE board_id=? AND owner_id=? AND scope='personal' AND is_default=1 AND deleted_at IS NULL",(utc_now(),row["board_id"],row["owner_id"]))
                    else: conn.execute("UPDATE saved_views SET is_default=0,version=version+1,updated_at=? WHERE board_id=? AND scope='shared' AND is_default=1 AND deleted_at IS NULL",(utc_now(),row["board_id"]))
                cursor=conn.execute("""UPDATE saved_views SET name=?,filter_json=?,sort_json=?,visible_fields_json=?,column_order_json=?,presentation_json=?,is_default=?,updated_at=?,version=version+1 WHERE id=? AND version=?""",(name,json.dumps(filter_ast,ensure_ascii=False),json.dumps(sorts,ensure_ascii=False),json.dumps(visible),json.dumps(columns),json.dumps(presentation),int(is_default),utc_now(),view_id,version));self._conflict(cursor,"视图版本冲突")
            return {"id":view_id,"version":version+1}
        finally: conn.close()

    def copy_view(self,user,view_id,data):
        reject_unknown(data,{"name","scope"});conn=self._db()
        try:
            with transaction(conn):
                row,board=self._view_context(conn,user,view_id)
                scope=validate_choice(data.get("scope","personal"),"scope",{"personal","shared"})
                if scope=="shared" and board["role"]=="viewer": raise ApiError(403,"READ_ONLY","只读成员不能创建共享视图")
                name=require_text({"name":data.get("name",f"{row['name']} 副本")},"name",max_length=120);stamp=utc_now()
                cursor=conn.execute("""INSERT INTO saved_views(board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,presentation_json,is_default,created_at,updated_at)
                    SELECT board_id,?, ?,view_type,?,filter_json,sort_json,visible_fields_json,column_order_json,presentation_json,0,?,? FROM saved_views WHERE id=?""",(user["id"],scope,name,stamp,stamp,view_id))
            return {"id":cursor.lastrowid,"version":1}
        finally: conn.close()

    def delete_view(self,user,view_id,data):
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                row,_=self._view_context(conn,user,view_id,write=True);cursor=conn.execute("UPDATE saved_views SET deleted_at=?,deleted_by=?,is_default=0,updated_at=?,version=version+1 WHERE id=? AND version=?",(utc_now(),user["id"],utc_now(),view_id,version));self._conflict(cursor,"视图版本冲突")
            return {"id":view_id,"version":version+1}
        finally: conn.close()

    def clear_personal_default(self,user,board_id,data):
        reject_unknown(data,set());conn=self._db()
        try:
            with transaction(conn):
                self._board_access(conn,user["id"],board_id,require_active=True);conn.execute("UPDATE saved_views SET is_default=0,version=version+1,updated_at=? WHERE board_id=? AND owner_id=? AND scope='personal' AND is_default=1 AND deleted_at IS NULL",(utc_now(),board_id,user["id"]))
            return self.list_views(user,board_id)
        finally: conn.close()

    # Dynamic fields ----------------------------------------------------
    def _validate_field_config(self,conn,user_id,board_id,kind,config,field_id=None):
        if not isinstance(config,dict): raise ApiError(422,"VALIDATION_ERROR","字段配置无效")
        if kind=="rating":
            if set(config)-{"max"}: raise ApiError(422,"UNKNOWN_FIELD","评分配置包含未知字段")
            maximum=config.get("max",5)
            if isinstance(maximum,bool) or not isinstance(maximum,int) or not 1<=maximum<=10: raise ApiError(422,"VALIDATION_ERROR","评分上限必须是 1-10")
            return {"max":maximum}
        if kind=="relation":
            if set(config)!={"target_board_id","bidirectional"} or not isinstance(config["bidirectional"],bool): raise ApiError(422,"VALIDATION_ERROR","关系配置无效")
            target=require_int(config["target_board_id"],"target_board_id",minimum=1)
            try:self._board_access(conn,user_id,target,require_active=True)
            except ApiError: raise ApiError(403,"RELATION_TARGET_FORBIDDEN","目标看板不可访问")
            return {"target_board_id":target,"bidirectional":config["bidirectional"]}
        if kind=="mirror":
            if set(config)!={"relation_field_id","source_field_id"}: raise ApiError(422,"VALIDATION_ERROR","镜像配置无效")
            relation_id=require_int(config["relation_field_id"],"relation_field_id",minimum=1);source_id=require_int(config["source_field_id"],"source_field_id",minimum=1)
            relation=conn.execute("SELECT * FROM field_definitions WHERE id=? AND board_id=? AND field_type='relation' AND deleted_at IS NULL AND is_active=1",(relation_id,board_id)).fetchone()
            if not relation: raise ApiError(422,"MIRROR_RELATION_INVALID","镜像关系字段无效")
            target=json.loads(relation["config_json"])["target_board_id"]
            try:self._board_access(conn,user_id,target,require_active=True)
            except ApiError: raise ApiError(403,"MIRROR_SOURCE_FORBIDDEN","字段来源不可访问")
            source=conn.execute("SELECT 1 FROM field_definitions WHERE id=? AND board_id=? AND deleted_at IS NULL AND is_active=1",(source_id,target)).fetchone()
            if not source: raise ApiError(422,"MIRROR_SOURCE_INVALID","镜像来源字段无效")
            return {"relation_field_id":relation_id,"source_field_id":source_id}
        if kind=="formula":
            if set(config)!={"expression"}: raise ApiError(422,"VALIDATION_ERROR","公式配置无效")
            expression=config["expression"]
            try: refs=formula_references(expression)
            except FormulaError as error: raise ApiError(422,str(error),"公式无效")
            rows=conn.execute(f"SELECT id,field_type,config_json FROM field_definitions WHERE board_id=? AND deleted_at IS NULL AND id IN ({','.join('?' for _ in refs)})",(board_id,*refs)).fetchall() if refs else []
            if len(rows)!=len(refs) or any(row["field_type"]=="relation" for row in rows): raise ApiError(422,"FORMULA_REFERENCE_INVALID","公式引用字段无效")
            graph={}
            for row in conn.execute("SELECT id,config_json FROM field_definitions WHERE board_id=? AND field_type='formula' AND deleted_at IS NULL",(board_id,)):
                if row["id"]==field_id: continue
                try: graph[row["id"]]=formula_references(json.loads(row["config_json"])["expression"])
                except Exception: graph[row["id"]]=set()
            node=field_id or -1;graph[node]=refs
            def visit(current,path):
                if current in path: raise ApiError(422,"FORMULA_CYCLE","公式字段依赖存在循环")
                for child in graph.get(current,set()): visit(child,path|{current})
            visit(node,set())
            return {"expression":expression}
        if kind in {"timeline","file","email","phone"}:
            if config: raise ApiError(422,"VALIDATION_ERROR","该字段无需配置")
            return {}
        if config and kind not in {"status","tags"}: raise ApiError(422,"VALIDATION_ERROR","字段配置无效")
        return config

    def create_field(self, user, board_id, data):
        reject_unknown(data,{"board_version","name","field_type","config","options"})
        board_version=require_int(data.get("board_version"),"board_version",minimum=1)
        name=require_text(data,"name",max_length=100);kind=validate_choice(data.get("field_type"),"field_type",FIELD_TYPES)
        config=data.get("config",{});options=data.get("options",[])
        if not isinstance(config,dict) or not isinstance(options,list): raise ApiError(422,"VALIDATION_ERROR","字段配置无效")
        if kind not in {"status","tags"} and options: raise ApiError(422,"VALIDATION_ERROR","该字段类型不支持选项")
        conn=self._db()
        try:
            with transaction(conn):
                board=self._board_access(conn,user["id"],board_id,write=True,require_active=True)
                if board["version"]!=board_version: raise ApiError(409,"VERSION_CONFLICT","看板字段集合版本冲突")
                config=self._validate_field_config(conn,user["id"],board_id,kind,config)
                order=conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM field_definitions WHERE board_id=?",(board_id,)).fetchone()[0]
                stamp=utc_now();cursor=conn.execute("""INSERT INTO field_definitions(board_id,name,field_type,config_json,sort_order,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)""",(board_id,name,kind,json.dumps(config,ensure_ascii=False),order,stamp,stamp));field_id=cursor.lastrowid
                labels=set()
                for index, option in enumerate(options):
                    if not isinstance(option,dict) or set(option)-{"label","color"}: raise ApiError(422,"VALIDATION_ERROR","字段选项无效")
                    label=require_text(option,"label",max_length=100)
                    if label in labels: raise ApiError(422,"VALIDATION_ERROR","字段选项重复")
                    labels.add(label);color=validate_choice(option.get("color","purple"),"color",COLORS)
                    conn.execute("INSERT INTO field_options(field_id,label,color,sort_order) VALUES (?,?,?,?)",(field_id,label,color,index))
                conn.execute("UPDATE boards SET version=version+1 WHERE id=?",(board_id,))
                self._activity(conn,board_id,"board",board_id,user["id"],"field.created",{"field_id":field_id,"name":name,"field_type":kind})
            return {"id":field_id,"version":1,"board_version":board_version+1}
        finally: conn.close()

    def update_field(self,user,field_id,data):
        reject_unknown(data,{"version","name","config","is_active","options"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                field=conn.execute("SELECT f.*,b.workspace_id FROM field_definitions f JOIN boards b ON b.id=f.board_id WHERE f.id=?",(field_id,)).fetchone()
                if not field: raise ApiError(404,"FIELD_NOT_FOUND","字段不存在")
                self._board_access(conn,user["id"],field["board_id"],write=True,require_active=True)
                changes={}
                if "name" in data: changes["name"]=require_text(data,"name",max_length=100)
                if "config" in data:
                    config=self._validate_field_config(conn,user["id"],field["board_id"],field["field_type"],data["config"],field_id)
                    changes["config_json"]=json.dumps(config,ensure_ascii=False)
                if "is_active" in data:
                    if not isinstance(data["is_active"],bool): raise ApiError(422,"VALIDATION_ERROR","is_active 必须是布尔值")
                    changes["is_active"]=int(data["is_active"])
                if "options" in data:
                    if field["field_type"] not in {"status","tags"} or not isinstance(data["options"],list): raise ApiError(422,"VALIDATION_ERROR","字段选项无效")
                    requested=[]
                    for option in data["options"]:
                        if not isinstance(option,dict) or set(option)-{"label","color"}: raise ApiError(422,"VALIDATION_ERROR","字段选项无效")
                        requested.append(require_text(option,"label",max_length=100))
                    if len(requested)!=len(set(requested)): raise ApiError(422,"DUPLICATE_OPTION","字段选项重复")
                    existing={row["label"] for row in conn.execute("SELECT label FROM field_options WHERE field_id=?",(field_id,))}
                    if existing.intersection(requested): raise ApiError(422,"DUPLICATE_OPTION","字段选项已存在")
                    for option in data["options"]:
                        label=require_text(option,"label",max_length=100);color=validate_choice(option.get("color","purple"),"color",COLORS)
                        conn.execute("INSERT INTO field_options(field_id,label,color,sort_order) VALUES (?,?,?,?)",(field_id,label,color,conn.execute("SELECT COUNT(*) FROM field_options WHERE field_id=?",(field_id,)).fetchone()[0]))
                if not changes and "options" not in data: raise ApiError(422,"VALIDATION_ERROR","没有可更新字段")
                changes["updated_at"]=utc_now();cursor=conn.execute(f"UPDATE field_definitions SET {','.join(f'{k}=?' for k in changes)},version=version+1 WHERE id=? AND version=?",(*changes.values(),field_id,version));self._conflict(cursor,"字段版本冲突")
                conn.execute("UPDATE boards SET version=version+1 WHERE id=?",(field["board_id"],));self._activity(conn,field["board_id"],"board",field["board_id"],user["id"],"field.updated",{"field_id":field_id})
            return {"id":field_id,"version":version+1}
        finally: conn.close()

    def reorder_fields(self,user,board_id,data):
        reject_unknown(data,{"board_version","field_ids"});board_version=require_int(data.get("board_version"),"board_version",minimum=1);ids=data.get("field_ids")
        if not isinstance(ids,list) or any(isinstance(value,bool) or not isinstance(value,int) for value in ids) or len(ids)!=len(set(ids)): raise ApiError(422,"VALIDATION_ERROR","field_ids 必须是无重复整数数组")
        conn=self._db()
        try:
            with transaction(conn):
                board=self._board_access(conn,user["id"],board_id,write=True,require_active=True)
                if board["version"]!=board_version: raise ApiError(409,"VERSION_CONFLICT","看板字段集合版本冲突")
                actual=[row["id"] for row in conn.execute("SELECT id FROM field_definitions WHERE board_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(board_id,))]
                if set(ids)!=set(actual) or len(ids)!=len(actual): raise ApiError(422,"INVALID_FIELD_ORDER","排序必须包含当前看板全部可用字段")
                for order,field_id in enumerate(ids): conn.execute("UPDATE field_definitions SET sort_order=?,version=version+1,updated_at=? WHERE id=? AND board_id=?",(order,utc_now(),field_id,board_id))
                conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(board_id,board_version));self._activity(conn,board_id,"board",board_id,user["id"],"field.reordered",{"field_ids":ids})
            return {"board_id":board_id,"board_version":board_version+1,"field_ids":ids}
        finally: conn.close()

    def field_command(self,user,field_id,command,data):
        if command not in {"delete","restore"}: raise ApiError(404,"NOT_FOUND","接口不存在")
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                field=conn.execute("SELECT * FROM field_definitions WHERE id=?",(field_id,)).fetchone()
                if not field: raise ApiError(404,"FIELD_NOT_FOUND","字段不存在")
                self._board_access(conn,user["id"],field["board_id"],write=True,require_active=True)
                if field["system_key"]: raise ApiError(409,"SYSTEM_FIELD","系统字段不可删除")
                if command=="delete": changes=(utc_now(),user["id"]); sql="deleted_at=?,deleted_by=?"; action="field.deleted"
                else: changes=();sql="deleted_at=NULL,deleted_by=NULL";action="field.restored"
                cursor=conn.execute(f"UPDATE field_definitions SET {sql},version=version+1,updated_at=? WHERE id=? AND version=?",(*changes,utc_now(),field_id,version));self._conflict(cursor,"字段版本冲突")
                conn.execute("UPDATE boards SET version=version+1 WHERE id=?",(field["board_id"],));self._activity(conn,field["board_id"],"board",field["board_id"],user["id"],action,{"field_id":field_id})
            return {"id":field_id,"version":version+1}
        finally: conn.close()

    def relation_targets(self,user,field_id,query=""):
        from .query import active_task_sql
        if not isinstance(query,str) or len(query)>100: raise ApiError(422,"VALIDATION_ERROR","query 无效")
        conn=self._db()
        try:
            field=conn.execute("SELECT * FROM field_definitions WHERE id=? AND field_type='relation' AND deleted_at IS NULL AND is_active=1",(field_id,)).fetchone()
            if not field: raise ApiError(404,"FIELD_NOT_FOUND","关系字段不存在")
            self._board_access(conn,user["id"],field["board_id"],require_active=True)
            target=json.loads(field["config_json"])["target_board_id"]
            self._board_access(conn,user["id"],target,require_active=True)
            rows=conn.execute(f"""SELECT t.id,t.title,t.version,g.name group_name FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
                WHERE g.board_id=? AND {active_task_sql('t','g','b')}
                AND LOWER(t.title) LIKE ? ORDER BY t.title,t.id LIMIT 50""",(target,f"%{query.lower()}%")).fetchall()
            return {"targets":[dict(row) for row in rows]}
        finally:conn.close()

    def add_task_relation(self,user,task_id,field_id,data):
        reject_unknown(data,{"version","board_version","target_task_id","target_version"})
        version=require_version(data);board_version=require_int(data.get("board_version"),"board_version",minimum=1)
        target_id=require_int(data.get("target_task_id"),"target_task_id",minimum=1);target_version=require_int(data.get("target_version"),"target_version",minimum=1)
        conn=self._db()
        try:
            with transaction(conn):
                source=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                if source["version"]!=version or source["board_version"]!=board_version: raise ApiError(409,"VERSION_CONFLICT","任务或看板版本冲突")
                field=conn.execute("SELECT * FROM field_definitions WHERE id=? AND board_id=? AND field_type='relation' AND deleted_at IS NULL AND is_active=1",(field_id,source["board_id"])).fetchone()
                if not field: raise ApiError(422,"RELATION_FIELD_INVALID","关系字段无效")
                target=self._task_context(conn,user["id"],target_id,require_active=True)
                config=json.loads(field["config_json"])
                if target["board_id"]!=config["target_board_id"] or target["version"]!=target_version: raise ApiError(409,"VERSION_CONFLICT","目标任务版本或看板不匹配")
                if task_id==target_id: raise ApiError(422,"RELATION_SELF","任务不能关联自身")
                existing=conn.execute("SELECT * FROM task_relation_values WHERE field_id=? AND source_task_id=? AND target_task_id=?",(field_id,task_id,target_id)).fetchone()
                if existing and not existing["deleted_at"]: raise ApiError(409,"RELATION_DUPLICATE","关系已存在")
                stamp=utc_now()
                if existing:
                    conn.execute("UPDATE task_relation_values SET deleted_at=NULL,deleted_by=NULL,created_by=?,created_at=?,version=version+1 WHERE id=?",(user["id"],stamp,existing["id"]));edge_id=existing["id"];edge_version=existing["version"]+1
                else:
                    cursor=conn.execute("INSERT INTO task_relation_values(field_id,source_task_id,target_task_id,created_by,created_at) VALUES (?,?,?,?,?)",(field_id,task_id,target_id,user["id"],stamp));edge_id=cursor.lastrowid;edge_version=1
                conn.execute("UPDATE tasks SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,task_id,version))
                conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(source["board_id"],board_version))
                self._activity(conn,source["board_id"],"task",task_id,user["id"],"relation.created",{"field_id":field_id,"edge_id":edge_id,"bidirectional":config["bidirectional"]},task_id)
            return {"id":edge_id,"version":edge_version,"task_version":version+1,"board_version":board_version+1}
        finally:conn.close()

    def delete_task_relation(self,user,task_id,relation_id,data):
        reject_unknown(data,{"version","board_version","relation_version"});version=require_version(data)
        board_version=require_int(data.get("board_version"),"board_version",minimum=1);relation_version=require_int(data.get("relation_version"),"relation_version",minimum=1)
        conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                if task["version"]!=version or task["board_version"]!=board_version: raise ApiError(409,"VERSION_CONFLICT","任务或看板版本冲突")
                edge=conn.execute("""SELECT r.*,f.board_id FROM task_relation_values r JOIN field_definitions f ON f.id=r.field_id
                    WHERE r.id=? AND r.source_task_id=? AND r.deleted_at IS NULL""",(relation_id,task_id)).fetchone()
                if not edge or edge["board_id"]!=task["board_id"]: raise ApiError(404,"RELATION_NOT_FOUND","关系不存在")
                stamp=utc_now();cursor=conn.execute("UPDATE task_relation_values SET deleted_at=?,deleted_by=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL",(stamp,user["id"],relation_id,relation_version));self._conflict(cursor,"关系版本冲突")
                conn.execute("UPDATE tasks SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,task_id,version));conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(task["board_id"],board_version))
                self._activity(conn,task["board_id"],"task",task_id,user["id"],"relation.deleted",{"edge_id":relation_id,"field_id":edge["field_id"]},task_id)
            return {"id":relation_id,"version":relation_version+1,"task_version":version+1,"board_version":board_version+1,"deleted":True}
        finally:conn.close()

    # Board lifecycle ----------------------------------------------------
    def _board_snapshot(self,conn,board_id,include_tasks):
        board=conn.execute("SELECT id,name,description,color,access_type FROM boards WHERE id=?",(board_id,)).fetchone();snapshot={"version":1,"source_board_id":board_id,"board":dict(board),"fields":[],"groups":[],"views":[],"relations":[],"dependencies":[]}
        for field in conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(board_id,)):
            item={key:field[key] for key in ("id","system_key","name","field_type","config_json","sort_order","is_active")};item["options"]=[{key:o[key] for key in ("id","label","color","sort_order","is_active")} for o in conn.execute("SELECT * FROM field_options WHERE field_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(field["id"],))];snapshot["fields"].append(item)
        for view in conn.execute("SELECT * FROM saved_views WHERE board_id=? AND scope='shared' AND deleted_at IS NULL ORDER BY id",(board_id,)):
            snapshot["views"].append({key:view[key] for key in ("view_type","name","filter_json","sort_json","visible_fields_json","column_order_json","presentation_json","is_default")})
        task_ids=[]
        for group in conn.execute("SELECT * FROM groups_ WHERE board_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id",(board_id,)):
            group_item={"id":group["id"],"name":group["name"],"color":group["color"],"sort_order":group["sort_order"],"tasks":[]}
            if include_tasks:
                for task in conn.execute("SELECT * FROM tasks WHERE group_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id",(group["id"],)):
                    item={key:task[key] for key in ("id","title","status","priority","due","owner_id","sort_order","board_order","parent_id","subtask_order")};item["values"]=[dict(v) for v in conn.execute("SELECT * FROM task_field_values WHERE task_id=?",(task["id"],))];item["tags"]=[dict(v) for v in conn.execute("SELECT * FROM task_field_tag_values WHERE task_id=?",(task["id"],))];group_item["tasks"].append(item);task_ids.append(task["id"])
            snapshot["groups"].append(group_item)
        if include_tasks:
            allowed=set(task_ids)
            snapshot["dependencies"]=[dict(row) for row in conn.execute("SELECT predecessor_id,successor_id FROM task_dependencies WHERE deleted_at IS NULL") if row["predecessor_id"] in allowed and row["successor_id"] in allowed]
            snapshot["relations"]=[dict(row) for row in conn.execute("SELECT field_id,source_task_id,target_task_id FROM task_relation_values WHERE deleted_at IS NULL") if row["source_task_id"] in allowed and row["target_task_id"] in allowed]
        return snapshot

    @staticmethod
    def _remap_view(value,field_map):
        if isinstance(value,list):return [FlowboardService._remap_view(item,field_map) for item in value]
        if isinstance(value,dict):
            result={key:FlowboardService._remap_view(item,field_map) for key,item in value.items()}
            if result.get("kind")=="dynamic" and isinstance(result.get("id"),int):result["id"]=field_map.get(result["id"],result["id"])
            for key in ("group_field_id","date_field_id"):
                if isinstance(result.get(key),int):result[key]=field_map.get(result[key],result[key])
            if isinstance(result.get("frozen_columns"),list):result["frozen_columns"]=[field_map.get(item,item) if isinstance(item,int) else item for item in result["frozen_columns"]]
            if isinstance(result.get("widths"),dict):result["widths"]={str(field_map.get(int(key),int(key))) if str(key).isdigit() else key:item for key,item in result["widths"].items()}
            return result
        return value

    def list_templates(self,user,workspace_id,include_deleted=False):
        conn=self._db()
        try:
            self._workspace_role(conn,user["id"],workspace_id)
            rows=conn.execute(f"SELECT id,workspace_id,source_board_id,template_type,name,description,include_tasks,version,created_by,created_at,updated_at,deleted_at FROM board_templates WHERE workspace_id=? {' ' if include_deleted else 'AND deleted_at IS NULL'} ORDER BY updated_at DESC,id DESC",(workspace_id,)).fetchall()
            return {"templates":[dict(row) for row in rows]}
        finally:conn.close()

    def create_template(self,user,workspace_id,data):
        reject_unknown(data,{"source_board_id","name","description","template_type","include_tasks"});source_id=require_int(data.get("source_board_id"),"source_board_id",minimum=1);name=require_text(data,"name",max_length=200);description=require_text({"description":data.get("description","")},"description",max_length=2000,allow_empty=True);kind=validate_choice(data.get("template_type","board"),"template_type",{"board","project"});include=data.get("include_tasks",False)
        if not isinstance(include,bool):raise ApiError(422,"VALIDATION_ERROR","include_tasks 必须是布尔值")
        conn=self._db()
        try:
            with transaction(conn):
                self._workspace_role(conn,user["id"],workspace_id,write=True);board=self._board_access(conn,user["id"],source_id,write=True,require_active=True)
                if board["workspace_id"]!=workspace_id:raise ApiError(422,"VALIDATION_ERROR","来源看板不属于该工作区")
                snapshot=self._board_snapshot(conn,source_id,include);stamp=utc_now();cursor=conn.execute("INSERT INTO board_templates(workspace_id,source_board_id,template_type,name,description,include_tasks,snapshot_json,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(workspace_id,source_id,kind,name,description,int(include),json.dumps(snapshot,ensure_ascii=False),user["id"],stamp,stamp));template_id=cursor.lastrowid
                self._activity(conn,source_id,"board",source_id,user["id"],"template.created",{"template_id":template_id,"type":kind,"include_tasks":include})
            return {"id":template_id,"version":1}
        finally:conn.close()

    def update_template(self,user,template_id,data):
        reject_unknown(data,{"version","name","description"});version=require_version(data);changes={}
        if "name" in data:changes["name"]=require_text(data,"name",max_length=200)
        if "description" in data:changes["description"]=require_text(data,"description",max_length=2000,allow_empty=True)
        if not changes:raise ApiError(422,"VALIDATION_ERROR","没有可更新字段")
        conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM board_templates WHERE id=? AND deleted_at IS NULL",(template_id,)).fetchone()
                if not row:raise ApiError(404,"TEMPLATE_NOT_FOUND","模板不存在")
                self._workspace_role(conn,user["id"],row["workspace_id"],write=True);cursor=conn.execute(f"UPDATE board_templates SET {','.join(f'{key}=?' for key in changes)},updated_at=?,version=version+1 WHERE id=? AND version=?",(*changes.values(),utc_now(),template_id,version));self._conflict(cursor,"模板版本冲突")
                if row["source_board_id"]:self._activity(conn,row["source_board_id"],"board",row["source_board_id"],user["id"],"template.updated",{"template_id":template_id,"fields":sorted(changes)})
            return {"id":template_id,"version":version+1}
        finally:conn.close()

    def delete_template(self,user,template_id,data):
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM board_templates WHERE id=? AND deleted_at IS NULL",(template_id,)).fetchone()
                if not row:raise ApiError(404,"TEMPLATE_NOT_FOUND","模板不存在")
                self._workspace_role(conn,user["id"],row["workspace_id"],write=True);cursor=conn.execute("UPDATE board_templates SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL",(utc_now(),user["id"],utc_now(),template_id,version));self._conflict(cursor,"模板版本冲突")
                if row["source_board_id"]:self._activity(conn,row["source_board_id"],"board",row["source_board_id"],user["id"],"template.deleted",{"template_id":template_id})
            return {"id":template_id,"version":version+1,"deleted":True}
        finally:conn.close()

    def instantiate_template(self,user,template_id,data):
        reject_unknown(data,{"name","access_type"});conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM board_templates WHERE id=? AND deleted_at IS NULL",(template_id,)).fetchone()
                if not row:raise ApiError(404,"TEMPLATE_NOT_FOUND","模板不存在")
                self._workspace_role(conn,user["id"],row["workspace_id"],write=True);snapshot=json.loads(row["snapshot_json"]);board=snapshot["board"];name=require_text({"name":data.get("name",f"{row['name']} 副本")},"name",max_length=200);access=validate_choice(data.get("access_type",board.get("access_type","open")),"access_type",{"open","private"})
                new_board=conn.execute("INSERT INTO boards(workspace_id,name,description,color,access_type,created_at) VALUES (?,?,?,?,?,?)",(row["workspace_id"],name,board.get("description",""),board.get("color","purple"),access,utc_now())).lastrowid
                if access=="private":conn.execute("INSERT INTO board_memberships VALUES (?,?)",(new_board,user["id"]))
                field_map={};option_map={};disabled=set()
                for field in snapshot["fields"]:
                    new_id=conn.execute("INSERT INTO field_definitions(board_id,system_key,name,field_type,config_json,sort_order,is_active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",(new_board,field["system_key"],field["name"],field["field_type"],field["config_json"],field["sort_order"],field["is_active"],utc_now(),utc_now())).lastrowid;field_map[field["id"]]=new_id
                    for option in field["options"]:
                        option_map[option["id"]]=conn.execute("INSERT INTO field_options(field_id,label,color,sort_order,is_active) VALUES (?,?,?,?,?)",(new_id,option["label"],option["color"],option["sort_order"],option["is_active"])).lastrowid
                for field in snapshot["fields"]:
                    config=json.loads(field["config_json"] or "{}");active=field["is_active"]
                    if field["field_type"]=="relation":
                        if config.get("target_board_id")==snapshot["source_board_id"]:config["target_board_id"]=new_board
                        else:config={"target_board_id":None,"bidirectional":bool(config.get("bidirectional")),"template_unbound":True};active=0;disabled.add(field["id"])
                    elif field["field_type"]=="mirror":
                        relation_id=config.get("relation_field_id");config["relation_field_id"]=field_map.get(relation_id,relation_id);config["source_field_id"]=field_map.get(config.get("source_field_id"),config.get("source_field_id"))
                        if relation_id in disabled:active=0;disabled.add(field["id"])
                    elif field["field_type"]=="formula":
                        refs=formula_references(config.get("expression",""));config["expression"]=re.sub(r"\bf(\d+)\b",lambda match:f"f{field_map.get(int(match.group(1)),int(match.group(1)))}",config.get("expression",""))
                        if refs.intersection(disabled):active=0;disabled.add(field["id"])
                    conn.execute("UPDATE field_definitions SET config_json=?,is_active=? WHERE id=?",(json.dumps(config,ensure_ascii=False),active,field_map[field["id"]]))
                task_map={}
                for group in snapshot.get("groups",[]):
                    group_id=conn.execute("INSERT INTO groups_(board_id,name,color,sort_order) VALUES (?,?,?,?)",(new_board,group["name"],group["color"],group["sort_order"])).lastrowid
                    for task in group["tasks"]:
                        task_id=conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,subtask_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(group_id,task["title"],task["status"],task["priority"],task["due"],task["owner_id"],task["sort_order"],task["board_order"],task["subtask_order"],utc_now(),utc_now())).lastrowid;task_map[task["id"]]=task_id
                        for value in task["values"]:
                            conn.execute("INSERT INTO task_field_values(task_id,field_id,text_value,number_value,option_id,user_id,date_value,boolean_value,link_url,link_label) VALUES (?,?,?,?,?,?,?,?,?,?)",(task_id,field_map[value["field_id"]],value["text_value"],value["number_value"],option_map.get(value["option_id"]),value["user_id"],value["date_value"],value["boolean_value"],value["link_url"],value["link_label"]))
                        for value in task["tags"]:conn.execute("INSERT INTO task_field_tag_values VALUES (?,?,?,?)",(task_id,field_map[value["field_id"]],option_map[value["option_id"]],value["sort_order"]))
                for group in snapshot.get("groups",[]):
                    for task in group["tasks"]:
                        if task.get("parent_id") in task_map:conn.execute("UPDATE tasks SET parent_id=? WHERE id=?",(task_map[task["parent_id"]],task_map[task["id"]]))
                for edge in snapshot.get("dependencies",[]):conn.execute("INSERT INTO task_dependencies(predecessor_id,successor_id,created_by,created_at) VALUES (?,?,?,?)",(task_map[edge["predecessor_id"]],task_map[edge["successor_id"]],user["id"],utc_now()))
                for edge in snapshot.get("relations",[]):
                    if edge["field_id"] not in disabled:conn.execute("INSERT INTO task_relation_values(field_id,source_task_id,target_task_id,created_by,created_at) VALUES (?,?,?,?,?)",(field_map[edge["field_id"]],task_map[edge["source_task_id"]],task_map[edge["target_task_id"]],user["id"],utc_now()))
                for view in snapshot["views"]:
                    configs={key:self._remap_view(json.loads(view[key]),field_map) for key in ("filter_json","sort_json","presentation_json")}
                    for key in ("visible_fields_json","column_order_json"):
                        configs[key]=[field_map.get(value,value) if isinstance(value,int) else value for value in json.loads(view[key])]
                    conn.execute("INSERT INTO saved_views(board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,presentation_json,is_default,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(new_board,user["id"],"shared",view["view_type"],view["name"],*(json.dumps(configs[key],ensure_ascii=False) for key in ("filter_json","sort_json","visible_fields_json","column_order_json","presentation_json")),view["is_default"],utc_now(),utc_now()))
                self._activity(conn,new_board,"board",new_board,user["id"],"template.instantiated",{"template_id":template_id,"type":row["template_type"],"tasks":len(task_map),"disabled_fields":len(disabled)})
            return {"id":new_board,"version":1,"template_id":template_id,"disabled_fields":len(disabled)}
        finally:conn.close()

    def restore_template(self,user,template_id,data):
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM board_templates WHERE id=? AND deleted_at IS NOT NULL",(template_id,)).fetchone()
                if not row:raise ApiError(404,"TEMPLATE_NOT_FOUND","已删除模板不存在")
                self._workspace_role(conn,user["id"],row["workspace_id"],write=True)
                cursor=conn.execute("UPDATE board_templates SET deleted_at=NULL,deleted_by=NULL,updated_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NOT NULL",(utc_now(),template_id,version));self._conflict(cursor,"模板版本冲突")
                if row["source_board_id"]:self._activity(conn,row["source_board_id"],"board",row["source_board_id"],user["id"],"template.restored",{"template_id":template_id})
            return {"id":template_id,"version":version+1,"deleted":False}
        finally:conn.close()

    @staticmethod
    def _transfer_error(error):
        return ApiError(422,error.code,error.message,error.details)

    def preview_import(self,user,board_id,data):
        reject_unknown(data,{"filename","content_base64","sheet","board_version"});filename=require_text(data,"filename",max_length=255);board_version=require_int(data.get("board_version"),"board_version",minimum=1)
        access_conn=self._db()
        try:self._board_access(access_conn,user["id"],board_id,write=True,require_active=True)
        finally:access_conn.close()
        encoded=data.get("content_base64")
        if not isinstance(encoded,str):raise ApiError(422,"VALIDATION_ERROR","content_base64 must be text")
        try:raw=base64.b64decode(encoded,validate=True)
        except (ValueError,TypeError):raise ApiError(422,"IMPORT_BASE64_INVALID","文件内容不是有效 Base64")
        try:parsed=parse_upload(filename,raw,data.get("sheet"))
        except TransferError as error:raise self._transfer_error(error)
        conn=self._db()
        try:
            with transaction(conn):
                board=self._board_access(conn,user["id"],board_id,write=True,require_active=True)
                if board["version"]!=board_version:raise ApiError(409,"VERSION_CONFLICT","看板版本冲突")
                preview={key:parsed.get(key) for key in ("format","encoding","sheet","sheets","headers","rows")};stamp=utc_now()
                batch_id=conn.execute("INSERT INTO import_batches(board_id,filename,file_format,content_sha256,preview_json,created_by,created_at) VALUES (?,?,?,?,?,?,?)",(board_id,filename,parsed["format"],hashlib.sha256(raw).hexdigest(),json.dumps(preview,ensure_ascii=False),user["id"],stamp)).lastrowid
                self._activity(conn,board_id,"board",board_id,user["id"],"import.previewed",{"batch_id":batch_id,"format":parsed["format"],"rows":len(parsed["rows"])})
            return {"batch_id":batch_id,"batch_version":1,"board_version":board_version,"format":parsed["format"],"encoding":parsed["encoding"],"sheet":parsed["sheet"],"sheets":parsed.get("sheets",[parsed["sheet"]]),"headers":parsed["headers"],"sample_rows":parsed["rows"][:20],"row_count":len(parsed["rows"]),"inferred":infer_columns(parsed["headers"],parsed["rows"])}
        finally:conn.close()

    @staticmethod
    def _import_value(conn,field,text):
        value=text.strip();kind=field["field_type"]
        if not value:return None
        if kind=="text":return value
        if kind=="email":
            if len(value)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",value):raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 需要有效邮箱")
            return value
        if kind=="phone":
            if len(value)>40 or not re.fullmatch(r"[0-9+() .-]{3,40}",value):raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 需要有效电话")
            return value
        if kind in {"number","rating"}:
            try:number=float(value)
            except ValueError:raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 需要数字")
            if kind=="rating" and not 0<=number<=json.loads(field["config_json"] or "{}").get("max",5):raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 超出评分范围")
            return number
        if kind=="checkbox":
            lowered=value.casefold()
            if lowered in {"true","yes","1","是"}:return True
            if lowered in {"false","no","0","否"}:return False
            raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 需要布尔值")
        if kind=="date":
            try:return validate_due(value)
            except ApiError:raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 需要 YYYY-MM-DD 日期")
        if kind=="status":
            option=conn.execute("SELECT id FROM field_options WHERE field_id=? AND label=? AND is_active=1 AND deleted_at IS NULL",(field["id"],value)).fetchone()
            if not option:raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 的选项不存在")
            return option["id"]
        if kind=="tags":
            labels=[item.strip() for item in value.split(",") if item.strip()];options=[]
            for label in labels:
                option=conn.execute("SELECT id FROM field_options WHERE field_id=? AND label=? AND is_active=1 AND deleted_at IS NULL",(field["id"],label)).fetchone()
                if not option:raise ApiError(422,"IMPORT_VALUE_INVALID",f"{field['name']} 的选项不存在: {label}")
                options.append(option["id"])
            return options
        raise ApiError(422,"IMPORT_FIELD_UNSUPPORTED",f"{field['name']} 不支持表格导入")

    def commit_import(self,user,board_id,data):
        reject_unknown(data,{"batch_id","batch_version","board_version","group_id","mapping"});batch_id=require_int(data.get("batch_id"),"batch_id",minimum=1);batch_version=require_int(data.get("batch_version"),"batch_version",minimum=1);board_version=require_int(data.get("board_version"),"board_version",minimum=1);group_id=require_int(data.get("group_id"),"group_id",minimum=1);mapping=data.get("mapping")
        if not isinstance(mapping,list) or not mapping:raise ApiError(422,"IMPORT_MAPPING_INVALID","mapping 必须是非空数组")
        conn=self._db()
        try:
            with transaction(conn):
                board=self._board_access(conn,user["id"],board_id,write=True,require_active=True)
                if board["version"]!=board_version:raise ApiError(409,"VERSION_CONFLICT","看板版本冲突")
                batch=conn.execute("SELECT * FROM import_batches WHERE id=? AND board_id=? AND created_by=? AND status='previewed'",(batch_id,board_id,user["id"])).fetchone()
                if not batch:raise ApiError(404,"IMPORT_BATCH_NOT_FOUND","导入预览不存在或已提交")
                if batch["version"]!=batch_version:raise ApiError(409,"VERSION_CONFLICT","导入批次版本冲突")
                group=conn.execute("SELECT g.*,b.workspace_id FROM groups_ g JOIN boards b ON b.id=g.board_id WHERE g.id=? AND g.board_id=? AND g.deleted_at IS NULL AND g.archived_at IS NULL",(group_id,board_id)).fetchone()
                if not group:raise ApiError(422,"IMPORT_GROUP_INVALID","目标分组不可用")
                preview=json.loads(batch["preview_json"]);headers=preview["headers"];columns={};targets=set();title_column=None
                for item in mapping:
                    if not isinstance(item,dict) or set(item)!={"column","target"} or item["column"] not in headers or not isinstance(item["target"],dict):raise ApiError(422,"IMPORT_MAPPING_INVALID","映射项无效")
                    column=item["column"];target=item["target"]
                    if column in columns:raise ApiError(422,"IMPORT_MAPPING_INVALID","来源列不能重复映射")
                    if target=={"kind":"core","key":"title"}:descriptor=("title",None);title_column=column
                    elif target.get("kind")=="dynamic" and set(target)=={"kind","id"} and isinstance(target.get("id"),int):
                        field=conn.execute("SELECT * FROM field_definitions WHERE id=? AND board_id=? AND deleted_at IS NULL AND is_active=1",(target["id"],board_id)).fetchone()
                        if not field or field["field_type"] in {"person","link","timeline","file","relation","mirror","formula"}:raise ApiError(422,"IMPORT_MAPPING_INVALID","目标字段不存在或不支持导入")
                        descriptor=("field",field)
                    else:raise ApiError(422,"IMPORT_MAPPING_INVALID","目标字段无效")
                    target_key=descriptor[0] if descriptor[0]=="title" else f"field:{descriptor[1]['id']}"
                    if target_key in targets:raise ApiError(422,"IMPORT_MAPPING_INVALID","目标字段不能重复映射")
                    targets.add(target_key);columns[column]=descriptor
                if title_column is None:raise ApiError(422,"IMPORT_TITLE_REQUIRED","必须映射任务标题")
                prepared=[]
                for row_number,row in enumerate(preview["rows"],2):
                    record={};dynamic=[]
                    for column,descriptor in columns.items():
                        raw=row[headers.index(column)]
                        if descriptor[0]=="title":record["title"]=raw.strip()
                        else:
                            try:value=self._import_value(conn,descriptor[1],raw)
                            except ApiError as error:
                                details=dict(error.details or {});details.update({"row":row_number,"header":column,"field_id":descriptor[1]["id"],"field_type":descriptor[1]["field_type"]})
                                raise ApiError(error.status,error.code,error.message,details)
                            dynamic.append((descriptor[1],value))
                    if not record.get("title") or len(record["title"])>500:raise ApiError(422,"IMPORT_VALUE_INVALID","任务标题为空或过长",{"row":row_number,"header":title_column,"field":"title","field_type":"text"})
                    prepared.append((record,dynamic))
                next_sort=conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tasks WHERE group_id=?",(group_id,)).fetchone()[0];next_board=conn.execute("SELECT COALESCE(MAX(t.board_order),-1)+1 FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?",(board_id,)).fetchone()[0]
                stamp=utc_now()
                for offset,(record,dynamic) in enumerate(prepared):
                    task_id=conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(group_id,record["title"],"待开始","中","未设置",user["id"],next_sort+offset,next_board+offset,stamp,stamp)).lastrowid
                    task={"id":task_id,"board_id":board_id,"workspace_id":group["workspace_id"]}
                    for field,value in dynamic:
                        self._write_field_value(conn,task,field,value)
                        projection={"status":"status","priority":"priority","due":"due","owner":"owner_id"}.get(field["system_key"])
                        if projection:
                            projected=value
                            if field["system_key"] in {"status","priority"} and value is not None:projected=conn.execute("SELECT label FROM field_options WHERE id=? AND field_id=?",(value,field["id"])).fetchone()["label"]
                            if field["system_key"]=="due" and not value:projected="未设置"
                            conn.execute(f"UPDATE tasks SET {projection}=? WHERE id=?",(projected,task_id))
                cursor=conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(board_id,board_version));self._conflict(cursor,"看板版本冲突")
                conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(group_id,));cursor=conn.execute("UPDATE import_batches SET status='committed',version=version+1,committed_at=? WHERE id=? AND version=?",(stamp,batch_id,batch_version));self._conflict(cursor,"导入批次版本冲突")
                self._activity(conn,board_id,"board",board_id,user["id"],"import.committed",{"batch_id":batch_id,"rows":len(prepared),"sha256":batch["content_sha256"]})
            return {"batch_id":batch_id,"batch_version":batch_version+1,"board_version":board_version+1,"created":len(prepared)}
        finally:conn.close()

    @staticmethod
    def _export_value(value):
        if value is None:return ""
        if isinstance(value,list):return ", ".join(FlowboardService._export_value(item) for item in value)
        if isinstance(value,dict):
            for key in ("label","name","title","url","value"):
                if key in value:return FlowboardService._export_value(value[key])
            if set(value)>={"start","end"}:return f"{value['start']} ~ {value['end']}"
            return json.dumps(value,ensure_ascii=False,sort_keys=True)
        return value

    def export_board(self,user,board_id,data):
        reject_unknown(data,{"format","query","visible_fields","view_id"});file_format=validate_choice(data.get("format","csv"),"format",{"csv","xlsx"});query=data.get("query",{"version":1,"filter":{"op":"and","children":[]},"sort":[]});visible=data.get("visible_fields");view_id=data.get("view_id")
        if not isinstance(query,dict):raise ApiError(422,"QUERY_INVALID","query 必须是对象")
        conn=self._db()
        try:
            board=self._board_access(conn,user["id"],board_id,require_active=True)
            if view_id is not None:
                view,row_board=self._view_context(conn,user,require_int(view_id,"view_id",minimum=1))
                if view["board_id"]!=board_id:raise ApiError(422,"VIEW_INVALID","视图不属于当前看板")
                query={"version":1,"filter":json.loads(view["filter_json"]),"sort":json.loads(view["sort_json"])};visible=json.loads(view["visible_fields_json"])
            fields=[dict(row) for row in conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND deleted_at IS NULL AND is_active=1 ORDER BY sort_order,id",(board_id,))]
            field_by_id={field["id"]:field for field in fields}
            option_labels={row["id"]:row["label"] for row in conn.execute("SELECT id,label FROM field_options WHERE field_id IN (SELECT id FROM field_definitions WHERE board_id=?)",(board_id,))}
            user_names={row["id"]:row["name"] for row in conn.execute("SELECT u.id,u.name FROM users u JOIN workspace_memberships wm ON wm.user_id=u.id WHERE wm.workspace_id=?",(board["workspace_id"],))}
            if visible is None:visible=[field["id"] for field in fields]
            if not isinstance(visible,list) or len(visible)!=len(set(visible)) or any(isinstance(item,bool) or not isinstance(item,int) for item in visible) or not set(visible)<=set(field_by_id):raise ApiError(422,"EXPORT_FIELDS_INVALID","导出字段无效")
            checked=set()
            def check_export_source(field_id):
                if field_id in checked:return
                checked.add(field_id);field=field_by_id.get(field_id)
                if not field:return
                try:config=json.loads(field["config_json"] or "{}")
                except (TypeError,json.JSONDecodeError):raise ApiError(422,"EXPORT_FIELD_INVALID","导出字段配置无效")
                if field["field_type"]=="relation":
                    try:self._board_access(conn,user["id"],config.get("target_board_id"),require_active=True)
                    except ApiError:raise ApiError(403,"FIELD_SOURCE_FORBIDDEN","字段来源不可访问")
                elif field["field_type"]=="mirror":check_export_source(config.get("relation_field_id"))
                elif field["field_type"]=="formula":
                    try:
                        for dependency in formula_references(config.get("expression","")):check_export_source(dependency)
                    except FormulaError:raise ApiError(422,"EXPORT_FIELD_INVALID","导出字段配置无效")
            for field_id in visible:check_export_source(field_id)
        finally:conn.close()
        tasks=[];offset=0
        while True:
            payload={**query,"limit":200,"offset":offset};page=self.query_tasks(user,board_id,payload)
            if page["total"]>1000:raise ApiError(422,"EXPORT_LIMIT","导出最多支持 1000 行",{"max_rows":1000,"total":page["total"]})
            tasks.extend(page["tasks"])
            if len(tasks)>=page["total"]:break
            offset+=len(page["tasks"])
            if not page["tasks"]:raise ApiError(409,"EXPORT_CHANGED","导出期间数据发生变化，请重试")
        headers=["Title","Group",*[field_by_id[field_id]["name"] for field_id in visible]];rows=[]
        for task in tasks:
            values=task.get("field_values",{});rendered=[]
            for field_id in visible:
                value=values.get(str(field_id),values.get(field_id));kind=field_by_id[field_id]["field_type"]
                if kind=="status":value=option_labels.get(value,value)
                elif kind=="tags" and isinstance(value,list):value=[option_labels.get(item,item) for item in value]
                elif kind=="person":value=user_names.get(value,value)
                rendered.append(self._export_value(value))
            rows.append([task["title"],task.get("group_name",""),*rendered])
        raw=make_csv(headers,rows) if file_format=="csv" else make_xlsx(headers,rows)
        return {"filename":f"board-{board_id}.{file_format}","media_type":"text/csv; charset=utf-8" if file_format=="csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","format":file_format,"row_count":len(rows),"headers":headers,"sha256":hashlib.sha256(raw).hexdigest(),"content_base64":base64.b64encode(raw).decode("ascii")}

    @staticmethod
    def _schedule_source(conn,board_id,source):
        if source=={"kind":"fixed"}:return source,None
        if not isinstance(source,dict) or set(source)!={"kind","id"} or source.get("kind")!="dynamic" or isinstance(source.get("id"),bool) or not isinstance(source.get("id"),int):raise ApiError(422,"SCHEDULE_SOURCE_INVALID","排期日期来源无效")
        field=conn.execute("SELECT * FROM field_definitions WHERE id=? AND board_id=? AND deleted_at IS NULL AND is_active=1",(source["id"],board_id)).fetchone()
        if not field or field["field_type"] not in {"date","timeline"}:raise ApiError(422,"SCHEDULE_SOURCE_INVALID","排期日期来源无效")
        return source,field

    def schedule(self,user,board_id,data):
        reject_unknown(data,{"query","presentation"});query=data.get("query",{"version":1,"filter":{"op":"and","children":[]},"sort":[]});presentation=data.get("presentation",{"version":1,"source":{"kind":"fixed"},"scale":"week","show_dependencies":True,"show_critical_path":True,"baseline":"disabled"})
        if not isinstance(query,dict) or not isinstance(presentation,dict):raise ApiError(422,"VALIDATION_ERROR","排期请求无效")
        allowed={"version","source","scale","show_dependencies","show_critical_path","baseline"}
        if set(presentation)-allowed or presentation.get("version")!=1 or presentation.get("scale","week") not in SCALES or presentation.get("baseline","disabled")!="disabled":raise ApiError(422,"SCHEDULE_PRESENTATION_INVALID","排期展示配置无效")
        for key in ("show_dependencies","show_critical_path"):
            if key in presentation and not isinstance(presentation[key],bool):raise ApiError(422,"SCHEDULE_PRESENTATION_INVALID","排期展示配置无效")
        conn=self._db()
        try:
            self._board_access(conn,user["id"],board_id,require_active=True);source,field=self._schedule_source(conn,board_id,presentation.get("source",{"kind":"fixed"}));field_types={field["id"]:field["field_type"]} if field else {}
        finally:conn.close()
        tasks=[];offset=0
        while True:
            page=self.query_tasks(user,board_id,{**query,"limit":200,"offset":offset})
            if page["total"]>MAX_SCHEDULE_TASKS:raise ApiError(422,"SCHEDULE_TASK_LIMIT","排期任务超过安全上限",{"max_tasks":MAX_SCHEDULE_TASKS,"total":page["total"]})
            tasks.extend(page["tasks"])
            if len(tasks)>=page["total"]:break
            if not page["tasks"]:raise ApiError(409,"SCHEDULE_CHANGED","排期数据发生变化，请重试")
            offset+=len(page["tasks"])
        try:scheduled,unscheduled,bounds=project_schedule(tasks,source,field_types)
        except ScheduleError as error:raise ApiError(422,error.code,error.message,error.details)
        visible={item["id"] for item in scheduled};conn=self._db()
        try:
            edges=[dict(row) for row in conn.execute("""SELECT d.id,d.predecessor_id,d.successor_id,d.version FROM task_dependencies d
                JOIN tasks p ON p.id=d.predecessor_id JOIN groups_ pg ON pg.id=p.group_id JOIN boards pb ON pb.id=pg.board_id
                JOIN tasks s ON s.id=d.successor_id JOIN groups_ sg ON sg.id=s.group_id JOIN boards sb ON sb.id=sg.board_id
                WHERE pg.board_id=? AND sg.board_id=? AND d.deleted_at IS NULL
                AND p.deleted_at IS NULL AND p.archived_at IS NULL AND pg.deleted_at IS NULL AND pg.archived_at IS NULL AND pb.deleted_at IS NULL AND pb.archived_at IS NULL
                AND s.deleted_at IS NULL AND s.archived_at IS NULL AND sg.deleted_at IS NULL AND sg.archived_at IS NULL AND sb.deleted_at IS NULL AND sb.archived_at IS NULL""",(board_id,board_id))]
        finally:conn.close()
        critical,visible_edges=critical_path(scheduled,edges);show_dependencies=presentation.get("show_dependencies",True)
        return {"source":source,"scale":presentation.get("scale","week"),"baseline":"disabled","tasks":scheduled,"unscheduled":unscheduled,"bounds":bounds,"dependencies":visible_edges if show_dependencies else [],"critical_path":critical if presentation.get("show_critical_path",True) else {"task_ids":[],"duration_days":0,"blocked":False},"total":len(tasks),"limit":MAX_SCHEDULE_TASKS}

    def update_schedule(self,user,task_id,data):
        reject_unknown(data,{"version","board_version","source","start","end","dependency_policy","successor_versions"});version=require_version(data);board_version=require_int(data.get("board_version"),"board_version",minimum=1);source=data.get("source",{"kind":"fixed"});start=data.get("start");end=data.get("end");policy=validate_choice(data.get("dependency_policy","none"),"dependency_policy",{"none","push_successors_once"});expected=data.get("successor_versions",{})
        start_day,end_day=parse_day(start),parse_day(end)
        if not start_day or not end_day or start_day>end_day or (end_day-start_day).days+1>3660:raise ApiError(422,"SCHEDULE_DATE_INVALID","排期日期范围无效")
        if not isinstance(expected,dict) or any(not str(key).isdigit() or isinstance(value,bool) or not isinstance(value,int) or value<1 for key,value in expected.items()):raise ApiError(422,"VALIDATION_ERROR","successor_versions 无效")
        conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                if task["version"]!=version or task["board_version"]!=board_version:raise ApiError(409,"VERSION_CONFLICT","任务或看板版本冲突")
                source,field=self._schedule_source(conn,task["board_id"],source)
                if field and field["field_type"]=="date" and start!=end:raise ApiError(422,"SCHEDULE_DATE_SINGLE_DAY","日期字段只支持单日任务")
                successors=[]
                if policy=="push_successors_once":
                    successors=conn.execute("""SELECT t.*,g.board_id,b.workspace_id FROM task_dependencies d JOIN tasks t ON t.id=d.successor_id JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
                        WHERE d.predecessor_id=? AND d.deleted_at IS NULL AND t.deleted_at IS NULL AND t.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL AND b.deleted_at IS NULL AND b.archived_at IS NULL ORDER BY t.id""",(task_id,)).fetchall()
                    if set(expected)!={str(row["id"]) for row in successors}:raise ApiError(428,"SUCCESSOR_VERSIONS_REQUIRED","联动必须提供全部后置任务版本")
                    if any(expected[str(row["id"])]!=row["version"] for row in successors):raise ApiError(409,"VERSION_CONFLICT","后置任务版本冲突")
                if field is None:
                    conn.execute("UPDATE tasks SET start_date=? WHERE id=?",(start,task_id));self._set_due_projection(conn,task,end)
                else:
                    self._write_field_value(conn,task,field,start if field["field_type"]=="date" else {"start":start,"end":end})
                    if field["system_key"]=="due":conn.execute("UPDATE tasks SET due=? WHERE id=?",(end,task_id))
                stamp=utc_now();cursor=conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(stamp,task_id,version));self._conflict(cursor,"任务版本冲突")
                pushed=[]
                for successor in successors:
                    if field is None:
                        before=successor["due"];after=end if before=="未设置" or (parse_day(before) and before<end) else None
                        if after:self._set_due_projection(conn,successor,after)
                    else:
                        before=self._task_values(conn,successor["id"]).get(str(field["id"]));after=None
                        if field["field_type"]=="date":
                            if not parse_day(before) or before<end:after=end
                        else:
                            prior_start=parse_day(before.get("start")) if isinstance(before,dict) else None;prior_end=parse_day(before.get("end")) if isinstance(before,dict) else None
                            if not prior_start or not prior_end or prior_start>prior_end:after={"start":end,"end":end}
                            elif prior_start.isoformat()<end:
                                shift=parse_day(end)-prior_start;after={"start":end,"end":(prior_end+shift).isoformat()}
                        if after:
                            self._write_field_value(conn,successor,field,after)
                            if field["system_key"]=="due":conn.execute("UPDATE tasks SET due=? WHERE id=?",(after if isinstance(after,str) else after["end"],successor["id"]))
                    if after:
                        conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(stamp,successor["id"],successor["version"]));pushed.append({"id":successor["id"],"version":successor["version"]+1,"source":source,"before":before,"after":after})
                cursor=conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(task["board_id"],board_version));self._conflict(cursor,"看板版本冲突")
                self._activity(conn,task["board_id"],"task",task_id,user["id"],"schedule.updated",{"source":source,"start":start,"end":end,"dependency_policy":policy,"pushed_successors":pushed},task_id=task_id)
            return {"id":task_id,"version":version+1,"board_version":board_version+1,"start":start,"end":end,"pushed_successors":pushed}
        finally:conn.close()

    # Typed aggregation and dashboards --------------------------------
    def _aggregation_catalog(self,conn,board_id):
        catalog={("core","status"):"status",("core","priority"):"priority",("core","owner_id"):"person",("core","due"):"date",("core","start_date"):"date",("core","board"):"board"}
        catalog.update({("dynamic",row["id"]):row["field_type"] for row in conn.execute("SELECT id,field_type FROM field_definitions WHERE board_id=? AND deleted_at IS NULL AND is_active=1",(board_id,))})
        return catalog

    def _aggregation_inputs(self,user,sources):
        rows=[];catalogs=[];total=0
        for source in sources:
            conn=self._db()
            try:
                board=self._board_access(conn,user["id"],source["board_id"],require_active=True);catalog=self._aggregation_catalog(conn,source["board_id"]);catalog["__source_key__"]=source.get("source_key");catalogs.append(catalog);board_name=board["name"];option_labels={row["id"]:row["label"] for row in conn.execute("SELECT o.id,o.label FROM field_options o JOIN field_definitions f ON f.id=o.field_id WHERE f.board_id=? AND o.deleted_at IS NULL",(source["board_id"],))};user_names={row["id"]:row["name"] for row in conn.execute("SELECT id,name FROM users")}
            finally:conn.close()
            query=source.get("query") or {"version":1,"filter":{"op":"and","children":[]},"sort":[]};page=self.query_tasks(user,source["board_id"],{**query,"limit":200,"offset":0})
            if page["total"]>2000 or total+page["total"]>MAX_WIDGET_TASKS:raise ApiError(422,"AGGREGATION_TASK_LIMIT","聚合任务超过安全上限",{"max_per_source":2000,"max_total":MAX_WIDGET_TASKS})
            tasks=list(page["tasks"]);offset=len(tasks);expected_total=page["total"]
            while offset<expected_total:
                batch=self.query_tasks(user,source["board_id"],{**query,"limit":200,"offset":offset})
                if batch["total"]!=expected_total or not batch["tasks"]:
                    raise ApiError(409,"AGGREGATION_SOURCE_CHANGED","聚合期间来源数据发生变化，请重试")
                if batch["total"]>2000 or total+batch["total"]>MAX_WIDGET_TASKS:
                    raise ApiError(422,"AGGREGATION_TASK_LIMIT","聚合任务超过安全上限",{"max_per_source":2000,"max_total":MAX_WIDGET_TASKS})
                tasks.extend(batch["tasks"]);offset+=len(batch["tasks"])
            for task in tasks:
                task["board_name"]=board_name;task["source_key"]=source.get("source_key");task["owner_id"]=user_names.get(task.get("owner_id"),task.get("owner_id"));values=task.get("field_values") or {}
                for key,value in list(values.items()):
                    field_type=catalog.get(("dynamic",int(key))) if str(key).isdigit() else None
                    if field_type=="tags" and isinstance(value,list):values[key]=[option_labels.get(item,item) for item in value]
                    elif field_type=="status" and isinstance(value,int):values[key]=option_labels.get(value,value)
            rows.extend(tasks);total+=len(tasks)
        return rows,catalogs

    def _aggregate_sources(self,user,sources,spec,*,scalar=False):
        rows,catalogs=self._aggregation_inputs(user,sources)
        try:return aggregate_value(rows,spec,catalogs) if scalar else aggregate_rows(rows,spec,catalogs)
        except AggregationError as error:raise ApiError(422,error.code,error.message,error.details)

    def aggregate_board(self,user,board_id,data):
        reject_unknown(data,{"query","spec"});query=data.get("query",{"version":1,"filter":{"op":"and","children":[]},"sort":[]})
        return self._aggregate_sources(user,[{"source_key":"board","board_id":board_id,"query":query}],data.get("spec"))

    @staticmethod
    def _dashboard_payload(row):
        item=dict(row)
        try:item["global_filters"]=json.loads(item.pop("global_filters_json"))
        except (TypeError,json.JSONDecodeError):item["global_filters"]={"version":1,"by_source":{}};item["blocked"]=True
        return item

    def _dashboard_context(self,conn,user,dashboard_id,*,write=False,include_deleted=False):
        row=conn.execute("SELECT d.*,wm.role FROM dashboards d JOIN workspace_memberships wm ON wm.workspace_id=d.workspace_id AND wm.user_id=? WHERE d.id=?"+("" if include_deleted else " AND d.deleted_at IS NULL"),(user["id"],dashboard_id)).fetchone()
        if not row or row["scope"]=="personal" and row["owner_id"]!=user["id"]:raise ApiError(403,"DASHBOARD_FORBIDDEN","仪表盘不存在或不可访问")
        if write and (row["role"]=="viewer" or row["scope"]=="personal" and row["owner_id"]!=user["id"]):raise ApiError(403,"READ_ONLY","没有权限修改仪表盘")
        return row

    @staticmethod
    def _dashboard_activity(conn,dashboard_id,user_id,action,details=None):
        conn.execute("INSERT INTO dashboard_activity(dashboard_id,user_id,action_code,details_json,created_at) VALUES (?,?,?,?,?)",(dashboard_id,user_id,action,json.dumps(details or {},ensure_ascii=False),utc_now()))

    @staticmethod
    def _ensure_dashboard_capacity(conn,dashboard_id,kind):
        table,limit,code = {"source":("dashboard_sources",8,"DASHBOARD_SOURCE_LIMIT"),"widget":("dashboard_widgets",20,"DASHBOARD_WIDGET_LIMIT")}[kind]
        if conn.execute(f"SELECT COUNT(*) FROM {table} WHERE dashboard_id=? AND deleted_at IS NULL",(dashboard_id,)).fetchone()[0]>=limit:
            raise ApiError(422,code,"仪表盘来源超过安全上限" if kind=="source" else "仪表盘组件超过安全上限",{"max":limit})

    def list_dashboards(self,user,workspace_id,include_deleted=False):
        conn=self._db()
        try:
            self._workspace_role(conn,user["id"],workspace_id);rows=conn.execute("SELECT d.*,wm.role FROM dashboards d JOIN workspace_memberships wm ON wm.workspace_id=d.workspace_id AND wm.user_id=? WHERE d.workspace_id=? AND (d.scope='shared' OR d.owner_id=?)"+("" if include_deleted else " AND d.deleted_at IS NULL")+" ORDER BY d.name,d.id",(user["id"],workspace_id,user["id"])).fetchall();return {"dashboards":[self._dashboard_payload(row) for row in rows]}
        finally:conn.close()

    def create_dashboard(self,user,workspace_id,data):
        reject_unknown(data,{"name","scope","global_filters"});name=require_text(data,"name",max_length=120);scope=validate_choice(data.get("scope","personal"),"scope",{"personal","shared"});filters=data.get("global_filters",{"version":1,"by_source":{}})
        if not isinstance(filters,dict) or filters.get("version")!=1 or set(filters)-{"version","by_source"} or not isinstance(filters.get("by_source",{}),dict):raise ApiError(422,"DASHBOARD_INVALID","全局筛选无效")
        conn=self._db()
        try:
            with transaction(conn):
                role=self._workspace_role(conn,user["id"],workspace_id,write=True)
                if scope=="shared" and role=="viewer":raise ApiError(403,"READ_ONLY","只读成员不能创建共享仪表盘")
                stamp=utc_now();cursor=conn.execute("INSERT INTO dashboards(workspace_id,owner_id,scope,name,global_filters_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",(workspace_id,user["id"],scope,name,json.dumps(filters,ensure_ascii=False),stamp,stamp));dashboard_id=cursor.lastrowid;self._dashboard_activity(conn,dashboard_id,user["id"],"dashboard.created")
            return {"id":dashboard_id,"version":1}
        finally:conn.close()

    def get_dashboard(self,user,dashboard_id):
        conn=self._db()
        try:
            row=self._dashboard_context(conn,user,dashboard_id);item=self._dashboard_payload(row);sources=[]
            for source in conn.execute("SELECT * FROM dashboard_sources WHERE dashboard_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(dashboard_id,)):
                try:self._board_access(conn,user["id"],source["board_id"],require_active=True)
                except ApiError:continue
                value=dict(source);value["query"]=json.loads(value.pop("query_json"));sources.append(value)
            widgets=[]
            for widget in conn.execute("SELECT * FROM dashboard_widgets WHERE dashboard_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(dashboard_id,)):
                value=dict(widget);value["config"]=json.loads(value.pop("config_json"));widgets.append(value)
            item["sources"],item["widgets"]=sources,widgets;item["can_update"]=row["role"]!="viewer" and (row["scope"]=="shared" or row["owner_id"]==user["id"]);return item
        finally:conn.close()

    def update_dashboard(self,user,dashboard_id,data):
        reject_unknown(data,{"version","name","global_filters"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                row=self._dashboard_context(conn,user,dashboard_id,write=True);name=require_text({"name":data.get("name",row["name"])} ,"name",max_length=120);filters=data.get("global_filters",json.loads(row["global_filters_json"]))
                if not isinstance(filters,dict) or filters.get("version")!=1 or set(filters)-{"version","by_source"} or not isinstance(filters.get("by_source",{}),dict):raise ApiError(422,"DASHBOARD_INVALID","全局筛选无效")
                cursor=conn.execute("UPDATE dashboards SET name=?,global_filters_json=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(name,json.dumps(filters,ensure_ascii=False),utc_now(),dashboard_id,version));self._conflict(cursor,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],"dashboard.updated")
            return {"id":dashboard_id,"version":version+1}
        finally:conn.close()

    def dashboard_command(self,user,dashboard_id,command,data):
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                row=self._dashboard_context(conn,user,dashboard_id,write=True,include_deleted=command=="restore");stamp=utc_now()
                if command=="delete":sql="UPDATE dashboards SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND version=?";args=(stamp,user["id"],stamp,dashboard_id,version)
                elif command=="restore":sql="UPDATE dashboards SET deleted_at=NULL,deleted_by=NULL,updated_at=?,version=version+1 WHERE id=? AND version=?";args=(stamp,dashboard_id,version)
                else:raise ApiError(404,"NOT_FOUND","未知操作")
                cursor=conn.execute(sql,args);self._conflict(cursor,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],f"dashboard.{command}d")
            return {"id":dashboard_id,"version":version+1}
        finally:conn.close()

    def copy_dashboard(self,user,dashboard_id,data):
        reject_unknown(data,{"name","scope"});conn=self._db()
        try:
            with transaction(conn):
                row=self._dashboard_context(conn,user,dashboard_id);scope=validate_choice(data.get("scope","personal"),"scope",{"personal","shared"});
                if scope=="shared" and row["role"]=="viewer":raise ApiError(403,"READ_ONLY","只读成员不能创建共享仪表盘")
                name=require_text({"name":data.get("name",row["name"]+" 副本")},"name",max_length=120);stamp=utc_now();cursor=conn.execute("INSERT INTO dashboards(workspace_id,owner_id,scope,name,global_filters_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",(row["workspace_id"],user["id"],scope,name,row["global_filters_json"],stamp,stamp));new_id=cursor.lastrowid
                conn.execute("INSERT INTO dashboard_sources(dashboard_id,source_key,board_id,query_json,sort_order,created_at,updated_at) SELECT ?,source_key,board_id,query_json,sort_order,?,? FROM dashboard_sources WHERE dashboard_id=? AND deleted_at IS NULL",(new_id,stamp,stamp,dashboard_id));conn.execute("INSERT INTO dashboard_widgets(dashboard_id,widget_type,title,config_json,x,y,width,height,sort_order,created_at,updated_at) SELECT ?,widget_type,title,config_json,x,y,width,height,sort_order,?,? FROM dashboard_widgets WHERE dashboard_id=? AND deleted_at IS NULL",(new_id,stamp,stamp,dashboard_id));self._dashboard_activity(conn,new_id,user["id"],"dashboard.copied",{"source_id":dashboard_id})
            return {"id":new_id,"version":1}
        finally:conn.close()

    def add_dashboard_source(self,user,dashboard_id,data):
        reject_unknown(data,{"dashboard_version","source_key","board_id","query"});dashboard_version=require_int(data.get("dashboard_version"),"dashboard_version",minimum=1);source_key=require_text(data,"source_key",max_length=40);board_id=require_int(data.get("board_id"),"board_id",minimum=1);query=data.get("query",{"version":1,"filter":{"op":"and","children":[]},"sort":[]});conn=self._db()
        try:
            with transaction(conn):
                dashboard=self._dashboard_context(conn,user,dashboard_id,write=True);board=self._board_access(conn,user["id"],board_id,require_active=True)
                if board["workspace_id"]!=dashboard["workspace_id"]:raise ApiError(422,"DASHBOARD_SOURCE_INVALID","来源看板不在同一工作区")
                normalized,*_=self._normalize_query(conn,board_id,query)
                self._ensure_dashboard_capacity(conn,dashboard_id,"source")
                stamp=utc_now();cursor=conn.execute("INSERT INTO dashboard_sources(dashboard_id,source_key,board_id,query_json,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",(dashboard_id,source_key,board_id,json.dumps(normalized,ensure_ascii=False),conn.execute("SELECT COUNT(*) FROM dashboard_sources WHERE dashboard_id=?",(dashboard_id,)).fetchone()[0],stamp,stamp));source_id=cursor.lastrowid
                updated=conn.execute("UPDATE dashboards SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,dashboard_id,dashboard_version));self._conflict(updated,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],"dashboard.source_added",{"source_id":source_id})
            return {"id":source_id,"version":1,"dashboard_version":dashboard_version+1}
        except Exception as error:
            if isinstance(error,ApiError):raise
            if "UNIQUE" in str(error):raise ApiError(409,"SOURCE_KEY_CONFLICT","来源标识已存在")
            raise
        finally:conn.close()

    def update_dashboard_source(self,user,dashboard_id,source_id,data):
        reject_unknown(data,{"version","dashboard_version","source_key","query"});version=require_version(data);dashboard_version=require_int(data.get("dashboard_version"),"dashboard_version",minimum=1);conn=self._db()
        try:
            with transaction(conn):
                self._dashboard_context(conn,user,dashboard_id,write=True);row=conn.execute("SELECT * FROM dashboard_sources WHERE id=? AND dashboard_id=? AND deleted_at IS NULL",(source_id,dashboard_id)).fetchone()
                if not row:raise ApiError(404,"SOURCE_NOT_FOUND","仪表盘来源不存在")
                source_key=require_text({"source_key":data.get("source_key",row["source_key"])},"source_key",max_length=40);query=data.get("query",json.loads(row["query_json"]));normalized,*_=self._normalize_query(conn,row["board_id"],query);stamp=utc_now();cursor=conn.execute("UPDATE dashboard_sources SET source_key=?,query_json=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(source_key,json.dumps(normalized,ensure_ascii=False),stamp,source_id,version));self._conflict(cursor,"来源版本冲突");updated=conn.execute("UPDATE dashboards SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,dashboard_id,dashboard_version));self._conflict(updated,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],"dashboard.source_updated",{"source_id":source_id})
            return {"id":source_id,"version":version+1,"dashboard_version":dashboard_version+1}
        finally:conn.close()

    @staticmethod
    def _validate_widget_config(kind,config):
        if not isinstance(config,dict) or config.get("version")!=1 or not isinstance(config.get("source_keys"),list) or not config["source_keys"] or len(config["source_keys"])>8 or any(not isinstance(key,str) or not key for key in config["source_keys"]):raise ApiError(422,"WIDGET_CONFIG_INVALID","组件配置无效")
        allowed={"number":{"version","source_keys","spec"},"chart":{"version","source_keys","spec"},"progress":{"version","source_keys","complete_values"},"calendar":{"version","source_keys","date_field","limit"},"table":{"version","source_keys","columns","limit"}}[kind]
        if set(config)-allowed:raise ApiError(422,"WIDGET_CONFIG_INVALID","组件配置含未知字段")
        if kind in {"number","chart"} and not isinstance(config.get("spec"),dict):raise ApiError(422,"WIDGET_CONFIG_INVALID","组件聚合配置无效")
        if kind=="progress" and (not isinstance(config.get("complete_values",["已完成"]),list) or any(not isinstance(v,str) for v in config.get("complete_values",[]))):raise ApiError(422,"WIDGET_CONFIG_INVALID","进度配置无效")
        if kind in {"calendar","table"}:
            limit=config.get("limit",50)
            if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=200:raise ApiError(422,"WIDGET_CONFIG_INVALID","组件行数无效")
        return config

    def add_dashboard_widget(self,user,dashboard_id,data):
        reject_unknown(data,{"dashboard_version","widget_type","title","config","x","y","width","height"});dashboard_version=require_int(data.get("dashboard_version"),"dashboard_version",minimum=1);kind=validate_choice(data.get("widget_type"),"widget_type",{"number","chart","progress","calendar","table"});title=require_text(data,"title",max_length=120);config=self._validate_widget_config(kind,data.get("config"));coords={key:require_int(data.get(key),key,minimum=0 if key in {"x","y"} else 1) for key in ("x","y","width","height")}
        if coords["x"]>11 or coords["width"]>12 or coords["x"]+coords["width"]>12 or coords["height"]>12:raise ApiError(422,"WIDGET_LAYOUT_INVALID","组件布局越界")
        conn=self._db()
        try:
            with transaction(conn):
                self._dashboard_context(conn,user,dashboard_id,write=True)
                self._ensure_dashboard_capacity(conn,dashboard_id,"widget")
                available={row[0] for row in conn.execute("SELECT source_key FROM dashboard_sources WHERE dashboard_id=? AND deleted_at IS NULL",(dashboard_id,))}
                if not set(config["source_keys"])<=available:raise ApiError(422,"WIDGET_CONFIG_INVALID","组件引用了不可用来源")
                stamp=utc_now();cursor=conn.execute("INSERT INTO dashboard_widgets(dashboard_id,widget_type,title,config_json,x,y,width,height,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(dashboard_id,kind,title,json.dumps(config,ensure_ascii=False),coords["x"],coords["y"],coords["width"],coords["height"],conn.execute("SELECT COUNT(*) FROM dashboard_widgets WHERE dashboard_id=?",(dashboard_id,)).fetchone()[0],stamp,stamp));widget_id=cursor.lastrowid;updated=conn.execute("UPDATE dashboards SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,dashboard_id,dashboard_version));self._conflict(updated,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],"dashboard.widget_added",{"widget_id":widget_id,"type":kind})
            return {"id":widget_id,"version":1,"dashboard_version":dashboard_version+1}
        finally:conn.close()

    def update_dashboard_widget(self,user,dashboard_id,widget_id,data):
        reject_unknown(data,{"version","dashboard_version","title","config","x","y","width","height"});version=require_version(data);dashboard_version=require_int(data.get("dashboard_version"),"dashboard_version",minimum=1);conn=self._db()
        try:
            with transaction(conn):
                self._dashboard_context(conn,user,dashboard_id,write=True);row=conn.execute("SELECT * FROM dashboard_widgets WHERE id=? AND dashboard_id=? AND deleted_at IS NULL",(widget_id,dashboard_id)).fetchone()
                if not row:raise ApiError(404,"WIDGET_NOT_FOUND","组件不存在")
                title=require_text({"title":data.get("title",row["title"])},"title",max_length=120);config=self._validate_widget_config(row["widget_type"],data.get("config",json.loads(row["config_json"])));coords={key:require_int(data.get(key,row[key]),key,minimum=0 if key in {"x","y"} else 1) for key in ("x","y","width","height")}
                if coords["x"]>11 or coords["width"]>12 or coords["x"]+coords["width"]>12 or coords["height"]>12:raise ApiError(422,"WIDGET_LAYOUT_INVALID","组件布局越界")
                stamp=utc_now();cursor=conn.execute("UPDATE dashboard_widgets SET title=?,config_json=?,x=?,y=?,width=?,height=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(title,json.dumps(config,ensure_ascii=False),coords["x"],coords["y"],coords["width"],coords["height"],stamp,widget_id,version));self._conflict(cursor,"组件版本冲突");updated=conn.execute("UPDATE dashboards SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,dashboard_id,dashboard_version));self._conflict(updated,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],"dashboard.widget_updated",{"widget_id":widget_id})
            return {"id":widget_id,"version":version+1,"dashboard_version":dashboard_version+1}
        finally:conn.close()

    def dashboard_widget_command(self,user,dashboard_id,widget_id,command,data):
        reject_unknown(data,{"version","dashboard_version"});version=require_version(data);dashboard_version=require_int(data.get("dashboard_version"),"dashboard_version",minimum=1);conn=self._db()
        try:
            with transaction(conn):
                self._dashboard_context(conn,user,dashboard_id,write=True);row=conn.execute("SELECT * FROM dashboard_widgets WHERE id=? AND dashboard_id=?",(widget_id,dashboard_id)).fetchone()
                if not row:raise ApiError(404,"WIDGET_NOT_FOUND","组件不存在")
                stamp=utc_now()
                if command=="copy":
                    if row["deleted_at"] is not None:raise ApiError(404,"WIDGET_NOT_FOUND","组件不存在")
                    if row["version"]!=version:raise ApiError(409,"VERSION_CONFLICT","组件版本冲突")
                    self._ensure_dashboard_capacity(conn,dashboard_id,"widget")
                    cursor=conn.execute("INSERT INTO dashboard_widgets(dashboard_id,widget_type,title,config_json,x,y,width,height,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(dashboard_id,row["widget_type"],row["title"]+" 副本",row["config_json"],row["x"],row["y"]+row["height"],row["width"],row["height"],row["sort_order"]+1,stamp,stamp));result_id=cursor.lastrowid;result_version=1
                elif command=="delete":
                    cursor=conn.execute("UPDATE dashboard_widgets SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL",(stamp,user["id"],stamp,widget_id,version));self._conflict(cursor,"组件版本冲突");result_id,result_version=widget_id,version+1
                elif command=="restore":
                    if row["deleted_at"] is None or row["version"]!=version:raise ApiError(409,"VERSION_CONFLICT","组件版本冲突")
                    self._ensure_dashboard_capacity(conn,dashboard_id,"widget")
                    cursor=conn.execute("UPDATE dashboard_widgets SET deleted_at=NULL,deleted_by=NULL,updated_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NOT NULL",(stamp,widget_id,version));self._conflict(cursor,"组件版本冲突");result_id,result_version=widget_id,version+1
                else:raise ApiError(404,"NOT_FOUND","未知操作")
                updated=conn.execute("UPDATE dashboards SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,dashboard_id,dashboard_version));self._conflict(updated,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],f"dashboard.widget_{command}d",{"widget_id":widget_id,"result_id":result_id})
            return {"id":result_id,"version":result_version,"dashboard_version":dashboard_version+1}
        finally:conn.close()

    def dashboard_source_command(self,user,dashboard_id,source_id,command,data):
        reject_unknown(data,{"version","dashboard_version"});version=require_version(data);dashboard_version=require_int(data.get("dashboard_version"),"dashboard_version",minimum=1);conn=self._db()
        try:
            with transaction(conn):
                self._dashboard_context(conn,user,dashboard_id,write=True);row=conn.execute("SELECT * FROM dashboard_sources WHERE id=? AND dashboard_id=?",(source_id,dashboard_id)).fetchone()
                if not row:raise ApiError(404,"SOURCE_NOT_FOUND","仪表盘来源不存在")
                stamp=utc_now()
                if command=="delete":sql="UPDATE dashboard_sources SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND dashboard_id=? AND version=? AND deleted_at IS NULL";args=(stamp,user["id"],stamp,source_id,dashboard_id,version)
                elif command=="restore":
                    if row["deleted_at"] is None or row["version"]!=version:raise ApiError(409,"VERSION_CONFLICT","来源版本冲突")
                    self._ensure_dashboard_capacity(conn,dashboard_id,"source");sql="UPDATE dashboard_sources SET deleted_at=NULL,deleted_by=NULL,updated_at=?,version=version+1 WHERE id=? AND dashboard_id=? AND version=? AND deleted_at IS NOT NULL";args=(stamp,source_id,dashboard_id,version)
                else:raise ApiError(404,"NOT_FOUND","未知操作")
                cursor=conn.execute(sql,args);self._conflict(cursor,"来源版本冲突");updated=conn.execute("UPDATE dashboards SET version=version+1,updated_at=? WHERE id=? AND version=?",(stamp,dashboard_id,dashboard_version));self._conflict(updated,"仪表盘版本冲突");self._dashboard_activity(conn,dashboard_id,user["id"],f"dashboard.source_{command}d",{"source_id":source_id})
            return {"id":source_id,"version":version+1,"dashboard_version":dashboard_version+1}
        except Exception as error:
            if isinstance(error,ApiError):raise
            if "UNIQUE" in str(error):raise ApiError(409,"SOURCE_KEY_CONFLICT","来源标识已存在")
            raise
        finally:conn.close()

    def dashboard_widget_data(self,user,dashboard_id,widget_id):
        conn=self._db()
        try:
            dashboard=self._dashboard_context(conn,user,dashboard_id);widget=conn.execute("SELECT * FROM dashboard_widgets WHERE id=? AND dashboard_id=? AND deleted_at IS NULL",(widget_id,dashboard_id)).fetchone()
            if not widget:raise ApiError(404,"WIDGET_NOT_FOUND","组件不存在")
            config=self._validate_widget_config(widget["widget_type"],json.loads(widget["config_json"]));keys=set(config["source_keys"]);rows=conn.execute("SELECT * FROM dashboard_sources WHERE dashboard_id=? AND deleted_at IS NULL",(dashboard_id,)).fetchall();by_key={row["source_key"]:row for row in rows}
            if not keys<=set(by_key):raise ApiError(422,"WIDGET_CONFIG_INVALID","组件来源配置已失效")
            global_filters=json.loads(dashboard["global_filters_json"]).get("by_source",{});sources=[]
            for key in config["source_keys"]:
                row=by_key[key]
                try:self._board_access(conn,user["id"],row["board_id"],require_active=True)
                except ApiError:raise ApiError(403,"WIDGET_SOURCE_UNAVAILABLE","组件来源不可访问")
                query=json.loads(row["query_json"]);extra=global_filters.get(key)
                if extra is not None:
                    if not isinstance(extra,dict):raise ApiError(422,"DASHBOARD_INVALID","全局筛选无效")
                    query={**query,"filter":{"op":"and","children":[query.get("filter",{"op":"and","children":[]}),extra]}}
                sources.append({"source_key":key,"board_id":row["board_id"],"query":query})
        finally:conn.close()
        kind=widget["widget_type"]
        if kind in {"chart","number"}:
            result=self._aggregate_sources(user,sources,config["spec"],scalar=kind=="number")
            return {"widget_id":widget_id,"type":kind,"data":result}
        if kind=="progress":
            spec={"version":1,"chart_type":"bar","dimension":{"kind":"core","key":"status"},"metric":{"op":"count"},"top_n":20,"null_policy":"include"};result=self._aggregate_sources(user,sources,spec);counts={label:result["series"][0]["values"][index] for index,label in enumerate(result["categories"])};total=sum(counts.values());complete=sum(counts.get(value,0) for value in config.get("complete_values",["已完成"]));return {"widget_id":widget_id,"type":kind,"data":{"complete":complete,"total":total,"ratio":None if total==0 else complete/total,"empty":total==0}}
        projected=[];limit=config.get("limit",50)
        for source in sources:
            page=self.query_tasks(user,source["board_id"],{**source["query"],"limit":min(200,limit),"offset":0})
            if page["total"]>2000:raise ApiError(422,"AGGREGATION_TASK_LIMIT","组件任务超过安全上限")
            for task in page["tasks"]:
                value={"id":task["id"],"title":task["title"],"board_id":source["board_id"],"source_key":source["source_key"],"status":task["status"],"due":task["due"],"field_values":task["field_values"]}
                if kind=="calendar":
                    binding=config.get("date_field",{"kind":"core","key":"due"});date_value=task.get(binding.get("key")) if binding.get("kind")=="core" else task["field_values"].get(str(binding.get("id")));value["date"]=date_value.get("start") if isinstance(date_value,dict) else date_value
                projected.append(value)
        projected.sort(key=lambda item:((item.get("date") or "9999") if kind=="calendar" else item["title"],item["board_id"],item["id"]));return {"widget_id":widget_id,"type":kind,"data":{"rows":projected[:limit],"empty":not projected,"truncated":len(projected)>limit}}

    def create_board(self, user, workspace_id, data):
        reject_unknown(data, {"name", "description", "color", "access_type"})
        name = require_text(data, "name", max_length=200)
        description = require_text({"description": data.get("description", "")}, "description", max_length=2000, allow_empty=True)
        color = validate_choice(data.get("color", "purple"), "color", COLORS)
        access = validate_choice(data.get("access_type", "open"), "access_type", {"open", "private"})
        conn = self._db()
        try:
            with transaction(conn):
                self._workspace_role(conn, user["id"], workspace_id, write=True)
                cursor = conn.execute("INSERT INTO boards(workspace_id,name,description,color,access_type,created_at) VALUES (?,?,?,?,?,?)", (workspace_id, name, description, color, access, utc_now()))
                board_id = cursor.lastrowid
                stamp=utc_now()
                for order,(key,label,kind) in enumerate((("status","状态","status"),("priority","优先级","status"),("owner","负责人","person"),("due","截止日期","date"))):
                    field=conn.execute("INSERT INTO field_definitions(board_id,system_key,name,field_type,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",(board_id,key,label,kind,order,stamp,stamp)).lastrowid
                    defaults=STATUSES if key=="status" else (PRIORITIES if key=="priority" else ())
                    for option_order,value in enumerate(sorted(defaults)):
                        conn.execute("INSERT INTO field_options(field_id,label,sort_order) VALUES (?,?,?)",(field,value,option_order))
                if access == "private":
                    conn.execute("INSERT INTO board_memberships VALUES (?,?)", (board_id, user["id"]))
                self._activity(conn, board_id, "board", board_id, user["id"], "board.created", {"name": name})
            return {"id": board_id, "version": 1}
        finally:
            conn.close()

    def update_board(self, user, board_id, data):
        reject_unknown(data, {"version", "name", "description", "color", "access_type"})
        version = require_version(data)
        changes = {}
        if "name" in data: changes["name"] = require_text(data, "name", max_length=200)
        if "description" in data: changes["description"] = require_text(data, "description", max_length=2000, allow_empty=True)
        if "color" in data: changes["color"] = validate_choice(data["color"], "color", COLORS)
        if "access_type" in data: changes["access_type"] = validate_choice(data["access_type"], "access_type", {"open", "private"})
        if not changes: raise ApiError(422, "VALIDATION_ERROR", "没有可更新字段")
        conn = self._db()
        try:
            with transaction(conn):
                board = self._board_access(conn, user["id"], board_id, write=True, require_active=True)
                cursor = conn.execute(f"UPDATE boards SET {','.join(f'{k}=?' for k in changes)},version=version+1 WHERE id=? AND version=?", (*changes.values(), board_id, version))
                self._conflict(cursor, "看板已被其他成员更新")
                if changes.get("access_type") == "private" and board["role"] != "admin":
                    conn.execute("INSERT OR IGNORE INTO board_memberships VALUES (?,?)", (board_id, user["id"]))
                self._activity(conn, board_id, "board", board_id, user["id"], "board.updated", {"fields": sorted(changes)})
            return {"id": board_id, "version": version + 1}
        finally: conn.close()

    def copy_board(self, user, board_id, data):
        reject_unknown(data, {"name"})
        conn = self._db()
        try:
            with transaction(conn):
                source = self._board_access(conn, user["id"], board_id, write=True)
                name = require_text({"name": data.get("name", f"{source['name']} 副本")}, "name", max_length=200)
                cursor = conn.execute("INSERT INTO boards(workspace_id,name,description,color,access_type,created_at) VALUES (?,?,?,?,?,?)", (source["workspace_id"], name, source["description"], source["color"], source["access_type"], utc_now()))
                new_board = cursor.lastrowid
                if source["access_type"] == "private": conn.execute("INSERT INTO board_memberships VALUES (?,?)", (new_board, user["id"]))
                field_map, option_map, task_map = {}, {}, {}
                for field in conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(board_id,)).fetchall():
                    new_field=conn.execute("""INSERT INTO field_definitions(board_id,system_key,name,field_type,config_json,sort_order,is_active,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",(new_board,field["system_key"],field["name"],field["field_type"],field["config_json"],field["sort_order"],field["is_active"],utc_now(),utc_now())).lastrowid;field_map[field["id"]]=new_field
                    for option in conn.execute("SELECT * FROM field_options WHERE field_id=? AND deleted_at IS NULL ORDER BY sort_order,id",(field["id"],)).fetchall():
                        new_option=conn.execute("INSERT INTO field_options(field_id,label,color,sort_order,is_active) VALUES (?,?,?,?,?)",(new_field,option["label"],option["color"],option["sort_order"],option["is_active"])).lastrowid;option_map[option["id"]]=new_option
                for field in conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND deleted_at IS NULL",(board_id,)).fetchall():
                    config=json.loads(field["config_json"] or "{}")
                    copied_active=field["is_active"]
                    if field["field_type"]=="relation" and config.get("target_board_id")==board_id: config["target_board_id"]=new_board
                    elif field["field_type"]=="relation":
                        config={"target_board_id":None,"bidirectional":bool(config.get("bidirectional")),"copied_unbound":True};copied_active=0
                    elif field["field_type"]=="mirror":
                        config["relation_field_id"]=field_map.get(config.get("relation_field_id"),config.get("relation_field_id"))
                        config["source_field_id"]=field_map.get(config.get("source_field_id"),config.get("source_field_id"))
                    elif field["field_type"]=="formula":
                        config["expression"]=re.sub(r"\bf(\d+)\b",lambda match:f"f{field_map.get(int(match.group(1)),int(match.group(1)))}",config.get("expression",""))
                    conn.execute("UPDATE field_definitions SET config_json=?,is_active=? WHERE id=?",(json.dumps(config,ensure_ascii=False),copied_active,field_map[field["id"]]))
                group_count = task_count = 0
                for group in conn.execute("SELECT * FROM groups_ WHERE board_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id", (board_id,)).fetchall():
                    gcur = conn.execute("INSERT INTO groups_(board_id,name,color,sort_order) VALUES (?,?,?,?)", (new_board, group["name"], group["color"], group_count)); new_group = gcur.lastrowid; group_count += 1
                    group_task_order = 0
                    for task in conn.execute("SELECT * FROM tasks WHERE group_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id", (group["id"],)).fetchall():
                        new_task=conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,subtask_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (new_group, task["title"], task["status"], task["priority"], task["due"], task["owner_id"], group_task_order, task_count, task["subtask_order"], utc_now(), utc_now())).lastrowid;task_map[task["id"]]=new_task
                        for value in conn.execute("SELECT * FROM task_field_values WHERE task_id=?",(task["id"],)).fetchall():
                            conn.execute("""INSERT INTO task_field_values(task_id,field_id,text_value,number_value,option_id,user_id,date_value,boolean_value,link_url,link_label)
                                VALUES (?,?,?,?,?,?,?,?,?,?)""",(new_task,field_map[value["field_id"]],value["text_value"],value["number_value"],option_map.get(value["option_id"]),value["user_id"],value["date_value"],value["boolean_value"],value["link_url"],value["link_label"]))
                        for value in conn.execute("SELECT * FROM task_field_tag_values WHERE task_id=?",(task["id"],)).fetchall(): conn.execute("INSERT INTO task_field_tag_values VALUES (?,?,?,?)",(new_task,field_map[value["field_id"]],option_map[value["option_id"]],value["sort_order"]))
                        for value in conn.execute("SELECT * FROM legacy_task_field_values WHERE task_id=?",(task["id"],)).fetchall(): conn.execute("INSERT INTO legacy_task_field_values VALUES (?,?,?,?)",(new_task,field_map[value["field_id"]],value["raw_value"],value["reason"]))
                        task_count += 1; group_task_order += 1
                for old_id,new_id in task_map.items():
                    old=conn.execute("SELECT parent_id FROM tasks WHERE id=?",(old_id,)).fetchone()
                    if old["parent_id"] in task_map:conn.execute("UPDATE tasks SET parent_id=? WHERE id=?",(task_map[old["parent_id"]],new_id))
                for edge in conn.execute("SELECT * FROM task_dependencies WHERE deleted_at IS NULL AND predecessor_id IN (SELECT t.id FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?)",(board_id,)).fetchall():
                    if edge["predecessor_id"] in task_map and edge["successor_id"] in task_map:conn.execute("INSERT INTO task_dependencies(predecessor_id,successor_id,created_by,created_at) VALUES (?,?,?,?)",(task_map[edge["predecessor_id"]],task_map[edge["successor_id"]],user["id"],utc_now()))
                for edge in conn.execute("SELECT * FROM task_relation_values WHERE deleted_at IS NULL").fetchall():
                    if edge["field_id"] in field_map and edge["source_task_id"] in task_map and edge["target_task_id"] in task_map:
                        conn.execute("INSERT INTO task_relation_values(field_id,source_task_id,target_task_id,created_by,created_at) VALUES (?,?,?,?,?)",(field_map[edge["field_id"]],task_map[edge["source_task_id"]],task_map[edge["target_task_id"]],user["id"],utc_now()))
                self._activity(conn, new_board, "board", new_board, user["id"], "board.copied", {"source_id": board_id, "groups": group_count, "tasks": task_count})
            return {"id": new_board, "version": 1}
        finally: conn.close()

    def board_command(self, user, board_id, command, data):
        if command not in {"archive", "unarchive", "restore"}: raise ApiError(404, "NOT_FOUND", "接口不存在")
        reject_unknown(data, {"version"}); version = require_version(data); conn = self._db()
        try:
            with transaction(conn):
                board = self._board_access(conn, user["id"], board_id, write=True)
                if command == "restore":
                    if not board["deleted_at"]: raise ApiError(409, "INVALID_STATE", "看板不在回收站")
                    changes = "deleted_at=NULL,deleted_by=NULL"
                elif command == "archive":
                    if board["deleted_at"] or board["archived_at"]: raise ApiError(409, "INVALID_STATE", "看板当前状态不可归档")
                    changes = "archived_at=?,archived_by=?"
                else:
                    if board["deleted_at"] or not board["archived_at"]: raise ApiError(409, "INVALID_STATE", "看板当前状态不可取消归档")
                    changes = "archived_at=NULL,archived_by=NULL"
                args = (utc_now(), user["id"]) if command == "archive" else ()
                cursor = conn.execute(f"UPDATE boards SET {changes},version=version+1 WHERE id=? AND version=?", (*args, board_id, version)); self._conflict(cursor, "看板版本冲突")
                self._activity(conn, board_id, "board", board_id, user["id"], f"board.{COMMAND_ACTION[command]}", {})
            return {"id": board_id, "version": version + 1}
        finally: conn.close()

    def delete_board(self, user, board_id, data):
        reject_unknown(data, {"version"}); version = require_version(data); conn = self._db()
        try:
            with transaction(conn):
                board = self._board_access(conn, user["id"], board_id, write=True)
                if board["deleted_at"]: raise ApiError(409, "INVALID_STATE", "看板已在回收站")
                descendants = conn.execute("SELECT COUNT(*) FROM groups_ g LEFT JOIN tasks t ON t.group_id=g.id WHERE g.board_id=?", (board_id,)).fetchone()[0]
                cursor = conn.execute("UPDATE boards SET deleted_at=?,deleted_by=?,version=version+1 WHERE id=? AND version=?", (utc_now(), user["id"], board_id, version)); self._conflict(cursor, "看板版本冲突")
                self._activity(conn, board_id, "board", board_id, user["id"], "board.deleted", {"affected_descendants": descendants})
            return {"id": board_id, "version": version + 1}
        finally: conn.close()

    # Group lifecycle ----------------------------------------------------
    def create_group(self, user, board_id, data):
        reject_unknown(data, {"name", "color"}); name = require_text(data, "name", max_length=200); color = validate_choice(data.get("color", "green"), "color", COLORS); conn = self._db()
        try:
            with transaction(conn):
                board = self._board_access(conn, user["id"], board_id, write=True, require_active=True)
                order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM groups_ WHERE board_id=?", (board_id,)).fetchone()[0]
                cursor = conn.execute("INSERT INTO groups_(board_id,name,color,sort_order) VALUES (?,?,?,?)", (board_id, name, color, order)); gid = cursor.lastrowid
                conn.execute("UPDATE boards SET version=version+1 WHERE id=?", (board_id,))
                self._activity(conn, board_id, "group", gid, user["id"], "group.created", {"name": name})
            return {"id": gid, "version": 1, "board_version": board["version"] + 1}
        finally: conn.close()

    def update_group(self, user, group_id, data):
        reject_unknown(data, {"version", "name", "color"}); version = require_version(data); changes = {}
        if "name" in data: changes["name"] = require_text(data, "name", max_length=200)
        if "color" in data: changes["color"] = validate_choice(data["color"], "color", COLORS)
        if not changes: raise ApiError(422, "VALIDATION_ERROR", "没有可更新字段")
        conn = self._db()
        try:
            with transaction(conn):
                group = self._group_context(conn, user["id"], group_id, write=True, require_active=True)
                cursor = conn.execute(f"UPDATE groups_ SET {','.join(f'{k}=?' for k in changes)},version=version+1 WHERE id=? AND version=?", (*changes.values(), group_id, version)); self._conflict(cursor, "分组版本冲突")
                self._activity(conn, group["board_id"], "group", group_id, user["id"], "group.updated", {"fields": sorted(changes)})
            return {"id": group_id, "version": version + 1}
        finally: conn.close()

    def copy_group(self, user, group_id, data):
        reject_unknown(data, {"name"}); conn = self._db()
        try:
            with transaction(conn):
                source = self._group_context(conn, user["id"], group_id, write=True, require_active=True)
                name = require_text({"name": data.get("name", f"{source['name']} 副本")}, "name", max_length=200)
                order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM groups_ WHERE board_id=?", (source["board_id"],)).fetchone()[0]
                cursor = conn.execute("INSERT INTO groups_(board_id,name,color,sort_order) VALUES (?,?,?,?)", (source["board_id"], name, source["color"], order)); new_group = cursor.lastrowid; count = 0;task_map={}
                board_order = conn.execute("SELECT COALESCE(MAX(t.board_order),-1)+1 FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?",(source["board_id"],)).fetchone()[0]
                for task in conn.execute("SELECT * FROM tasks WHERE group_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id", (group_id,)).fetchall():
                    new_task=conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,subtask_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (new_group, task["title"], task["status"], task["priority"], task["due"], task["owner_id"], count, board_order + count, task["subtask_order"], utc_now(), utc_now())).lastrowid;task_map[task["id"]]=new_task
                    conn.execute("""INSERT INTO task_field_values(task_id,field_id,text_value,number_value,option_id,user_id,date_value,boolean_value,link_url,link_label)
                        SELECT ?,field_id,text_value,number_value,option_id,user_id,date_value,boolean_value,link_url,link_label FROM task_field_values WHERE task_id=?""",(new_task,task["id"]))
                    conn.execute("INSERT INTO task_field_tag_values SELECT ?,field_id,option_id,sort_order FROM task_field_tag_values WHERE task_id=?",(new_task,task["id"]))
                    conn.execute("INSERT INTO legacy_task_field_values SELECT ?,field_id,raw_value,reason FROM legacy_task_field_values WHERE task_id=?",(new_task,task["id"]));count += 1
                for old_id,new_id in task_map.items():
                    old=conn.execute("SELECT parent_id FROM tasks WHERE id=?",(old_id,)).fetchone()
                    if old["parent_id"] in task_map:conn.execute("UPDATE tasks SET parent_id=? WHERE id=?",(task_map[old["parent_id"]],new_id))
                for edge in conn.execute("SELECT * FROM task_dependencies WHERE deleted_at IS NULL").fetchall():
                    if edge["predecessor_id"] in task_map and edge["successor_id"] in task_map:conn.execute("INSERT INTO task_dependencies(predecessor_id,successor_id,created_by,created_at) VALUES (?,?,?,?)",(task_map[edge["predecessor_id"]],task_map[edge["successor_id"]],user["id"],utc_now()))
                conn.execute("UPDATE boards SET version=version+1 WHERE id=?", (source["board_id"],))
                self._activity(conn, source["board_id"], "group", new_group, user["id"], "group.copied", {"source_id": group_id, "tasks": count})
            return {"id": new_group, "version": 1}
        finally: conn.close()

    def move_group(self, user, group_id, data):
        reject_unknown(data, {"version", "board_version", "target_index"}); version = require_version(data); board_version = require_int(data.get("board_version"), "board_version", minimum=1); target = require_int(data.get("target_index"), "target_index", minimum=0); conn = self._db()
        try:
            with transaction(conn):
                group = self._group_context(conn, user["id"], group_id, write=True, require_active=True)
                ids = [row["id"] for row in conn.execute("SELECT id FROM groups_ WHERE board_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id", (group["board_id"],))]
                if target >= len(ids): raise ApiError(422, "VALIDATION_ERROR", "target_index is out of range")
                if group["version"] != version or group["board_version"] != board_version: raise ApiError(409, "VERSION_CONFLICT", "分组排序版本冲突")
                old = ids.index(group_id); ids.pop(old); ids.insert(target, group_id)
                for index, gid in enumerate(ids): conn.execute("UPDATE groups_ SET sort_order=?,version=version+1 WHERE id=?", (index, gid))
                conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?", (group["board_id"], board_version))
                self._activity(conn, group["board_id"], "group", group_id, user["id"], "group.moved", {"from_index": old, "to_index": target})
                moved = conn.execute("SELECT version FROM groups_ WHERE id=?", (group_id,)).fetchone()
            return {"id": group_id, "version": moved["version"], "board_version": board_version + 1}
        finally: conn.close()

    def group_command(self, user, group_id, command, data):
        if command not in {"archive", "unarchive", "restore"}: raise ApiError(404, "NOT_FOUND", "接口不存在")
        reject_unknown(data, {"version"}); version = require_version(data); conn = self._db()
        try:
            with transaction(conn):
                group = self._group_context(conn, user["id"], group_id, write=True)
                if group["board_deleted_at"]: raise ApiError(409, "PARENT_DELETED", "请先恢复父看板")
                if command == "restore":
                    if not group["deleted_at"]: raise ApiError(409, "INVALID_STATE", "分组不在回收站")
                    order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM groups_ WHERE board_id=?", (group["board_id"],)).fetchone()[0]; changes="deleted_at=NULL,deleted_by=NULL,sort_order=?"; args=(order,)
                elif command == "archive":
                    if group["deleted_at"] or group["archived_at"]: raise ApiError(409, "INVALID_STATE", "分组当前状态不可归档")
                    changes="archived_at=?,archived_by=?"; args=(utc_now(),user["id"])
                else:
                    if group["deleted_at"] or not group["archived_at"]: raise ApiError(409, "INVALID_STATE", "分组当前状态不可取消归档")
                    changes="archived_at=NULL,archived_by=NULL"; args=()
                cursor=conn.execute(f"UPDATE groups_ SET {changes},version=version+1 WHERE id=? AND version=?",(*args,group_id,version));self._conflict(cursor,"分组版本冲突")
                self._activity(conn,group["board_id"],"group",group_id,user["id"],f"group.{COMMAND_ACTION[command]}",{})
            return {"id":group_id,"version":version+1}
        finally: conn.close()

    def delete_group(self,user,group_id,data):
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                group=self._group_context(conn,user["id"],group_id,write=True)
                if group["deleted_at"]:raise ApiError(409,"INVALID_STATE","分组已在回收站")
                count=conn.execute("SELECT COUNT(*) FROM tasks WHERE group_id=?",(group_id,)).fetchone()[0]
                cursor=conn.execute("UPDATE groups_ SET deleted_at=?,deleted_by=?,version=version+1 WHERE id=? AND version=?",(utc_now(),user["id"],group_id,version));self._conflict(cursor,"分组版本冲突")
                self._activity(conn,group["board_id"],"group",group_id,user["id"],"group.deleted",{"affected_descendants":count})
            return {"id":group_id,"version":version+1}
        finally:conn.close()

    # Task lifecycle -----------------------------------------------------
    def _validated_task_fields(self, data, *, create=False):
        fields={}
        if create or "title" in data: fields["title"]=require_text(data,"title",max_length=500)
        if "status" in data: fields["status"]=validate_choice(data["status"],"status",STATUSES)
        elif create: fields["status"]="待开始"
        if "priority" in data: fields["priority"]=validate_choice(data["priority"],"priority",PRIORITIES)
        elif create: fields["priority"]="中"
        if "due" in data: fields["due"]=validate_due(data["due"])
        elif create: fields["due"]="未设置"
        if "owner_id" in data:
            if data["owner_id"] is not None and not isinstance(data["owner_id"],str): raise ApiError(422,"VALIDATION_ERROR","owner_id is invalid")
            fields["owner_id"]=data["owner_id"]
        if "description" in data: fields["description"]=require_text(data,"description",max_length=10000,allow_empty=True)
        elif create: fields["description"]=""
        return fields

    @staticmethod
    def _validate_owner(conn, workspace_id, owner_id):
        if owner_id is None:return
        row=conn.execute("""SELECT 1 FROM users u JOIN workspace_memberships wm ON wm.user_id=u.id
            WHERE u.id=? AND u.is_active=1 AND wm.workspace_id=?""",(owner_id,workspace_id)).fetchone()
        if not row:raise ApiError(422,"INVALID_OWNER","负责人不是当前工作区有效成员")

    def create_task(self,user,group_id,data):
        reject_unknown(data,{"title","status","priority","due","owner_id","description","parent_id"});fields=self._validated_task_fields(data,create=True);parent_id=data.get("parent_id")
        if parent_id is not None: parent_id=require_int(parent_id,"parent_id",minimum=1)
        conn=self._db()
        try:
            with transaction(conn):
                group=self._group_context(conn,user["id"],group_id,write=True,require_active=True);owner=fields.get("owner_id",user["id"]);self._validate_owner(conn,group["workspace_id"],owner)
                order=conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tasks WHERE group_id=?",(group_id,)).fetchone()[0];board_order=conn.execute("SELECT COALESCE(MAX(t.board_order),-1)+1 FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?",(group["board_id"],)).fetchone()[0]
                subtask_order=conn.execute("SELECT COALESCE(MAX(subtask_order),-1)+1 FROM tasks WHERE parent_id IS ?",(parent_id,)).fetchone()[0]
                cursor=conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,description,sort_order,board_order,parent_id,subtask_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(group_id,fields["title"],fields["status"],fields["priority"],fields["due"],owner,fields["description"],order,board_order,parent_id,subtask_order,utc_now(),utc_now()));tid=cursor.lastrowid
                now=utc_now();conn.execute("INSERT INTO task_subscriptions(task_id,user_id,state,source,version,created_at,updated_at) VALUES (?,?, 'following','creator',1,?,?)",(tid,user["id"],now,now))
                created=self._task_context(conn,user["id"],tid,write=True)
                self._validate_parent(conn,created,parent_id)
                for key,value in (("status",fields["status"]),("priority",fields["priority"]),("owner",owner),("due",fields["due"])):
                    field=conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND system_key=?",(group["board_id"],key)).fetchone()
                    if key in {"status","priority"}: value=conn.execute("SELECT id FROM field_options WHERE field_id=? AND label=?",(field["id"],value)).fetchone()["id"]
                    self._write_field_value(conn,created,field,value)
                conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(group_id,));self._activity(conn,group["board_id"],"task",tid,user["id"],"task.created",{"title":fields["title"],"parent_id":parent_id},task_id=tid)
            return {"id":tid,"version":1}
        finally:conn.close()

    def update_task(self,user,task_id,data):
        reject_unknown(data,{"version","title","status","priority","due","owner_id","description","field_values"});version=require_version(data);fields=self._validated_task_fields(data)
        field_values=data.get("field_values",{})
        if not isinstance(field_values,dict):raise ApiError(422,"VALIDATION_ERROR","field_values must be an object")
        if not fields and not field_values:raise ApiError(422,"VALIDATION_ERROR","没有可更新字段")
        conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                if "owner_id" in fields:self._validate_owner(conn,task["workspace_id"],fields["owner_id"])
                dynamic={}
                for raw_id,value in field_values.items():
                    try: field_id=int(raw_id)
                    except (TypeError,ValueError): raise ApiError(422,"VALIDATION_ERROR","字段 ID 无效")
                    field=conn.execute("SELECT * FROM field_definitions WHERE id=? AND board_id=? AND deleted_at IS NULL AND is_active=1",(field_id,task["board_id"])).fetchone()
                    if not field: raise ApiError(422,"FIELD_NOT_EDITABLE","字段不存在或不可编辑")
                    alias={"status":"status","priority":"priority","owner":"owner_id","due":"due"}.get(field["system_key"])
                    if alias and alias in fields: raise ApiError(422,"DUPLICATE_FIELD_INPUT","旧字段别名与动态值不能同时提交")
                    dynamic[field_id]=(field,value)
                if task["version"]!=version: raise ApiError(409,"VERSION_CONFLICT","任务已被其他成员更新")
                for field_id,(field,value) in dynamic.items():
                    self._write_field_value(conn,task,field,value)
                    projection={"status":"status","priority":"priority","owner":"owner_id","due":"due"}.get(field["system_key"])
                    if projection:
                        projected=value
                        if field["system_key"] in {"status","priority"} and value is not None:
                            option=conn.execute("SELECT label FROM field_options WHERE id=? AND field_id=?",(value,field_id)).fetchone();projected=option["label"]
                        if field["system_key"]=="due" and not value: projected="未设置"
                        conn.execute(f"UPDATE tasks SET {projection}=? WHERE id=?",(projected,task_id))
                if fields:
                    if "status" in fields or "priority" in fields:
                        for alias in set(fields)&{"status","priority"}:
                            field=conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND system_key=?",(task["board_id"],alias)).fetchone()
                            option=conn.execute("SELECT id FROM field_options WHERE field_id=? AND label=?",(field["id"],fields[alias])).fetchone()
                            self._write_field_value(conn,task,field,option["id"])
                    for alias,key in (("owner_id","owner"),("due","due")):
                        if alias in fields:
                            field=conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND system_key=?",(task["board_id"],key)).fetchone();self._write_field_value(conn,task,field,fields[alias])
                    conn.execute(f"UPDATE tasks SET {','.join(f'{k}=?' for k in fields)} WHERE id=?",(*fields.values(),task_id))
                cursor=conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(utc_now(),task_id,version));self._conflict(cursor,"任务已被其他成员更新")
                self._activity(conn,task["board_id"],"task",task_id,user["id"],"task.field_values.updated",{"legacy_fields":sorted(fields),"field_ids":sorted(dynamic)},task_id=task_id)
            return {"id":task_id,"version":version+1}
        finally:conn.close()

    def batch_tasks(self,user,workspace_id,data):
        reject_unknown(data,{"operation","items","changes","target_group_id","target_group_version"});operation=data.get("operation")
        if operation not in {"update","move","archive","delete","assign"}:raise ApiError(422,"VALIDATION_ERROR","operation is invalid")
        items=data.get("items")
        if not isinstance(items,list) or not 1<=len(items)<=100:raise ApiError(422,"VALIDATION_ERROR","items must contain 1 to 100 tasks")
        normalized=[];seen=set()
        for item in items:
            if not isinstance(item,dict) or set(item)!={"id","version"}:raise ApiError(422,"VALIDATION_ERROR","each item requires id and version")
            task_id=require_int(item["id"],"id",minimum=1);version=require_int(item["version"],"version",minimum=1)
            if task_id in seen:raise ApiError(422,"DUPLICATE_TASK","task IDs must be unique")
            seen.add(task_id);normalized.append((task_id,version))
        changes=data.get("changes")
        if operation in {"update","assign"}:
            if not isinstance(changes,dict):raise ApiError(422,"VALIDATION_ERROR","changes must be an object")
            allowed={"title","status","priority","due","owner_id","description"} if operation=="update" else {"owner_id"}
            reject_unknown(changes,allowed)
            fields=self._validated_task_fields(changes)
            if not fields:raise ApiError(422,"VALIDATION_ERROR","changes cannot be empty")
        else:
            if changes is not None:raise ApiError(422,"VALIDATION_ERROR","changes is not allowed for this operation")
            fields={}
        target_group_id=target_group_version=None
        if operation=="move":
            target_group_id=require_int(data.get("target_group_id"),"target_group_id",minimum=1);target_group_version=require_int(data.get("target_group_version"),"target_group_version",minimum=1)
        elif data.get("target_group_id") is not None or data.get("target_group_version") is not None:raise ApiError(422,"VALIDATION_ERROR","target group is only valid for move")
        conn=self._db()
        try:
            with transaction(conn):
                role=self._workspace_role(conn,user["id"],workspace_id,write=True);del role
                tasks=[]
                for task_id,version in normalized:
                    task=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                    if task["workspace_id"]!=workspace_id:raise ApiError(403,"RESOURCE_FORBIDDEN","资源不存在或不可访问")
                    if task["version"]!=version:raise ApiError(409,"VERSION_CONFLICT","批量操作包含过期任务版本")
                    tasks.append(task)
                target=None
                if operation=="move":
                    target=self._group_context(conn,user["id"],target_group_id,write=True,require_active=True)
                    if target["workspace_id"]!=workspace_id or target["version"]!=target_group_version:raise ApiError(409,"VERSION_CONFLICT","目标分组版本冲突")
                    if any(task["board_id"]!=target["board_id"] for task in tasks):raise ApiError(422,"CROSS_BOARD_MOVE","批量移动只能在同一看板内完成")
                if operation in {"archive","delete"}:
                    selected=set(seen)
                    for task in tasks:
                        child=conn.execute("SELECT id FROM tasks WHERE parent_id=? AND deleted_at IS NULL AND archived_at IS NULL AND id NOT IN ("+','.join('?' for _ in selected)+") LIMIT 1",(task["id"],*selected)).fetchone()
                        if child:raise ApiError(409,"ACTIVE_SUBTASKS","批量操作必须同时包含全部活跃子任务")
                if "owner_id" in fields:self._validate_owner(conn,workspace_id,fields["owner_id"])
                batch_key=secrets.token_hex(12);stamp=utc_now();results=[]
                move_start=conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tasks WHERE group_id=?",(target_group_id,)).fetchone()[0] if target else None
                ordered=sorted(tasks,key=lambda task:self._task_depth(conn,task["id"]),reverse=True) if operation in {"archive","delete"} else tasks
                for index,task in enumerate(ordered):
                    task_id=task["id"]
                    if operation in {"update","assign"}:
                        for alias in set(fields)&{"status","priority"}:
                            field=conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND system_key=?",(task["board_id"],alias)).fetchone();option=conn.execute("SELECT id FROM field_options WHERE field_id=? AND label=?",(field["id"],fields[alias])).fetchone();self._write_field_value(conn,task,field,option["id"])
                        for alias,key in (("owner_id","owner"),("due","due")):
                            if alias in fields:
                                field=conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND system_key=?",(task["board_id"],key)).fetchone();self._write_field_value(conn,task,field,fields[alias])
                        sql=','.join(f'{key}=?' for key in fields);args=(*fields.values(),stamp)
                        conn.execute(f"UPDATE tasks SET {sql},updated_at=?,version=version+1 WHERE id=?",(*args,task_id));action="task.batch_assigned" if operation=="assign" else "task.batch_updated";details={"fields":sorted(fields)}
                    elif operation=="move":
                        conn.execute("UPDATE tasks SET group_id=?,sort_order=?,updated_at=?,version=version+1 WHERE id=?",(target_group_id,move_start+index,stamp,task_id));action="task.batch_moved";details={"source_group_id":task["group_id"],"target_group_id":target_group_id}
                    elif operation=="archive":
                        conn.execute("UPDATE tasks SET archived_at=?,archived_by=?,updated_at=?,version=version+1 WHERE id=?",(stamp,user["id"],stamp,task_id));action="task.batch_archived";details={}
                    else:
                        conn.execute("UPDATE tasks SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=?",(stamp,user["id"],stamp,task_id));action="task.batch_deleted";details={}
                    details.update({"batch_key":batch_key,"batch_size":len(tasks)});self._activity(conn,task["board_id"],"task",task_id,user["id"],action,details,task_id=task_id);results.append({"id":task_id,"version":task["version"]+1})
                if target:
                    source_groups={task["group_id"] for task in tasks};conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(target_group_id,))
                    for source_group in source_groups-{target_group_id}:conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(source_group,))
            return {"operation":operation,"batch_key":batch_key,"updated":len(results),"items":sorted(results,key=lambda item:item["id"])}
        finally:conn.close()

    def copy_task(self,user,task_id,data):
        reject_unknown(data,{"title"});conn=self._db()
        try:
            with transaction(conn):
                source=self._task_context(conn,user["id"],task_id,write=True,require_active=True);title=require_text({"title":data.get("title",f"{source['title']} 副本")},"title",max_length=500);order=conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tasks WHERE group_id=?",(source["group_id"],)).fetchone()[0];board_order=conn.execute("SELECT COALESCE(MAX(t.board_order),-1)+1 FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?",(source["board_id"],)).fetchone()[0]
                cursor=conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(source["group_id"],title,source["status"],source["priority"],source["due"],source["owner_id"],order,board_order,utc_now(),utc_now()));tid=cursor.lastrowid
                conn.execute("""INSERT INTO task_field_values(task_id,field_id,text_value,number_value,option_id,user_id,date_value,boolean_value,link_url,link_label)
                    SELECT ?,field_id,text_value,number_value,option_id,user_id,date_value,boolean_value,link_url,link_label FROM task_field_values WHERE task_id=?""",(tid,task_id))
                conn.execute("INSERT INTO task_field_tag_values SELECT ?,field_id,option_id,sort_order FROM task_field_tag_values WHERE task_id=?",(tid,task_id))
                conn.execute("INSERT INTO legacy_task_field_values SELECT ?,field_id,raw_value,reason FROM legacy_task_field_values WHERE task_id=?",(tid,task_id))
                conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(source["group_id"],));self._activity(conn,source["board_id"],"task",tid,user["id"],"task.copied",{"source_id":task_id},task_id=tid)
            return {"id":tid,"version":1}
        finally:conn.close()

    def move_task(self,user,task_id,data):
        reject_unknown(data,{"version","source_group_version","target_group_version","target_group_id","target_index"});version=require_version(data);sgv=require_int(data.get("source_group_version"),"source_group_version",minimum=1);target_group=require_int(data.get("target_group_id"),"target_group_id",minimum=1);target_index=require_int(data.get("target_index"),"target_index",minimum=0);tgv=require_int(data.get("target_group_version"),"target_group_version",minimum=1);conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True);target=self._group_context(conn,user["id"],target_group,write=True,require_active=True)
                if target["board_id"]!=task["board_id"]:raise ApiError(422,"CROSS_BOARD_MOVE","任务只能在同一看板内移动")
                source_id=task["group_id"]
                if task["version"]!=version or task["group_version"]!=sgv or target["version"]!=tgv:raise ApiError(409,"VERSION_CONFLICT","任务移动版本冲突")
                source_ids=[r["id"] for r in conn.execute("SELECT id FROM tasks WHERE group_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id",(source_id,))];source_index=source_ids.index(task_id);source_ids.remove(task_id)
                target_ids=source_ids if source_id==target_group else [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE group_id=? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY sort_order,id",(target_group,))]
                if target_index>len(target_ids) or (source_id==target_group and target_index>=len(target_ids)+1):raise ApiError(422,"VALIDATION_ERROR","target_index is out of range")
                target_ids.insert(target_index,task_id)
                if source_id!=target_group:
                    for index,tid in enumerate(source_ids):conn.execute("UPDATE tasks SET sort_order=?,version=version+1 WHERE id=?",(index,tid))
                for index,tid in enumerate(target_ids):conn.execute("UPDATE tasks SET group_id=?,sort_order=?,version=version+1 WHERE id=?",(target_group,index,tid))
                conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(source_id,))
                if target_group!=source_id:conn.execute("UPDATE groups_ SET version=version+1 WHERE id=?",(target_group,))
                self._activity(conn,task["board_id"],"task",task_id,user["id"],"task.moved",{"source_group_id":source_id,"target_group_id":target_group,"from_index":source_index,"to_index":target_index},task_id=task_id)
                moved=conn.execute("SELECT version FROM tasks WHERE id=?",(task_id,)).fetchone()
            return {"id":task_id,"version":moved["version"]}
        finally:conn.close()

    def set_task_parent(self,user,task_id,data):
        reject_unknown(data,{"version","board_version","parent_id","position"});version=require_version(data);board_version=require_int(data.get("board_version"),"board_version",minimum=1);parent_id=data.get("parent_id")
        if parent_id is not None: parent_id=require_int(parent_id,"parent_id",minimum=1)
        position=require_int(data.get("position",0),"position",minimum=0);conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                if task["version"]!=version or task["board_version"]!=board_version: raise ApiError(409,"VERSION_CONFLICT","任务层级版本冲突")
                self._validate_parent(conn,task,parent_id)
                old_parent=task["parent_id"]
                if parent_id is None:
                    if position!=0: raise ApiError(422,"VALIDATION_ERROR","detached task position must be 0")
                    siblings=[]
                else:
                    siblings=[row["id"] for row in conn.execute("""SELECT t.id FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE t.parent_id=?
                        AND g.board_id=? AND t.deleted_at IS NULL AND t.archived_at IS NULL AND t.id<>? ORDER BY t.subtask_order,t.id""",(parent_id,task["board_id"],task_id))]
                    if position>len(siblings): raise ApiError(422,"VALIDATION_ERROR","position is out of range")
                    siblings.insert(position,task_id)
                    for index,candidate in enumerate(siblings): conn.execute("UPDATE tasks SET subtask_order=? WHERE id=?",(index,candidate))
                if old_parent is not None and old_parent!=parent_id:
                    old=[row["id"] for row in conn.execute("SELECT id FROM tasks WHERE parent_id=? AND id<>? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY subtask_order,id",(old_parent,task_id))]
                    for index,candidate in enumerate(old):conn.execute("UPDATE tasks SET subtask_order=? WHERE id=?",(index,candidate))
                cursor=conn.execute("UPDATE tasks SET parent_id=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(parent_id,utc_now(),task_id,version));self._conflict(cursor,"任务层级版本冲突")
                board_cursor=conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(task["board_id"],board_version));self._conflict(board_cursor,"任务层级版本冲突")
                self._activity(conn,task["board_id"],"task",task_id,user["id"],"task.parent_changed",{"from_parent_id":task["parent_id"],"to_parent_id":parent_id,"position":position},task_id=task_id)
            return {"id":task_id,"version":version+1,"board_version":board_version+1,"parent_id":parent_id,"position":position}
        finally:conn.close()

    @staticmethod
    def _dependency_cycle(conn,predecessor_id,successor_id):
        return bool(conn.execute("""WITH RECURSIVE reach(id) AS (
            SELECT successor_id FROM task_dependencies WHERE predecessor_id=? AND deleted_at IS NULL
            UNION SELECT d.successor_id FROM task_dependencies d JOIN reach r ON d.predecessor_id=r.id WHERE d.deleted_at IS NULL)
            SELECT 1 FROM reach WHERE id=? LIMIT 1""",(successor_id,predecessor_id)).fetchone())

    def _set_due_projection(self,conn,task,due):
        field=conn.execute("SELECT * FROM field_definitions WHERE board_id=? AND system_key='due' AND deleted_at IS NULL",(task["board_id"],)).fetchone()
        if field:self._write_field_value(conn,task,field,due)
        conn.execute("UPDATE tasks SET due=? WHERE id=?",(due,task["id"]))

    def create_dependency(self,user,successor_id,data):
        reject_unknown(data,{"version","predecessor_id","predecessor_version","due_policy"});version=require_version(data);predecessor_id=require_int(data.get("predecessor_id"),"predecessor_id",minimum=1);predecessor_version=require_int(data.get("predecessor_version"),"predecessor_version",minimum=1);policy=validate_choice(data.get("due_policy","none"),"due_policy",{"none","push_successor_once"});propagate=policy=="push_successor_once"
        if not isinstance(propagate,bool): raise ApiError(422,"VALIDATION_ERROR","propagate_due must be boolean")
        conn=self._db()
        try:
            with transaction(conn):
                successor=self._task_context(conn,user["id"],successor_id,write=True,require_active=True);predecessor=self._task_context(conn,user["id"],predecessor_id,require_active=True)
                if successor_id==predecessor_id: raise ApiError(422,"DEPENDENCY_SELF","任务不能依赖自身")
                if successor["board_id"]!=predecessor["board_id"]: raise ApiError(422,"DEPENDENCY_CROSS_BOARD","依赖仅限同一看板")
                if successor["version"]!=version or predecessor["version"]!=predecessor_version: raise ApiError(409,"VERSION_CONFLICT","依赖操作版本冲突")
                existing=conn.execute("SELECT * FROM task_dependencies WHERE predecessor_id=? AND successor_id=?",(predecessor_id,successor_id)).fetchone()
                if existing and not existing["deleted_at"]: raise ApiError(409,"DEPENDENCY_DUPLICATE","依赖已经存在")
                if self._dependency_cycle(conn,predecessor_id,successor_id): raise ApiError(422,"DEPENDENCY_CYCLE","依赖会形成循环")
                stamp=utc_now()
                if existing:
                    conn.execute("UPDATE task_dependencies SET deleted_at=NULL,deleted_by=NULL,version=version+1,created_by=?,created_at=? WHERE id=?",(user["id"],stamp,existing["id"]));dependency_id=existing["id"];dependency_version=existing["version"]+1
                else:
                    cursor=conn.execute("INSERT INTO task_dependencies(predecessor_id,successor_id,created_by,created_at) VALUES (?,?,?,?)",(predecessor_id,successor_id,user["id"],stamp));dependency_id=cursor.lastrowid;dependency_version=1
                date_result={"status":"disabled"};before=successor["due"]
                if propagate:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",predecessor["due"] or ""): date_result={"status":"no-op","reason":"predecessor_has_no_valid_due"}
                    elif successor["due"]=="未设置" or (re.fullmatch(r"\d{4}-\d{2}-\d{2}",successor["due"] or "") and successor["due"]<predecessor["due"]):
                        self._set_due_projection(conn,successor,predecessor["due"]);date_result={"status":"pushed","before":before,"after":predecessor["due"]}
                    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}",successor["due"] or ""): date_result={"status":"no-op","reason":"successor_already_not_earlier"}
                    else: date_result={"status":"no-op","reason":"successor_has_legacy_due"}
                cursor=conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(stamp,successor_id,version));self._conflict(cursor,"依赖操作版本冲突")
                predecessor_cursor=conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(stamp,predecessor_id,predecessor_version));self._conflict(predecessor_cursor,"依赖操作版本冲突")
                self._activity(conn,successor["board_id"],"task",successor_id,user["id"],"task.dependency_created",{"dependency_id":dependency_id,"predecessor_id":predecessor_id,"due_policy":policy,"date_result":date_result},task_id=successor_id)
            return {"id":dependency_id,"version":dependency_version,"task_version":version+1,"predecessor_version":predecessor_version+1,"date_result":date_result}
        finally:conn.close()

    def delete_dependency(self,user,successor_id,dependency_id,data):
        reject_unknown(data,{"version","dependency_version","predecessor_version"});version=require_version(data);dependency_version=require_int(data.get("dependency_version"),"dependency_version",minimum=1);predecessor_version=require_int(data.get("predecessor_version"),"predecessor_version",minimum=1);conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],successor_id,write=True,require_active=True)
                row=conn.execute("SELECT * FROM task_dependencies WHERE id=? AND successor_id=? AND deleted_at IS NULL",(dependency_id,successor_id)).fetchone()
                if not row: raise ApiError(404,"DEPENDENCY_NOT_FOUND","依赖不存在")
                predecessor=self._task_context(conn,user["id"],row["predecessor_id"],write=True,require_active=True)
                if task["version"]!=version or row["version"]!=dependency_version or predecessor["version"]!=predecessor_version: raise ApiError(409,"VERSION_CONFLICT","依赖删除版本冲突")
                cursor=conn.execute("UPDATE task_dependencies SET deleted_at=?,deleted_by=?,version=version+1 WHERE id=? AND version=?",(utc_now(),user["id"],dependency_id,dependency_version));self._conflict(cursor,"依赖删除版本冲突")
                stamp=utc_now();conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=?",(stamp,successor_id));conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(stamp,row["predecessor_id"],predecessor_version));self._activity(conn,task["board_id"],"task",successor_id,user["id"],"task.dependency_deleted",{"dependency_id":dependency_id,"predecessor_id":row["predecessor_id"]},task_id=successor_id)
            return {"id":dependency_id,"version":dependency_version+1,"task_version":version+1,"predecessor_version":predecessor_version+1}
        finally:conn.close()

    def kanban_move_task(self,user,task_id,data):
        reject_unknown(data,{"version","board_version","field_id","value","anchor_task_id","placement"});version=require_version(data);board_version=require_int(data.get("board_version"),"board_version",minimum=1);field_id=require_int(data.get("field_id"),"field_id",minimum=1);placement=validate_choice(data.get("placement","after"),"placement",{"before","after"});anchor_id=data.get("anchor_task_id")
        if anchor_id is not None: anchor_id=require_int(anchor_id,"anchor_task_id",minimum=1)
        value=data.get("value");conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True);field=conn.execute("SELECT * FROM field_definitions WHERE id=? AND board_id=? AND deleted_at IS NULL AND is_active=1",(field_id,task["board_id"])).fetchone()
                if not field or field["field_type"] not in {"status","person"}: raise ApiError(422,"FIELD_NOT_EDITABLE","Kanban 字段必须是可用的状态或人员字段")
                board=conn.execute("SELECT version FROM boards WHERE id=?",(task["board_id"],)).fetchone()
                if task["version"]!=version or board["version"]!=board_version: raise ApiError(409,"VERSION_CONFLICT","Kanban 顺序版本冲突")
                anchor=None
                if anchor_id is not None:
                    if anchor_id==task_id: raise ApiError(422,"VALIDATION_ERROR","任务不能锚定自身")
                    anchor=self._task_context(conn,user["id"],anchor_id,require_active=True)
                    if anchor["board_id"]!=task["board_id"]: raise ApiError(422,"CROSS_BOARD_MOVE","锚点任务不属于当前看板")
                    anchor_value=self._task_values(conn,anchor_id).get(str(field_id))
                    if anchor_value!=value: raise ApiError(409,"VERSION_CONFLICT","锚点已不在目标 Kanban 列")
                self._write_field_value(conn,task,field,value)
                projection={"status":"status","owner":"owner_id"}.get(field["system_key"])
                if projection:
                    projected=value
                    if field["system_key"]=="status" and value is not None: projected=conn.execute("SELECT label FROM field_options WHERE id=? AND field_id=?",(value,field_id)).fetchone()["label"]
                    if field["system_key"]=="status" and value is None: projected="未设置"
                    conn.execute(f"UPDATE tasks SET {projection}=? WHERE id=?",(projected,task_id))
                rows=conn.execute("""SELECT t.id FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id=?
                    AND t.deleted_at IS NULL AND t.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL
                    ORDER BY t.board_order,t.id""",(task["board_id"],)).fetchall();ordered=[row["id"] for row in rows if row["id"]!=task_id]
                if anchor_id is not None:
                    target=ordered.index(anchor_id)+(1 if placement=="after" else 0)
                else:
                    lane=[]
                    for candidate in ordered:
                        if self._task_values(conn,candidate).get(str(field_id))==value: lane.append(candidate)
                    target=ordered.index(lane[-1])+1 if lane else len(ordered)
                ordered.insert(target,task_id)
                for index,candidate in enumerate(ordered): conn.execute("UPDATE tasks SET board_order=? WHERE id=?",(index,candidate))
                cursor=conn.execute("UPDATE tasks SET updated_at=?,version=version+1 WHERE id=? AND version=?",(utc_now(),task_id,version));self._conflict(cursor,"任务已被其他成员更新")
                board_cursor=conn.execute("UPDATE boards SET version=version+1 WHERE id=? AND version=?",(task["board_id"],board_version));self._conflict(board_cursor,"Kanban 顺序版本冲突")
                self._activity(conn,task["board_id"],"task",task_id,user["id"],"task.kanban_moved",{"field_id":field_id,"value":value,"anchor_task_id":anchor_id,"placement":placement},task_id=task_id)
            return {"id":task_id,"version":version+1,"board_version":board_version+1}
        finally:conn.close()

    def task_command(self,user,task_id,command,data):
        if command not in {"archive","unarchive","restore"}:raise ApiError(404,"NOT_FOUND","接口不存在")
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True)
                if task["board_deleted_at"] or task["group_deleted_at"]:raise ApiError(409,"PARENT_DELETED","请先恢复父实体")
                if command=="restore":
                    if not task["deleted_at"]:raise ApiError(409,"INVALID_STATE","任务不在回收站")
                    if task["parent_id"]:
                        parent=conn.execute("SELECT deleted_at,archived_at FROM tasks WHERE id=?",(task["parent_id"],)).fetchone()
                        if not parent or parent["deleted_at"] or parent["archived_at"]: raise ApiError(409,"PARENT_TASK_INACTIVE","请先恢复父任务")
                    order=conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM tasks WHERE group_id=?",(task["group_id"],)).fetchone()[0];changes="deleted_at=NULL,deleted_by=NULL,sort_order=?,updated_at=?";args=(order,utc_now())
                elif command=="archive":
                    if task["deleted_at"] or task["archived_at"]:raise ApiError(409,"INVALID_STATE","任务当前状态不可归档")
                    if conn.execute("SELECT 1 FROM tasks WHERE parent_id=? AND deleted_at IS NULL AND archived_at IS NULL LIMIT 1",(task_id,)).fetchone(): raise ApiError(409,"ACTIVE_SUBTASKS","请先归档或解除活跃子任务")
                    changes="archived_at=?,archived_by=?,updated_at=?";args=(utc_now(),user["id"],utc_now())
                else:
                    if task["deleted_at"] or not task["archived_at"]:raise ApiError(409,"INVALID_STATE","任务当前状态不可取消归档")
                    changes="archived_at=NULL,archived_by=NULL,updated_at=?";args=(utc_now(),)
                cursor=conn.execute(f"UPDATE tasks SET {changes},version=version+1 WHERE id=? AND version=?",(*args,task_id,version));self._conflict(cursor,"任务版本冲突");self._activity(conn,task["board_id"],"task",task_id,user["id"],f"task.{COMMAND_ACTION[command]}",{},task_id=task_id)
            return {"id":task_id,"version":version+1}
        finally:conn.close()

    def delete_task(self,user,task_id,data):
        reject_unknown(data,{"version"});version=require_version(data);conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True)
                if task["deleted_at"]:raise ApiError(409,"INVALID_STATE","任务已在回收站")
                if conn.execute("SELECT 1 FROM tasks WHERE parent_id=? AND deleted_at IS NULL AND archived_at IS NULL LIMIT 1",(task_id,)).fetchone(): raise ApiError(409,"ACTIVE_SUBTASKS","请先删除或解除活跃子任务")
                cursor=conn.execute("UPDATE tasks SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(utc_now(),user["id"],utc_now(),task_id,version));self._conflict(cursor,"任务版本冲突");self._activity(conn,task["board_id"],"task",task_id,user["id"],"task.deleted",{},task_id=task_id)
            return {"id":task_id,"version":version+1}
        finally:conn.close()

    def _mentions(self,conn,task,data):
        raw=data.get("mentions",[])
        if not isinstance(raw,list) or len(raw)>50: raise ApiError(422,"VALIDATION_ERROR","mentions is invalid")
        result=[]; seen=set()
        for item in raw:
            if not isinstance(item,dict) or set(item)-{"type","user_id"}: raise ApiError(422,"VALIDATION_ERROR","mention is invalid")
            kind=item.get("type")
            if kind=="all": key="all"; uid=None
            elif kind=="user" and isinstance(item.get("user_id"),str) and item.get("user_id"):
                uid=item["user_id"]; key=f"user:{uid}"
                if not conn.execute("SELECT 1 FROM workspace_memberships wm JOIN users u ON u.id=wm.user_id WHERE wm.workspace_id=? AND wm.user_id=? AND u.is_active=1",(task["workspace_id"],uid)).fetchone(): raise ApiError(422,"MENTION_INVALID","被提及用户不在工作区")
            else: raise ApiError(422,"VALIDATION_ERROR","mention is invalid")
            if key not in seen: seen.add(key); result.append((key,uid,kind))
        return result

    @staticmethod
    def _subscription_auto_follow(conn,task_id,user_id,source,now):
        row=conn.execute("SELECT state FROM task_subscriptions WHERE task_id=? AND user_id=?",(task_id,user_id)).fetchone()
        if row:return False
        conn.execute("INSERT INTO task_subscriptions(task_id,user_id,state,source,version,created_at,updated_at) VALUES (?,?, 'following',?,1,?,?)",(task_id,user_id,source,now,now));return True

    @staticmethod
    def _collaboration_event(conn,event_key,event_type,task,actor_id,*,comment_id=None,attachment_id=None,recipient_user_id=None,payload=None,now=None):
        conn.execute("""INSERT INTO collaboration_events(event_key,event_type,board_id,task_id,actor_id,comment_id,attachment_id,recipient_user_id,payload_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",(event_key,event_type,task["board_id"],task["id"],actor_id,comment_id,attachment_id,recipient_user_id,
            json.dumps(payload or {},ensure_ascii=False,sort_keys=True,separators=(",",":")),now or utc_now()))

    def create_comment(self,user,task_id,data):
        reject_unknown(data,{"body","parent_id","mentions"});body=require_text(data,"body",max_length=10000);conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True); parent=data.get("parent_id")
                if parent is not None:
                    if isinstance(parent,bool) or not isinstance(parent,int): raise ApiError(422,"VALIDATION_ERROR","parent_id is invalid")
                    p=conn.execute("SELECT task_id,parent_id,deleted_at FROM comments WHERE id=?",(parent,)).fetchone()
                    if not p or p["task_id"]!=task_id or p["parent_id"] is not None or p["deleted_at"]: raise ApiError(422,"INVALID_PARENT_COMMENT","只能回复本任务的有效顶层评论")
                mentions=self._mentions(conn,task,data); now=utc_now()
                cursor=conn.execute("INSERT INTO comments(task_id,user_id,parent_id,body,version,created_at,updated_at) VALUES (?,?,?,?,1,?,?)",(task_id,user["id"],parent,body,now,now));cid=cursor.lastrowid
                conn.execute("INSERT INTO comment_versions(comment_id,version,body,edited_by,created_at) VALUES (?,1,?,?,?)",(cid,body,user["id"],now))
                for key,uid,kind in mentions: conn.execute("INSERT INTO comment_mentions(comment_id,target_key,user_id,mention_type,created_at) VALUES (?,?,?,?,?)",(cid,key,uid,kind,now))
                self._subscription_auto_follow(conn,task_id,user["id"],"comment",now)
                for key,uid,kind in mentions:
                    if uid is not None:self._subscription_auto_follow(conn,task_id,uid,"mention",now)
                self._collaboration_event(conn,f"comment:{cid}:1","comment.created",task,user["id"],comment_id=cid,payload={"parent_id":parent},now=now)
                for key,uid,kind in mentions:self._collaboration_event(conn,f"mention:{cid}:1:add:{key}","mention.added",task,user["id"],comment_id=cid,recipient_user_id=uid,payload={"target":key},now=now)
                self._activity(conn,task["board_id"],"comment",cid,user["id"],"comment.created",{},task_id=task_id)
            return {"id":cid,"version":1}
        finally:conn.close()

    def update_comment(self,user,comment_id,data):
        reject_unknown(data,{"body","mentions","version"}); version=require_version(data); body=require_text(data,"body",max_length=10000); conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT c.*,t.id task_id FROM comments c JOIN tasks t ON t.id=c.task_id WHERE c.id=?",(comment_id,)).fetchone()
                if not row: raise ApiError(404,"COMMENT_NOT_FOUND","评论不存在")
                task=self._task_context(conn,user["id"],row["task_id"],write=True,require_active=True)
                if row["deleted_at"] or row["user_id"]!=user["id"]: raise ApiError(403,"COMMENT_FORBIDDEN","只能编辑自己的有效评论")
                old_mentions={x["target_key"]:(x["user_id"],x["mention_type"]) for x in conn.execute("SELECT target_key,user_id,mention_type FROM comment_mentions WHERE comment_id=?",(comment_id,))};mentions=self._mentions(conn,task,data) if "mentions" in data else [(key,uid,kind) for key,(uid,kind) in old_mentions.items()];new_mentions={key:(uid,kind) for key,uid,kind in mentions}; added=sorted(set(new_mentions)-set(old_mentions)); removed=sorted(set(old_mentions)-set(new_mentions)); now=utc_now(); cursor=conn.execute("UPDATE comments SET body=?,version=version+1,updated_at=?,edited_at=? WHERE id=? AND version=?",(body,now,now,comment_id,version)); self._conflict(cursor,"评论版本冲突")
                conn.execute("INSERT INTO comment_versions(comment_id,version,body,edited_by,created_at) VALUES (?,?,?,?,?)",(comment_id,version+1,body,user["id"],now))
                conn.execute("DELETE FROM comment_mentions WHERE comment_id=?",(comment_id,))
                for key,uid,kind in mentions: conn.execute("INSERT INTO comment_mentions(comment_id,target_key,user_id,mention_type,created_at) VALUES (?,?,?,?,?)",(comment_id,key,uid,kind,now))
                for key in added:
                    uid,_=new_mentions[key]
                    if uid is not None:self._subscription_auto_follow(conn,row["task_id"],uid,"mention",now)
                self._collaboration_event(conn,f"comment:{comment_id}:{version+1}","comment.updated",task,user["id"],comment_id=comment_id,payload={"mentions_added":added,"mentions_removed":removed},now=now)
                for key in added:
                    uid,_=new_mentions[key];self._collaboration_event(conn,f"mention:{comment_id}:{version+1}:add:{key}","mention.added",task,user["id"],comment_id=comment_id,recipient_user_id=uid,payload={"target":key},now=now)
                for key in removed:
                    uid,_=old_mentions[key];self._collaboration_event(conn,f"mention:{comment_id}:{version+1}:remove:{key}","mention.removed",task,user["id"],comment_id=comment_id,recipient_user_id=uid,payload={"target":key},now=now)
                self._activity(conn,task["board_id"],"comment",comment_id,user["id"],"comment.updated",{},task_id=row["task_id"])
            return {"id":comment_id,"version":version+1}
        finally: conn.close()

    def delete_comment(self,user,comment_id,data):
        reject_unknown(data,{"version"}); version=require_version(data); conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM comments WHERE id=?",(comment_id,)).fetchone()
                if not row: raise ApiError(404,"COMMENT_NOT_FOUND","评论不存在")
                task=self._task_context(conn,user["id"],row["task_id"],write=True,require_active=True)
                role=self._workspace_role(conn,user["id"],task["workspace_id"])
                if row["user_id"]!=user["id"] and role!="admin": raise ApiError(403,"COMMENT_FORBIDDEN","无权删除评论")
                if row["version"]!=version: raise ApiError(409,"VERSION_CONFLICT","评论版本冲突")
                if row["deleted_at"]: raise ApiError(403,"COMMENT_FORBIDDEN","评论已删除")
                now=utc_now(); cursor=conn.execute("UPDATE comments SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(now,user["id"],now,comment_id,version)); self._conflict(cursor,"评论版本冲突")
                self._collaboration_event(conn,f"comment:{comment_id}:{version+1}","comment.deleted",task,user["id"],comment_id=comment_id,now=now)
                self._activity(conn,task["board_id"],"comment",comment_id,user["id"],"comment.deleted",{},task_id=row["task_id"])
            return {"id":comment_id,"version":version+1,"deleted":True}
        finally: conn.close()

    def set_subscription(self,user,task_id,data):
        reject_unknown(data,{"subscribed"}); subscribed=data.get("subscribed")
        if not isinstance(subscribed,bool): raise ApiError(422,"VALIDATION_ERROR","subscribed must be boolean")
        conn=self._db()
        try:
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True); now=utc_now()
                desired="following" if subscribed else "opted_out";row=conn.execute("SELECT * FROM task_subscriptions WHERE task_id=? AND user_id=?",(task_id,user["id"])).fetchone();changed=not row or row["state"]!=desired
                if not row:conn.execute("INSERT INTO task_subscriptions(task_id,user_id,state,source,version,created_at,updated_at) VALUES (?,?,?,'manual',1,?,?)",(task_id,user["id"],desired,now,now));current_version=1
                elif changed:current_version=row["version"]+1;conn.execute("UPDATE task_subscriptions SET state=?,source='manual',version=?,updated_at=? WHERE id=?",(desired,current_version,now,row["id"]))
                else:current_version=row["version"]
                if changed:
                    action="subscription.subscribed" if subscribed else "subscription.unsubscribed";self._collaboration_event(conn,f"subscription:{task_id}:{user['id']}:v{current_version}",action,task,user["id"],recipient_user_id=user["id"],payload={"state":desired},now=now);self._activity(conn,task["board_id"],"task",task_id,user["id"],action,{"state":desired},task_id=task_id)
            return {"subscribed":subscribed,"state":desired,"version":current_version,"changed":changed}
        finally: conn.close()

    @staticmethod
    def _attachment_data(data):
        reject_unknown(data,{"name","content_type","content_base64"}); name=unicodedata.normalize("NFC",require_text(data,"name",max_length=180))
        if any(x in name for x in ("/","\\",":","\x00")) or name in {".",".."} or any(ord(x)<32 for x in name): raise ApiError(422,"ATTACHMENT_NAME_INVALID","附件名称无效")
        declared=data.get("content_type"); encoded=data.get("content_base64")
        if not isinstance(encoded,str): raise ApiError(422,"VALIDATION_ERROR","content_base64 is required")
        try: raw=base64.b64decode(encoded,validate=True)
        except (ValueError,base64.binascii.Error): raise ApiError(422,"ATTACHMENT_ENCODING_INVALID","附件编码无效")
        if not raw or len(raw)>1_000_000: raise ApiError(413,"ATTACHMENT_TOO_LARGE","附件必须为 1 byte 到 1 MB")
        suffix=Path(name).suffix.lower(); detected=None
        if raw.startswith(b"\x89PNG\r\n\x1a\n"): detected=(".png","image/png","image")
        elif raw.startswith(b"\xff\xd8\xff"): detected=(".jpg","image/jpeg","image")
        elif raw[:6] in {b"GIF87a",b"GIF89a"}: detected=(".gif","image/gif","image")
        elif raw.startswith(b"%PDF-"): detected=(".pdf","application/pdf","none")
        elif b"\x00" not in raw:
            try:
                decoded=raw.decode("utf-8")
                if any(ord(x)<32 and x not in "\t\r\n" for x in decoded):raise UnicodeDecodeError("utf-8",raw,0,1,"control")
                detected=(".txt","text/plain","text")
            except UnicodeDecodeError: pass
        allowed={detected[0]} if detected and detected[0]!=".jpg" else {".jpg",".jpeg"}
        if not detected or suffix not in allowed or declared!=detected[1]: raise ApiError(415,"ATTACHMENT_TYPE_REJECTED","文件扩展名、MIME 与内容不匹配")
        return name,raw,detected

    def create_attachment(self,user,task_id,data):
        name,raw,(suffix,mime,preview)=self._attachment_data(data); conn=self._db(); storage=secrets.token_hex(24)+suffix; target=self.attachment_root/storage
        try:
            self.attachment_root.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
            with transaction(conn):
                task=self._task_context(conn,user["id"],task_id,write=True,require_active=True)
                if conn.execute("SELECT COUNT(*) FROM attachments WHERE task_id=? AND deleted_at IS NULL",(task_id,)).fetchone()[0]>=20: raise ApiError(422,"ATTACHMENT_LIMIT","每个任务最多 20 个附件")
                now=utc_now(); cur=conn.execute("INSERT INTO attachments(task_id,uploader_id,storage_name,original_name,content_type,size_bytes,sha256,preview_kind,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(task_id,user["id"],storage,name,mime,len(raw),hashlib.sha256(raw).hexdigest(),preview,now,now)); aid=cur.lastrowid
                conn.execute("INSERT INTO collaboration_events(event_key,event_type,board_id,task_id,actor_id,attachment_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",(f"attachment:{aid}:1","attachment.created",task["board_id"],task_id,user["id"],aid,"{}",now)); self._activity(conn,task["board_id"],"task",task_id,user["id"],"attachment.created",{"attachment_id":aid},task_id=task_id)
            return {"id":aid,"version":1,"name":name,"size_bytes":len(raw)}
        except Exception:
            target.unlink(missing_ok=True); raise
        finally: conn.close()

    def attachment_content(self,user,attachment_id,*,preview=False):
        conn=self._db()
        try:
            row=conn.execute("SELECT * FROM attachments WHERE id=? AND deleted_at IS NULL",(attachment_id,)).fetchone()
            if not row: raise ApiError(404,"ATTACHMENT_NOT_FOUND","附件不存在")
            self._task_context(conn,user["id"],row["task_id"],require_active=True)
            if preview and row["preview_kind"]=="none":raise ApiError(415,"ATTACHMENT_PREVIEW_UNAVAILABLE","此附件不支持预览")
            path=(self.attachment_root/row["storage_name"]).resolve()
            if path.parent!=self.attachment_root or not path.is_file(): raise ApiError(404,"ATTACHMENT_CONTENT_MISSING","附件内容不存在")
            return dict(row),path.read_bytes()
        finally: conn.close()

    def delete_attachment(self,user,attachment_id,data):
        reject_unknown(data,{"version"}); version=require_version(data); conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM attachments WHERE id=?",(attachment_id,)).fetchone()
                if not row: raise ApiError(404,"ATTACHMENT_NOT_FOUND","附件不存在")
                task=self._task_context(conn,user["id"],row["task_id"],write=True,require_active=True)
                role=self._workspace_role(conn,user["id"],task["workspace_id"])
                if row["deleted_at"] or (row["uploader_id"]!=user["id"] and role!="admin"): raise ApiError(403,"ATTACHMENT_FORBIDDEN","无权删除附件")
                now=utc_now(); cur=conn.execute("UPDATE attachments SET deleted_at=?,deleted_by=?,updated_at=?,version=version+1 WHERE id=? AND version=?",(now,user["id"],now,attachment_id,version)); self._conflict(cur,"附件版本冲突")
                self._collaboration_event(conn,f"attachment:{attachment_id}:{version+1}","attachment.deleted",task,user["id"],attachment_id=attachment_id,now=now);self._activity(conn,task["board_id"],"task",row["task_id"],user["id"],"attachment.deleted",{"attachment_id":attachment_id},task_id=row["task_id"])
            return {"id":attachment_id,"version":version+1,"deleted":True}
        finally: conn.close()

    # I12 notifications, search, realtime and audit ---------------------
    @staticmethod
    def _page(value, name, default, maximum):
        if value is None:return default
        try:value=int(value)
        except (TypeError,ValueError):raise ApiError(422,"VALIDATION_ERROR",f"{name} must be an integer")
        if value<0 or value>maximum:raise ApiError(422,"VALIDATION_ERROR",f"{name} is out of range")
        return value

    def process_notifications_once(self, *, now=None, batch_size=200):
        """Deterministic, injectable notification projection; safe to call on every read."""
        now=now or utc_now();batch_size=self._page(batch_size,"batch_size",200,500);conn=self._db()
        task_actions={"task.created","task.updated","task.field_values.updated","task.moved","task.kanban_moved","task.parent_changed","task.dependency_created","task.dependency_deleted","task.archived","task.unarchived","task.restored","task.batch_updated","task.batch_assigned","task.batch_moved","task.batch_archived"}
        try:
            with transaction(conn):
                cursor=conn.execute("SELECT last_event_id FROM event_consumers WHERE consumer_key='collaboration_notifications'").fetchone()[0]
                rows=conn.execute("SELECT * FROM collaboration_events WHERE id>? ORDER BY id LIMIT ?",(cursor,batch_size)).fetchall()
                for event in rows:
                    recipients=set()
                    if event["recipient_user_id"]:recipients.add(event["recipient_user_id"])
                    if event["event_type"]!="mention.removed":
                        recipients.update(row[0] for row in conn.execute("SELECT user_id FROM task_subscriptions WHERE task_id=? AND state='following'",(event["task_id"],)))
                    for uid in recipients-{event["actor_id"]}:
                        conn.execute("""INSERT OR IGNORE INTO notifications(recipient_user_id,event_key,kind,actor_user_id,workspace_id,board_id,task_id,comment_id,created_at)
                            SELECT ?,?,?,?,b.workspace_id,?,?,?,? FROM boards b WHERE b.id=?""",(uid,event["event_key"],event["event_type"],event["actor_id"],event["board_id"],event["task_id"],event["comment_id"],event["created_at"],event["board_id"]))
                if rows:conn.execute("UPDATE event_consumers SET last_event_id=?,updated_at=? WHERE consumer_key='collaboration_notifications'",(rows[-1]["id"],now))
                cursor=conn.execute("SELECT last_event_id FROM event_consumers WHERE consumer_key='activity_notifications'").fetchone()[0]
                rows=conn.execute("SELECT a.*,b.workspace_id FROM activity a JOIN boards b ON b.id=a.board_id WHERE a.id>? ORDER BY a.id LIMIT ?",(cursor,batch_size)).fetchall()
                for event in rows:
                    if event["task_id"] and event["action_code"] in task_actions:
                        for sub in conn.execute("SELECT user_id FROM task_subscriptions WHERE task_id=? AND state='following' AND user_id<>?",(event["task_id"],event["user_id"])):
                            conn.execute("""INSERT OR IGNORE INTO notifications(recipient_user_id,event_key,kind,actor_user_id,workspace_id,board_id,task_id,created_at)
                                VALUES (?,?,?,?,?,?,?,?)""",(sub[0],f"activity:{event['id']}","task.changed",event["user_id"],event["workspace_id"],event["board_id"],event["task_id"],event["created_at"]))
                if rows:conn.execute("UPDATE event_consumers SET last_event_id=?,updated_at=? WHERE consumer_key='activity_notifications'",(rows[-1]["id"],now))
                today=now[:10]
                for task in conn.execute("""SELECT t.id,t.due,g.board_id,b.workspace_id FROM tasks t JOIN groups_ g ON g.id=t.group_id JOIN boards b ON b.id=g.board_id
                    WHERE t.deleted_at IS NULL AND t.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL AND b.deleted_at IS NULL AND b.archived_at IS NULL
                    AND t.status<>'已完成' AND t.due<>'未设置' AND t.due<=date(?, '+1 day')""",(today,)):
                    kind="task.overdue" if task["due"]<today else "task.due"
                    for sub in conn.execute("SELECT user_id FROM task_subscriptions WHERE task_id=? AND state='following'",(task["id"],)):
                        conn.execute("""INSERT OR IGNORE INTO notifications(recipient_user_id,event_key,kind,workspace_id,board_id,task_id,created_at)
                            VALUES (?,?,?,?,?,?,?)""",(sub[0],f"due:{task['id']}:{task['due']}:{kind}",kind,task["workspace_id"],task["board_id"],task["id"],now))
            return {"processed":True}
        finally:conn.close()

    def notifications(self,user,workspace_id,*,after=0,limit=50):
        self.process_notifications_once();after=self._page(after,"after",0,2_147_483_647);limit=self._page(limit,"limit",50,100);conn=self._db()
        try:
            self._workspace_role(conn,user["id"],workspace_id)
            result=[]
            rows=conn.execute("""SELECT n.*,u.name actor_name,t.title task_title FROM notifications n LEFT JOIN users u ON u.id=n.actor_user_id
                LEFT JOIN tasks t ON t.id=n.task_id WHERE n.recipient_user_id=? AND n.workspace_id=? AND (?=0 OR n.id<?) ORDER BY n.id DESC LIMIT ?""",(user["id"],workspace_id,after,after,limit+1)).fetchall()
            for row in rows:
                try:self._task_context(conn,user["id"],row["task_id"],require_active=True)
                except ApiError:continue
                result.append({"id":row["id"],"kind":row["kind"],"actor":{"id":row["actor_user_id"],"name":row["actor_name"]},"task":{"id":row["task_id"],"title":row["task_title"]},"board_id":row["board_id"],"created_at":row["created_at"],"read_at":row["read_at"],"version":row["version"]})
                if len(result)>limit:break
            items=result[:limit]
            unread=0
            for row in conn.execute("SELECT task_id FROM notifications WHERE recipient_user_id=? AND workspace_id=? AND read_at IS NULL",(user["id"],workspace_id)):
                try:self._task_context(conn,user["id"],row["task_id"],require_active=True);unread+=1
                except ApiError:continue
            return {"items":items,"has_more":len(result)>limit,"next_after":items[-1]["id"] if items else None,"unread":unread}
        finally:conn.close()

    def read_notification(self,user,notification_id,data):
        version=require_version(require_object(data));conn=self._db()
        try:
            with transaction(conn):
                row=conn.execute("SELECT * FROM notifications WHERE id=? AND recipient_user_id=?",(notification_id,user["id"])).fetchone()
                if not row:raise ApiError(404,"NOTIFICATION_NOT_FOUND","通知不存在")
                self._workspace_role(conn,user["id"],row["workspace_id"])
                try:self._task_context(conn,user["id"],row["task_id"],require_active=True)
                except ApiError:raise ApiError(404,"NOTIFICATION_NOT_FOUND","通知不存在")
                cursor=conn.execute("UPDATE notifications SET read_at=COALESCE(read_at,?),version=version+1 WHERE id=? AND version=?",(utc_now(),notification_id,version));self._conflict(cursor,"通知版本冲突")
            return {"id":notification_id,"read":True,"version":version+1}
        finally:conn.close()

    def read_all_notifications(self,user,workspace_id):
        conn=self._db()
        try:
            with transaction(conn):
                self._workspace_role(conn,user["id"],workspace_id);stamp=utc_now();visible=[]
                for row in conn.execute("SELECT id,task_id FROM notifications WHERE recipient_user_id=? AND workspace_id=? AND read_at IS NULL",(user["id"],workspace_id)):
                    try:self._task_context(conn,user["id"],row["task_id"],require_active=True);visible.append(row["id"])
                    except ApiError:continue
                count=0
                if visible:
                    marks=','.join('?'*len(visible));count=conn.execute(f"UPDATE notifications SET read_at=?,version=version+1 WHERE id IN ({marks})",(stamp,*visible)).rowcount
            return {"updated":count,"read_at":stamp}
        finally:conn.close()

    def global_search(self,user,workspace_id,q,*,after=0,limit=30):
        if not isinstance(q,str):raise ApiError(422,"VALIDATION_ERROR","q must be text")
        q=unicodedata.normalize("NFKC",q).strip()
        if not q:return {"items":[],"has_more":False,"next_after":None}
        if len(q)>100:raise ApiError(422,"VALIDATION_ERROR","q is too long")
        after=self._page(after,"after",0,100000);limit=self._page(limit,"limit",30,50);needle=q.casefold();conn=self._db()
        try:
            self._workspace_role(conn,user["id"],workspace_id);items=[]
            boards=[]
            for row in conn.execute("SELECT id,name,access_type,deleted_at,archived_at FROM boards WHERE workspace_id=?",(workspace_id,)):
                try:self._board_access(conn,user["id"],row["id"],require_active=True)
                except ApiError:continue
                boards.append(row["id"])
                if needle in row["name"].casefold():items.append((0 if row["name"].casefold()==needle else 1,"board",row["id"],row["name"],row["id"],None))
            if boards:
                marks=','.join('?'*len(boards))
                for row in conn.execute(f"""SELECT t.id,t.title,g.board_id FROM tasks t JOIN groups_ g ON g.id=t.group_id WHERE g.board_id IN ({marks}) AND t.deleted_at IS NULL AND t.archived_at IS NULL AND g.deleted_at IS NULL AND g.archived_at IS NULL""",boards):
                    if needle in row["title"].casefold():items.append((0 if row["title"].casefold()==needle else 2,"task",row["id"],row["title"],row["board_id"],row["id"]))
                for row in conn.execute(f"""SELECT c.id,c.body,t.id task_id,g.board_id FROM comments c JOIN tasks t ON t.id=c.task_id JOIN groups_ g ON g.id=t.group_id WHERE g.board_id IN ({marks}) AND c.deleted_at IS NULL AND t.deleted_at IS NULL AND g.deleted_at IS NULL""",boards):
                    if needle in row["body"].casefold():items.append((3,"comment",row["id"],row["body"][:160],row["board_id"],row["task_id"]))
                for row in conn.execute(f"""SELECT a.id,a.original_name,a.task_id,g.board_id FROM attachments a JOIN tasks t ON t.id=a.task_id JOIN groups_ g ON g.id=t.group_id WHERE g.board_id IN ({marks}) AND a.deleted_at IS NULL AND t.deleted_at IS NULL AND g.deleted_at IS NULL""",boards):
                    if needle in row["original_name"].casefold():items.append((3,"attachment",row["id"],row["original_name"],row["board_id"],row["task_id"]))
            for row in conn.execute("""SELECT u.id,u.name FROM users u JOIN workspace_memberships wm ON wm.user_id=u.id WHERE wm.workspace_id=? AND u.is_active=1""",(workspace_id,)):
                if needle in row["name"].casefold():items.append((1,"member",row["id"],row["name"],None,None))
            items.sort(key=lambda item:(item[0],item[1],str(item[2])));page=items[after:after+limit+1]
            return {"items":[{"type":x[1],"id":x[2],"label":x[3],"board_id":x[4],"task_id":x[5]} for x in page[:limit]],"has_more":len(page)>limit,"next_after":after+limit if len(page)>limit else None}
        finally:conn.close()

    def realtime_poll(self,user,workspace_id,*,cursor=0,limit=100):
        cursor=self._page(cursor,"cursor",0,2_147_483_647);limit=self._page(limit,"limit",100,200);conn=self._db()
        try:
            self._workspace_role(conn,user["id"],workspace_id);events=[]
            rows=conn.execute("SELECT * FROM realtime_events WHERE workspace_id=? AND id>? ORDER BY id LIMIT ?",(workspace_id,cursor,limit)).fetchall()
            for row in rows:
                try:self._board_access(conn,user["id"],row["board_id"])
                except ApiError:continue
                events.append({"id":row["id"],"action":row["action_code"],"board_id":row["board_id"],"task_id":row["task_id"],"actor_user_id":row["actor_user_id"],"created_at":row["created_at"]})
            return {"events":events,"cursor":rows[-1]["id"] if rows else cursor,"online":[]}
        finally:conn.close()

    @staticmethod
    def _csv_safe(value):
        value=str(value if value is not None else "")
        return "'"+value if value.lstrip().startswith(("=","+","-","@","\t","\r")) else value

    def audit(self,user,workspace_id,*,after=0,limit=50,action=None):
        after=self._page(after,"after",0,2_147_483_647);limit=self._page(limit,"limit",50,200);conn=self._db()
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
            args=[workspace_id,after];where="workspace_id=? AND id>?"
            if action:
                if not isinstance(action,str) or len(action)>80:raise ApiError(422,"VALIDATION_ERROR","action is invalid")
                where+=" AND action_code=?";args.append(action)
            args.append(limit+1);rows=conn.execute(f"SELECT * FROM audit_log WHERE {where} ORDER BY id LIMIT ?",args).fetchall();items=[]
            for row in rows[:limit]:
                item=dict(row);item["details"]=json.loads(item.pop("details_json") or "{}");items.append(item)
            return {"items":items,"has_more":len(rows)>limit,"next_after":items[-1]["id"] if items and len(rows)>limit else None}
        finally:conn.close()

    def audit_csv(self,user,workspace_id,*,action=None):
        rows=self.audit(user,workspace_id,after=0,limit=200,action=action)["items"];stream=io.StringIO(newline="");writer=csv.writer(stream);writer.writerow(["id","created_at","action","outcome","actor","entity_type","entity_id","details"])
        for row in rows:writer.writerow([self._csv_safe(row.get(k)) for k in ("id","created_at","action_code","outcome","actor_user_id","entity_type","entity_id")]+[self._csv_safe(json.dumps(row["details"],ensure_ascii=False,sort_keys=True))])
        return stream.getvalue()

    def backups(self,user,workspace_id):
        conn=self._db()
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
        finally:conn.close()
        return {"backups":list_backups(self.backup_root),"restore_mode":"offline_cli_only"}

    def create_admin_backup(self,user,workspace_id):
        conn=self._db()
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
        finally:conn.close()
        try:package=create_backup(self.db_path,self.attachment_root,self.backup_root,label="manual")
        except OperationsError as error:raise ApiError(409,"BACKUP_FAILED",str(error)) from error
        return {"name":package.name,"verified":True,"restore_mode":"offline_cli_only"}

    def verify_admin_backup(self,user,workspace_id,name):
        conn=self._db()
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
        finally:conn.close()
        if not isinstance(name,str) or Path(name).name!=name or not name.startswith("flowboard-"):raise ApiError(422,"VALIDATION_ERROR","backup name is invalid")
        package=(self.backup_root/name).resolve()
        if package.parent!=self.backup_root:raise ApiError(422,"VALIDATION_ERROR","backup name is invalid")
        try:manifest=verify_backup(package)
        except (OperationsError,OSError) as error:raise ApiError(409,"BACKUP_INVALID",str(error)) from error
        return {"name":name,"verified":True,"schema_version":manifest["schema_version"],"created_at":manifest["created_at"]}

    # Existing admin API -------------------------------------------------
    def memberships(self,user,workspace_id):
        conn=self._db()
        try:
            if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
            return [dict(row) for row in conn.execute("""SELECT u.id,u.username,u.name,u.is_active,wm.role FROM users u JOIN workspace_memberships wm ON wm.user_id=u.id WHERE wm.workspace_id=? ORDER BY u.name""",(workspace_id,))]
        finally:conn.close()

    def update_membership(self,user,workspace_id,target_user_id,role):
        validate_choice(role,"role",{"admin","member","viewer"});conn=self._db()
        try:
            with transaction(conn):
                if self._workspace_role(conn,user["id"],workspace_id)!="admin":raise ApiError(403,"ADMIN_REQUIRED","需要管理员权限")
                cursor=conn.execute("UPDATE workspace_memberships SET role=? WHERE workspace_id=? AND user_id=?",(role,workspace_id,target_user_id))
                if cursor.rowcount!=1:raise ApiError(404,"MEMBERSHIP_NOT_FOUND","成员关系不存在")
                conn.execute("""INSERT INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",(f"membership:{workspace_id}:{target_user_id}:{secrets.token_hex(12)}",workspace_id,user["id"],"membership.role_changed","success","membership",target_user_id,json.dumps({"role":role}),utc_now()))
            return {"user_id":target_user_id,"role":role}
        finally:conn.close()
