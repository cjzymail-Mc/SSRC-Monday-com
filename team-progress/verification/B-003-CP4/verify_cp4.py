import base64
import hashlib
import http.client
import json
import os
import tempfile
import threading
from pathlib import Path

from flowboard.database import connect, migrate
from flowboard.transfer import parse_upload
from server import create_server


HEADERS = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]


def check(condition, key, actual=None):
    if not condition:
        raise AssertionError(f"{key}: {actual!r}")
    print(f"PASS {key}")


class Probe:
    def __init__(self, db_path):
        self.db_path = db_path
        self.server = create_server("127.0.0.1", 0, db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, cookie=None, csrf=None):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, None if body is None else json.dumps(body).encode(), headers)
        response = conn.getresponse()
        raw = response.read()
        payload = json.loads(raw)
        cookie_out = response.getheader("Set-Cookie")
        status = response.status
        conn.close()
        return status, payload, cookie_out

    def login(self, username):
        status, payload, cookie = self.request("POST", "/api/auth/login", {"username": username, "password": "test-password"})
        check(status == 200, f"LOGIN_{username}", (status, payload))
        return cookie.split(";", 1)[0], payload["csrf_token"]


def main():
    os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
    with tempfile.TemporaryDirectory(prefix="planner-cp4-") as directory:
        db_path = str(Path(directory) / "flowboard.db")
        migrate(db_path, initial_password="test-password")
        db = connect(db_path)
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
        db.execute("INSERT INTO workspaces VALUES (2,'回导空间','2026-01-01T00:00:00+00:00',30)")
        db.execute("INSERT INTO workspace_memberships VALUES (2,'u1','admin')")
        db.commit()
        db.close()

        probe = Probe(db_path)
        try:
            cookie, csrf = probe.login("u1")
            viewer_cookie, viewer_csrf = probe.login("u3")

            project_ids = []
            for name in ("P10", "P2"):
                status, payload, _ = probe.request("POST", "/api/workspaces/1/timeline/projects", {"name": name}, cookie, csrf)
                check(status == 201, f"CREATE_{name}", (status, payload))
                project_ids.append(payload["project_id"])

            changes = [
                {"create": {"track": "parallel", "stage": "设计", "name": "Z", "date": "2026-08-01", "done_at": True}},
                {"create": {"track": "main", "stage": "创意", "name": "N10", "date": "2026-08-01", "done_at": True}},
                {"create": {"track": "main", "stage": "创意", "name": "N2", "date": "2026-08-01", "done_at": True}},
                {"create": {"track": "main", "stage": "创意", "name": "Same", "date": "2026-08-01", "done_at": True, "remark": "id-first"}},
                {"create": {"track": "main", "stage": "创意", "name": "same", "date": "2026-08-01", "done_at": True, "remark": "id-second"}},
                {"create": {"track": "main", "stage": "开发", "name": "Earlier", "date": "2026-07-31", "done_at": True}},
            ]
            body = {"requests": [{"project_id": project_ids[0], "base_version": 1, "changes": changes}]}
            status, payload, _ = probe.request("POST", "/api/workspaces/1/timeline/batches", body, cookie, csrf)
            check(status == 200, "SEED_PROJECT_1", (status, payload))
            body = {"requests": [{"project_id": project_ids[1], "base_version": 1, "changes": [{"create": {"track": "main", "stage": "测试", "name": "Only", "date": "2026-08-03", "done_at": True}}]}]}
            status, payload, _ = probe.request("POST", "/api/workspaces/1/timeline/batches", body, cookie, csrf)
            check(status == 200, "SEED_PROJECT_2", (status, payload))

            path = "/api/workspaces/1/timeline/export"
            status, _, _ = probe.request("GET", path, cookie=cookie)
            check(status != 200, "R11_GET_NOT_SUCCESS", status)
            status, payload, _ = probe.request("POST", path, {}, cookie=cookie)
            check((status, payload["error"]["code"]) == (403, "CSRF_INVALID"), "R11_CSRF", (status, payload))
            status, payload, _ = probe.request("POST", path, {}, viewer_cookie, viewer_csrf)
            check((status, payload["error"]["code"]) == (403, "PROJECT_FORBIDDEN"), "R11_VIEWER", (status, payload))
            for field in ("project_id", "project_ids"):
                status, payload, _ = probe.request("POST", path, {field: project_ids[0]}, cookie, csrf)
                check(status != 200, f"R11_REJECT_{field}", (status, payload))

            status, exported, _ = probe.request("POST", path, {}, cookie, csrf)
            check(status == 200, "R11_POST_200", (status, exported))
            raw = base64.b64decode(exported["content_base64"], validate=True)
            check(hashlib.sha256(raw).hexdigest() == exported["sha256"], "R11_SHA256")
            parsed = parse_upload(exported["filename"], raw)
            check(parsed["headers"] == HEADERS, "R11_8_COLUMNS", parsed["headers"])
            check(len(parsed["sheets"]) == 1, "R11_ONE_SHEET", parsed["sheets"])
            observed = [(row[0], row[2], row[3], row[7]) for row in parsed["rows"]]
            expected = [("P10", "main", "Earlier", ""), ("P10", "main", "N2", ""), ("P10", "main", "N10", ""), ("P10", "main", "Same", "id-first"), ("P10", "main", "same", "id-second"), ("P10", "parallel", "Z", ""), ("P2", "main", "Only", "")]
            check(observed == expected, "D6_ORDER_PROJECT_TRACK_DATE_NATURAL_ID", observed)

            upload = {"filename": "planner-roundtrip.xlsx", "content_base64": base64.b64encode(raw).decode()}
            status, preview, _ = probe.request("POST", "/api/workspaces/2/timeline/imports/preview", upload, cookie, csrf)
            check((status, preview.get("row_count")) == (201, 7), "R09_REAL_EXPORT_PREVIEW", (status, preview))
            status, committed, _ = probe.request("POST", "/api/workspaces/2/timeline/imports/commit", {"batch_id": preview["batch_id"]}, cookie, csrf)
            check((status, committed.get("projects"), committed.get("nodes")) == (201, 2, 7), "R10_REAL_EXPORT_COMMIT", (status, committed))
            status, listed, _ = probe.request("GET", "/api/workspaces/2/timeline", cookie=cookie)
            check(status == 200 and len(listed["projects"]) == 2 and sum(len(item["nodes"]) for item in listed["projects"]) == 7, "R01_ROUNDTRIP_READBACK", (status, listed))

            db = connect(db_path)
            stamp = "2026-08-01T00:00:00+00:00"
            db.executemany(
                "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ((project_ids[0], "parallel", "创意", f"L{index}", "2026-08-04", "2026-08-04", "", stamp, stamp) for index in range(994)),
            )
            db.commit()
            before = db.execute("SELECT COUNT(*) FROM timeline_nodes").fetchone()[0]
            db.close()
            status, payload, _ = probe.request("POST", path, {}, cookie, csrf)
            check((status, payload["error"]["code"], payload["error"]["details"]) == (422, "EXPORT_LIMIT", {"total": 1001, "max": 1000}), "R11_LIMIT_1001", (status, payload))
            db = connect(db_path)
            after = db.execute("SELECT COUNT(*) FROM timeline_nodes").fetchone()[0]
            db.close()
            check(before == after, "R11_LIMIT_ZERO_WRITE", (before, after))
        finally:
            probe.close()
    os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)
    print("CP4_PLANNER_PASS")


if __name__ == "__main__":
    main()
