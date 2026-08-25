import hashlib
import http.client
import json
import os
import tempfile
import threading
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from flowboard.database import connect, migrate
from server import create_server


TABLES = ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes")
results = []


def check(name, condition, observed=None):
    if not condition:
        raise AssertionError(f"{name}: {observed!r}")
    results.append({"check": name, "status": "PASS", "observed": observed})


class Harness:
    def __init__(self, route):
        self.route = route
        self.temp = tempfile.TemporaryDirectory(prefix=f"b003-cp2-{route.lower()}-")
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

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()
        os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)

    def request(self, method, path, body=None, cookie=None, csrf=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = conn.getresponse()
        payload = json.loads(response.read())
        status = response.status
        set_cookie = response.getheader("Set-Cookie")
        conn.close()
        return status, payload, set_cookie

    def login(self, username="u1"):
        status, payload, cookie = self.request("POST", "/api/auth/login", {"username": username, "password": "test-password"})
        check(f"{self.route}.{username}.login", status == 200, status)
        return cookie.split(";", 1)[0], payload["csrf_token"]

    def project(self, cookie, csrf, name):
        status, payload, _ = self.request("POST", "/api/workspaces/1/timeline/projects", {"name": name}, cookie, csrf)
        check(f"{self.route}.{name}.create", status == 201, (status, payload))
        return payload

    def batch(self, cookie, csrf, project_id, version, changes):
        return self.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": project_id, "base_version": version, "changes": changes}]}, cookie, csrf)

    def state(self):
        db = connect(self.db_path)
        try:
            rows = []
            for table in TABLES:
                rows.append((table, [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1")]))
            return hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()
        finally:
            db.close()


def error(response):
    status, payload, _ = response
    return status, payload.get("error", {}).get("code")


def complete_view(payload):
    view = payload["results"][0]["view"]
    return {"nodes", "segments", "stage_intervals", "metrics", "server_today"} <= set(view)


def probe_r06():
    h = Harness("R06")
    try:
        admin, csrf = h.login()
        viewer, viewer_csrf = h.login("u3")
        p = h.project(admin, csrf, "R06-A")
        pid = p["project_id"]
        changes = [
            {"create": {"track": "main", "stage": "创意", "name": "A", "date": "2026-08-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "B", "date": "2036-07-29"}},
        ]
        status, made, _ = h.batch(admin, csrf, pid, 1, changes)
        check("R06.success_complete_view", status == 200 and complete_view(made), status)
        nodes = made["results"][0]["view"]["nodes"]
        check("R06.interval_3650_accept", nodes[1]["interval_days"] == 3650, nodes[1]["interval_days"])

        stable = h.state()
        r = h.batch(admin, None, pid, 2, [{"node_id": nodes[1]["id"], "set": {"remark": "x"}}])
        check("R06.csrf_zero_write", error(r) == (403, "CSRF_INVALID") and h.state() == stable, error(r))
        r = h.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [{"project_id": pid, "changes": [{"node_id": nodes[1]["id"], "set": {"remark": "x"}}]}]}, admin, csrf)
        check("R06.missing_version_428_zero_write", error(r) == (428, "VERSION_REQUIRED") and h.state() == stable, error(r))
        r = h.batch(admin, csrf, pid, 999, [{"node_id": nodes[1]["id"], "set": {"remark": "x"}}])
        check("R06.version_conflict_zero_write", error(r) == (409, "VERSION_CONFLICT") and h.state() == stable, error(r))
        r = h.batch(viewer, viewer_csrf, pid, 2, [{"node_id": nodes[1]["id"], "set": {"remark": "x"}}])
        check("R06.permission_zero_write", error(r) == (403, "PROJECT_FORBIDDEN") and h.state() == stable, error(r))
        r = h.batch(admin, csrf, pid, 2, [{"node_id": nodes[1]["id"], "set": {"interval_days": 3651}}])
        check("R06.interval_3651_reject_zero_write", error(r) == (422, "VALIDATION_ERROR") and h.state() == stable, error(r))

        other = h.project(admin, csrf, "R06-B")
        atomic = h.state()
        r = h.request("POST", "/api/workspaces/1/timeline/batches", {"requests": [
            {"project_id": pid, "base_version": 2, "changes": [{"node_id": nodes[0]["id"], "set": {"remark": "must-rollback"}}]},
            {"project_id": other["project_id"], "base_version": 999, "changes": [{"create": {"track": "main", "stage": "创意", "name": "must-rollback", "date": "2026-08-01"}}]},
        ]}, admin, csrf)
        check("R06.multi_project_atomic_zero_write", error(r) == (409, "VERSION_CONFLICT") and h.state() == atomic, error(r))
    finally:
        h.close()


def probe_r07():
    h = Harness("R07")
    try:
        admin, csrf = h.login()
        member, member_csrf = h.login("u2")
        p = h.project(admin, csrf, "R07-A")
        status, made, _ = h.batch(admin, csrf, p["project_id"], 1, [{"create": {"track": "main", "stage": "创意", "name": "N", "date": "2026-08-01"}}])
        check("R07.fixture_batch", status == 200, status)
        bid = made["results"][0]["batch_id"]
        path = "/api/workspaces/1/timeline/batches/undo"
        stable = h.state()
        r = h.request("POST", path, {"batch_ids": [bid]}, admin, None)
        check("R07.csrf_zero_write", error(r) == (403, "CSRF_INVALID") and h.state() == stable, error(r))
        status, undone, _ = h.request("POST", path, {"batch_ids": [bid]}, admin, csrf)
        check("R07.success_complete_view", status == 200 and complete_view(undone) and undone["results"][0]["view"]["nodes"] == [], status)
        undo_bid = undone["results"][0]["batch_id"]
        stable = h.state()
        r = h.request("POST", path, {"batch_ids": [bid]}, admin, csrf)
        check("R07.stale_zero_write", error(r) == (409, "UNDO_TARGET_STALE") and h.state() == stable, error(r))
        r = h.request("POST", path, {"batch_ids": [undo_bid]}, admin, csrf)
        check("R07.undo_of_undo_zero_write", error(r) == (409, "UNDO_TARGET_STALE") and h.state() == stable, error(r))

        deleted = h.project(admin, csrf, "R07-deleted")
        _, made, _ = h.batch(admin, csrf, deleted["project_id"], 1, [{"create": {"track": "main", "stage": "创意", "name": "D", "date": "2026-08-01"}}])
        deleted_bid = made["results"][0]["batch_id"]
        h.request("DELETE", f"/api/workspaces/1/timeline/projects/{deleted['project_id']}", {"base_version": 2}, admin, csrf)
        stable = h.state()
        r = h.request("POST", path, {"batch_ids": [deleted_bid]}, admin, csrf)
        check("R07.soft_deleted_404_zero_write", error(r) == (404, "PROJECT_NOT_ACTIVE") and h.state() == stable, error(r))

        owned = h.project(member, member_csrf, "R07-member")
        _, made, _ = h.batch(member, member_csrf, owned["project_id"], 1, [{"create": {"track": "main", "stage": "创意", "name": "M", "date": "2026-08-01"}}])
        node = made["results"][0]["view"]["nodes"][0]
        correction = {"project_id": owned["project_id"], "base_version": 2, "corrections": [{"node_id": node["id"], "initial_date": "2026-07-01"}]}
        status, corrected, _ = h.request("POST", "/api/workspaces/1/timeline/batches/initial-correction", correction, admin, csrf)
        check("R07.initial_correction_fixture", status == 200, status)
        correction_bid = corrected["results"][0]["batch_id"]
        stable = h.state()
        r = h.request("POST", path, {"batch_ids": [correction_bid]}, member, member_csrf)
        check("R07.member_undo_initial_403_zero_write", error(r) == (403, "ADMIN_REQUIRED") and h.state() == stable, error(r))
    finally:
        h.close()


def probe_r08():
    h = Harness("R08")
    try:
        admin, csrf = h.login()
        member, member_csrf = h.login("u2")
        viewer, viewer_csrf = h.login("u3")
        p = h.project(admin, csrf, "R08-A")
        pid = p["project_id"]
        _, made, _ = h.batch(admin, csrf, pid, 1, [
            {"create": {"track": "main", "stage": "创意", "name": "A", "date": "2026-08-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "B", "date": "2026-08-05"}},
        ])
        nodes = made["results"][0]["view"]["nodes"]
        path = "/api/workspaces/1/timeline/batches/initial-correction"
        body = {"project_id": pid, "base_version": 2, "corrections": [{"node_id": nodes[0]["id"], "initial_date": "2026-09-01"}]}
        stable = h.state()
        r = h.request("POST", path, body, admin, None)
        check("R08.csrf_zero_write", error(r) == (403, "CSRF_INVALID") and h.state() == stable, error(r))
        missing = {"project_id": pid, "corrections": body["corrections"]}
        r = h.request("POST", path, missing, admin, csrf)
        check("R08.missing_version_428_zero_write", error(r) == (428, "VERSION_REQUIRED") and h.state() == stable, error(r))
        conflict = {**body, "base_version": 999}
        r = h.request("POST", path, conflict, admin, csrf)
        check("R08.version_conflict_zero_write", error(r) == (409, "VERSION_CONFLICT") and h.state() == stable, error(r))
        r = h.request("POST", path, body, viewer, viewer_csrf)
        check("R08.permission_zero_write", error(r) == (403, "PROJECT_FORBIDDEN") and h.state() == stable, error(r))
        r = h.request("POST", path, body, member, member_csrf)
        check("R08.foreign_member_forbidden_zero_write", error(r) == (403, "PROJECT_FORBIDDEN") and h.state() == stable, error(r))

        owned = h.project(member, member_csrf, "R08-member")
        _, member_made, _ = h.batch(member, member_csrf, owned["project_id"], 1, [{"create": {"track": "main", "stage": "创意", "name": "M", "date": "2026-08-01"}}])
        member_node = member_made["results"][0]["view"]["nodes"][0]
        member_body = {"project_id": owned["project_id"], "base_version": 2, "corrections": [{"node_id": member_node["id"], "initial_date": "2026-07-01"}]}
        member_stable = h.state()
        r = h.request("POST", path, member_body, member, member_csrf)
        check("R08.admin_required_zero_write", error(r) == (403, "ADMIN_REQUIRED") and h.state() == member_stable, error(r))

        status, corrected, _ = h.request("POST", path, body, admin, csrf)
        view = corrected["results"][0]["view"]
        observed = [(n["initial_date"], n["date"]) for n in view["nodes"]]
        check("R08.no_clamp_no_cascade_no_date_change", status == 200 and observed == [("2026-09-01", "2026-08-01"), ("2026-08-05", "2026-08-05")], observed)
        stable = h.state()
        noop = {**body, "base_version": 3}
        status, payload, _ = h.request("POST", path, noop, admin, csrf)
        check("R08.noop_no_version_or_write", status == 200 and payload["results"][0]["no_op"] is True and payload["results"][0]["version"] == 3 and h.state() == stable, (status, payload))
        invalid = {"project_id": pid, "base_version": 3, "corrections": [{"node_id": 999999, "initial_date": "2026-01-01"}]}
        r = h.request("POST", path, invalid, admin, csrf)
        check("R08.invalid_node_zero_write", error(r) == (422, "VALIDATION_ERROR") and h.state() == stable, error(r))
        h.request("DELETE", f"/api/workspaces/1/timeline/projects/{pid}", {"base_version": 3}, admin, csrf)
        stable = h.state()
        deleted = {"project_id": pid, "base_version": 4, "corrections": [{"node_id": nodes[0]["id"], "initial_date": "2026-07-01"}]}
        r = h.request("POST", path, deleted, admin, csrf)
        check("R08.soft_deleted_404_zero_write", error(r) == (404, "PROJECT_NOT_ACTIVE") and h.state() == stable, error(r))
    finally:
        h.close()


if __name__ == "__main__":
    probe_r06()
    probe_r07()
    probe_r08()
    counts = {route: sum(1 for item in results if item["check"].startswith(route + ".")) for route in ("R06", "R07", "R08")}
    print(json.dumps({"status": "PASS", "counts": counts, "checks": results}, ensure_ascii=False, indent=2))
