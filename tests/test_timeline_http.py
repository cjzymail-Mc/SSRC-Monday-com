import base64
import hashlib
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from flowboard.database import connect, migrate
from flowboard.transfer import make_xlsx, parse_upload
from flowboard.timeline_excel import TEMPLATE_ROWS, make_timeline_xlsx
from server import create_server


class TimelineHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="timeline-http-")
        self.db_path = str(Path(self.temp.name) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(self.db_path, initial_password="test-password")
        db = connect(self.db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
        db.commit()
        db.close()
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

    def request(self, method, path, body=None, *, cookie=None, csrf=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        connection.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        set_cookie = response.getheader("Set-Cookie")
        status = response.status
        connection.close()
        return status, payload, set_cookie

    def login(self, username="u1"):
        status, payload, cookie = self.request("POST", "/api/auth/login", {"username": username, "password": "test-password"})
        self.assertEqual(status, 200)
        return cookie.split(";", 1)[0], payload["csrf_token"]

    def test_member_card_order_is_private_versioned_and_scoped(self):
        path = "/api/workspaces/1/timeline/member-order"
        admin, admin_csrf = self.login("u1")
        member, member_csrf = self.login("u2")
        viewer, viewer_csrf = self.login("u3")
        status, initial, _ = self.request("GET", path, cookie=admin)
        self.assertEqual(status, 200)
        self.assertEqual(set(initial["member_ids"]), {"u1", "u2", "u3"})
        self.assertEqual(initial["order_version"], 0)
        reversed_ids = list(reversed(initial["member_ids"]))
        status, saved, _ = self.request("PUT", path, {"base_order_version": 0, "member_ids": reversed_ids}, cookie=admin, csrf=admin_csrf)
        self.assertEqual((status, saved), (200, {"order_version": 1, "member_ids": reversed_ids}))
        self.assertEqual(self.request("GET", path, cookie=admin)[1], saved)
        self.assertEqual(self.request("GET", path, cookie=member)[1], initial)
        status, member_saved, _ = self.request("PUT", path, {"base_order_version": 0, "member_ids": initial["member_ids"][1:] + initial["member_ids"][:1]}, cookie=member, csrf=member_csrf)
        self.assertEqual(status, 200)
        self.assertEqual(member_saved["order_version"], 1)
        self.assertEqual(self.request("GET", path, cookie=admin)[1], saved)
        status, conflict, _ = self.request("PUT", path, {"base_order_version": 0, "member_ids": initial["member_ids"]}, cookie=admin, csrf=admin_csrf)
        self.assertEqual((status, conflict["error"]["code"]), (409, "ORDER_VERSION_CONFLICT"))
        self.assertEqual(self.request("PUT", path, {"base_order_version": 1, "member_ids": ["u1", "u1", "u3"]}, cookie=admin, csrf=admin_csrf)[0], 422)
        self.assertEqual(self.request("PUT", path, {"base_order_version": 1, "member_ids": ["u1", "u2", "ghost"]}, cookie=admin, csrf=admin_csrf)[1]["error"]["code"], "ORDER_SCOPE_CHANGED")
        self.assertEqual(self.request("PUT", path, {"base_order_version": 1, "member_ids": reversed_ids}, cookie=admin)[0], 403)
        self.assertEqual(self.request("GET", path, cookie=viewer)[0], 403)
        self.assertEqual(self.request("PUT", path, {"base_order_version": 0, "member_ids": reversed_ids}, cookie=viewer, csrf=viewer_csrf)[0], 403)
        self.assertEqual(self.request("GET", path.replace("/1/", "/999/"), cookie=admin)[0], 403)
        db = connect(self.db_path)
        try:
            db.execute("UPDATE users SET is_active=0 WHERE id='u3'")
            db.commit()
        finally:
            db.close()
        current = self.request("GET", path, cookie=admin)[1]
        self.assertEqual(current["member_ids"], [value for value in reversed_ids if value != "u3"])
        self.assertEqual(self.request("PUT", path, {"base_order_version": 1, "member_ids": reversed_ids}, cookie=admin, csrf=admin_csrf)[1]["error"]["code"], "ORDER_SCOPE_CHANGED")
        db = connect(self.db_path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_log WHERE action_code='timeline.member_order_changed'").fetchone()[0], 2)
        finally:
            db.close()

    def test_import_sheet_metadata_selection_and_access(self):
        cookie, csrf = self.login()
        headers = ["项目名称", "阶段", "主线/并行", "节点", "日期", "状态", "备注"]
        raw = make_xlsx(headers, [["所选表项目", "创意", "主线", "立项", "2026-08-01", "", ""]], sheet="数据表")
        data = {"filename": "sheets.xlsx", "content_base64": base64.b64encode(raw).decode()}
        path = "/api/workspaces/1/timeline/imports/"
        before = self.counts()
        status, payload, _ = self.request("POST", path + "sheets", data, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(payload["sheets"], ["数据表"])
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.request("POST", path + "sheets", data, cookie=cookie)[0], 403)
        viewer, viewer_csrf = self.login("u3")
        self.assertEqual(self.request("POST", path + "sheets", data, cookie=viewer, csrf=viewer_csrf)[0], 403)
        self.assertEqual(self.request("POST", path.replace('/1/', '/999/') + "sheets", data, cookie=cookie, csrf=csrf)[0], 403)
        status, payload, _ = self.request("POST", path + "preview", {**data, "sheet_name": "不存在"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "IMPORT_SHEET_NOT_FOUND")
        self.assertEqual(self.counts(), before)
        status, payload, _ = self.request("POST", path + "preview", {**data, "sheet_name": "数据表"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        self.assertEqual(payload["sheet"], "数据表")
        self.assertEqual(payload["projects"], [{"name": "所选表项目", "node_count": 1}])

    def create_project(self, cookie, csrf, name="HTTP 项目"):
        status, payload, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": name}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201, payload)
        return payload

    def batch(self, cookie, csrf, project_id, version, changes, **extra):
        request = {"project_id": project_id, "base_version": version, "changes": changes, **extra}
        return self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [request]}, cookie=cookie, csrf=csrf)

    def counts(self):
        db = connect(self.db_path)
        try:
            return tuple(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
                "timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes"
            ))
        finally:
            db.close()

    @staticmethod
    def upload(filename, raw):
        return {"filename": filename, "content_base64": base64.b64encode(raw).decode("ascii")}

    @staticmethod
    def two_sheet_xlsx(headers, rows):
        first = make_xlsx(headers, rows, "First")
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(first)) as source, zipfile.ZipFile(output, "w") as target:
            second_sheet = source.read("xl/worksheets/sheet1.xml")
            for item in source.infolist():
                content = source.read(item.filename)
                if item.filename == "xl/workbook.xml":
                    content = content.replace(b"</sheets>", b'<sheet name="Second" sheetId="2" r:id="rId2"/></sheets>')
                elif item.filename == "xl/_rels/workbook.xml.rels":
                    content = content.replace(b"</Relationships>", b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
                elif item.filename == "[Content_Types].xml":
                    content = content.replace(b"</Types>", b'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
                target.writestr(item, content)
            target.writestr("xl/worksheets/sheet2.xml", second_sheet)
        return output.getvalue()

    def test_r01_r02_list_and_single_get_auth_permissions_and_shapes(self):
        admin_cookie, admin_csrf = self.login()
        created = self.create_project(admin_cookie, admin_csrf)
        status, listed, _ = self.request("GET", "/api/workspaces/1/timeline", cookie=admin_cookie)
        self.assertEqual((status, listed["projects"][0]["created_by"]), (200, "u1"))
        status, project, _ = self.request("GET", f"/api/timeline/projects/{created['project_id']}", cookie=admin_cookie)
        self.assertEqual(status, 200)
        self.assertTrue({"nodes", "segments", "stage_intervals", "metrics", "server_today"} <= project.keys())
        status, error, _ = self.request("GET", f"/api/timeline/projects/{created['project_id']}")
        self.assertEqual((status, error["error"]["code"]), (401, "AUTH_REQUIRED"))
        viewer_cookie, _ = self.login("u3")
        status, error, _ = self.request("GET", f"/api/timeline/projects/{created['project_id']}", cookie=viewer_cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))

    def test_project_rename_patch_permissions_conflicts_and_csrf(self):
        admin_cookie, admin_csrf = self.login()
        project = self.create_project(admin_cookie, admin_csrf, "HTTP 旧名称")
        self.create_project(admin_cookie, admin_csrf, "HTTP 已存在")
        path = f"/api/workspaces/1/timeline/projects/{project['project_id']}"

        status, error, _ = self.request("PATCH", path, {"name": "无 CSRF", "base_version": 1}, cookie=admin_cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        status, renamed, _ = self.request(
            "PATCH", path, {"name": "HTTP 新名称", "base_version": 1}, cookie=admin_cookie, csrf=admin_csrf
        )
        self.assertEqual((status, renamed["name"], renamed["version"]), (200, "HTTP 新名称", 2))

        status, error, _ = self.request(
            "PATCH", path, {"name": "过期名称", "base_version": 1}, cookie=admin_cookie, csrf=admin_csrf
        )
        self.assertEqual((status, error["error"]["code"], error["error"]["details"]["project"]["name"]), (409, "VERSION_CONFLICT", "HTTP 新名称"))
        status, error, _ = self.request(
            "PATCH", path, {"name": "http 已存在", "base_version": 2}, cookie=admin_cookie, csrf=admin_csrf
        )
        self.assertEqual((status, error["error"]["code"]), (422, "NAME_CONFLICT"))

        member_cookie, member_csrf = self.login("u2")
        status, error, _ = self.request(
            "PATCH", path, {"name": "成员越权", "base_version": 2}, cookie=member_cookie, csrf=member_csrf
        )
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        db = connect(self.db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_log WHERE action_code='timeline.project_renamed'").fetchone()[0], 1)
        db.close()

    def test_r03_review_actor_change_rows_metrics_and_overlap_rows(self):
        cookie, csrf = self.login()
        created = self.create_project(cookie, csrf, "复盘项目")
        changes = [
            {"create": {"track": "main", "stage": "创意", "name": "A", "date": "2026-08-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "B", "date": "2026-08-01"}},
            {"create": {"track": "main", "stage": "创意", "name": "C", "date": "2026-08-02"}},
        ]
        status, result, _ = self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": created["project_id"], "base_version": 1, "changes": changes}]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, result)
        intervals = result["results"][0]["view"]["stage_intervals"]
        self.assertEqual([item["row_index"] for item in intervals], [0, 1, 0])
        node_id = result["results"][0]["view"]["nodes"][0]["id"]
        status, _, _ = self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": created["project_id"], "base_version": 2, "changes": [{"node_id": node_id, "set": {"date": "2026-08-03"}}]}]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200)
        status, review, _ = self.request("GET", f"/api/workspaces/1/timeline/review?project_ids={created['project_id']}", cookie=cookie)
        batch = review["projects"][0]["batches"][0]
        self.assertEqual((status, batch["actor"]), (200, {"id": "u1", "name": "管理员"}))
        self.assertTrue(batch["change_rows"])
        self.assertEqual(review["projects"][0]["summary"]["direct_edit_total"], 1)

    def test_r04_create_lifecycle_conflict_csrf_and_viewer(self):
        cookie, csrf = self.login()
        created = self.create_project(cookie, csrf, "Mc Prj 01")
        status, error, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": "mc prj 01"}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (422, "NAME_CONFLICT"))
        status, error, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": "缺 CSRF"}, cookie=cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        viewer_cookie, viewer_csrf = self.login("u3")
        status, error, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": "viewer"}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        self.assertEqual(created["created_by"], "u1")

    def test_r05_delete_path_version_admin_soft_delete_and_repeat(self):
        cookie, csrf = self.login()
        created = self.create_project(cookie, csrf, "待删除")
        path = f"/api/workspaces/1/timeline/projects/{created['project_id']}"
        status, error, _ = self.request("DELETE", path, {}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (428, "VERSION_REQUIRED"))
        status, error, _ = self.request("DELETE", path, {"base_version": 2}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (409, "VERSION_CONFLICT"))
        member_cookie, member_csrf = self.login("u2")
        status, error, _ = self.request("DELETE", path, {"base_version": 1}, cookie=member_cookie, csrf=member_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        status, deleted, _ = self.request("DELETE", path, {"base_version": 1}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, deleted["version"]), (200, 2))
        db = connect(self.db_path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_projects WHERE id=? AND deleted_at IS NOT NULL", (created["project_id"],)).fetchone()[0], 1)
        db.close()
        status, error, _ = self.request("DELETE", path, {"base_version": 2}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (404, "PROJECT_NOT_ACTIVE"))

    def test_creator_can_delete_archived_project_through_http(self):
        member_cookie, member_csrf = self.login("u2")
        created = self.create_project(member_cookie, member_csrf, "成员归档后删除")
        project_id = created["project_id"]
        path = f"/api/workspaces/1/timeline/projects/{project_id}"
        admin_cookie, admin_csrf = self.login()
        other_project = self.create_project(admin_cookie, admin_csrf, "其他人项目")
        other_path = f"/api/workspaces/1/timeline/projects/{other_project['project_id']}"
        status, error, _ = self.request("DELETE", other_path, {"base_version": 1}, cookie=member_cookie, csrf=member_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))

        status, archived, _ = self.request("POST", path + "/archive", {"base_version": 1}, cookie=member_cookie, csrf=member_csrf)
        self.assertEqual(status, 200)
        status, deleted, _ = self.request("DELETE", path, {"base_version": archived["version"]}, cookie=member_cookie, csrf=member_csrf)
        self.assertEqual((status, deleted["project_id"]), (200, project_id))
        status, listed, _ = self.request("GET", "/api/workspaces/1/timeline?archive_state=archived", cookie=member_cookie)
        self.assertEqual(status, 200)
        self.assertNotIn(project_id, [item["project_id"] for item in listed["projects"]])
        db = connect(self.db_path)
        try:
            event = db.execute(
                "SELECT actor_user_id,details_json FROM audit_log WHERE action_code='timeline.project_deleted' AND entity_id=?",
                (str(project_id),),
            ).fetchone()
            self.assertEqual(event["actor_user_id"], "u2")
            self.assertIsNotNone(json.loads(event["details_json"])["archived_at"])
        finally:
            db.close()

    def test_r06_batch_http_complete_view_csrf_version_atomic_and_interval_bounds(self):
        cookie, csrf = self.login()
        project = self.create_project(cookie, csrf, "批次 HTTP")
        project_id = project["project_id"]
        changes = [
            {"create": {"track": "main", "stage": "创意", "name": "起点", "date": "2026-08-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "终点", "date": "2036-07-29"}},
        ]
        status, result, _ = self.batch(cookie, csrf, project_id, 1, changes)
        self.assertEqual(status, 200, result)
        view = result["results"][0]["view"]
        self.assertTrue({"nodes", "segments", "stage_intervals", "metrics", "server_today"} <= view.keys())
        self.assertEqual(view["nodes"][1]["interval_days"], 3650)

        before = self.counts()
        status, error, _ = self.batch(cookie, None, project_id, 2, [{"node_id": view["nodes"][1]["id"], "set": {"remark": "x"}}])
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        status, error, _ = self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": project_id, "changes": [{"node_id": view["nodes"][1]["id"], "set": {"remark": "x"}}]}]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (428, "VERSION_REQUIRED"))
        status, error, _ = self.batch(cookie, csrf, project_id, 999, [{"node_id": view["nodes"][1]["id"], "set": {"remark": "x"}}])
        self.assertEqual((status, error["error"]["code"]), (409, "VERSION_CONFLICT"))
        status, error, _ = self.batch(cookie, csrf, project_id, 2, [{"node_id": view["nodes"][1]["id"], "set": {"interval_days": 3651}}])
        self.assertEqual((status, error["error"]["code"]), (422, "VALIDATION_ERROR"))
        self.assertEqual(self.counts(), before)

        viewer_cookie, viewer_csrf = self.login("u3")
        status, error, _ = self.batch(viewer_cookie, viewer_csrf, project_id, 2, [{"node_id": view["nodes"][1]["id"], "set": {"remark": "x"}}])
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        self.assertEqual(self.counts(), before)

        status, noop, _ = self.batch(cookie, csrf, project_id, 2, [{"node_id": view["nodes"][1]["id"], "set": {"date": view["nodes"][1]["date"]}}])
        self.assertEqual((status, noop["results"][0]["no_op"], noop["results"][0]["version"]), (200, True, 2))
        other = self.create_project(cookie, csrf, "原子 HTTP")
        atomic_before = self.counts()
        status, error, _ = self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [
            {"project_id": project_id, "base_version": 2, "changes": [{"node_id": view["nodes"][0]["id"], "set": {"remark": "不得落盘"}}]},
            {"project_id": other["project_id"], "base_version": 999, "changes": [{"create": {"track": "main", "stage": "创意", "name": "不得创建", "date": "2026-08-01"}}]},
        ]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (409, "VERSION_CONFLICT"))
        self.assertEqual(self.counts(), atomic_before)

    def test_r07_undo_http_success_csrf_stale_soft_delete_and_zero_write(self):
        cookie, csrf = self.login()
        project = self.create_project(cookie, csrf, "撤销 HTTP")
        project_id = project["project_id"]
        status, made, _ = self.batch(cookie, csrf, project_id, 1, [{"create": {"track": "main", "stage": "创意", "name": "临时", "date": "2026-08-01"}}])
        self.assertEqual(status, 200, made)
        batch_id = made["results"][0]["batch_id"]
        before = self.counts()
        path = "/api/workspaces/1/timeline/batches/undo"
        status, error, _ = self.request("POST", path, {"batch_ids": [batch_id]}, cookie=cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        self.assertEqual(self.counts(), before)
        status, undone, _ = self.request("POST", path, {"batch_ids": [batch_id]}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, undone)
        self.assertEqual(undone["results"][0]["view"]["nodes"], [])
        db = connect(self.db_path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NOT NULL", (project_id,)).fetchone()[0], 1)
        finally:
            db.close()
        after = self.counts()
        status, error, _ = self.request("POST", path, {"batch_ids": [batch_id]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (409, "UNDO_TARGET_STALE"))
        self.assertEqual(self.counts(), after)

        deleted = self.create_project(cookie, csrf, "已删撤销")
        _, deleted_batch, _ = self.batch(cookie, csrf, deleted["project_id"], 1, [{"create": {"track": "main", "stage": "创意", "name": "N", "date": "2026-08-01"}}])
        deleted_batch_id = deleted_batch["results"][0]["batch_id"]
        self.request("DELETE", f"/api/workspaces/1/timeline/projects/{deleted['project_id']}", {"base_version": 2}, cookie=cookie, csrf=csrf)
        deleted_before = self.counts()
        status, error, _ = self.request("POST", path, {"batch_ids": [deleted_batch_id]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (404, "PROJECT_NOT_ACTIVE"))
        self.assertEqual(self.counts(), deleted_before)

    def test_r08_initial_correction_http_noop_no_cascade_permissions_and_invalid_node(self):
        cookie, csrf = self.login()
        project = self.create_project(cookie, csrf, "纠正 HTTP")
        project_id = project["project_id"]
        status, made, _ = self.batch(cookie, csrf, project_id, 1, [
            {"create": {"track": "main", "stage": "创意", "name": "A", "date": "2026-08-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "B", "date": "2026-08-05"}},
        ])
        self.assertEqual(status, 200, made)
        nodes = made["results"][0]["view"]["nodes"]
        path = "/api/workspaces/1/timeline/batches/initial-correction"
        body = {"project_id": project_id, "base_version": 2, "corrections": [{"node_id": nodes[0]["id"], "initial_date": "2026-09-01"}]}
        before = self.counts()
        status, error, _ = self.request("POST", path, body, cookie=cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        self.assertEqual(self.counts(), before)
        member_cookie, member_csrf = self.login("u2")
        member_project = self.create_project(member_cookie, member_csrf, "成员纠正")
        _, member_made, _ = self.batch(member_cookie, member_csrf, member_project["project_id"], 1, [{"create": {"track": "main", "stage": "创意", "name": "M", "date": "2026-08-01"}}])
        member_node = member_made["results"][0]["view"]["nodes"][0]
        member_before = self.counts()
        status, error, _ = self.request("POST", path, {"project_id": member_project["project_id"], "base_version": 2, "corrections": [{"node_id": member_node["id"], "initial_date": "2026-07-01"}]}, cookie=member_cookie, csrf=member_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "ADMIN_REQUIRED"))
        self.assertEqual(self.counts(), member_before)
        status, corrected, _ = self.request("POST", path, body, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, corrected)
        view = corrected["results"][0]["view"]
        self.assertEqual((view["nodes"][0]["initial_date"], view["nodes"][0]["date"], view["nodes"][1]["initial_date"]), ("2026-09-01", "2026-08-01", "2026-08-05"))
        status, noop, _ = self.request("POST", path, {**body, "base_version": 3}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, noop["results"][0]["no_op"]), (200, True))
        stable = self.counts()
        status, error, _ = self.request("POST", path, {"project_id": project_id, "base_version": 3, "corrections": [{"node_id": 999999, "initial_date": "2026-01-01"}]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (422, "VALIDATION_ERROR"))
        self.assertEqual(self.counts(), stable)

        self.request("DELETE", f"/api/workspaces/1/timeline/projects/{project_id}", {"base_version": 3}, cookie=cookie, csrf=csrf)
        deleted_stable = self.counts()
        status, error, _ = self.request("POST", path, {"project_id": project_id, "base_version": 4, "corrections": [{"node_id": nodes[0]["id"], "initial_date": "2026-07-01"}]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (404, "PROJECT_NOT_ACTIVE"))
        self.assertEqual(self.counts(), deleted_stable)

    def test_r09_r10_import_http_preview_commit_permissions_state_and_race(self):
        cookie, csrf = self.login()
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        raw = make_xlsx(headers, [["HTTP 导入", "创意", "main", "节点", 46234, "", "已完成", "备注"]])
        path = "/api/workspaces/1/timeline/imports/preview"
        before = self.counts()
        status, error, _ = self.request("POST", path, self.upload("timeline.xlsx", raw), cookie=cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        viewer_cookie, viewer_csrf = self.login("u3")
        status, error, _ = self.request("POST", path, self.upload("timeline.xlsx", raw), cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        self.assertEqual(self.counts(), before)

        status, preview, _ = self.request("POST", path, self.upload("timeline.xlsx", raw), cookie=cookie, csrf=csrf)
        self.assertEqual((status, preview["row_count"]), (201, 1))
        commit_path = "/api/workspaces/1/timeline/imports/commit"
        status, committed, _ = self.request("POST", commit_path, {"batch_id": preview["batch_id"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, committed["projects"], committed["nodes"]), (201, 1, 1))
        status, error, _ = self.request("POST", commit_path, {"batch_id": preview["batch_id"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (409, "TIMELINE_IMPORT_ALREADY_COMMITTED"))

        race_raw = make_xlsx(headers, [["竞态项目", "设计", "parallel", "N", "2026-08-02", "", "未开始", ""]])
        _, race, _ = self.request("POST", path, self.upload("race.xlsx", race_raw), cookie=cookie, csrf=csrf)
        self.create_project(cookie, csrf, "竞态项目")
        stable = self.counts()
        status, error, _ = self.request("POST", commit_path, {"batch_id": race["batch_id"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (422, "NAME_CONFLICT"))
        self.assertEqual(self.counts(), stable)

        other_cookie, other_csrf = self.login("u2")
        status, error, _ = self.request("POST", commit_path, {"batch_id": race["batch_id"]}, cookie=other_cookie, csrf=other_csrf)
        self.assertEqual((status, error["error"]["code"]), (404, "TIMELINE_IMPORT_BATCH_NOT_FOUND"))
        member_raw = make_xlsx(headers, [["降权项目", "创意", "main", "N", "2026-08-03", "", "", ""]])
        _, member_preview, _ = self.request("POST", path, self.upload("member.xlsx", member_raw), cookie=other_cookie, csrf=other_csrf)
        db = connect(self.db_path)
        db.execute("UPDATE workspace_memberships SET role='viewer' WHERE workspace_id=1 AND user_id='u2'")
        db.commit()
        db.close()
        demoted_stable = self.counts()
        status, error, _ = self.request("POST", commit_path, {"batch_id": member_preview["batch_id"]}, cookie=other_cookie, csrf=other_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        self.assertEqual(self.counts(), demoted_stable)
        status, error, _ = self.request("POST", "/api/workspaces/2/timeline/imports/commit", {"batch_id": race["batch_id"]}, cookie=cookie, csrf=csrf)
        self.assertIn(status, (403, 404))

    def test_r09_import_d4_d5_d7_error_rows_warnings_and_cell_types(self):
        cookie, csrf = self.login()
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        self.create_project(cookie, csrf, "已有")
        conflict = make_xlsx(headers, [
            ["已有", "创意", "main", "A", "2026-08-01", "", "", ""],
            ["新项目", "创意", "main", "B", "2026-08-01", "", "", ""],
            ["已有", "设计", "parallel", "C", "2026-08-02", "", "", ""],
        ])
        path = "/api/workspaces/1/timeline/imports/preview"
        status, error, _ = self.request("POST", path, self.upload("conflict.xlsx", conflict), cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (422, "NAME_CONFLICT"))
        self.assertEqual([item["row"] for item in error["error"]["details"]["rows"]], [2, 4])

        multi = self.two_sheet_xlsx(headers, [["多表", "创意", "main", "A", "2026-08-01", "", "", ""]])
        status, preview, _ = self.request("POST", path, self.upload("multi.xlsx", multi), cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201, preview)
        self.assertIn("仅导入所选工作表：First", preview["warnings"])

        text_integer = make_xlsx(headers, [["文本整数", "创意", "main", "A", "46234", "", "", ""]])
        status, error, _ = self.request("POST", path, self.upload("text.xlsx", text_integer), cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"]), (422, "VALIDATION_ERROR"))
        csv_raw = "项目名称,阶段,轨道,节点,日期,间隔,状态,备注\nCSV日期,创意,main,A,46234,,,\n".encode()
        status, error, _ = self.request("POST", path, self.upload("dates.csv", csv_raw), cookie=cookie, csrf=csrf)
        self.assertEqual(status, 422)
        self.assertIn("改用 .xlsx 导入", error["error"]["message"])

    def test_template_download_permissions_example_data_and_no_mutation(self):
        cookie, csrf = self.login()
        path = "/api/workspaces/1/timeline/template"
        before = self.counts()
        status, error, _ = self.request("POST", path, {}, cookie=cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        viewer_cookie, viewer_csrf = self.login("u3")
        status, error, _ = self.request("POST", path, {}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        status, error, _ = self.request("POST", "/api/workspaces/999/timeline/template", {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 403)
        for username in ("u1", "u2"):
            member_cookie, member_csrf = self.login(username)
            status, exported, _ = self.request("POST", path, {}, cookie=member_cookie, csrf=member_csrf)
            self.assertEqual(status, 200, exported)
            raw = base64.b64decode(exported["content_base64"], validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), exported["sha256"])
            parsed = parse_upload(exported["filename"], raw)
            self.assertEqual(len(parsed["rows"]), 15)
            self.assertEqual(len({row[0] for row in parsed["rows"]}), 3)
            self.assertEqual(self.counts(), before)
            status, preview, _ = self.request("POST", "/api/workspaces/1/timeline/imports/preview", self.upload("examples.xlsx", raw), cookie=member_cookie, csrf=member_csrf)
            self.assertEqual((status, preview["row_count"], len(preview["projects"])), (201, 15, 3))
            status, error, _ = self.request("POST", "/api/workspaces/1/timeline/imports/preview", self.upload("blank.xlsx", make_timeline_xlsx([])), cookie=member_cookie, csrf=member_csrf)
            self.assertEqual((status, error["error"]["code"]), (422, "IMPORT_EMPTY"))
        self.assertEqual(self.counts(), before)

    def test_template_three_projects_commit_and_single_project_reuse(self):
        cookie, csrf = self.login()
        _, template, _ = self.request('POST', '/api/workspaces/1/timeline/template', {}, cookie=cookie, csrf=csrf)
        path = '/api/workspaces/1/timeline/imports/'
        status, preview, _ = self.request('POST', path + 'preview', {"filename": template['filename'], "content_base64": template['content_base64'], "sheet_name": "Timeline"}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 201)
        status, result, _ = self.request('POST', path + 'commit', {"batch_id": preview['batch_id']}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, result['projects'], result['nodes']), (201, 3, 15))
        single = [["我的新项目", *row[1:]] for row in TEMPLATE_ROWS if row[0] == TEMPLATE_ROWS[0][0]]
        status, preview, _ = self.request('POST', path + 'preview', self.upload('single.xlsx', make_timeline_xlsx(single)), cookie=cookie, csrf=csrf)
        self.assertEqual((status, preview['row_count'], preview['projects']), (201, 7, [{"name": "我的新项目", "node_count": 7}]))
        status, result, _ = self.request('POST', path + 'commit', {"batch_id": preview['batch_id']}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, result['projects'], result['nodes']), (201, 1, 7))

    def test_r11_export_post_json_order_permissions_and_round_trip(self):
        cookie, csrf = self.login()
        first = self.create_project(cookie, csrf, "P10")
        second = self.create_project(cookie, csrf, "P2")
        status, result, _ = self.batch(cookie, csrf, first["project_id"], 1, [
            {"create": {"track": "parallel", "stage": "设计", "name": "B10", "date": "2026-08-02", "done_at": True}},
            {"create": {"track": "main", "stage": "创意", "name": "B10", "date": "2026-08-01", "done_at": True}},
            {"create": {"track": "main", "stage": "创意", "name": "B2", "date": "2026-08-01", "done_at": True}},
        ])
        self.assertEqual(status, 200, result)
        status, result, _ = self.batch(cookie, csrf, second["project_id"], 1, [
            {"create": {"track": "main", "stage": "测试", "name": "N", "date": "2026-08-03", "done_at": True}}
        ])
        self.assertEqual(status, 200, result)

        path = "/api/workspaces/1/timeline/export"
        status, error, _ = self.request("GET", path, cookie=cookie)
        self.assertEqual(status, 404, error)
        status, error, _ = self.request("POST", path, {}, cookie=cookie)
        self.assertEqual((status, error["error"]["code"]), (403, "CSRF_INVALID"))
        viewer_cookie, viewer_csrf = self.login("u3")
        status, error, _ = self.request("POST", path, {}, cookie=viewer_cookie, csrf=viewer_csrf)
        self.assertEqual((status, error["error"]["code"]), (403, "PROJECT_FORBIDDEN"))
        for body in ({"project_ids": [first["project_id"]]}, {"project_id": first["project_id"]}):
            status, error, _ = self.request("POST", path, body, cookie=cookie, csrf=csrf)
            self.assertEqual((status, error["error"]["code"]), (422, "UNKNOWN_FIELD"))

        status, exported, _ = self.request("POST", path, {}, cookie=cookie, csrf=csrf)
        self.assertEqual(status, 200, exported)
        raw = base64.b64decode(exported["content_base64"], validate=True)
        self.assertEqual(exported["sha256"], hashlib.sha256(raw).hexdigest())
        parsed = parse_upload(exported["filename"], raw)
        self.assertEqual(parsed["headers"], ["项目名称", "阶段", "主线/并行", "节点", "日期", "状态", "备注"])
        self.assertEqual(parsed["sheets"], ["Timeline", "填写说明"])
        self.assertEqual([(row[0], row[2], row[3]) for row in parsed["rows"]], [
            ("P10", "主线", "B2"), ("P10", "主线", "B10"), ("P10", "并行", "B10"), ("P2", "主线", "N")
        ])

        db = connect(self.db_path)
        db.execute("INSERT INTO workspaces VALUES (2,'往返空间','2026-01-01T00:00:00+00:00',30)")
        db.execute("INSERT INTO workspace_memberships VALUES (2,'u1','admin')")
        db.commit()
        db.close()
        status, preview, _ = self.request("POST", "/api/workspaces/2/timeline/imports/preview", self.upload("timeline.xlsx", raw), cookie=cookie, csrf=csrf)
        self.assertEqual((status, preview["row_count"]), (201, 4))
        status, committed, _ = self.request("POST", "/api/workspaces/2/timeline/imports/commit", {"batch_id": preview["batch_id"]}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, committed["projects"], committed["nodes"]), (201, 2, 4))

        db = connect(self.db_path)
        stamp = "2026-08-01T00:00:00+00:00"
        db.executemany(
            "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ((first["project_id"], "parallel", "创意", f"OVER{index}", "2026-08-04", "2026-08-04", "", stamp, stamp) for index in range(997)),
        )
        db.commit()
        db.close()
        status, error, _ = self.request("POST", path, {}, cookie=cookie, csrf=csrf)
        self.assertEqual((status, error["error"]["code"], error["error"]["details"]), (422, "EXPORT_LIMIT", {"total": 1001, "max": 1000}))


if __name__ == "__main__":
    unittest.main()
