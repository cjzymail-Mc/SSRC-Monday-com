import http.client
import json
import os
import tempfile
import threading
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from flowboard.database import connect, migrate
from server import create_server


class Probe:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b003-cp1-planner-")
        self.db_path = str(Path(self.temp.name) / "probe.db")
        migrate(self.db_path, initial_password="probe-password")
        db = connect(self.db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
        db.execute("INSERT INTO users SELECT 'u4','u4','外部',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.commit()
        db.close()
        self.server = create_server("127.0.0.1", 0, self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, *, cookie=None, csrf=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        raw = json.dumps(body).encode() if body is not None else None
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        cookie_out = response.getheader("Set-Cookie")
        status = response.status
        connection.close()
        return status, payload, cookie_out

    def login(self, username):
        status, payload, cookie = self.request("POST", "/api/auth/login", {"username": username, "password": "probe-password"})
        assert status == 200, (status, payload)
        return cookie.split(";", 1)[0], payload["csrf_token"]

    def count(self, table, where="1=1", args=()):
        db = connect(self.db_path)
        try:
            return db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]
        finally:
            db.close()

    def create(self, cookie, csrf, name):
        status, payload, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": name}, cookie=cookie, csrf=csrf)
        assert status == 201, (status, payload)
        return payload

    def run(self):
        admin, admin_csrf = self.login("u1")
        member, member_csrf = self.login("u2")
        viewer, viewer_csrf = self.login("u3")
        outsider, _ = self.login("u4")

        # R04: response/created_by plus three fail-capable, zero-write negatives.
        baseline = self.count("timeline_projects")
        created = self.create(member, member_csrf, "独立验收项目")
        assert created["created_by"] == "u2" and created["version"] == 1
        assert self.count("timeline_projects") == baseline + 1
        for cookie, csrf, name, expected in [
            (member, None, "无csrf", (403, "CSRF_INVALID")),
            (viewer, viewer_csrf, "只读创建", (403, "PROJECT_FORBIDDEN")),
            (member, member_csrf, "独立验收项目", (422, "NAME_CONFLICT")),
        ]:
            before = self.count("timeline_projects")
            status, payload, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": name}, cookie=cookie, csrf=csrf)
            assert (status, payload["error"]["code"]) == expected
            assert self.count("timeline_projects") == before

        project_id = created["project_id"]
        status, empty, _ = self.request("GET", f"/api/timeline/projects/{project_id}", cookie=member)
        assert status == 200 and empty["created_by"] == "u2"
        today = date.fromisoformat(empty["server_today"])
        week_start = today - timedelta(days=today.weekday())
        overdue = today - timedelta(days=1)
        assert overdue >= week_start, "red/orange coexistence fixture requires a non-Monday run"
        changes = [
            {"create": {"track": "main", "stage": "创意", "name": "逾期且本周", "date": overdue.isoformat()}},
            {"create": {"track": "main", "stage": "设计", "name": "同日重叠", "date": overdue.isoformat()}},
            {"create": {"track": "main", "stage": "创意", "name": "今天", "date": today.isoformat()}},
        ]
        status, batch, _ = self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": project_id, "base_version": 1, "changes": changes}]}, cookie=member, csrf=member_csrf)
        assert status == 200, (status, batch)

        # R01/R02: success shapes, M3/M5, red+orange, overlap rows, auth/membership.
        status, listing, _ = self.request("GET", "/api/workspaces/1/timeline", cookie=member)
        view = next(item for item in listing["projects"] if item["project_id"] == project_id)
        required = {"project_id", "name", "created_by", "version", "nodes", "segments", "stage_intervals", "metrics", "server_today"}
        assert status == 200 and required <= view.keys()
        assert view["metrics"]["upcoming"] and view["metrics"]["this_week_count"] > 0
        assert view["metrics"]["overdue_count"] > 0  # red and orange independently true
        assert max(item["row_index"] for item in view["stage_intervals"]) > 0
        status, single, _ = self.request("GET", f"/api/timeline/projects/{project_id}", cookie=member)
        assert status == 200 and single["metrics"] == view["metrics"] and single["stage_intervals"] == view["stage_intervals"]
        for path, cookie, expected in [
            ("/api/workspaces/1/timeline", None, (401, "AUTH_REQUIRED")),
            ("/api/workspaces/1/timeline", viewer, (403, "PROJECT_FORBIDDEN")),
            (f"/api/timeline/projects/{project_id}", viewer, (403, "PROJECT_FORBIDDEN")),
            (f"/api/timeline/projects/{project_id}", outsider, (403, "PROJECT_FORBIDDEN")),
        ]:
            status, payload, _ = self.request("GET", path, cookie=cookie)
            assert (status, payload["error"]["code"]) == expected

        # R03: create 51 actual HTTP batches, then assert cap/order/shape/has_more.
        node_id = single["nodes"][0]["id"]
        version = single["version"]
        for index in range(51):
            new_date = (overdue - timedelta(days=(index % 2) + 1)).isoformat()
            status, result, _ = self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": project_id, "base_version": version, "changes": [{"node_id": node_id, "set": {"date": new_date}}]}]}, cookie=member, csrf=member_csrf)
            assert status == 200, (index, status, result)
            version = result["results"][0]["version"]
        status, review, _ = self.request("GET", f"/api/workspaces/1/timeline/review?project_ids={project_id}", cookie=member)
        review_project = review["projects"][0]
        batches = review_project["batches"]
        assert status == 200 and len(batches) == 50 and review_project["has_more"] is True
        assert [row["batch_id"] for row in batches] == sorted((row["batch_id"] for row in batches), reverse=True)
        assert all(row["actor"] == {"id": "u2", "name": "成员"} for row in batches)
        assert all(row["change_rows"] for row in batches)
        status, payload, _ = self.request("GET", f"/api/workspaces/1/timeline/review?project_ids={project_id}", cookie=viewer)
        assert (status, payload["error"]["code"]) == (403, "PROJECT_FORBIDDEN")

        # R05: missing CSRF/version, conflict, member all write nothing; admin soft-deletes.
        doomed = self.create(member, member_csrf, "删除验收")
        doomed_id = doomed["project_id"]
        path = f"/api/workspaces/1/timeline/projects/{doomed_id}"
        negatives = [
            (admin, None, {"base_version": 1}, (403, "CSRF_INVALID")),
            (admin, admin_csrf, {}, (428, "VERSION_REQUIRED")),
            (admin, admin_csrf, {"base_version": 2}, (409, "VERSION_CONFLICT")),
            (member, member_csrf, {"base_version": 1}, (403, "ADMIN_REQUIRED")),
        ]
        for cookie, csrf, body, expected in negatives:
            before = self.count("timeline_projects", "id=? AND deleted_at IS NOT NULL", (doomed_id,))
            status, payload, _ = self.request("DELETE", path, body, cookie=cookie, csrf=csrf)
            assert (status, payload["error"]["code"]) == expected
            assert self.count("timeline_projects", "id=? AND deleted_at IS NOT NULL", (doomed_id,)) == before == 0
        status, deleted, _ = self.request("DELETE", path, {"base_version": 1}, cookie=admin, csrf=admin_csrf)
        assert status == 200 and deleted["project_id"] == doomed_id and deleted["version"] == 2 and deleted["deleted_at"]
        assert self.count("timeline_projects", "id=? AND deleted_at IS NOT NULL", (doomed_id,)) == 1
        status, payload, _ = self.request("GET", f"/api/timeline/projects/{doomed_id}", cookie=admin)
        assert (status, payload["error"]["code"]) == (404, "PROJECT_NOT_ACTIVE")
        status, payload, _ = self.request("DELETE", path, {"base_version": 2}, cookie=admin, csrf=admin_csrf)
        assert (status, payload["error"]["code"]) == (404, "PROJECT_NOT_ACTIVE")
        assert self.count("timeline_projects", "id=? AND deleted_at IS NOT NULL", (doomed_id,)) == 1
        print(json.dumps({"R01": "PASS", "R02": "PASS", "R03": "PASS", "R04": "PASS", "R05": "PASS", "review_batches": len(batches), "has_more": True, "metrics": view["metrics"], "max_row_index": max(item["row_index"] for item in view["stage_intervals"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    probe = Probe()
    try:
        probe.run()
    finally:
        probe.close()
