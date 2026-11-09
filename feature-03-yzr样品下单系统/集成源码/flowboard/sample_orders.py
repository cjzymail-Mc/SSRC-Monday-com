"""Shared sample shoe orders inside a Flowboard workspace."""

import base64
import hashlib
import json
import re
import secrets
import sqlite3
import uuid
from datetime import date
from pathlib import Path

from .database import connect, transaction, utc_now
from .sample_order_excel import annual_workbook, signed_workbook
from .service import ApiError, FlowboardService


FILE_RE = re.compile(r"^[0-9a-f]{32}\.(?:png|jpg|pdf)$")
MAKERS = {"杨祖锐", "徐亮", "张宇昂", "隋晗", "庄旭宏", "延领"}
ASSETS = Path(__file__).resolve().parent / "assets"


def _field(obj, key, limit=300):
    return str(obj.get(key) or "").strip()[:limit]


def _date(value, *, required=False):
    if not value and not required:
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ApiError(422, "VALIDATION_ERROR", "日期格式须为 YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", "日期无效") from None
    return value


def _row(row):
    order = dict(row)
    order["items"] = json.loads(order.pop("items_json"))
    return order


class SampleOrders:
    def __init__(self, db_path):
        self.db_path = db_path
        self.auth = FlowboardService(db_path)
        self.uploads = self.auth.attachment_root

    def _db(self):
        return connect(self.db_path)

    def _access(self, conn, user, workspace_id, *, write=False):
        self.auth._workspace_role(conn, user["id"], workspace_id, write=write)

    @staticmethod
    def _audit(conn, user, workspace_id, action, order_id, details=None):
        conn.execute("""INSERT INTO audit_log
            (source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (f"sample-order:{uuid.uuid4().hex}", workspace_id, user["id"], action,
             "success", "sample_order", order_id, json.dumps(details or {}, ensure_ascii=False), utc_now()))

    def _file(self, conn, workspace_id, name, kind):
        if not name:
            return
        if not FILE_RE.fullmatch(name) or not conn.execute(
            "SELECT 1 FROM sample_order_files WHERE workspace_id=? AND storage_name=? AND kind=?",
            (workspace_id, name, kind),
        ).fetchone() or not (self.uploads / name).is_file():
            raise ApiError(422, "VALIDATION_ERROR", "附件无效，请重新上传")

    def _validate(self, conn, workspace_id, raw):
        if not isinstance(raw, dict):
            raise ApiError(422, "VALIDATION_ERROR", "需求单内容无效")
        number = _field(raw, "number", 80)
        if not number:
            raise ApiError(422, "VALIDATION_ERROR", "请填写需求单编号")
        order_date = _date(raw.get("order_date"), required=True)
        status = _field(raw, "status", 10)
        handover = _field(raw, "handover_status", 10)
        receiver = _field(raw, "receiver", 80)
        requester = _field(raw, "requester", 80)
        if status not in {"待签字", "已签字", "已下单"}:
            raise ApiError(422, "VALIDATION_ERROR", "流程状态无效")
        if handover not in {"未接收", "部分接收", "完全接收"}:
            raise ApiError(422, "VALIDATION_ERROR", "交接状态无效")
        if handover != "未接收" and not receiver:
            raise ApiError(422, "VALIDATION_ERROR", "请填写接收人")
        if requester and requester not in MAKERS:
            raise ApiError(422, "VALIDATION_ERROR", "制表人无效")
        scan_file = _field(raw, "scan_file", 40)
        self._file(conn, workspace_id, scan_file, "scan")
        incoming = raw.get("items")
        if not isinstance(incoming, list) or not 1 <= len(incoming) <= 50:
            raise ApiError(422, "VALIDATION_ERROR", "每张需求单须有 1 至 50 行鞋款")
        items = []
        for i, item in enumerate(incoming, 1):
            if not isinstance(item, dict):
                raise ApiError(422, "VALIDATION_ERROR", f"第 {i} 行鞋款无效")
            style = _field(item, "style", 80)
            category = _field(item, "category", 40)
            contractor = _field(item, "contractor", 10)
            try:
                quantity = int(item.get("quantity"))
            except (ValueError, TypeError):
                raise ApiError(422, "VALIDATION_ERROR", f"第 {i} 行数量无效") from None
            if not style or not category or not 1 <= quantity <= 9999:
                raise ApiError(422, "VALIDATION_ERROR", f"第 {i} 行须填写款号、品类及有效双数")
            if contractor not in {"先锋", "外协", "大货"}:
                raise ApiError(422, "VALIDATION_ERROR", f"第 {i} 行请选择承接单位")
            photo = _field(item, "photo_file", 40)
            self._file(conn, workspace_id, photo, "photo")
            items.append({"id": _field(item, "id", 80) or uuid.uuid4().hex,
                          "style": style, "category": category, "contractor": contractor,
                          "sole": _field(item, "sole", 80), "gender": _field(item, "gender", 20),
                          "photo_file": photo, "color": _field(item, "color", 80),
                          "quantity": quantity, "size": _field(item, "size", 50),
                          "purpose": _field(item, "purpose", 500),
                          "due_date": _date(item.get("due_date")),
                          "remark": _field(item, "remark", 500)})
        return {"number": number, "order_date": order_date, "status": status,
                "contractor": items[0]["contractor"] if len({x["contractor"] for x in items}) == 1 else "混合",
                "handover_status": handover, "receiver": receiver,
                "requester": requester, "department": _field(raw, "department", 80),
                "note": _field(raw, "note", 500), "scan_file": scan_file,
                "items_json": json.dumps(items, ensure_ascii=False)}

    def list(self, user, workspace_id, *, deleted=False):
        conn = self._db()
        try:
            self._access(conn, user, workspace_id)
            rows = conn.execute("SELECT * FROM sample_orders WHERE workspace_id=? AND deleted_at IS "
                                + ("NOT NULL" if deleted else "NULL")
                                + " ORDER BY order_date DESC,created_at DESC", (workspace_id,)).fetchall()
            return [_row(row) for row in rows]
        finally:
            conn.close()

    def get(self, user, workspace_id, order_id, *, deleted=False):
        conn = self._db()
        try:
            self._access(conn, user, workspace_id)
            row = conn.execute("SELECT * FROM sample_orders WHERE workspace_id=? AND id=? AND deleted_at IS "
                               + ("NOT NULL" if deleted else "NULL"), (workspace_id, order_id)).fetchone()
            if not row:
                raise ApiError(404, "NOT_FOUND", "需求单不存在")
            return _row(row)
        finally:
            conn.close()

    def save(self, user, workspace_id, raw, order_id=None):
        conn = self._db()
        try:
            with transaction(conn):
                self._access(conn, user, workspace_id, write=True)
                values = self._validate(conn, workspace_id, raw)
                now = utc_now()
                if order_id:
                    old = conn.execute("SELECT version FROM sample_orders WHERE workspace_id=? AND id=? AND deleted_at IS NULL",
                                       (workspace_id, order_id)).fetchone()
                    if not old:
                        raise ApiError(404, "NOT_FOUND", "需求单不存在")
                    if raw.get("version") != old["version"]:
                        raise ApiError(409, "VERSION_CONFLICT", "需求单已被同事更新，请刷新后重试")
                    fields = ",".join(f"{key}=?" for key in values)
                    conn.execute(f"UPDATE sample_orders SET {fields},version=version+1,updated_by=?,updated_at=? WHERE id=?",
                                 (*values.values(), user["id"], now, order_id))
                    action = "sample_order.updated"
                else:
                    order_id = uuid.uuid4().hex
                    columns = ",".join(values)
                    placeholders = ",".join("?" for _ in values)
                    conn.execute(f"INSERT INTO sample_orders(id,workspace_id,{columns},created_by,updated_by,created_at,updated_at) VALUES (?,?,{placeholders},?,?,?,?)",
                                 (order_id, workspace_id, *values.values(), user["id"], user["id"], now, now))
                    action = "sample_order.created"
                self._audit(conn, user, workspace_id, action, order_id, {"number": values["number"]})
            return self.get(user, workspace_id, order_id)
        except sqlite3.IntegrityError as error:
            raise ApiError(409, "DUPLICATE_NUMBER", "该工作区已有相同编号的需求单") from error
        finally:
            conn.close()

    def delete(self, user, workspace_id, order_id, version):
        conn = self._db()
        try:
            with transaction(conn):
                self._access(conn, user, workspace_id, write=True)
                row = conn.execute("SELECT version,number FROM sample_orders WHERE workspace_id=? AND id=? AND deleted_at IS NULL",
                                   (workspace_id, order_id)).fetchone()
                if not row:
                    raise ApiError(404, "NOT_FOUND", "需求单不存在")
                if version != row["version"]:
                    raise ApiError(409, "VERSION_CONFLICT", "需求单已被同事更新，请刷新后重试")
                conn.execute("UPDATE sample_orders SET deleted_at=?,deleted_by=?,version=version+1 WHERE id=?",
                             (utc_now(), user["id"], order_id))
                self._audit(conn, user, workspace_id, "sample_order.deleted", order_id, {"number": row["number"]})
            return {"ok": True}
        finally:
            conn.close()

    def restore(self, user, workspace_id, order_id, version):
        conn = self._db()
        try:
            with transaction(conn):
                self._access(conn, user, workspace_id, write=True)
                row = conn.execute("SELECT version,number FROM sample_orders WHERE workspace_id=? AND id=? AND deleted_at IS NOT NULL",
                                   (workspace_id, order_id)).fetchone()
                if not row:
                    raise ApiError(404, "NOT_FOUND", "需求单不存在")
                if version != row["version"]:
                    raise ApiError(409, "VERSION_CONFLICT", "需求单已被同事更新，请刷新后重试")
                try:
                    conn.execute("UPDATE sample_orders SET deleted_at=NULL,deleted_by=NULL,version=version+1 WHERE id=?", (order_id,))
                except sqlite3.IntegrityError:
                    raise ApiError(409, "DUPLICATE_NUMBER", "已有相同编号的在用需求单") from None
                self._audit(conn, user, workspace_id, "sample_order.restored", order_id, {"number": row["number"]})
            return self.get(user, workspace_id, order_id)
        finally:
            conn.close()

    def upload(self, user, workspace_id, raw):
        kind = raw.get("kind")
        if kind not in {"photo", "scan"} or not isinstance(raw.get("data"), str):
            raise ApiError(422, "VALIDATION_ERROR", "附件类型或内容无效")
        try:
            payload = base64.b64decode(raw["data"], validate=True)
        except (ValueError, base64.binascii.Error):
            raise ApiError(422, "VALIDATION_ERROR", "附件内容无效") from None
        if kind == "photo":
            if len(payload) > 10 * 1024 * 1024:
                raise ApiError(413, "REQUEST_TOO_LARGE", "鞋款图片不能超过 10 MB")
            suffix = ".png" if payload.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg" if payload.startswith(b"\xff\xd8\xff") else None
        else:
            if len(payload) > 30 * 1024 * 1024:
                raise ApiError(413, "REQUEST_TOO_LARGE", "扫描件不能超过 30 MB")
            suffix = ".pdf" if payload.startswith(b"%PDF-") else None
        if not suffix:
            raise ApiError(422, "VALIDATION_ERROR", "仅支持 JPG、PNG 图片或 PDF 扫描件")
        conn = self._db()
        name = secrets.token_hex(16) + suffix
        target = self.uploads / name
        try:
            self._access(conn, user, workspace_id, write=True)
            self.uploads.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            with transaction(conn):
                conn.execute("INSERT INTO sample_order_files VALUES (?,?,?,?,?,?,?,?)",
                             (uuid.uuid4().hex, workspace_id, name, kind, len(payload),
                              hashlib.sha256(payload).hexdigest(), user["id"], utc_now()))
                self._audit(conn, user, workspace_id, "sample_order.file_uploaded", name, {"kind": kind})
            return {"file": name}
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            conn.close()

    def file(self, user, workspace_id, name):
        conn = self._db()
        try:
            self._access(conn, user, workspace_id)
            row = conn.execute("SELECT kind FROM sample_order_files WHERE workspace_id=? AND storage_name=?",
                               (workspace_id, name)).fetchone()
            if not row or not FILE_RE.fullmatch(name):
                raise ApiError(404, "NOT_FOUND", "附件不存在")
            target = self.uploads / name
            if not target.is_file():
                raise ApiError(404, "NOT_FOUND", "附件文件不存在")
            return ("application/pdf" if row["kind"] == "scan" else
                    "image/png" if name.endswith(".png") else "image/jpeg"), target.read_bytes()
        finally:
            conn.close()

    def signed(self, user, workspace_id, order_id):
        order = self.get(user, workspace_id, order_id)
        template = base64.b64decode((ASSETS / "sample_order_template.b64").read_text(encoding="ascii"))
        anchors = json.loads((ASSETS / "sample_order_photo_anchors.json").read_text(encoding="utf-8"))
        return order["number"], signed_workbook(order, template, anchors, self.uploads)

    def annual(self, user, workspace_id, year):
        if not re.fullmatch(r"\d{4}", str(year)):
            raise ApiError(422, "VALIDATION_ERROR", "年份无效")
        return annual_workbook(int(year), self.list(user, workspace_id))
