"""Independent B-003 CP5 same-disk HTTP verifier (planner-owned evidence)."""
import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("timeline_http", ROOT / "tests/test_timeline_http.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from flowboard.database import connect
from flowboard.transfer import make_xlsx


def require(status, expected, label, payload):
    if status != expected:
        raise AssertionError(f"{label}: expected {expected}, got {status}: {payload}")


case = module.TimelineHTTPTests(methodName="runTest")
case.setUp()
try:
    cookie, csrf = case.login()

    tables = ("timeline_projects", "timeline_nodes", "timeline_change_batches",
              "timeline_node_changes", "timeline_import_batches", "audit_log")
    def snapshot():
        db = connect(case.db_path)
        try:
            data = {}
            for table in tables:
                rows = [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1")]
                data[table] = rows
            raw = json.dumps(data, ensure_ascii=False, default=str, sort_keys=True).encode()
            return {"counts": {k: len(v) for k, v in data.items()}, "sha256": hashlib.sha256(raw).hexdigest()}
        finally:
            db.close()

    # Every write route must reject missing CSRF before parsing/mutation.
    csrf_cases = [
        ("R04", "POST", "/api/workspaces/1/timeline/projects", {"name": "csrf"}),
        ("R05", "DELETE", "/api/workspaces/1/timeline/projects/999", {"base_version": 1}),
        ("R06", "POST", "/api/workspaces/1/timeline/batches", {"requests": []}),
        ("R07", "POST", "/api/workspaces/1/timeline/batches/undo", {"batch_ids": [1]}),
        ("R08", "POST", "/api/workspaces/1/timeline/batches/initial-correction", {"project_id": 1, "base_version": 1, "corrections": []}),
        ("R09", "POST", "/api/workspaces/1/timeline/imports/preview", {}),
        ("R10", "POST", "/api/workspaces/1/timeline/imports/commit", {"batch_id": 1}),
        ("R11", "POST", "/api/workspaces/1/timeline/export", {}),
    ]
    csrf_results = {}
    for rid, method, path, body in csrf_cases:
        before = snapshot()
        status, payload, _ = case.request(method, path, body, cookie=cookie)
        require(status, 403, f"{rid} missing CSRF", payload)
        if payload.get("error", {}).get("code") != "CSRF_INVALID":
            raise AssertionError(f"{rid}: wrong error {payload}")
        after = snapshot()
        if before != after:
            raise AssertionError(f"{rid}: missing-CSRF request wrote state: {before} != {after}")
        csrf_results[rid] = {"status": status, "zero_write": True, **after}

    success = {}
    created = case.create_project(cookie, csrf, "CP5 同盘项目")
    pid = created["project_id"]
    success["R04"] = 201
    for rid, path in (("R01", "/api/workspaces/1/timeline"), ("R02", f"/api/timeline/projects/{pid}"), ("R03", "/api/workspaces/1/timeline/review")):
        status, payload, _ = case.request("GET", path, cookie=cookie)
        require(status, 200, rid, payload)
        success[rid] = status
    status, batched, _ = case.batch(cookie, csrf, pid, 1, [{"create": {"track": "main", "stage": "创意", "name": "CP5-N", "date": "2026-08-10"}}])
    require(status, 200, "R06", batched); success["R06"] = status
    node_id = batched["results"][0]["view"]["nodes"][0]["id"]
    status, corrected, _ = case.request("POST", "/api/workspaces/1/timeline/batches/initial-correction", {"project_id": pid, "base_version": 2, "corrections": [{"node_id": node_id, "initial_date": "2026-08-01"}]}, cookie=cookie, csrf=csrf)
    require(status, 200, "R08", corrected); success["R08"] = status
    correction_batch = corrected["results"][0]["batch_id"]
    status, undone, _ = case.request("POST", "/api/workspaces/1/timeline/batches/undo", {"batch_ids": [correction_batch]}, cookie=cookie, csrf=csrf)
    require(status, 200, "R07", undone); success["R07"] = status

    headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
    raw = make_xlsx(headers, [["CP5 导入", "创意", "main", "I1", "2026-08-12", "", "", ""]], "Timeline")
    upload = case.upload("cp5.xlsx", raw)
    status, preview, _ = case.request("POST", "/api/workspaces/1/timeline/imports/preview", upload, cookie=cookie, csrf=csrf)
    require(status, 201, "R09", preview); success["R09"] = status
    status, committed, _ = case.request("POST", "/api/workspaces/1/timeline/imports/commit", {"batch_id": preview["batch_id"]}, cookie=cookie, csrf=csrf)
    require(status, 201, "R10", committed); success["R10"] = status
    status, exported, _ = case.request("POST", "/api/workspaces/1/timeline/export", {}, cookie=cookie, csrf=csrf)
    require(status, 200, "R11", exported)
    decoded = base64.b64decode(exported["content_base64"], validate=True)
    if hashlib.sha256(decoded).hexdigest() != exported["sha256"]:
        raise AssertionError("R11 sha256 mismatch")
    success["R11"] = status

    negative_results = {}
    def zero_write(label, method, path, body, expected, *, who=cookie, token=csrf):
        before = snapshot()
        status, payload, _ = case.request(method, path, body, cookie=who, csrf=token)
        require(status, expected, label, payload)
        after = snapshot()
        if before != after:
            raise AssertionError(f"{label}: 4xx wrote state: {before} != {after}")
        negative_results[label] = {"status": status, "zero_write": True, **after}
        return payload

    member_cookie, member_csrf = case.login("u2")
    viewer_cookie, viewer_csrf = case.login("u3")
    zero_write("viewer_read", "GET", "/api/workspaces/1/timeline", None, 403, who=viewer_cookie, token=None)
    zero_write("member_writes_other", "POST", "/api/workspaces/1/timeline/batches",
               {"requests": [{"project_id": pid, "base_version": 4, "changes": [{"node_id": node_id, "set": {"remark": "x"}}]}]},
               403, who=member_cookie, token=member_csrf)
    zero_write("admin_only_delete", "DELETE", f"/api/workspaces/1/timeline/projects/{pid}",
               {"base_version": 4}, 403, who=member_cookie, token=member_csrf)
    zero_write("cross_workspace", "DELETE", f"/api/workspaces/2/timeline/projects/{pid}",
               {"base_version": 4}, 403)
    zero_write("version_conflict", "POST", "/api/workspaces/1/timeline/batches",
               {"requests": [{"project_id": pid, "base_version": 999, "changes": [{"node_id": node_id, "set": {"remark": "x"}}]}]}, 409)
    zero_write("undo_stale", "POST", "/api/workspaces/1/timeline/batches/undo",
               {"batch_ids": [batched["results"][0]["batch_id"]]}, 409)
    zero_write("import_replay", "POST", "/api/workspaces/1/timeline/imports/commit",
               {"batch_id": preview["batch_id"]}, 409)
    race_raw = make_xlsx(headers, [["CP5 竞态", "创意", "main", "R1", "2026-08-12", "", "", ""]], "Timeline")
    status, race_preview, _ = case.request("POST", "/api/workspaces/1/timeline/imports/preview", case.upload("race.xlsx", race_raw), cookie=cookie, csrf=csrf)
    require(status, 201, "race preview setup", race_preview)
    case.create_project(cookie, csrf, "CP5 竞态")
    zero_write("import_race", "POST", "/api/workspaces/1/timeline/imports/commit",
               {"batch_id": race_preview["batch_id"]}, 422)
    zero_write("export_get", "GET", "/api/workspaces/1/timeline/export", None, 404, token=None)
    current = case.request("GET", f"/api/timeline/projects/{pid}", cookie=cookie)[1]
    status, deleted, _ = case.request("DELETE", f"/api/workspaces/1/timeline/projects/{pid}", {"base_version": current["version"]}, cookie=cookie, csrf=csrf)
    require(status, 200, "R05", deleted); success["R05"] = status
    zero_write("soft_deleted_correction", "POST", "/api/workspaces/1/timeline/batches/initial-correction",
               {"project_id": pid, "base_version": deleted["version"], "corrections": [{"node_id": node_id, "initial_date": "2026-01-01"}]}, 404)

    if set(success) != {f"R{i:02d}" for i in range(1, 12)}:
        raise AssertionError(f"route set mismatch: {sorted(success)}")
    result = {"result": "PASS", "port": case.port, "db": case.db_path,
              "success_routes": success, "csrf_routes": csrf_results,
              "negative_controls": negative_results,
              "final_snapshot": snapshot()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
finally:
    case.tearDown()
