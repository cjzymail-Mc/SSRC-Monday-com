import json
import http.client
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path

from flowboard.database import connect, migrate
from flowboard.service import ApiError
from flowboard.timeline import TimelineService
from server import create_server


class TimelineArchiveServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="timeline-archive-")
        self.db = Path(self.temp.name) / "flowboard.db"
        migrate(self.db, initial_password="test-password")
        conn = connect(self.db)
        for user_id, name in (("u2", "创建者"), ("u3", "其他成员")):
            conn.execute(
                "INSERT INTO users SELECT ?,?,?,password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'",
                (user_id, user_id, name),
            )
            conn.execute("INSERT INTO workspace_memberships VALUES (1,?,'member')", (user_id,))
        conn.commit()
        conn.close()
        self.service = TimelineService(self.db)
        self.admin = {"id": "u1"}
        self.creator = {"id": "u2"}
        self.other = {"id": "u3"}

    def tearDown(self):
        self.temp.cleanup()

    def project(self, user, name, dates=()):
        project = self.service.create_project(user, 1, {"name": name})
        if dates:
            result = self.service.submit_batches(user, 1, {"requests": [{
                "project_id": project["project_id"],
                "base_version": 1,
                "changes": [{"create": {"track": "main", "stage": "创意", "name": f"节点 {index}", "date": value}} for index, value in enumerate(dates, 1)],
            }]})
            project["version"] = result["results"][0]["version"]
        return project

    def test_manual_archive_permissions_readonly_visibility_and_restore(self):
        first = self.project(self.creator, "创建者项目", ("2026-08-01", "2026-08-10"))
        second = self.project(self.admin, "管理员项目", ("2026-08-02",))
        tag = self.service.create_tag(self.admin, 1, {"name": "保留组织"})
        self.service.set_tag_project(self.admin, 1, tag["tag_id"], first["project_id"], {"base_tag_version": 1}, included=True)
        saved = self.service.put_personal_order(self.creator, 1, {
            "context_type": "all", "tag_id": None, "base_order_version": 0,
            "project_ids": [second["project_id"], first["project_id"]],
        })

        with self.assertRaises(ApiError) as denied:
            self.service.archive_project(self.other, 1, first["project_id"], {"base_version": first["version"]})
        self.assertEqual(denied.exception.code, "PROJECT_ARCHIVE_FORBIDDEN")

        archived = self.service.archive_project(self.creator, 1, first["project_id"], {"base_version": first["version"]})
        self.assertTrue(archived["read_only"])
        self.assertTrue(archived["can_unarchive"])
        self.assertEqual([row["project_id"] for row in self.service.list_projects(self.creator, 1)["projects"]], [second["project_id"]])
        self.assertEqual([row["project_id"] for row in self.service.list_projects(self.creator, 1, "archived")["projects"]], [first["project_id"]])
        catalog = self.service.list_tags(self.creator, 1)
        self.assertEqual(catalog["tags"][0]["project_count"], 0)
        self.assertEqual(catalog["virtual"][1], {"context_type": "mine", "name": "我的项目", "project_count": 0})
        self.assertEqual(catalog["virtual"][-1], {"context_type": "archived", "name": "已归档项目", "project_count": 1})
        self.assertEqual(self.service.get_personal_order(self.creator, 1, "mine")["project_ids"], [])
        self.assertEqual(self.service.get_personal_order(self.creator, 1, "all")["project_ids"], [second["project_id"]])

        with self.assertRaises(ApiError) as write_denied:
            self.service.submit_batches(self.creator, 1, {"requests": [{
                "project_id": first["project_id"], "base_version": archived["version"],
                "changes": [{"create": {"track": "main", "stage": "设计", "name": "不应写入", "date": "2026-08-20"}}],
            }]})
        self.assertEqual(write_denied.exception.code, "PROJECT_ARCHIVED")
        with self.assertRaises(ApiError) as tag_denied:
            self.service.set_tag_project(self.creator, 1, tag["tag_id"], first["project_id"], {"base_tag_version": 2}, included=False)
        self.assertEqual(tag_denied.exception.code, "PROJECT_ARCHIVED")
        with self.assertRaises(ApiError) as delete_denied:
            self.service.delete_project(self.admin, 1, first["project_id"], {"base_version": archived["version"]})
        self.assertEqual(delete_denied.exception.code, "PROJECT_ARCHIVED")

        restored = self.service.unarchive_project(self.creator, 1, first["project_id"], {"base_version": archived["version"]})
        self.assertFalse(restored["read_only"])
        self.assertEqual(self.service.get_personal_order(self.creator, 1, "all")["project_ids"], [second["project_id"], first["project_id"]])
        membership = self.service.get_tag_projects(self.creator, 1, tag["tag_id"])
        self.assertEqual([row["project_id"] for row in membership["included"]], [first["project_id"]])
        conn = connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM timeline_project_tags WHERE project_id=? AND deleted_at IS NULL", (first["project_id"],)).fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM timeline_order_items WHERE project_id=? AND deleted_at IS NULL", (first["project_id"],)).fetchone()[0], 1)
        actions = [row[0] for row in conn.execute("SELECT action_code FROM audit_log WHERE entity_id=? ORDER BY id", (str(first["project_id"]),))]
        self.assertIn("timeline.project_archived", actions)
        self.assertIn("timeline.project_unarchived", actions)
        conn.close()

    def test_reordering_visible_projects_preserves_archived_hidden_slot(self):
        projects = [self.project(self.admin, name) for name in ("顺序一", "顺序二", "顺序三")]
        ids = [row["project_id"] for row in projects]
        saved = self.service.put_personal_order(self.admin, 1, {
            "context_type": "all", "tag_id": None, "base_order_version": 0,
            "project_ids": [ids[2], ids[1], ids[0]],
        })
        archived = self.service.archive_project(self.admin, 1, ids[1], {"base_version": 1})
        current = self.service.get_personal_order(self.admin, 1, "all")
        self.assertEqual(current["project_ids"], [ids[2], ids[0]])
        reordered = self.service.put_personal_order(self.admin, 1, {
            "context_type": "all", "tag_id": None, "base_order_version": saved["order_version"],
            "project_ids": [ids[0], ids[2]],
        })
        self.assertEqual(reordered["project_ids"], [ids[0], ids[2]])
        self.service.unarchive_project(self.admin, 1, ids[1], {"base_version": archived["version"]})
        self.assertEqual(self.service.get_personal_order(self.admin, 1, "all")["project_ids"], [ids[0], ids[1], ids[2]])

    def test_one_time_bootstrap_uses_strict_last_node_date_snapshot(self):
        today = self.service._server_today()
        expired = self.project(self.admin, "过期候选", ((today - timedelta(days=2)).isoformat(), (today - timedelta(days=1)).isoformat()))
        self.project(self.admin, "今天收尾", (today.isoformat(),))
        self.project(self.admin, "未来项目", ((today + timedelta(days=1)).isoformat(),))
        self.project(self.admin, "空项目")
        preview = self.service.preview_archive_bootstrap(self.admin, 1, {})
        self.assertEqual([row["project_id"] for row in preview["candidates"]], [expired["project_id"]])
        with self.assertRaises(ApiError) as member_denied:
            self.service.preview_archive_bootstrap(self.creator, 1, {})
        self.assertEqual(member_denied.exception.code, "ADMIN_REQUIRED")
        applied = self.service.apply_archive_bootstrap(self.admin, 1, {
            "today": preview["today"], "candidates": preview["candidates"], "snapshot_sha256": preview["snapshot_sha256"],
        })
        self.assertEqual(applied["archived_count"], 1)
        with self.assertRaises(ApiError) as repeated:
            self.service.apply_archive_bootstrap(self.admin, 1, {
                "today": preview["today"], "candidates": preview["candidates"], "snapshot_sha256": preview["snapshot_sha256"],
            })
        self.assertEqual(repeated.exception.code, "ARCHIVE_BOOTSTRAP_ALREADY_COMPLETED")

    def test_bootstrap_snapshot_drift_is_atomic(self):
        today = self.service._server_today()
        project = self.project(self.admin, "漂移候选", ((today - timedelta(days=1)).isoformat(),))
        preview = self.service.preview_archive_bootstrap(self.admin, 1, {})
        conn = connect(self.db)
        conn.execute("UPDATE timeline_projects SET version=version+1 WHERE id=?", (project["project_id"],))
        conn.commit()
        conn.close()
        with self.assertRaises(ApiError) as drift:
            self.service.apply_archive_bootstrap(self.admin, 1, {
                "today": preview["today"], "candidates": preview["candidates"], "snapshot_sha256": preview["snapshot_sha256"],
            })
        self.assertEqual(drift.exception.code, "ARCHIVE_BOOTSTRAP_SNAPSHOT_CHANGED")
        self.assertEqual(self.service.list_projects(self.admin, 1, "archived")["projects"], [])


class TimelineArchiveHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="timeline-archive-http-")
        self.db = str(Path(self.temp.name) / "flowboard.db")
        migrate(self.db, initial_password="test-password")
        self.server = create_server("127.0.0.1", 0, self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, cookie=None, csrf=None):
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
        connection.close()
        return response.status, payload, set_cookie

    def test_http_archive_unarchive_and_bootstrap_preview(self):
        status, session, cookie = self.request("POST", "/api/auth/login", {"username": "u1", "password": "test-password"})
        self.assertEqual(status, 200)
        cookie = cookie.split(";", 1)[0]
        csrf = session["csrf_token"]
        status, project, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": "HTTP 归档"}, cookie, csrf)
        self.assertEqual(status, 201)
        path = f"/api/workspaces/1/timeline/projects/{project['project_id']}/archive"
        status, archived, _ = self.request("POST", path, {"base_version": project["version"]}, cookie, csrf)
        self.assertEqual((status, archived["read_only"]), (200, True))
        status, listing, _ = self.request("GET", "/api/workspaces/1/timeline?archive_state=archived", cookie=cookie)
        self.assertEqual([row["project_id"] for row in listing["projects"]], [project["project_id"]])
        status, restored, _ = self.request("POST", path.replace("/archive", "/unarchive"), {"base_version": archived["version"]}, cookie, csrf)
        self.assertEqual((status, restored["read_only"]), (200, False))
        status, preview, _ = self.request("POST", "/api/admin/workspaces/1/timeline/archive-bootstrap/preview", {}, cookie, csrf)
        self.assertEqual((status, preview["candidate_count"]), (200, 0))


if __name__ == "__main__":
    unittest.main()
