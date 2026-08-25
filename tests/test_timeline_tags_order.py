import json
import http.client
import os
import tempfile
import threading
import unittest
from pathlib import Path

from flowboard.database import SCHEMA_VERSION, connect, migrate
from flowboard.service import ApiError
from flowboard.timeline import TimelineService
from server import create_server


class TimelineTagOrderServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="timeline-tag-order-")
        self.db = Path(self.temp.name) / "flowboard.db"
        migrate(self.db, initial_password="test-password")
        conn = connect(self.db)
        conn.execute("INSERT INTO users SELECT 'u2','u2','成员二',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        conn.execute("INSERT OR REPLACE INTO workspace_memberships VALUES (1,'u2','member')")
        conn.execute("INSERT INTO users SELECT 'u3','u3','成员三',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        conn.execute("INSERT INTO workspace_memberships VALUES (1,'u3','member')")
        conn.execute("INSERT INTO users SELECT 'u4','u4','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        conn.execute("INSERT INTO workspace_memberships VALUES (1,'u4','viewer')")
        conn.commit()
        conn.close()
        self.service = TimelineService(self.db)
        self.admin = {"id": "u1"}
        self.member = {"id": "u2"}
        self.other = {"id": "u3"}
        self.viewer = {"id": "u4"}

    def tearDown(self):
        self.temp.cleanup()

    def project(self, user, name):
        return self.service.create_project(user, 1, {"name": name})["project_id"]

    def test_v17_and_v18_migrations_are_additive_and_healthy(self):
        conn = connect(self.db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"timeline_tags", "timeline_project_tags", "timeline_order_contexts", "timeline_order_items"} <= tables)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=17").fetchone()[0], "flowboard-schema-v17")
        self.assertEqual(conn.execute("SELECT checksum FROM schema_migrations WHERE version=18").fetchone()[0], "flowboard-schema-v18")
        self.assertTrue({"archived_at", "archived_by"} <= {row["name"] for row in conn.execute("PRAGMA table_info(timeline_projects)")})
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        conn.close()

    def test_v16_to_v18_preserves_existing_timeline_rows_and_is_idempotent(self):
        legacy = Path(self.temp.name) / "v16-shape.db"
        migrate(legacy, initial_password="test-password")
        conn = connect(legacy)
        conn.execute("DROP TABLE timeline_order_items")
        conn.execute("DROP TABLE timeline_order_contexts")
        conn.execute("DROP TABLE timeline_project_tags")
        conn.execute("DROP TABLE timeline_tags")
        conn.execute("DELETE FROM schema_migrations WHERE version=17")
        conn.execute("DELETE FROM schema_migrations WHERE version=18")
        now = "2026-08-24T00:00:00+00:00"
        conn.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,created_at,updated_at) VALUES (1,'v16 存量','u1',?,?)", (now, now))
        conn.execute("PRAGMA user_version=16")
        conn.commit(); conn.close()
        backup = migrate(legacy)
        self.assertIn("-pre-v18-", Path(backup).name)
        self.assertIsNone(migrate(legacy))
        conn = connect(legacy)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM timeline_projects WHERE name='v16 存量'").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=17").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=18").fetchone()[0], 1)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 18)
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        conn.close()

    def test_shared_tag_permissions_membership_and_soft_delete(self):
        project_id = self.project(self.admin, "管理员项目")
        tag = self.service.create_tag(self.member, 1, {"name": "重点"})
        view = self.service.set_tag_project(self.other, 1, tag["tag_id"], project_id, {"base_tag_version": tag["version"]}, included=True)
        self.assertEqual([row["project_id"] for row in view["included"]], [project_id])
        self.assertEqual(self.service.list_tags(self.member, 1)["tags"][0]["project_count"], 1)
        with self.assertRaises(ApiError) as denied_content:
            self.service.submit_batches(self.other, 1, {"requests": [{"project_id": project_id, "base_version": 1, "changes": [{"create": {"track": "main", "stage": "创意", "name": "越权", "date": "2026-08-24"}}]}]})
        self.assertEqual(denied_content.exception.status, 403)
        with self.assertRaises(ApiError) as viewer_denied:
            self.service.create_tag(self.viewer, 1, {"name": "只读越权"})
        self.assertEqual(viewer_denied.exception.status, 403)
        with self.assertRaises(ApiError) as member_delete:
            self.service.delete_tag(self.member, 1, tag["tag_id"], {"base_version": view["tag"]["version"]})
        self.assertEqual(member_delete.exception.code, "ADMIN_REQUIRED")
        deleted = self.service.delete_tag(self.admin, 1, tag["tag_id"], {"base_version": view["tag"]["version"]})
        self.assertIsNotNone(deleted["deleted_at"])
        conn = connect(self.db)
        self.assertIsNotNone(conn.execute("SELECT deleted_at FROM timeline_tags WHERE id=?", (tag["tag_id"],)).fetchone()[0])
        self.assertIsNotNone(conn.execute("SELECT deleted_at FROM timeline_project_tags WHERE tag_id=?", (tag["tag_id"],)).fetchone()[0])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM timeline_projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()[0], 1)
        actions = {row[0] for row in conn.execute("SELECT action_code FROM audit_log WHERE action_code LIKE 'timeline.tag%'")}
        self.assertTrue({"timeline.tag_created", "timeline.tag_project_added", "timeline.tag_deleted"} <= actions)
        conn.close()

    def test_tag_name_version_conflict_and_multi_tag(self):
        project_id = self.project(self.admin, "多标签项目")
        first = self.service.create_tag(self.member, 1, {"name": "喜爱"})
        second = self.service.create_tag(self.other, 1, {"name": "本周"})
        with self.assertRaises(ApiError) as duplicate:
            self.service.create_tag(self.admin, 1, {"name": "喜爱"})
        self.assertEqual(duplicate.exception.code, "TAG_NAME_CONFLICT")
        first_view = self.service.set_tag_project(self.member, 1, first["tag_id"], project_id, {"base_tag_version": 1}, included=True)
        self.service.set_tag_project(self.other, 1, second["tag_id"], project_id, {"base_tag_version": 1}, included=True)
        with self.assertRaises(ApiError) as stale:
            self.service.rename_tag(self.admin, 1, first["tag_id"], {"name": "新名称", "base_version": 1})
        self.assertEqual(stale.exception.code, "TAG_VERSION_CONFLICT")
        renamed = self.service.rename_tag(self.admin, 1, first["tag_id"], {"name": "新名称", "base_version": first_view["tag"]["version"]})
        self.assertEqual(renamed["name"], "新名称")
        self.assertEqual(self.service.list_tags(self.admin, 1)["virtual"][1]["project_count"], 0)

    def test_personal_orders_are_isolated_and_scope_checked(self):
        p1 = self.project(self.admin, "A1")
        p2 = self.project(self.admin, "A2")
        p3 = self.project(self.member, "B1")
        initial = self.service.get_personal_order(self.admin, 1, "all")
        self.assertEqual(initial["project_ids"], [p1, p2, p3])
        saved = self.service.put_personal_order(self.admin, 1, {"context_type": "all", "tag_id": None, "base_order_version": 0, "project_ids": [p3, p1, p2]})
        self.assertEqual(saved["order_version"], 1)
        self.assertEqual(self.service.get_personal_order(self.admin, 1, "all")["project_ids"], [p3, p1, p2])
        self.assertEqual(self.service.get_personal_order(self.member, 1, "all")["project_ids"], [p1, p2, p3])
        self.assertEqual(self.service.get_personal_order(self.member, 1, "mine")["project_ids"], [p3])
        self.project(self.other, "集合变化")
        with self.assertRaises(ApiError) as changed:
            self.service.put_personal_order(self.admin, 1, {"context_type": "all", "tag_id": None, "base_order_version": 1, "project_ids": [p3, p1, p2]})
        self.assertEqual(changed.exception.code, "ORDER_SCOPE_CHANGED")

    def test_tag_remove_and_readd_appends_for_each_user(self):
        p1 = self.project(self.admin, "顺序一")
        p2 = self.project(self.admin, "顺序二")
        tag = self.service.create_tag(self.admin, 1, {"name": "排序标签"})
        view = self.service.set_tag_project(self.admin, 1, tag["tag_id"], p1, {"base_tag_version": 1}, included=True)
        view = self.service.set_tag_project(self.admin, 1, tag["tag_id"], p2, {"base_tag_version": view["tag"]["version"]}, included=True)
        self.service.put_personal_order(self.admin, 1, {"context_type": "tag", "tag_id": tag["tag_id"], "base_order_version": 0, "project_ids": [p2, p1]})
        view = self.service.set_tag_project(self.member, 1, tag["tag_id"], p2, {"base_tag_version": view["tag"]["version"]}, included=False)
        view = self.service.set_tag_project(self.member, 1, tag["tag_id"], p2, {"base_tag_version": view["tag"]["version"]}, included=True)
        self.assertEqual(self.service.get_personal_order(self.admin, 1, "tag", tag["tag_id"])["project_ids"], [p1, p2])


class TimelineTagOrderHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="timeline-tag-order-http-")
        self.db = str(Path(self.temp.name) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(self.db, initial_password="test-password")
        self.server = create_server("127.0.0.1", 0, self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.temp.cleanup(); os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)

    def request(self, method, path, body=None, cookie=None, csrf=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie: headers["Cookie"] = cookie
        if csrf: headers["X-CSRF-Token"] = csrf
        connection.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = connection.getresponse(); payload = json.loads(response.read()); set_cookie = response.getheader("Set-Cookie")
        connection.close(); return response.status, payload, set_cookie

    def login(self):
        status, payload, cookie = self.request("POST", "/api/auth/login", {"username": "u1", "password": "test-password"})
        self.assertEqual(status, 200)
        return cookie.split(";", 1)[0], payload["csrf_token"]

    def test_http_tag_membership_and_put_order_require_csrf(self):
        cookie, csrf = self.login()
        status, project, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": "HTTP 标签项目"}, cookie, csrf)
        self.assertEqual(status, 201)
        status, tag, _ = self.request("POST", "/api/workspaces/1/timeline/tags", {"name": "HTTP 标签"}, cookie, csrf)
        self.assertEqual(status, 201)
        relation_path = f"/api/workspaces/1/timeline/tags/{tag['tag_id']}/projects/{project['project_id']}"
        status, denied, _ = self.request("PUT", relation_path, {"base_tag_version": 1}, cookie)
        self.assertEqual((status, denied["error"]["code"]), (403, "CSRF_INVALID"))
        status, view, _ = self.request("PUT", relation_path, {"base_tag_version": 1}, cookie, csrf)
        self.assertEqual(status, 200)
        self.assertEqual(view["included"][0]["project_id"], project["project_id"])
        status, order, _ = self.request("GET", f"/api/workspaces/1/timeline/order?context_type=tag&tag_id={tag['tag_id']}", cookie=cookie)
        self.assertEqual((status, order["project_ids"]), (200, [project["project_id"]]))
        status, saved, _ = self.request("PUT", "/api/workspaces/1/timeline/order", {"context_type": "tag", "tag_id": tag["tag_id"], "base_order_version": 0, "project_ids": [project["project_id"]]}, cookie, csrf)
        self.assertEqual((status, saved["order_version"]), (200, 1))


if __name__ == "__main__":
    unittest.main()
