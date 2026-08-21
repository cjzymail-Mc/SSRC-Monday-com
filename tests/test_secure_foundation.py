import base64
import http.client
import json
import io
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from flowboard.database import SCHEMA_VERSION, _migration_v1, _migration_v2, _migration_v3, _migration_v4, _migration_v5, _migration_v6, _migration_v7, _migration_v8, connect, copy_database, migrate
from flowboard.transfer import MAX_FILE_BYTES, TransferError, make_xlsx, parse_upload, safe_cell
from flowboard.query import apply_python_query, python_matches
from server import create_server


def create_legacy_database(path):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE members(id TEXT PRIMARY KEY,name TEXT NOT NULL,avatar TEXT,avatar_class TEXT);
            CREATE TABLE boards(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT '',color TEXT DEFAULT 'purple',created_at TEXT);
            CREATE TABLE groups_(id INTEGER PRIMARY KEY AUTOINCREMENT,board_id INTEGER,name TEXT NOT NULL,color TEXT DEFAULT 'purple',sort_order INTEGER DEFAULT 0);
            CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER,title TEXT NOT NULL,status TEXT DEFAULT '待开始',priority TEXT DEFAULT '中',due TEXT DEFAULT '未设置',owner_id TEXT,sort_order INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
            CREATE TABLE comments(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER,user_id TEXT,body TEXT,created_at TEXT);
            CREATE TABLE activity(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER,user_id TEXT,action TEXT,created_at TEXT);
            INSERT INTO members VALUES ('u1','管理员','管','avatar-blue'),('u2','只读测试','读','avatar-pink');
            INSERT INTO boards VALUES (1,'测试看板','迁移测试','purple','2026-01-01T00:00:00');
            INSERT INTO groups_ VALUES (1,1,'分组一','purple',0),(2,1,'分组二','orange',1);
            INSERT INTO tasks VALUES
              (1,1,'任务一','进行中','高','今天','u1',0,'2026-01-01','2026-01-01'),
              (2,1,'任务二','待开始','中','8月04日','u2',1,'2026-01-01','2026-01-01'),
              (3,1,'任务三','审核中','中','8月06日','u1',2,'2026-01-01','2026-01-01'),
              (4,2,'任务四','已完成','低','7月30日','u1',0,'2026-01-01','2026-01-01'),
              (5,2,'任务五','进行中','高','8月09日','u2',1,'2026-01-01','2026-01-01');
            """
        )
        conn.commit()
    finally:
        conn.close()


def make_two_sheet_xlsx(first_headers,first_rows,second_headers,second_rows):
    first=make_xlsx(first_headers,first_rows,"First");second=make_xlsx(second_headers,second_rows,"Second");first_zip=zipfile.ZipFile(io.BytesIO(first));second_zip=zipfile.ZipFile(io.BytesIO(second));output=io.BytesIO()
    with first_zip,second_zip,zipfile.ZipFile(output,"w") as target:
        for item in first_zip.infolist():
            content=first_zip.read(item.filename)
            if item.filename=="xl/workbook.xml":content=content.replace(b'</sheets>',b'<sheet name="Second" sheetId="2" r:id="rId2"/></sheets>')
            elif item.filename=="xl/_rels/workbook.xml.rels":content=content.replace(b'</Relationships>',b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
            elif item.filename=="[Content_Types].xml":content=content.replace(b'</Types>',b'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            target.writestr(item,content)
        target.writestr("xl/worksheets/sheet2.xml",second_zip.read("xl/worksheets/sheet1.xml"))
    return output.getvalue()


class QueryProjectionTests(unittest.TestCase):
    def test_derived_comparator_type_matrix_is_total_and_deterministic(self):
        formula={"field_type":"formula"};mirror={"field_type":"mirror"}
        for operator,wanted in (("gt",0),("gte",0),("lt",0),("lte",0),("between",[0,10])):
            self.assertFalse(python_matches(formula,"none",operator,wanted));self.assertFalse(python_matches(formula,True,operator,wanted));self.assertFalse(python_matches(formula,float("nan"),operator,wanted))
        self.assertTrue(python_matches(formula,5,"gt",0));self.assertTrue(python_matches(formula,5,"between",[0,10]));self.assertTrue(python_matches(formula,"z","gt","a"))
        self.assertTrue(python_matches(mirror,[5,"none"],"equals",5));self.assertFalse(python_matches(mirror,["none"],"gt",0))
        tasks=[{"id":1,"title":"a","field_values":{"1":"none"}},{"id":2,"title":"b","field_values":{"1":5}},{"id":3,"title":"c","field_values":{"1":None}}]
        sorts=[{"field":{"kind":"dynamic","id":1},"direction":"asc","nulls":"last"}]
        self.assertEqual([2,1,3],[item["id"] for item in apply_python_query(tasks,{"op":"and","children":[]},sorts,{1:formula})])

    def test_transfer_rejects_malformed_and_unsafe_inputs(self):
        cases=[("empty.csv",b"", "IMPORT_EMPTY"),("duplicate.csv",b"A,a\n1,2\n","IMPORT_DUPLICATE_HEADER"),("empty-header.csv",b"A,\n1,2\n","IMPORT_EMPTY_HEADER"),("oversize.csv",b"x"*(MAX_FILE_BYTES+1),"IMPORT_FILE_TOO_LARGE"),("encoding.csv",b"\x81","IMPORT_ENCODING_UNSUPPORTED")]
        for filename,raw,code in cases:
            with self.subTest(code=code),self.assertRaises(TransferError) as caught:parse_upload(filename,raw)
            self.assertEqual(caught.exception.code,code)
        source=make_xlsx(["A"],[["safe"]]);input_zip=zipfile.ZipFile(io.BytesIO(source));formula=io.BytesIO()
        with input_zip,zipfile.ZipFile(formula,"w") as target:
            for item in input_zip.infolist():
                content=input_zip.read(item.filename)
                if item.filename=="xl/worksheets/sheet1.xml":content=content.replace(b"<c r=\"A2\" t=\"inlineStr\"><is><t xml:space=\"preserve\">safe</t></is></c>",b"<c r=\"A2\"><f>1+1</f><v>2</v></c>")
                target.writestr(item,content)
        with self.assertRaises(TransferError) as caught:parse_upload("formula.xlsx",formula.getvalue())
        self.assertEqual(caught.exception.code,"IMPORT_FORMULA_FORBIDDEN")
        source=make_xlsx(["A"],[["safe"]]);input_zip=zipfile.ZipFile(io.BytesIO(source));output=io.BytesIO()
        with input_zip,zipfile.ZipFile(output,"w") as target:
            for item in input_zip.infolist():target.writestr(item,input_zip.read(item.filename))
            target.writestr("xl/vbaProject.bin",b"macro")
        with self.assertRaises(TransferError) as caught:parse_upload("macro.xlsx",output.getvalue())
        self.assertEqual(caught.exception.code,"IMPORT_XLSX_UNSAFE")
        input_zip=zipfile.ZipFile(io.BytesIO(source));output=io.BytesIO()
        with input_zip,zipfile.ZipFile(output,"w") as target:
            for item in input_zip.infolist():target.writestr(item,input_zip.read(item.filename))
            target.writestr("xl/externalLinks/externalLink1.xml",b"external")
        with self.assertRaises(TransferError) as caught:parse_upload("external.xlsx",output.getvalue())
        self.assertEqual(caught.exception.code,"IMPORT_XLSX_UNSAFE")


class FlowboardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flowboard-tests-")
        self.db_path = str(Path(self.temp.name) / "flowboard.db")
        create_legacy_database(self.db_path)
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        self.server = create_server("127.0.0.1", 0, self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()
        os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)

    def request(self, method, path, body=None, *, cookie=None, csrf=None, extra_headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if extra_headers:
            headers.update(extra_headers)
        connection.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        set_cookie = response.getheader("Set-Cookie")
        connection.close()
        return response.status, payload, set_cookie

    def raw_request(self, path, *, cookie=None, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Cookie": cookie} if cookie else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        result = (response.status, response.getheader("Content-Type"), body)
        connection.close()
        return result

    def login(self, username="u1"):
        status, payload, cookie = self.request(
            "POST", "/api/auth/login", {"username": username, "password": "test-password"}
        )
        self.assertEqual(status, 200)
        return cookie.split(";", 1)[0], payload["csrf_token"]

    def test_migration_preserves_existing_tasks_and_creates_backup(self):
        conn = connect(self.db_path)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tasks = conn.execute("SELECT id,title,group_id,owner_id,status,priority,due FROM tasks ORDER BY id").fetchall()
            self.assertEqual([row["id"] for row in tasks], [1, 2, 3, 4, 5])
            self.assertTrue(all(row["title"] for row in tasks))
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            conn.close()
        backups = list((Path(self.temp.name) / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        restored = str(Path(self.temp.name) / "restored.db")
        copy_database(backups[0], restored)
        check = sqlite3.connect(restored)
        try:
            self.assertEqual(check.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 5)
        finally:
            check.close()

    def test_authentication_csrf_and_header_spoofing(self):
        status, payload, _ = self.request("GET", "/api/bootstrap", extra_headers={"X-User-Id": "u1"})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "AUTH_REQUIRED")
        cookie, csrf = self.login()
        status, payload, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(payload["current_user"]["id"], "u1")
        group_id = payload["groups"][0]["id"]
        status, payload, _ = self.request("POST", "/api/tasks", {"group_id": group_id, "title": "blocked"}, cookie=cookie)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "CSRF_INVALID")
        status, _, _ = self.request("POST", "/api/tasks", {"group_id": group_id, "title": "allowed"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)

    def test_viewer_cannot_write_and_private_board_is_hidden(self):
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'")
            conn.commit()
        finally:
            conn.close()
        cookie, csrf = self.login("u2")
        status, payload, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        self.assertEqual(status, 200)
        group_id = payload["groups"][0]["id"]
        status, payload, _ = self.request("POST", "/api/tasks", {"group_id": group_id, "title": "no"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "READ_ONLY")
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE boards SET access_type='private' WHERE id=1")
            conn.commit()
        finally:
            conn.close()
        status, payload, _ = self.request("GET", "/api/bootstrap?board_id=1", cookie=cookie)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "BOARD_FORBIDDEN")

    def test_optimistic_version_conflict(self):
        cookie, csrf = self.login()
        status, bootstrap, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        self.assertEqual(status, 200)
        task = bootstrap["groups"][0]["tasks"][0]
        status, updated, _ = self.request("PATCH", f"/api/tasks/{task['id']}", {"title": "first", "version": task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(updated["version"], task["version"] + 1)
        status, payload, _ = self.request("PATCH", f"/api/tasks/{task['id']}", {"title": "stale", "version": task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "VERSION_CONFLICT")

    def test_admin_can_change_workspace_role(self):
        cookie, csrf = self.login()
        status, payload, _ = self.request("PATCH", "/api/admin/workspace-memberships/u2?workspace_id=1", {"role": "viewer"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"user_id": "u2", "role": "viewer"})

    def test_static_allowlist_blocks_repository_files(self):
        for path in ("/", "/index.html", "/styles.css", "/auth.css", "/lifecycle.css", "/view-state.js", "/view-ui.js", "/app.js"):
            for method in ("GET", "HEAD"):
                status, _, body = self.raw_request(path, method=method)
                self.assertEqual(status, 200, (method, path))
                if method == "GET":
                    self.assertTrue(body, path)
        cookie, csrf = self.login()
        for path in (
            "/flowboard.db",
            "/backups/flowboard-pre-v1-example.db",
            "/server.py",
            "/.copilot-task.md",
            "/tests/test_secure_foundation.py",
            "/unknown.txt",
        ):
            for method in ("GET", "HEAD"):
                for credentials in (None, cookie):
                    status, content_type, body = self.raw_request(path, cookie=credentials, method=method)
                    self.assertEqual(status, 404, (method, path, credentials))
                    self.assertIn("application/json", content_type)
                    self.assertNotIn("application/octet-stream", content_type)
                    self.assertNotIn("text/x-python", content_type)
                    self.assertNotIn(b"SQLite format", body)
                    self.assertNotIn(b"FlowboardIntegrationTests", body)

    def test_v1_to_v2_migration_preserves_data_and_activity(self):
        path = str(Path(self.temp.name) / "explicit-v1.db")
        create_legacy_database(path)
        conn = connect(path)
        try:
            _migration_v1(conn, "test-password")
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            before = [tuple(row) for row in conn.execute("SELECT id,title,group_id,owner_id FROM tasks ORDER BY id")]
        finally:
            conn.close()
        backup = migrate(path)
        self.assertTrue(backup and Path(backup).exists())
        conn = connect(path)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(before, [tuple(row) for row in conn.execute("SELECT id,title,group_id,owner_id FROM tasks ORDER BY id")])
            self.assertIn("action_code", {row["name"] for row in conn.execute("PRAGMA table_info(activity)")})
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            conn.close()

    def test_v6_to_v7_migration_backup_restore_and_idempotence(self):
        path=str(Path(self.temp.name)/"explicit-v6.db");create_legacy_database(path);conn=connect(path)
        try:
            _migration_v1(conn,"test-password")
            for migration in (_migration_v2,_migration_v3,_migration_v4,_migration_v5,_migration_v6):migration(conn)
            before=[tuple(row) for row in conn.execute("SELECT id,title,board_order FROM tasks ORDER BY id")];self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],6)
        finally:conn.close()
        backup=migrate(path);self.assertTrue(backup and Path(backup).exists())
        conn=connect(path)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION);self.assertEqual(before,[tuple(row) for row in conn.execute("SELECT id,title,board_order FROM tasks ORDER BY id")]);self.assertEqual(conn.execute("SELECT COUNT(*) FROM task_dependencies").fetchone()[0],0);self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=7").fetchone()[0],"flowboard-schema-v7")
        finally:conn.close()
        restored=str(Path(self.temp.name)/"restored-v6.db");copy_database(backup,restored);check=sqlite3.connect(restored)
        try:self.assertEqual(check.execute("PRAGMA user_version").fetchone()[0],6);self.assertEqual(check.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],len(before))
        finally:check.close()
        self.assertIsNone(migrate(path))

    def test_board_lifecycle_and_stale_version(self):
        cookie, csrf = self.login()
        status, created, _ = self.request("POST", "/api/workspaces/1/boards", {"name": "Lifecycle", "description": "board", "color": "blue", "access_type": "private"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        board_id = created["id"]
        status, updated, _ = self.request("PATCH", f"/api/boards/{board_id}", {"version": 1, "name": "Lifecycle 2"}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, updated["version"]), (200, 2))
        status, payload, _ = self.request("PATCH", f"/api/boards/{board_id}", {"version": 1, "name": "stale"}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (409, "VERSION_CONFLICT"))
        status, copied, _ = self.request("POST", f"/api/boards/{board_id}/copy", {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        status, archived, _ = self.request("POST", f"/api/boards/{board_id}/archive", {"version": 2}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", f"/api/boards/{board_id}/unarchive", {"version": archived["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, deleted, _ = self.request("DELETE", f"/api/boards/{board_id}", {"version": 4}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, trash, _ = self.request("GET", "/api/workspaces/1/trash", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(board_id, [item["id"] for item in trash["boards"]])
        status, restored, _ = self.request("POST", f"/api/boards/{board_id}/restore", {"version": deleted["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, restored["version"]), (200, 6))
        conn = connect(self.db_path)
        try:
            event = conn.execute("SELECT action_code,details_json FROM activity WHERE board_id=? ORDER BY id DESC LIMIT 1", (copied["id"],)).fetchone()
            self.assertEqual(event["action_code"], "board.copied")
            self.assertIn("source_id", json.loads(event["details_json"]))
        finally:
            conn.close()

    def test_group_and_task_lifecycle_parent_restore_and_activity(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id = boot["board"]["id"]
        status, group, _ = self.request("POST", f"/api/boards/{board_id}/groups", {"name": "Lifecycle group", "color": "green"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        group_id = group["id"]
        status, group_updated, _ = self.request("PATCH", f"/api/groups/{group_id}", {"version": 1, "name": "Renamed", "color": "blue"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, group_copy, _ = self.request("POST", f"/api/groups/{group_id}/copy", {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        _, refreshed, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        source_group = next(item for item in refreshed["groups"] if item["id"] == group_id)
        status, moved_group, _ = self.request("POST", f"/api/groups/{group_id}/move", {"version": source_group["version"], "board_version": refreshed["board"]["version"], "target_index": 0}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)

        status, task, _ = self.request("POST", f"/api/groups/{group_id}/tasks", {"title": "Lifecycle task", "status": "待开始", "priority": "高", "due": "2026-08-10", "owner_id": "u2"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        task_id = task["id"]
        status, detail, _ = self.request("GET", f"/api/tasks/{task_id}", cookie=cookie)
        self.assertEqual((status, detail["title"]), (200, "Lifecycle task"))
        status, task_updated, _ = self.request("PATCH", f"/api/tasks/{task_id}", {"version": detail["version"], "status": "进行中"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", f"/api/tasks/{task_id}/comments", {"body": "source only"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        status, task_copy, _ = self.request("POST", f"/api/tasks/{task_id}/copy", {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        _, copy_detail, _ = self.request("GET", f"/api/tasks/{task_copy['id']}", cookie=cookie)
        self.assertEqual(copy_detail["comments"], [])
        self.assertEqual([event["action_code"] for event in copy_detail["activity"]], ["task.copied"])

        _, refreshed, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        source_group = next(item for item in refreshed["groups"] if item["id"] == group_id)
        target_group = next(item for item in refreshed["groups"] if item["id"] == group_copy["id"])
        source_task = next(item for item in source_group["tasks"] if item["id"] == task_id)
        status, moved_task, _ = self.request("POST", f"/api/tasks/{task_id}/move", {"version": source_task["version"], "source_group_version": source_group["version"], "target_group_version": target_group["version"], "target_group_id": target_group["id"], "target_index": len(target_group["tasks"])}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, archived, _ = self.request("POST", f"/api/tasks/{task_id}/archive", {"version": moved_task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, unarchived, _ = self.request("POST", f"/api/tasks/{task_id}/unarchive", {"version": archived["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, deleted_task, _ = self.request("DELETE", f"/api/tasks/{task_id}", {"version": unarchived["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)

        _, target_detail, _ = self.request("GET", f"/api/groups/{target_group['id']}", cookie=cookie)
        status, deleted_group, _ = self.request("DELETE", f"/api/groups/{target_group['id']}", {"version": target_detail["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, payload, _ = self.request("POST", f"/api/tasks/{task_id}/restore", {"version": deleted_task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (409, "PARENT_DELETED"))
        status, restored_group, _ = self.request("POST", f"/api/groups/{target_group['id']}/restore", {"version": deleted_group["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, restored_task, _ = self.request("POST", f"/api/tasks/{task_id}/restore", {"version": deleted_task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertGreater(restored_task["version"], deleted_task["version"])
        _, events, _ = self.request("GET", f"/api/boards/{board_id}/activity", cookie=cookie)
        codes = {event["action_code"] for event in events}
        expected = {"group.created", "group.moved", "task.created", "task.moved", "task.deleted", "task.restored"}
        conn = connect(self.db_path)
        try:
            sql_rows = [dict(row) for row in conn.execute(
                """SELECT id,board_id,task_id,entity_type,entity_id,action_code,details_json
                   FROM activity WHERE board_id=? ORDER BY id""", (board_id,)
            )]
        finally:
            conn.close()
        missing = expected - codes
        self.assertFalse(missing, {"missing": sorted(missing), "api_codes": sorted(codes), "sql_rows": sql_rows})

    def test_validation_viewer_and_cross_board_boundaries(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        group_id = boot["groups"][0]["id"]
        invalid_cases = [
            {"title": "x", "status": "arbitrary"},
            {"title": "x", "priority": "urgent"},
            {"title": "x", "due": "tomorrow"},
            {"title": "x", "owner_id": "missing"},
            {"title": "x" * 501},
        ]
        for body in invalid_cases:
            status, payload, _ = self.request("POST", f"/api/groups/{group_id}/tasks", body, cookie=cookie, csrf=csrf)
            self.assertEqual(status, 422, body)
            self.assertIn(payload["error"]["code"], {"VALIDATION_ERROR", "INVALID_OWNER"})
        status, task, _ = self.request("POST", f"/api/groups/{group_id}/tasks", {"title": "move me"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        status, board, _ = self.request("POST", "/api/workspaces/1/boards", {"name": "Other"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        status, other_group, _ = self.request("POST", f"/api/boards/{board['id']}/groups", {"name": "Other group"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        _, source, _ = self.request("GET", f"/api/groups/{group_id}", cookie=cookie)
        _, target, _ = self.request("GET", f"/api/groups/{other_group['id']}", cookie=cookie)
        status, payload, _ = self.request("POST", f"/api/tasks/{task['id']}/move", {"version": task["version"], "source_group_version": source["version"], "target_group_version": target["version"], "target_group_id": target["id"], "target_index": 0}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (422, "CROSS_BOARD_MOVE"))
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'")
            conn.commit()
        finally: conn.close()
        status, payload, _ = self.request("PATCH", "/api/admin/workspace-memberships/u2?workspace_id=1", {"role": "viewer"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, payload)
        viewer_cookie, viewer_csrf = self.login("u2")
        status, payload, _ = self.request("POST", "/api/workspaces/1/boards", {"name": "No"}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, payload["error"]["code"]), (403, "READ_ONLY"))

    def test_archive_parent_visibility_copy_history_and_strict_inputs(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board, group = boot["board"], boot["groups"][0]
        task = group["tasks"][0]
        status, _, _ = self.request("POST", f"/api/tasks/{task['id']}/comments", {"body": "do not copy"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        status, copied, _ = self.request("POST", f"/api/boards/{board['id']}/copy", {"name": "Copy contract"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        _, copied_boot, _ = self.request("GET", f"/api/bootstrap?board_id={copied['id']}", cookie=cookie)
        copied_task = copied_boot["groups"][0]["tasks"][0]
        _, copied_detail, _ = self.request("GET", f"/api/tasks/{copied_task['id']}", cookie=cookie)
        self.assertEqual(copied_detail["comments"], [])
        self.assertEqual(copied_detail["activity"], [])
        _, copied_events, _ = self.request("GET", f"/api/boards/{copied['id']}/activity", cookie=cookie)
        self.assertEqual([event["action_code"] for event in copied_events], ["board.copied"])

        status, archived_group, _ = self.request("POST", f"/api/groups/{group['id']}/archive", {"version": group["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        _, after_archive, _ = self.request("GET", f"/api/bootstrap?board_id={board['id']}", cookie=cookie)
        self.assertNotIn(group["id"], [item["id"] for item in after_archive["groups"]])
        _, archived_items, _ = self.request("GET", f"/api/boards/{board['id']}/archived", cookie=cookie)
        self.assertIn(group["id"], [item["id"] for item in archived_items["groups"]])
        status, restored_group, _ = self.request("POST", f"/api/groups/{group['id']}/unarchive", {"version": archived_group["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, payload, _ = self.request("PATCH", f"/api/groups/{group['id']}", {"version": archived_group["version"], "name": "stale"}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (409, "VERSION_CONFLICT"))

        status, deleted_task, _ = self.request("DELETE", f"/api/tasks/{task['id']}", {"version": task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        _, current_board, _ = self.request("GET", f"/api/boards/{board['id']}", cookie=cookie)
        status, deleted_board, _ = self.request("DELETE", f"/api/boards/{board['id']}", {"version": current_board["board"]["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        for path in (f"/api/boards/{board['id']}", f"/api/groups/{group['id']}", f"/api/tasks/{task['id']}", f"/api/boards/{board['id']}/activity", f"/api/boards/{board['id']}/archived"):
            status, _, _ = self.request("GET", path, cookie=cookie)
            self.assertEqual(status, 404, path)
        status, trash, _ = self.request("GET", "/api/workspaces/1/trash", cookie=cookie)
        self.assertIn(board["id"], [item["id"] for item in trash["boards"]])
        status, payload, _ = self.request("POST", f"/api/tasks/{task['id']}/restore", {"version": deleted_task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (409, "PARENT_DELETED"))
        status, _, _ = self.request("POST", f"/api/boards/{board['id']}/restore", {"version": deleted_board["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)

        _, restored_group_detail, _ = self.request("GET", f"/api/groups/{group['id']}", cookie=cookie)
        status, deleted_group, _ = self.request("DELETE", f"/api/groups/{group['id']}", {"version": restored_group_detail["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        for path in (f"/api/groups/{group['id']}", f"/api/tasks/{task['id']}"):
            status, _, _ = self.request("GET", path, cookie=cookie)
            self.assertEqual(status, 404, path)
        status, payload, _ = self.request("POST", f"/api/tasks/{task['id']}/restore", {"version": deleted_task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (409, "PARENT_DELETED"))
        status, _, _ = self.request("POST", f"/api/groups/{group['id']}/restore", {"version": deleted_group["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", f"/api/tasks/{task['id']}/restore", {"version": deleted_task["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)

        status, payload, _ = self.request("POST", "/api/workspaces/1/boards", ["not", "object"], cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (400, "INVALID_REQUEST"))
        status, payload, _ = self.request("POST", "/api/workspaces/1/boards", {"name": "x", "unexpected": True}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (422, "UNKNOWN_FIELD"))

        app_source = (Path(__file__).resolve().parents[1] / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-field="title"', app_source)
        self.assertIn("color:color.trim()", app_source)

    def test_dynamic_fields_all_types_permissions_and_versions(self):
        cookie, csrf = self.login()
        status, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        self.assertEqual(status, 200)
        board_id, board_version = boot["board"]["id"], boot["board"]["version"]
        specs = [
            ("文本", "text", []), ("数字", "number", []),
            ("自定义状态", "status", [{"label": "红", "color": "orange"}]),
            ("人员", "person", []), ("日期", "date", []),
            ("完成", "checkbox", []),
            ("标签", "tags", [{"label": "A", "color": "blue"}, {"label": "B", "color": "green"}]),
            ("链接", "link", []),
        ]
        created_ids = []
        for name, kind, options in specs:
            status, created, _ = self.request("POST", f"/api/boards/{board_id}/fields",
                {"board_version": board_version, "name": name, "field_type": kind, "config": {}, "options": options},
                cookie=cookie, csrf=csrf)
            self.assertEqual(status, 201, created)
            created_ids.append(created["id"]); board_version = created["board_version"]
        _, boot, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        task = boot["groups"][0]["tasks"][0]
        custom = {field["field_type"]: field for field in boot["fields"] if field["id"] in created_ids}
        values = {
            str(custom["text"]["id"]): "hello", str(custom["number"]["id"]): 12.5,
            str(custom["status"]["id"]): custom["status"]["options"][0]["id"],
            str(custom["person"]["id"]): "u2", str(custom["date"]["id"]): "2026-08-20",
            str(custom["checkbox"]["id"]): True,
            str(custom["tags"]["id"]): [item["id"] for item in custom["tags"]["options"]],
            str(custom["link"]["id"]): {"url": "https://example.com", "label": "example"},
        }
        status, updated, _ = self.request("PATCH", f"/api/tasks/{task['id']}",
            {"version": task["version"], "field_values": values}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, updated)
        status, detail, _ = self.request("GET", f"/api/tasks/{task['id']}", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(detail["field_values"][str(custom["text"]["id"])], "hello")
        self.assertEqual(detail["field_values"][str(custom["tags"]["id"])], values[str(custom["tags"]["id"])])
        ordered_ids=[field["id"] for field in reversed(boot["fields"])]
        status, reordered, _ = self.request("POST", f"/api/boards/{board_id}/fields/reorder",
            {"board_version": board_version, "field_ids": ordered_ids}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, reordered)
        status, refreshed, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        self.assertEqual([field["id"] for field in refreshed["fields"]], ordered_ids)
        status, payload, _ = self.request("POST", f"/api/boards/{board_id}/fields/reorder",
            {"board_version": board_version, "field_ids": ordered_ids}, cookie=cookie, csrf=csrf)
        self.assertEqual((status,payload["error"]["code"]),(409,"VERSION_CONFLICT"))
        status, payload, _ = self.request("POST", f"/api/boards/{board_id}/fields/reorder",
            {"board_version": reordered["board_version"], "field_ids": ordered_ids[:-1]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status,payload["error"]["code"]),(422,"INVALID_FIELD_ORDER"))
        text_field=next(field for field in refreshed["fields"] if field["id"]==custom["text"]["id"])
        status, renamed, _ = self.request("PATCH", f"/api/fields/{text_field['id']}",
            {"version":text_field["version"],"name":"文本已改"},cookie=cookie,csrf=csrf)
        self.assertEqual(status,200)
        status, payload, _ = self.request("PATCH", f"/api/fields/{text_field['id']}",
            {"version":text_field["version"],"name":"stale"},cookie=cookie,csrf=csrf)
        self.assertEqual((status,payload["error"]["code"]),(409,"VERSION_CONFLICT"))
        status, deleted, _ = self.request("POST", f"/api/fields/{text_field['id']}/delete",
            {"version":renamed["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200)
        conn=connect(self.db_path);self.assertEqual(conn.execute("SELECT text_value FROM task_field_values WHERE task_id=? AND field_id=?",(task["id"],text_field["id"])).fetchone()[0],"hello");conn.close()
        status, after_delete, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}",cookie=cookie)
        removed=next(field for field in after_delete["deleted_fields"] if field["id"]==text_field["id"])
        status, _, _ = self.request("POST", f"/api/fields/{text_field['id']}/restore",{"version":removed["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200)
        system=next(field for field in after_delete["fields"] if field["system_key"])
        status,payload,_=self.request("POST",f"/api/fields/{system['id']}/delete",{"version":system["version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,payload["error"]["code"]),(409,"SYSTEM_FIELD"))
        status,payload,_=self.request("PATCH",f"/api/fields/{custom['status']['id']}",{"version":custom["status"]["version"],"options":[{"label":"红"},{"label":"红"}]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,payload["error"]["code"]),(422,"DUPLICATE_OPTION"))
        for bad in ([],[custom["status"]["options"][0]["id"]],"bad"):
            status,payload,_=self.request("PATCH",f"/api/tasks/{task['id']}",{"version":updated["version"],"field_values":{str(custom['status']['id']):bad}},cookie=cookie,csrf=csrf)
            self.assertEqual((status,payload["error"]["code"]),(422,"VALIDATION_ERROR"))
        duplicate_tag=custom["tags"]["options"][0]["id"]
        status,payload,_=self.request("PATCH",f"/api/tasks/{task['id']}",{"version":updated["version"],"field_values":{str(custom['tags']['id']):[duplicate_tag,duplicate_tag]}},cookie=cookie,csrf=csrf)
        self.assertEqual((status,payload["error"]["code"]),(422,"DUPLICATE_OPTION"))
        status, payload, _ = self.request("PATCH", f"/api/tasks/{task['id']}",
            {"version": task["version"], "field_values": {str(custom["number"]["id"]): 9}}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (409, "VERSION_CONFLICT"))
        status, payload, _ = self.request("PATCH", f"/api/tasks/{task['id']}",
            {"version": updated["version"], "field_values": {str(custom["date"]["id"]): "today"}}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (422, "VALIDATION_ERROR"))
        viewer_cookie, viewer_csrf = self.login("u2")
        conn = connect(self.db_path); conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'"); conn.commit(); conn.close()
        status, payload, _ = self.request("PATCH", f"/api/tasks/{task['id']}",
            {"version": updated["version"], "field_values": {str(custom["text"]["id"]): "blocked"}}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, payload["error"]["code"]), (403, "READ_ONLY"))

    def test_server_query_ast_dynamic_types_sort_and_fail_closed_validation(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id = boot["board"]["id"]
        status, created_number, _ = self.request(
            "POST", f"/api/boards/{board_id}/fields",
            {"board_version": boot["board"]["version"], "name": "分值", "field_type": "number", "config": {}, "options": []},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(status, 201, created_number)
        _, boot, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        number = next(field for field in boot["fields"] if field["id"] == created_number["id"])
        status_field = next(field for field in boot["fields"] if field["system_key"] == "status")
        active = next(option for option in status_field["options"] if option["label"] == "进行中")
        task = boot["groups"][0]["tasks"][0]
        status, updated, _ = self.request(
            "PATCH", f"/api/tasks/{task['id']}",
            {"version": task["version"], "field_values": {str(number["id"]): 42}},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(status, 200, updated)
        query = {
            "version": 1,
            "filter": {"op": "and", "children": [
                {"field": {"kind": "core", "key": "title"}, "operator": "contains", "value": "任务"},
                {"field": {"kind": "dynamic", "id": number["id"]}, "operator": "gte", "value": 40},
                {"field": {"kind": "dynamic", "id": status_field["id"]}, "operator": "in", "value": [active["id"]]},
            ]},
            "sort": [{"field": {"kind": "dynamic", "id": number["id"]}, "direction": "desc", "nulls": "last"}],
        }
        status, result, _ = self.request("POST", f"/api/boards/{board_id}/query", query, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, result)
        self.assertIn(task["id"], [item["id"] for item in result["tasks"]])
        invalid = dict(query)
        invalid["filter"] = {"field": {"kind": "dynamic", "id": number["id"]}, "operator": "contains", "value": "4"}
        status, payload, _ = self.request("POST", f"/api/boards/{board_id}/query", invalid, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (422, "QUERY_INVALID"))
        invalid["filter"] = {"field": {"kind": "dynamic", "id": 999999}, "operator": "equals", "value": 4}
        status, payload, _ = self.request("POST", f"/api/boards/{board_id}/query", invalid, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (422, "QUERY_INVALID"))

    def test_saved_view_defaults_permissions_copy_delete_and_blocked_config(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id = boot["board"]["id"]
        body = {"name": "我的进行中", "scope": "personal", "is_default": True,
                "filter": {"op": "and", "children": []}, "sort": [], "visible_fields": [], "column_order": ["title"]}
        status, personal, _ = self.request("POST", f"/api/boards/{board_id}/views", body, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201, personal)
        shared_body = dict(body, name="团队视图", scope="shared", is_default=True)
        status, shared, _ = self.request("POST", f"/api/boards/{board_id}/views", shared_body, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201, shared)
        status, listing, _ = self.request("GET", f"/api/boards/{board_id}/views", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(listing["effective_default_id"], personal["id"])
        status, listing, _ = self.request("POST", f"/api/boards/{board_id}/views/clear-personal-default", {}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, listing["effective_default_id"]), (200, shared["id"]))
        status, copied, _ = self.request("POST", f"/api/views/{shared['id']}/copy", {"name": "个人副本"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201, copied)
        viewer_cookie, viewer_csrf = self.login("u2")
        conn = connect(self.db_path)
        conn.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'")
        conn.commit(); conn.close()
        status, viewer_listing, _ = self.request("GET", f"/api/boards/{board_id}/views", cookie=viewer_cookie)
        self.assertEqual(status, 200)
        self.assertIn(shared["id"], [view["id"] for view in viewer_listing["views"]])
        status, own, _ = self.request("POST", f"/api/boards/{board_id}/views", dict(body, name="只读者个人", is_default=False), cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual(status, 201, own)
        status, payload, _ = self.request("PATCH", f"/api/views/{shared['id']}", {"version": 1, "name": "越权"}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, payload["error"]["code"]), (403, "READ_ONLY"))
        status, deleted, _ = self.request("DELETE", f"/api/views/{own['id']}", {"version": 1}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual(status, 200, deleted)
        conn = connect(self.db_path)
        conn.execute("UPDATE saved_views SET filter_json=? WHERE id=?", ('{"field":{"kind":"dynamic","id":999999},"operator":"equals","value":1}', shared["id"]))
        conn.commit(); conn.close()
        _, listing, _ = self.request("GET", f"/api/boards/{board_id}/views", cookie=cookie)
        blocked = next(view for view in listing["views"] if view["id"] == shared["id"])
        self.assertTrue(blocked["blocked"])
        self.assertTrue(blocked["diagnostics"])
        conn = connect(self.db_path)
        conn.execute("UPDATE saved_views SET filter_json='{' WHERE id=?", (shared["id"],))
        conn.commit(); conn.close()
        status, listing, _ = self.request("GET", f"/api/boards/{board_id}/views", cookie=cookie)
        self.assertEqual(status, 200)
        blocked = next(view for view in listing["views"] if view["id"] == shared["id"])
        self.assertEqual(blocked["diagnostics"][0]["code"], "VIEW_JSON_INVALID")
        status, repaired, _ = self.request("PATCH", f"/api/views/{shared['id']}", {
            "version": blocked["version"], "filter": {"op": "and", "children": []},
            "sort": [], "visible_fields": [], "column_order": ["title"],
        }, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, repaired)
        status, deleted_shared, _ = self.request("DELETE", f"/api/views/{shared['id']}", {"version": repaired["version"]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, deleted_shared)
        _, listing, _ = self.request("GET", f"/api/boards/{board_id}/views", cookie=cookie)
        self.assertTrue(listing["synthetic_default"])


    def test_query_hundreds_of_tasks_is_bounded_and_indexed(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id, group_id = boot["board"]["id"], boot["groups"][0]["id"]
        conn = connect(self.db_path)
        stamp = "2026-08-02T00:00:00+00:00"
        conn.executemany(
            "INSERT INTO tasks(group_id,title,status,priority,due,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            [(group_id, f"性能任务 {index:04d}", "待开始", "中", "未设置", index + 10, stamp, stamp) for index in range(600)],
        )
        plan = [row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT t.id FROM groups_ g JOIN tasks t ON t.group_id=g.id WHERE g.board_id=? AND t.deleted_at IS NULL ORDER BY g.sort_order,t.sort_order,t.id LIMIT 200",
            (board_id,),
        )]
        conn.commit(); conn.close()
        started = time.monotonic()
        status, result, _ = self.request("POST", f"/api/boards/{board_id}/query", {
            "version": 1,
            "filter": {"field": {"kind": "core", "key": "title"}, "operator": "contains", "value": "性能任务"},
            "sort": [], "limit": 200,
        }, cookie=cookie, csrf=csrf)
        elapsed = time.monotonic() - started
        self.assertEqual(status, 200, result)
        self.assertEqual((result["total"], len(result["tasks"])), (600, 200))
        self.assertLess(elapsed, 3.0)
        self.assertTrue(any("INDEX" in item.upper() for item in plan), plan)

    def test_saved_view_presentations_are_typed_and_fail_closed(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id = boot["board"]["id"]
        ids = [field["id"] for field in boot["fields"] if field["is_active"]]
        status_field = next(field for field in boot["fields"] if field["field_type"] == "status")
        date_field = next(field for field in boot["fields"] if field["field_type"] == "date")
        base = {"scope": "personal", "filter": {"op": "and", "children": []}, "sort": [],
                "visible_fields": ids, "column_order": ["title", *ids], "is_default": False}
        for name, view_type, presentation in (
            ("表格配置", "table", {"version": 1, "widths": {"title": 320, str(ids[0]): 120}, "frozen_columns": ["title"]}),
            ("看板配置", "kanban", {"version": 1, "group_field_id": status_field["id"]}),
            ("日历配置", "calendar", {"version": 1, "date_field_id": date_field["id"]}),
        ):
            status, created, _ = self.request("POST", f"/api/boards/{board_id}/views",
                {**base, "name": name, "view_type": view_type, "presentation": presentation}, cookie=cookie, csrf=csrf)
            self.assertEqual(status, 201, created)
        status, payload, _ = self.request("POST", f"/api/boards/{board_id}/views",
            {**base, "name": "错误看板", "view_type": "kanban", "presentation": {"version": 1, "group_field_id": date_field["id"]}}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, payload["error"]["code"]), (422, "VIEW_INVALID"))
        conn = connect(self.db_path)
        conn.execute("UPDATE saved_views SET presentation_json='{' WHERE name='日历配置'")
        conn.commit(); conn.close()
        status, listing, _ = self.request("GET", f"/api/boards/{board_id}/views", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(next(view for view in listing["views"] if view["name"] == "日历配置")["blocked"])

    def test_kanban_move_is_atomic_persistent_and_versioned(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id, group_id = boot["board"]["id"], boot["groups"][0]["id"]
        status_field = next(field for field in boot["fields"] if field["field_type"] == "status")
        for title in ("Kanban A", "Kanban B"):
            status, payload, _ = self.request("POST", f"/api/groups/{group_id}/tasks", {"title": title}, cookie=cookie, csrf=csrf)
            self.assertEqual(status, 201, payload)
        _, boot, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        status, result, _ = self.request("POST", f"/api/boards/{board_id}/query", {"version": 1, "filter": {"op": "and", "children": []}, "sort": []}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        a = next(task for task in result["tasks"] if task["title"] == "Kanban A")
        b = next(task for task in result["tasks"] if task["title"] == "Kanban B")
        lane = a["field_values"][str(status_field["id"])]
        body = {"version": b["version"], "board_version": boot["board"]["version"], "field_id": status_field["id"],
                "value": lane, "anchor_task_id": a["id"], "placement": "before"}
        status, moved, _ = self.request("POST", f"/api/tasks/{b['id']}/kanban-move", body, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, moved)
        conn = connect(self.db_path)
        orders = {row["id"]: row["board_order"] for row in conn.execute("SELECT id,board_order FROM tasks WHERE id IN (?,?)", (a["id"], b["id"]))}
        conn.close(); self.assertLess(orders[b["id"]], orders[a["id"]])
        status, stale, _ = self.request("POST", f"/api/tasks/{b['id']}/kanban-move", body, cookie=cookie, csrf=csrf)
        self.assertEqual((status, stale["error"]["code"]), (409, "VERSION_CONFLICT"))
        other = next(option["id"] for option in status_field["options"] if option["id"] != lane)
        _, boot, _ = self.request("GET", f"/api/bootstrap?board_id={board_id}", cookie=cookie)
        status, moved, _ = self.request("POST", f"/api/tasks/{b['id']}/kanban-move", {"version": moved["version"], "board_version": boot["board"]["version"], "field_id": status_field["id"], "value": other, "anchor_task_id": None, "placement": "after"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, moved)
        status, payload, _ = self.request("PATCH", "/api/admin/workspace-memberships/u2?workspace_id=1", {"role": "viewer"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, payload)
        viewer_cookie, viewer_csrf = self.login("u2")
        status, payload, _ = self.request("POST", f"/api/tasks/{b['id']}/kanban-move", {"version": moved["version"], "board_version": moved["board_version"], "field_id": status_field["id"], "value": lane, "anchor_task_id": None, "placement": "after"}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual(status, 403, payload)

    def test_hierarchy_dependencies_progress_dates_permissions_and_cycles(self):
        cookie, csrf = self.login()
        _, boot, _ = self.request("GET", "/api/bootstrap", cookie=cookie)
        board_id, group_id = boot["board"]["id"], boot["groups"][0]["id"]
        def create(title, **extra):
            status, payload, _ = self.request("POST", f"/api/groups/{group_id}/tasks", {"title": title, **extra}, cookie=cookie, csrf=csrf)
            self.assertEqual(status, 201, payload); return payload
        parent=create("Parent"); child_a=create("Child A",parent_id=parent["id"]); child_b=create("Child B",parent_id=parent["id"])
        grand=create("Grand",parent_id=child_a["id"])
        status, too_deep, _ = self.request("POST",f"/api/groups/{group_id}/tasks",{"title":"Too deep","parent_id":grand["id"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,too_deep["error"]["code"]),(422,"HIERARCHY_DEPTH"))
        status, moved, _ = self.request("POST",f"/api/tasks/{child_b['id']}/parent",{"version":child_b["version"],"board_version":boot["board"]["version"],"parent_id":parent["id"],"position":0},cookie=cookie,csrf=csrf)
        self.assertEqual(status,200,moved)
        status, stale, _ = self.request("POST",f"/api/tasks/{child_b['id']}/parent",{"version":child_b["version"],"board_version":boot["board"]["version"],"parent_id":None,"position":0},cookie=cookie,csrf=csrf)
        self.assertEqual((status,stale["error"]["code"]),(409,"VERSION_CONFLICT"))
        status, cycle, _ = self.request("POST",f"/api/tasks/{parent['id']}/parent",{"version":parent["version"],"board_version":moved["board_version"],"parent_id":grand["id"],"position":0},cookie=cookie,csrf=csrf)
        self.assertEqual((status,cycle["error"]["code"]),(422,"HIERARCHY_CYCLE"))
        status, detail, _ = self.request("GET",f"/api/tasks/{parent['id']}",cookie=cookie)
        self.assertEqual(status,200); self.assertEqual((detail["relations"]["progress"]["completed"],detail["relations"]["progress"]["total"]),(0,3))
        status, child_done, _ = self.request("PATCH",f"/api/tasks/{child_a['id']}",{"version":child_a["version"],"status":"已完成"},cookie=cookie,csrf=csrf);self.assertEqual(status,200,child_done)
        _, detail, _ = self.request("GET",f"/api/tasks/{parent['id']}",cookie=cookie);self.assertEqual((detail["relations"]["progress"]["completed"],detail["relations"]["progress"]["total"]),(1,3))
        predecessor=create("Predecessor",due="2026-09-10"); successor=create("Successor",due="2026-09-01")
        status, edge, _ = self.request("POST",f"/api/tasks/{successor['id']}/dependencies",{"version":successor["version"],"predecessor_id":predecessor["id"],"predecessor_version":predecessor["version"],"due_policy":"push_successor_once"},cookie=cookie,csrf=csrf)
        self.assertEqual(status,201,edge); self.assertEqual(edge["date_result"]["after"],"2026-09-10")
        status, successor_detail, _ = self.request("GET",f"/api/tasks/{successor['id']}",cookie=cookie)
        self.assertTrue(successor_detail["relations"]["blocked"]); self.assertEqual(successor_detail["due"],"2026-09-10")
        status, direct_cycle, _ = self.request("POST",f"/api/tasks/{predecessor['id']}/dependencies",{"version":edge["predecessor_version"],"predecessor_id":successor["id"],"predecessor_version":edge["task_version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,direct_cycle["error"]["code"]),(422,"DEPENDENCY_CYCLE"))
        x,y,z=create("Graph X"),create("Graph Y"),create("Graph Z")
        status, xy, _ = self.request("POST",f"/api/tasks/{y['id']}/dependencies",{"version":y["version"],"predecessor_id":x["id"],"predecessor_version":x["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,xy)
        status, yz, _ = self.request("POST",f"/api/tasks/{z['id']}/dependencies",{"version":z["version"],"predecessor_id":y["id"],"predecessor_version":xy["task_version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,yz)
        status, long_cycle, _ = self.request("POST",f"/api/tasks/{x['id']}/dependencies",{"version":xy["predecessor_version"],"predecessor_id":z["id"],"predecessor_version":yz["task_version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,long_cycle["error"]["code"]),(422,"DEPENDENCY_CYCLE"))
        status, duplicate, _ = self.request("POST",f"/api/tasks/{y['id']}/dependencies",{"version":yz["predecessor_version"],"predecessor_id":x["id"],"predecessor_version":xy["predecessor_version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,duplicate["error"]["code"]),(409,"DEPENDENCY_DUPLICATE"))
        status, self_edge, _ = self.request("POST",f"/api/tasks/{x['id']}/dependencies",{"version":xy["predecessor_version"],"predecessor_id":x["id"],"predecessor_version":xy["predecessor_version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,self_edge["error"]["code"]),(422,"DEPENDENCY_SELF"))
        status, archived_x, _ = self.request("POST",f"/api/tasks/{x['id']}/archive",{"version":xy["predecessor_version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,archived_x)
        _, y_detail, _ = self.request("GET",f"/api/tasks/{y['id']}",cookie=cookie);self.assertFalse(y_detail["relations"]["blocked"])
        status, restored_x, _ = self.request("POST",f"/api/tasks/{x['id']}/unarchive",{"version":archived_x["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,restored_x)
        _, y_detail, _ = self.request("GET",f"/api/tasks/{y['id']}",cookie=cookie);self.assertTrue(y_detail["relations"]["blocked"])
        status, completed, _ = self.request("PATCH",f"/api/tasks/{predecessor['id']}",{"version":edge["predecessor_version"],"status":"已完成"},cookie=cookie,csrf=csrf)
        self.assertEqual(status,200,completed)
        _, successor_detail, _ = self.request("GET",f"/api/tasks/{successor['id']}",cookie=cookie)
        self.assertFalse(successor_detail["relations"]["blocked"])
        predecessor_relation=successor_detail["relations"]["predecessors"][0]
        status, removed, _ = self.request("DELETE",f"/api/tasks/{successor['id']}/dependencies/{edge['id']}",{"version":edge["task_version"],"dependency_version":edge["version"],"predecessor_version":predecessor_relation["predecessor_task_version"]},cookie=cookie,csrf=csrf)
        self.assertEqual(status,200,removed)
        status, parent_delete, _ = self.request("DELETE",f"/api/tasks/{parent['id']}",{"version":parent["version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,parent_delete["error"]["code"]),(409,"ACTIVE_SUBTASKS"))
        status, board2, _ = self.request("POST","/api/workspaces/1/boards",{"name":"Other"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,board2)
        status, group2, _ = self.request("POST",f"/api/boards/{board2['id']}/groups",{"name":"Other group"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,group2)
        status, other_task, _ = self.request("POST",f"/api/groups/{group2['id']}/tasks",{"title":"Other task"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,other_task)
        status, cross_parent, _ = self.request("POST",f"/api/tasks/{child_b['id']}/parent",{"version":moved["version"],"board_version":moved["board_version"],"parent_id":other_task["id"],"position":0},cookie=cookie,csrf=csrf)
        self.assertEqual((status,cross_parent["error"]["code"]),(422,"HIERARCHY_PARENT_INVALID"))
        status, cross_edge, _ = self.request("POST",f"/api/tasks/{child_b['id']}/dependencies",{"version":moved["version"],"predecessor_id":other_task["id"],"predecessor_version":other_task["version"]},cookie=cookie,csrf=csrf)
        self.assertEqual((status,cross_edge["error"]["code"]),(422,"DEPENDENCY_CROSS_BOARD"))
        status, _, _ = self.request("PATCH","/api/admin/workspace-memberships/u2?workspace_id=1",{"role":"viewer"},cookie=cookie,csrf=csrf);self.assertEqual(status,200)
        viewer_cookie, viewer_csrf = self.login("u2")
        status, denied, _ = self.request("POST",f"/api/tasks/{child_a['id']}/parent",{"version":child_a["version"],"board_version":moved["board_version"],"parent_id":None,"position":0},cookie=viewer_cookie,csrf=viewer_csrf)
        self.assertEqual((status,denied["error"]["code"]),(403,"READ_ONLY"))

    def test_advanced_fields_relations_mirror_formula_and_acl(self):
        cookie,csrf=self.login();_,boot,_=self.request("GET","/api/bootstrap",cookie=cookie)
        source_board=boot["board"]["id"];source_task=boot["groups"][0]["tasks"][0]
        status,target_board,_=self.request("POST","/api/workspaces/1/boards",{"name":"I7 目标","access_type":"open"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,target_board)
        status,target_group,_=self.request("POST",f"/api/boards/{target_board['id']}/groups",{"name":"目标组"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,target_group)
        status,target_task,_=self.request("POST",f"/api/groups/{target_group['id']}/tasks",{"title":"受控来源"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,target_task)
        _,target_boot,_=self.request("GET",f"/api/bootstrap?board_id={target_board['id']}",cookie=cookie)
        status,amount,_=self.request("POST",f"/api/boards/{target_board['id']}/fields",{"board_version":target_boot["board"]["version"],"name":"金额","field_type":"number","config":{},"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,amount)
        status,updated,_=self.request("PATCH",f"/api/tasks/{target_task['id']}",{"version":target_task["version"],"field_values":{str(amount["id"]):42}},cookie=cookie,csrf=csrf);self.assertEqual(status,200,updated);target_task["version"]=updated["version"]
        _,boot,_=self.request("GET",f"/api/bootstrap?board_id={source_board}",cookie=cookie);board_version=boot["board"]["version"]
        fields={}
        for kind,name,config in [("timeline","周期",{}),("rating","评分",{"max":5}),("file","文件",{}),("email","邮箱",{}),("phone","电话",{})]:
            status,created,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":name,"field_type":kind,"config":config,"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,created);fields[kind]=created["id"];board_version=created["board_version"]
        status,tags,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":"标签","field_type":"tags","config":{},"options":[{"label":"红","color":"orange"},{"label":"蓝","color":"blue"}]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,tags);board_version=tags["board_version"]
        status,relation,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":"关联","field_type":"relation","config":{"target_board_id":target_board["id"],"bidirectional":True},"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,relation);board_version=relation["board_version"]
        status,mirror,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":"镜像金额","field_type":"mirror","config":{"relation_field_id":relation["id"],"source_field_id":amount["id"]},"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,mirror);board_version=mirror["board_version"]
        status,formula,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":"汇总","field_type":"formula","config":{"expression":f"SUM(f{mirror['id']})"},"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,formula);board_version=formula["board_version"]
        status,conditional,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":"条件","field_type":"formula","config":{"expression":f"IF(f{formula['id']} > 40, '高', '低')"},"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,conditional);board_version=conditional["board_version"]
        status,mixed_formula,_=self.request("POST",f"/api/boards/{source_board}/fields",{"board_version":board_version,"name":"异构公式","field_type":"formula","config":{"expression":f"IF(f{fields['rating']} > 3, f{fields['rating']}, 'none')"},"options":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,mixed_formula);board_version=mixed_formula["board_version"]
        status,advanced_template,_=self.request("POST","/api/workspaces/1/templates",{"source_board_id":source_board,"name":"外部关系模板","template_type":"project","include_tasks":False},cookie=cookie,csrf=csrf);self.assertEqual(status,201,advanced_template);status,advanced_copy,_=self.request("POST",f"/api/templates/{advanced_template['id']}/instantiate",{"name":"外部关系安全副本"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,advanced_copy);_,advanced_boot,_=self.request("GET",f"/api/bootstrap?board_id={advanced_copy['id']}",cookie=cookie);copied_by_name={item["name"]:item for item in advanced_boot["fields"]};self.assertEqual((copied_by_name["关联"]["is_active"],copied_by_name["关联"]["config"].get("target_board_id"),copied_by_name["关联"]["config"].get("template_unbound")),(0,None,True));self.assertEqual((copied_by_name["镜像金额"]["is_active"],copied_by_name["汇总"]["is_active"],copied_by_name["条件"]["is_active"]),(0,0,0))
        status,cycle,_=self.request("PATCH",f"/api/fields/{formula['id']}",{"version":formula["version"],"config":{"expression":f"f{conditional['id']}"}},cookie=cookie,csrf=csrf);self.assertEqual((status,cycle["error"]["code"]),(422,"FORMULA_CYCLE"))
        _,source_boot,_=self.request("GET",f"/api/bootstrap?board_id={source_board}",cookie=cookie);tag_payload=next(item for item in source_boot["fields"] if item["id"]==tags["id"]);tag_ids=[item["id"] for item in tag_payload["options"]];status_payload=next(item for item in source_boot["fields"] if item["field_type"]=="status");status_id=status_payload["id"];status_option=status_payload["options"][0]["id"]
        values={str(fields["timeline"]):{"start":"2026-08-01","end":"2026-08-03"},str(fields["rating"]):4,str(fields["file"]):{"name":"brief.pdf","size":123,"media_type":"application/pdf"},str(fields["email"]):"team@example.com",str(fields["phone"]):"+86 138-0000-0000",str(tags["id"]):tag_ids,str(status_id):status_option}
        status,updated,_=self.request("PATCH",f"/api/tasks/{source_task['id']}",{"version":source_task["version"],"field_values":values},cookie=cookie,csrf=csrf);self.assertEqual(status,200,updated);source_task["version"]=updated["version"]
        status,mixed_task,_=self.request("POST",f"/api/groups/{source_task['group_id']}/tasks",{"title":"异构文本结果"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,mixed_task)
        status,mixed_task,_=self.request("PATCH",f"/api/tasks/{mixed_task['id']}",{"version":mixed_task["version"],"field_values":{str(fields["rating"]):2}},cookie=cookie,csrf=csrf);self.assertEqual(status,200,mixed_task)
        status,bad,_=self.request("PATCH",f"/api/tasks/{source_task['id']}",{"version":source_task["version"],"field_values":{str(fields["email"]):"bad"}},cookie=cookie,csrf=csrf);self.assertEqual((status,bad["error"]["code"]),(422,"VALIDATION_ERROR"))
        status,linked,_=self.request("POST",f"/api/tasks/{source_task['id']}/relations/{relation['id']}",{"version":source_task["version"],"board_version":board_version,"target_task_id":target_task["id"],"target_version":target_task["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,linked);source_task["version"]=linked["task_version"]
        status,detail,_=self.request("GET",f"/api/tasks/{source_task['id']}",cookie=cookie);self.assertEqual(status,200,detail);self.assertEqual(detail["field_values"][str(mirror["id"])],[42]);self.assertEqual(detail["field_values"][str(formula["id"])],42);self.assertEqual(detail["field_values"][str(conditional["id"])],"高")
        _,back,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertTrue(any(item["task_id"]==source_task["id"] for item in back["relation_backlinks"]))
        status,result,_=self.request("POST",f"/api/boards/{source_board}/query",{"version":1,"filter":{"field":{"kind":"dynamic","id":formula["id"]},"operator":"equals","value":42},"sort":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,result);self.assertIn(source_task["id"],[task["id"] for task in result["tasks"]])
        def query(filter_ast,sort=None,limit=100,offset=0):
            status,payload,_=self.request("POST",f"/api/boards/{source_board}/query",{"version":1,"filter":filter_ast,"sort":sort or [],"limit":limit,"offset":offset},cookie=cookie,csrf=csrf);self.assertEqual(status,200,payload);return payload
        mixed_ref={"kind":"dynamic","id":mixed_formula["id"]}
        self.assertIn(source_task["id"],[item["id"] for item in query({"field":mixed_ref,"operator":"gt","value":0})["tasks"]]);self.assertIn(mixed_task["id"],[item["id"] for item in query({"field":mixed_ref,"operator":"equals","value":"none"})["tasks"]]);self.assertIn(mixed_task["id"],[item["id"] for item in query({"field":mixed_ref,"operator":"contains","value":"non"})["tasks"]]);query({"field":mixed_ref,"operator":"between","value":[0,10]});mixed_sorted=query({"op":"and","children":[]},[{"field":mixed_ref,"direction":"asc","nulls":"last"}],1,0);self.assertEqual(mixed_sorted["limit"],1)
        derived={"op":"or","children":[{"field":{"kind":"dynamic","id":formula["id"]},"operator":"is_empty","value":None},{"field":{"kind":"dynamic","id":formula["id"]},"operator":"is_not_empty","value":None}]}
        relation_match={"field":{"kind":"dynamic","id":relation["id"]},"operator":"contains_any","value":[target_task["id"]]}
        self.assertEqual([source_task["id"]],[task["id"] for task in query({"op":"and","children":[{"field":{"kind":"dynamic","id":formula["id"]},"operator":"equals","value":42},relation_match]})["tasks"]])
        self.assertEqual([],query({"op":"and","children":[{"field":{"kind":"dynamic","id":formula["id"]},"operator":"equals","value":42},dict(relation_match,value=[999999])]})["tasks"])
        for plain in ({"field":{"kind":"dynamic","id":status_id},"operator":"in","value":[status_option]},{"field":{"kind":"dynamic","id":tags["id"]},"operator":"contains_any","value":[tag_ids[0]]},{"field":{"kind":"dynamic","id":tags["id"]},"operator":"contains_all","value":tag_ids},{"field":{"kind":"dynamic","id":fields["timeline"]},"operator":"equals","value":"2026-08-01"},{"field":{"kind":"dynamic","id":fields["file"]},"operator":"contains","value":"brief"}):
            direct=query(plain);replayed=query({"op":"and","children":[plain,derived]});self.assertEqual([task["id"] for task in direct["tasks"]],[task["id"] for task in replayed["tasks"]])
        sort=[{"field":{"kind":"dynamic","id":mirror["id"]},"direction":"asc","nulls":"last"},{"field":{"kind":"dynamic","id":formula["id"]},"direction":"desc","nulls":"last"}]
        whole=query(derived,sort);pages=[query(derived,sort,1,index)["tasks"] for index in range(min(whole["total"],3))];self.assertEqual([task["id"] for page in pages for task in page],[task["id"] for task in whole["tasks"][:len(pages)]])
        view_body={"name":"I7 派生视图","scope":"personal","is_default":False,"filter":{"op":"and","children":[relation_match,derived]},"sort":sort,"visible_fields":[relation["id"],mirror["id"],formula["id"]],"column_order":["title",relation["id"],mirror["id"],formula["id"]]}
        status,saved,_=self.request("POST",f"/api/boards/{source_board}/views",view_body,cookie=cookie,csrf=csrf);self.assertEqual(status,201,saved);_,listing,_=self.request("GET",f"/api/boards/{source_board}/views",cookie=cookie);loaded=next(item for item in listing["views"] if item["id"]==saved["id"]);self.assertEqual([task["id"] for task in query(loaded["filter"],loaded["sort"])["tasks"]],[source_task["id"]])
        empty_relation={"field":{"kind":"dynamic","id":relation["id"]},"operator":"is_empty","value":None}
        def assert_relation_consistent(visible):
            _,current,_=self.request("GET",f"/api/tasks/{source_task['id']}",cookie=cookie);related=current["field_values"].get(str(relation["id"])) or [];self.assertEqual(any(item["id"]==target_task["id"] for item in related),visible)
            direct_empty=query(empty_relation);derived_empty=query({"op":"and","children":[empty_relation,derived]});self.assertEqual([item["id"] for item in direct_empty["tasks"]],[item["id"] for item in derived_empty["tasks"]])
            direct_contains=query(relation_match);derived_contains=query({"op":"and","children":[relation_match,derived]});self.assertEqual([item["id"] for item in direct_contains["tasks"]],[item["id"] for item in derived_contains["tasks"]]);self.assertEqual(source_task["id"] in [item["id"] for item in direct_contains["tasks"]],visible)
            relation_sort=[{"field":{"kind":"dynamic","id":relation["id"]},"direction":"asc","nulls":"last"}];self.assertEqual([item["id"] for item in query({"op":"and","children":[]},relation_sort)["tasks"]],[item["id"] for item in query(derived,relation_sort)["tasks"]])
        status,archived_target,_=self.request("POST",f"/api/tasks/{target_task['id']}/archive",{"version":target_task["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,archived_target);assert_relation_consistent(False)
        status,target_task,_=self.request("POST",f"/api/tasks/{target_task['id']}/unarchive",{"version":archived_target["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,target_task);assert_relation_consistent(True)
        _,fresh_group,_=self.request("GET",f"/api/groups/{target_group['id']}",cookie=cookie)
        status,archived_group,_=self.request("POST",f"/api/groups/{target_group['id']}/archive",{"version":fresh_group["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,archived_group);assert_relation_consistent(False)
        status,restored_group,_=self.request("POST",f"/api/groups/{target_group['id']}/unarchive",{"version":archived_group["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,restored_group);assert_relation_consistent(True)
        status,deleted_group,_=self.request("DELETE",f"/api/groups/{target_group['id']}",{"version":restored_group["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,deleted_group);assert_relation_consistent(False)
        status,restored_group,_=self.request("POST",f"/api/groups/{target_group['id']}/restore",{"version":deleted_group["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,restored_group);assert_relation_consistent(True)
        status,deleted_target,_=self.request("DELETE",f"/api/tasks/{target_task['id']}",{"version":target_task["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,deleted_target);assert_relation_consistent(False)
        status,target_task,_=self.request("POST",f"/api/tasks/{target_task['id']}/restore",{"version":deleted_target["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,target_task);assert_relation_consistent(True)
        status,archived_source,_=self.request("POST",f"/api/tasks/{source_task['id']}/archive",{"version":source_task["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,archived_source)
        _,back_hidden,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertFalse(any(item["task_id"]==source_task["id"] for item in back_hidden["relation_backlinks"]))
        status,source_restored,_=self.request("POST",f"/api/tasks/{source_task['id']}/unarchive",{"version":archived_source["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_restored);source_task["version"]=source_restored["version"];linked["task_version"]=source_restored["version"]
        status,source_deleted,_=self.request("DELETE",f"/api/tasks/{source_task['id']}",{"version":source_task["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_deleted)
        _,back_hidden,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertFalse(any(item["task_id"]==source_task["id"] for item in back_hidden["relation_backlinks"]))
        status,source_restored,_=self.request("POST",f"/api/tasks/{source_task['id']}/restore",{"version":source_deleted["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_restored);source_task["version"]=source_restored["version"];linked["task_version"]=source_restored["version"]
        _,fresh_source_group,_=self.request("GET",f"/api/groups/{source_task['group_id']}",cookie=cookie);status,source_group_archived,_=self.request("POST",f"/api/groups/{source_task['group_id']}/archive",{"version":fresh_source_group["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_group_archived)
        _,back_hidden,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertFalse(any(item["task_id"]==source_task["id"] for item in back_hidden["relation_backlinks"]))
        status,source_group_restored,_=self.request("POST",f"/api/groups/{source_task['group_id']}/unarchive",{"version":source_group_archived["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_group_restored)
        status,source_group_deleted,_=self.request("DELETE",f"/api/groups/{source_task['group_id']}",{"version":source_group_restored["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_group_deleted)
        _,back_hidden,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertFalse(any(item["task_id"]==source_task["id"] for item in back_hidden["relation_backlinks"]))
        status,source_group_restored,_=self.request("POST",f"/api/groups/{source_task['group_id']}/restore",{"version":source_group_deleted["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_group_restored)
        _,fresh_source_board,_=self.request("GET",f"/api/bootstrap?board_id={source_board}",cookie=cookie);status,source_board_archived,_=self.request("POST",f"/api/boards/{source_board}/archive",{"version":fresh_source_board["board"]["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_board_archived)
        _,back_hidden,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertFalse(any(item["task_id"]==source_task["id"] for item in back_hidden["relation_backlinks"]))
        status,source_board_restored,_=self.request("POST",f"/api/boards/{source_board}/unarchive",{"version":source_board_archived["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_board_restored)
        status,source_board_deleted,_=self.request("DELETE",f"/api/boards/{source_board}",{"version":source_board_restored["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_board_deleted)
        _,back_hidden,_=self.request("GET",f"/api/tasks/{target_task['id']}",cookie=cookie);self.assertFalse(any(item["task_id"]==source_task["id"] for item in back_hidden["relation_backlinks"]))
        status,source_board_restored,_=self.request("POST",f"/api/boards/{source_board}/restore",{"version":source_board_deleted["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,source_board_restored)
        _,target_before_delete,_=self.request("GET",f"/api/bootstrap?board_id={target_board['id']}",cookie=cookie);status,target_archived,_=self.request("POST",f"/api/boards/{target_board['id']}/archive",{"version":target_before_delete["board"]["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,target_archived)
        status,archived_query,_=self.request("POST",f"/api/boards/{source_board}/query",{"version":1,"filter":relation_match,"sort":[]},cookie=cookie,csrf=csrf);self.assertEqual((status,archived_query["error"]["code"]),(403,"FIELD_SOURCE_FORBIDDEN"))
        status,target_unarchived,_=self.request("POST",f"/api/boards/{target_board['id']}/unarchive",{"version":target_archived["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,target_unarchived)
        status,target_deleted,_=self.request("DELETE",f"/api/boards/{target_board['id']}",{"version":target_unarchived["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,target_deleted)
        denied=[]
        for ast in (relation_match,{"op":"and","children":[relation_match,derived]}):
            status,payload,_=self.request("POST",f"/api/boards/{source_board}/query",{"version":1,"filter":ast,"sort":[]},cookie=cookie,csrf=csrf);denied.append((status,payload["error"]["code"]))
        self.assertEqual(denied,[(403,"FIELD_SOURCE_FORBIDDEN"),(403,"FIELD_SOURCE_FORBIDDEN")])
        status,target_board_restored,_=self.request("POST",f"/api/boards/{target_board['id']}/restore",{"version":target_deleted["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,target_board_restored);assert_relation_consistent(True)
        _,target_boot,_=self.request("GET",f"/api/bootstrap?board_id={target_board['id']}",cookie=cookie)
        status,private,_=self.request("PATCH",f"/api/boards/{target_board['id']}",{"version":target_boot["board"]["version"],"access_type":"private"},cookie=cookie,csrf=csrf);self.assertEqual(status,200,private)
        member_cookie,member_csrf=self.login("u2")
        responses=[]
        for source_id in (amount["id"],999999):
            status,payload,_=self.request("PATCH",f"/api/fields/{mirror['id']}",{"version":mirror["version"],"config":{"relation_field_id":relation["id"],"source_field_id":source_id}},cookie=member_cookie,csrf=member_csrf);responses.append((status,payload))
        self.assertEqual(responses[0],responses[1]);self.assertEqual((responses[0][0],responses[0][1]["error"]["code"]),(403,"MIRROR_SOURCE_FORBIDDEN"))
        status,opened,_=self.request("PATCH",f"/api/boards/{target_board['id']}",{"version":private["version"],"access_type":"open"},cookie=cookie,csrf=csrf);self.assertEqual(status,200,opened)
        status,restored,_=self.request("PATCH",f"/api/fields/{mirror['id']}",{"version":mirror["version"],"config":{"relation_field_id":relation["id"],"source_field_id":amount["id"]}},cookie=member_cookie,csrf=member_csrf);self.assertEqual(status,200,restored);mirror["version"]=restored["version"]
        status,private,_=self.request("PATCH",f"/api/boards/{target_board['id']}",{"version":opened["version"],"access_type":"private"},cookie=cookie,csrf=csrf);self.assertEqual(status,200,private)
        self.request("PATCH","/api/admin/workspace-memberships/u2?workspace_id=1",{"role":"viewer"},cookie=cookie,csrf=csrf);viewer_cookie,viewer_csrf=self.login("u2")
        status,viewer_boot,_=self.request("GET",f"/api/bootstrap?board_id={source_board}",cookie=viewer_cookie);self.assertEqual(status,200,viewer_boot);payload=next(field for field in viewer_boot["fields"] if field["id"]==relation["id"]);self.assertEqual(payload["config"],{"unavailable":True})
        view_task=next(task for group in viewer_boot["groups"] for task in group["tasks"] if task["id"]==source_task["id"]);self.assertIsNone(view_task["field_values"][str(mirror["id"])]);self.assertEqual(view_task["field_diagnostics"][str(mirror["id"])]["code"],"FIELD_SOURCE_UNAVAILABLE")
        status,forbidden,_=self.request("GET",f"/api/fields/{relation['id']}/targets",cookie=viewer_cookie);self.assertEqual(status,403,forbidden)
        status,query_forbidden,_=self.request("POST",f"/api/boards/{source_board}/query",{"version":1,"filter":{"field":{"kind":"dynamic","id":relation["id"]},"operator":"is_empty","value":None},"sort":[]},cookie=viewer_cookie,csrf=viewer_csrf);self.assertEqual((status,query_forbidden["error"]["code"]),(403,"FIELD_SOURCE_FORBIDDEN"))
        status,export_forbidden,_=self.request("POST",f"/api/boards/{source_board}/export",{"format":"csv","visible_fields":[relation["id"],mirror["id"],formula["id"]]},cookie=viewer_cookie,csrf=viewer_csrf);self.assertEqual((status,export_forbidden["error"]["code"]),(403,"FIELD_SOURCE_FORBIDDEN"))
        check=sqlite3.connect(self.db_path)
        try:self.assertEqual(check.execute("SELECT COUNT(*) FROM task_relation_values WHERE id=? AND deleted_at IS NULL",(linked["id"],)).fetchone()[0],1)
        finally:check.close()
        _,fresh_source,_=self.request("GET",f"/api/bootstrap?board_id={source_board}",cookie=cookie);linked["board_version"]=fresh_source["board"]["version"]
        status,deleted,_=self.request("DELETE",f"/api/tasks/{source_task['id']}/relations/{linked['id']}",{"version":linked["task_version"],"board_version":linked["board_version"],"relation_version":linked["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,deleted)
        status,stale,_=self.request("DELETE",f"/api/tasks/{source_task['id']}/relations/{linked['id']}",{"version":linked["task_version"],"board_version":linked["board_version"],"relation_version":linked["version"]},cookie=cookie,csrf=csrf);self.assertEqual((status,stale["error"]["code"]),(409,"VERSION_CONFLICT"))

    def test_templates_import_export_and_spreadsheet_safety(self):
        cookie,csrf=self.login();_,boot,_=self.request("GET","/api/bootstrap",cookie=cookie);board=boot["board"];group=boot["groups"][0]
        source_field=boot["fields"][0];status,view,_=self.request("POST",f"/api/boards/{board['id']}/views",{"name":"模板共享视图","scope":"shared","view_type":"table","filter":{"op":"and","children":[]},"sort":[],"visible_fields":[source_field["id"]],"column_order":["title",source_field["id"]],"presentation":{"version":1,"widths":{str(source_field["id"]):180},"frozen_columns":["title",source_field["id"]]}},cookie=cookie,csrf=csrf);self.assertEqual(status,201,view)
        status,template,_=self.request("POST","/api/workspaces/1/templates",{"source_board_id":board["id"],"name":"无样例模板","template_type":"board","include_tasks":False},cookie=cookie,csrf=csrf);self.assertEqual(status,201,template)
        status,copy,_=self.request("POST",f"/api/templates/{template['id']}/instantiate",{"name":"模板副本"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,copy)
        _,copy_boot,_=self.request("GET",f"/api/bootstrap?board_id={copy['id']}",cookie=cookie);self.assertEqual([item["name"] for item in copy_boot["groups"]],[item["name"] for item in boot["groups"]]);self.assertFalse(any(item["tasks"] for item in copy_boot["groups"]));self.assertNotEqual([item["id"] for item in copy_boot["fields"]],[item["id"] for item in boot["fields"]]);copied_view=next(item for item in copy_boot["saved_views"] if item["name"]=="模板共享视图");copied_field=next(item for item in copy_boot["fields"] if item["name"]==source_field["name"]);self.assertEqual(copied_view["visible_fields"],[copied_field["id"]]);self.assertEqual(copied_view["presentation"]["widths"],{str(copied_field["id"]):180})
        status,updated,_=self.request("PATCH",f"/api/templates/{template['id']}",{"version":1,"name":"更新模板"},cookie=cookie,csrf=csrf);self.assertEqual(status,200,updated);status,deleted,_=self.request("DELETE",f"/api/templates/{template['id']}",{"version":updated["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,deleted);_,active,_=self.request("GET","/api/workspaces/1/templates",cookie=cookie);self.assertFalse(active["templates"]);_,trashed,_=self.request("GET","/api/workspaces/1/templates?include_deleted=1",cookie=cookie);self.assertEqual(trashed["templates"][0]["deleted_at"] is not None,True);status,restored,_=self.request("POST",f"/api/templates/{template['id']}/restore",{"version":deleted["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,restored)
        raw="Title,Status\n正常任务,进行中\n=2+2,已完成\n".encode();status,preview,_=self.request("POST",f"/api/boards/{board['id']}/imports/preview",{"filename":"tasks.csv","content_base64":base64.b64encode(raw).decode(),"board_version":board["version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,preview)
        status_field=next(item for item in boot["fields"] if item["system_key"]=="status");status,committed,_=self.request("POST",f"/api/boards/{board['id']}/imports/commit",{"batch_id":preview["batch_id"],"batch_version":preview["batch_version"],"board_version":board["version"],"group_id":group["id"],"mapping":[{"column":"Title","target":{"kind":"core","key":"title"}},{"column":"Status","target":{"kind":"dynamic","id":status_field["id"]}}]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,committed);self.assertEqual(committed["created"],2);_,queried,_=self.request("POST",f"/api/boards/{board['id']}/query",{"version":1,"filter":{"field":{"kind":"core","key":"title"},"operator":"equals","value":"正常任务"},"sort":[]},cookie=cookie,csrf=csrf);self.assertEqual(queried["tasks"][0]["status"],"进行中")
        status,exported,_=self.request("POST",f"/api/boards/{board['id']}/export",{"format":"xlsx","visible_fields":[]},cookie=cookie,csrf=csrf);self.assertEqual(status,200,exported);parsed=parse_upload("roundtrip.xlsx",base64.b64decode(exported["content_base64"]));self.assertIn("=2+2",[row[0].lstrip("'") for row in parsed["rows"]]);self.assertTrue(any(row[0].startswith("'") for row in parsed["rows"] if "=2+2" in row[0]))
        for dangerous in ("=1","+1","-1","@cmd","  =1","\t+1","\x01-1","\x00@cmd"):self.assertEqual(safe_cell(dangerous),"'"+dangerous)
        unsafe=make_xlsx(["Title"],[["=SUM(1,2)"]]);self.assertEqual(parse_upload("safe.xlsx",unsafe)["rows"][0][0],"'=SUM(1,2)")
        bad=b"Title,Status\nwould-write,\nrollback-me,not-an-option\n";status,bad_preview,_=self.request("POST",f"/api/boards/{board['id']}/imports/preview",{"filename":"bad.csv","content_base64":base64.b64encode(bad).decode(),"board_version":committed["board_version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,bad_preview);status,error,_=self.request("POST",f"/api/boards/{board['id']}/imports/commit",{"batch_id":bad_preview["batch_id"],"batch_version":1,"board_version":committed["board_version"],"group_id":group["id"],"mapping":[{"column":"Title","target":{"kind":"core","key":"title"}},{"column":"Status","target":{"kind":"dynamic","id":status_field["id"]}}]},cookie=cookie,csrf=csrf);self.assertEqual((status,error["error"]["code"]),(422,"IMPORT_VALUE_INVALID"));self.assertEqual(error["error"]["details"],{"row":3,"header":"Status","field_id":status_field["id"],"field_type":"status"});_,rolled_back,_=self.request("POST",f"/api/boards/{board['id']}/query",{"version":1,"filter":{"field":{"kind":"core","key":"title"},"operator":"contains","value":"write"},"sort":[]},cookie=cookie,csrf=csrf);self.assertEqual(rolled_back["total"],0)
        workbook=make_two_sheet_xlsx(["Title"],[["ignore-first"]],["Title","Status"],[["xlsx-before",""],["xlsx-bad","not-an-option"]]);status,xlsx_preview,_=self.request("POST",f"/api/boards/{board['id']}/imports/preview",{"filename":"multi.xlsx","content_base64":base64.b64encode(workbook).decode(),"sheet":"Second","board_version":committed["board_version"]},cookie=cookie,csrf=csrf);self.assertEqual(status,201,xlsx_preview);self.assertEqual((xlsx_preview["sheet"],xlsx_preview["sheets"]),("Second",["First","Second"]));status,xlsx_error,_=self.request("POST",f"/api/boards/{board['id']}/imports/commit",{"batch_id":xlsx_preview["batch_id"],"batch_version":1,"board_version":committed["board_version"],"group_id":group["id"],"mapping":[{"column":"Title","target":{"kind":"core","key":"title"}},{"column":"Status","target":{"kind":"dynamic","id":status_field["id"]}}]},cookie=cookie,csrf=csrf);self.assertEqual((status,xlsx_error["error"]["details"]["row"],xlsx_error["error"]["details"]["header"]),(422,3,"Status"));_,xlsx_rolled_back,_=self.request("POST",f"/api/boards/{board['id']}/query",{"version":1,"filter":{"field":{"kind":"core","key":"title"},"operator":"contains","value":"xlsx-"},"sort":[]},cookie=cookie,csrf=csrf);self.assertEqual(xlsx_rolled_back["total"],0)
        due_field=next(item for item in boot["fields"] if item["system_key"]=="due");date_bad=b"Title,Due\ndate-before,2026-08-03\ndate-bad,03/08/2026\n";_,date_preview,_=self.request("POST",f"/api/boards/{board['id']}/imports/preview",{"filename":"date.csv","content_base64":base64.b64encode(date_bad).decode(),"board_version":committed["board_version"]},cookie=cookie,csrf=csrf);status,date_error,_=self.request("POST",f"/api/boards/{board['id']}/imports/commit",{"batch_id":date_preview["batch_id"],"batch_version":1,"board_version":committed["board_version"],"group_id":group["id"],"mapping":[{"column":"Title","target":{"kind":"core","key":"title"}},{"column":"Due","target":{"kind":"dynamic","id":due_field["id"]}}]},cookie=cookie,csrf=csrf);self.assertEqual((status,date_error["error"]["details"]["row"],date_error["error"]["details"]["header"],date_error["error"]["details"]["field_type"]),(422,3,"Due","date"))
        title_bad=b"Title,Status\n,not-an-option\n";_,title_preview,_=self.request("POST",f"/api/boards/{board['id']}/imports/preview",{"filename":"title.csv","content_base64":base64.b64encode(title_bad).decode(),"board_version":committed["board_version"]},cookie=cookie,csrf=csrf);status,title_error,_=self.request("POST",f"/api/boards/{board['id']}/imports/commit",{"batch_id":title_preview["batch_id"],"batch_version":1,"board_version":committed["board_version"],"group_id":group["id"],"mapping":[{"column":"Title","target":{"kind":"core","key":"title"}}]},cookie=cookie,csrf=csrf);self.assertEqual((status,title_error["error"]["details"]),(422,{"row":2,"header":"Title","field":"title","field_type":"text"}))
        check=sqlite3.connect(self.db_path)
        try:
            self.assertEqual(check.execute("SELECT version FROM boards WHERE id=?",(board["id"],)).fetchone()[0],committed["board_version"]);self.assertEqual(check.execute("SELECT COUNT(*) FROM tasks WHERE title LIKE 'date-%' OR title LIKE 'xlsx-%' OR title IN ('would-write','rollback-me')").fetchone()[0],0);self.assertEqual(check.execute("SELECT COUNT(*) FROM import_batches WHERE id IN (?,?,?,?) AND status='previewed' AND version=1",(bad_preview["batch_id"],xlsx_preview["batch_id"],date_preview["batch_id"],title_preview["batch_id"])).fetchone()[0],4);self.assertEqual(check.execute("SELECT COUNT(*) FROM activity WHERE action_code='import.committed'").fetchone()[0],1)
        finally:check.close()
        self.request("PATCH","/api/admin/workspace-memberships/u2?workspace_id=1",{"role":"viewer"},cookie=cookie,csrf=csrf);viewer_cookie,viewer_csrf=self.login("u2");status,_,_=self.request("POST",f"/api/workspaces/1/templates",{"source_board_id":board["id"],"name":"forbidden","include_tasks":False},cookie=viewer_cookie,csrf=viewer_csrf);self.assertEqual(status,403);status,_,_=self.request("POST",f"/api/boards/{board['id']}/imports/preview",{"filename":"x.csv","content_base64":base64.b64encode(b"Title\nx\n").decode(),"board_version":committed["board_version"]},cookie=viewer_cookie,csrf=viewer_csrf);self.assertEqual(status,403);status,_,_=self.request("POST",f"/api/boards/{board['id']}/export",{"format":"csv","visible_fields":[]},cookie=viewer_cookie,csrf=viewer_csrf);self.assertEqual(status,200)

    def test_export_hard_limit_at_1000_before_materialization(self):
        cookie,csrf=self.login();status,board,_=self.request("POST","/api/workspaces/1/boards",{"name":"Export boundary"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,board);status,group,_=self.request("POST",f"/api/boards/{board['id']}/groups",{"name":"Rows"},cookie=cookie,csrf=csrf);self.assertEqual(status,201,group)
        conn=sqlite3.connect(self.db_path);stamp="2026-08-02T00:00:00+00:00"
        try:
            conn.executemany("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",[(group["id"],f"boundary-{index:04d}","待开始","中","未设置","u1",index,index,stamp,stamp) for index in range(1000)]);conn.commit()
        finally:conn.close()
        query={"version":1,"filter":{"field":{"kind":"core","key":"title"},"operator":"contains","value":"boundary-"},"sort":[]};view_body={"name":"Boundary view","scope":"shared","view_type":"table","filter":query["filter"],"sort":[],"visible_fields":[],"column_order":["title"],"presentation":{"version":1,"widths":{},"frozen_columns":[]}};status,view,_=self.request("POST",f"/api/boards/{board['id']}/views",view_body,cookie=cookie,csrf=csrf);self.assertEqual(status,201,view)
        allowed=[{"format":"csv","visible_fields":[]},{"format":"xlsx","query":query,"visible_fields":[]},{"format":"csv","view_id":view["id"]}]
        for payload in allowed:
            status,exported,_=self.request("POST",f"/api/boards/{board['id']}/export",payload,cookie=cookie,csrf=csrf);self.assertEqual((status,exported.get("row_count")),(200,1000),payload)
        conn=sqlite3.connect(self.db_path)
        try:conn.execute("INSERT INTO tasks(group_id,title,status,priority,due,owner_id,sort_order,board_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(group["id"],"boundary-1001","待开始","中","未设置","u1",1000,1000,stamp,stamp));conn.commit()
        finally:conn.close()
        paths=[{"visible_fields":[]},{"query":query,"visible_fields":[]},{"view_id":view["id"]}]
        for file_format in ("csv","xlsx"):
            for payload in paths:
                status,error,_=self.request("POST",f"/api/boards/{board['id']}/export",{"format":file_format,**payload},cookie=cookie,csrf=csrf);self.assertEqual((status,error["error"]["code"],error["error"]["details"]),(422,"EXPORT_LIMIT",{"max_rows":1000,"total":1001}),(file_format,payload))

    def test_v8_to_v9_migration_backup_restore_and_idempotence(self):
        path=str(Path(self.temp.name)/"v8.db");conn=connect(path)
        try:
            _migration_v1(conn,"test-password")
            for migration in (_migration_v2,_migration_v3,_migration_v4,_migration_v5,_migration_v6,_migration_v7,_migration_v8):migration(conn)
            before=conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        finally:conn.close()
        backup=migrate(path);self.assertTrue(backup and Path(backup).exists());conn=connect(path)
        try:self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION);self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],before);self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=9").fetchone()[0],"flowboard-schema-v9");self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        finally:conn.close()
        restored=str(Path(self.temp.name)/"restored-v8.db");copy_database(backup,restored);check=sqlite3.connect(restored)
        try:self.assertEqual(check.execute("PRAGMA user_version").fetchone()[0],8)
        finally:check.close()
        self.assertIsNone(migrate(path))

    def test_v7_to_v8_migration_backup_restore_and_idempotence(self):
        path=str(Path(self.temp.name)/"v7.db");conn=connect(path)
        try:
            _migration_v1(conn,"test-password")
            for migration in (_migration_v2,_migration_v3,_migration_v4,_migration_v5,_migration_v6,_migration_v7):migration(conn)
            before=[tuple(row) for row in conn.execute("SELECT id,title,parent_id FROM tasks ORDER BY id")]
        finally:conn.close()
        backup=migrate(path);self.assertTrue(backup and Path(backup).exists());conn=connect(path)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],SCHEMA_VERSION);self.assertEqual(before,[tuple(row) for row in conn.execute("SELECT id,title,parent_id FROM tasks ORDER BY id")]);self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[]);self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok");self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=8").fetchone()[0],"flowboard-schema-v8")
        finally:conn.close()
        restored=str(Path(self.temp.name)/"restored-v7.db");copy_database(backup,restored);check=sqlite3.connect(restored)
        try:self.assertEqual(check.execute("PRAGMA user_version").fetchone()[0],7);self.assertEqual(check.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],len(before))
        finally:check.close()
        self.assertIsNone(migrate(path))


if __name__ == "__main__":
    unittest.main()
