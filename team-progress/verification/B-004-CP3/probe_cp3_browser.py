import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from flowboard.database import connect, migrate
from server import create_server


TABLES = ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes")


def require(value, key, detail=None):
    if not value:
        raise AssertionError(f"{key}: {detail!r}")


def snapshot(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        rows = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")] for table in TABLES}
        hashes = {
            table: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
            for table, value in rows.items()
        }
        return hashes, {table: len(value) for table, value in rows.items()}
    finally:
        db.close()


def physical(page, locator, button="left"):
    box = locator.bounding_box()
    require(box, "NO_HIT_TARGET", str(locator))
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down(button=button)
    page.mouse.up(button=button)


def login(browser, base, username):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base)
    page.locator("#loginUser").fill(username)
    page.locator("#loginPassword").fill("test-password")
    physical(page, page.locator('#loginForm button[type="submit"]'))
    page.locator("#loadState", has_text="刚刚同步").wait_for()
    return context, page, errors


def open_editor(page, project_id):
    physical(page, page.locator("#timelineBtn"))
    page.locator('[data-timeline-page="home"]').wait_for()
    physical(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
    page.locator('[data-timeline-page="editor"] .timeline-node').first.wait_for()


def seed(db_path, created_by="u1", name="Planner CP3"):
    db = connect(db_path)
    try:
        now = "2026-08-20T00:00:00+00:00"
        pid = db.execute(
            "INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES(1,?,?,1,?,?)",
            (name, created_by, now, now),
        ).lastrowid
        ids = []
        for track, stage, node_name, date in (
            ("main", "创意", "A1", "2026-08-01"),
            ("main", "设计", "A2", "2026-08-05"),
            ("main", "开发", "A3", "2026-08-09"),
            ("parallel", "测试", "P1", "2026-08-03"),
        ):
            ids.append(db.execute(
                "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES(?,?,?,?,?,?,'',1,?,?)",
                (pid, track, stage, node_name, date, date, now, now),
            ).lastrowid)
        db.commit()
        return pid, ids
    finally:
        db.close()


def main():
    real = ROOT / "flowboard.db"
    locks = [ROOT / name for name in (".copilot-state.json", ".copilot-task.md", ".copilot-message.md")]
    guards = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in [real, *locks]}
    previous_password = os.environ.get("FLOWBOARD_INITIAL_PASSWORD")
    result = {"status": "RUNNING"}
    with tempfile.TemporaryDirectory(prefix="planner-b004-cp3-") as temp:
        db_path = str(Path(temp) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(db_path, initial_password="test-password")
        db = connect(db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.commit(); db.close()
        project_id, ids = seed(db_path)
        member_project_id, _ = seed(db_path, "u2", "Member CP3")
        server = create_server("127.0.0.1", 0, db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context, page, errors = login(browser, base, "u1")
                batches = []
                page.on("request", lambda r: batches.append(r.post_data_json) if r.method == "POST" and r.url.endswith("/timeline/batches") else None)
                open_editor(page, project_id)

                # True right-click and click: menu remains exactly four; remove is separate.
                node = page.locator(f'.timeline-node[data-node-id="{ids[0]}"]')
                page.evaluate("""id=>{window.__cp3ctx=[];const n=document.querySelector(`[data-node-id="${id}"]`);for(const t of ['mousedown','mouseup','contextmenu'])n.addEventListener(t,()=>window.__cp3ctx.push(t),{once:true})}""", ids[0])
                physical(page, node, "right")
                menu_text = page.locator('[data-timeline-context] [role="menuitem"]').all_inner_texts()
                require(page.evaluate("window.__cp3ctx") == ["mousedown", "mouseup", "contextmenu"], "RIGHT_CLICK_SEQUENCE")
                require(menu_text == ["拖拽—仅此节点", "拖拽（顺延）", "已完成", "未完成"], "RIGHT_MENU_NOT_FOUR", menu_text)
                require(page.locator('[data-timeline-remove-last]').count() == 1, "REMOVE_NOT_INDEPENDENT")
                physical(page, page.locator('[data-draft-action="cascade"]'))
                node = page.locator(f'.timeline-node[data-node-id="{ids[0]}"]'); box = node.bounding_box()
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.down(); page.mouse.move(box["x"] + box["width"] / 2 + 170, box["y"] + box["height"] / 2, steps=8); page.mouse.up()
                physical(page, page.locator(f'.timeline-node[data-node-id="{ids[1]}"]'), "right")
                physical(page, page.locator('[data-draft-action="done"]'))
                physical(page, page.locator('[data-timeline-remove-last]'))
                answers = iter(["Planner 新节点", "2026-08-15", "测试", "parallel"])
                handler = lambda dialog: dialog.accept(next(answers))
                page.on("dialog", handler); physical(page, page.locator('[data-timeline-add]')); page.remove_listener("dialog", handler)
                page.locator('.timeline-node', has_text="测试 · 2026-08-15").wait_for()
                with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/timeline/batches")) as response:
                    physical(page, page.locator('[data-timeline-submit]'))
                require(response.value.status == 200, "R06_STATUS", response.value.status)
                require(len(batches) == 1, "R06_NOT_EXACTLY_ONE", len(batches))
                request = batches[0]["requests"][0]
                require({k: request["details"].get(k) for k in ("mode", "magnet", "zoom_band")} == {"mode":"cascade","magnet":"standard","zoom_band":"±10d×8"}, "R06_DETAILS", request)
                require(any("date" in c.get("set", {}) for c in request["changes"]), "R06_NO_DATE")
                require(any("done_at" in c.get("set", {}) for c in request["changes"]), "R06_NO_STATUS")
                require(any("create" in c for c in request["changes"]), "R06_NO_CREATE")
                require(any(c.get("remove") for c in request["changes"]), "R06_NO_REMOVE")
                db = connect(db_path)
                require(db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=?", (project_id,)).fetchone()[0] == 1, "R06_BATCH_DB_COUNT")
                db.close()
                with page.expect_response(lambda r: r.url.endswith("/timeline/batches/undo")) as undone:
                    physical(page, page.locator('[data-timeline-undo]'))
                require(undone.value.status == 200, "R07_STATUS", undone.value.status)
                db = connect(db_path)
                require(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL", (project_id,)).fetchone()[0] == 4, "R07_NODE_RESTORE")
                require(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND name='Planner 新节点' AND deleted_at IS NULL", (project_id,)).fetchone()[0] == 0, "R07_CREATE_NOT_UNDONE")
                db.close()

                # Persist a status batch, reload production entry, and inspect R03 UI.
                physical(page, page.locator(f'.timeline-node[data-node-id="{ids[1]}"]'), "right"); physical(page, page.locator('[data-draft-action="done"]'))
                with page.expect_response(lambda r: r.url.endswith("/timeline/batches")) as persisted:
                    physical(page, page.locator('[data-timeline-submit]'))
                require(persisted.value.status == 200, "PERSIST_STATUS")
                page.reload(); open_editor(page, project_id)
                db = connect(db_path); require(db.execute("SELECT done_at FROM timeline_nodes WHERE id=?", (ids[1],)).fetchone()[0], "REFRESH_NOT_PERSISTED"); db.close()
                physical(page, page.locator('[data-timeline-review]'))
                panel = page.locator('[data-timeline-review-panel]'); panel.locator("article").first.wait_for()
                review_text = panel.inner_text()
                require("管理员" in review_text and "项变更" in review_text, "R03_ACTOR_CHANGE_ROWS", review_text)
                correction = lambda d: d.accept("2026-07-25")
                page.once("dialog", correction)
                with page.expect_response(lambda r: r.url.endswith("/timeline/batches/initial-correction")) as corrected:
                    physical(page, page.locator('[data-timeline-correct]'))
                require(corrected.value.status == 200, "R08_ADMIN_STATUS")

                # 409 must display server latest view and leave all four content hashes unchanged.
                physical(page, page.locator(f'.timeline-node[data-node-id="{ids[2]}"]'), "right"); physical(page, page.locator('[data-draft-action="done"]'))
                db = connect(db_path); db.execute("UPDATE timeline_projects SET version=version+1 WHERE id=?", (project_id,)); db.commit(); db.close()
                before_409 = snapshot(db_path)
                with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/timeline/batches")) as conflict:
                    physical(page, page.locator('[data-timeline-submit]'))
                conflict_json = conflict.value.json()
                require(conflict.value.status == 409, "R06_CONFLICT_STATUS")
                require(conflict_json["error"]["details"]["conflicts"][0].get("view"), "R06_NO_LATEST_VIEW", conflict_json)
                page.locator("#toast", has_text="已显示服务端最新时间线").wait_for()
                require(page.locator('[data-timeline-draft-count]').inner_text() == "0 项草稿", "R06_LATEST_VIEW_NOT_RENDERED")
                require(snapshot(db_path) == before_409, "R06_CONFLICT_WROTE_DB", {"before":before_409,"after":snapshot(db_path)})
                require(not errors, "ADMIN_PAGE_ERRORS", errors)
                context.close()

                # Member owns the project, so the precise denial must be ADMIN_REQUIRED and zero-write.
                member_context, member_page, member_errors = login(browser, base, "u2")
                open_editor(member_page, member_project_id)
                member_page.once("dialog", lambda d: d.accept("2026-07-20"))
                member_before = snapshot(db_path)
                with member_page.expect_response(lambda r: r.url.endswith("/timeline/batches/initial-correction")) as denied:
                    physical(member_page, member_page.locator('[data-timeline-correct]'))
                denied_json = denied.value.json()
                require(denied.value.status == 403 and denied_json["error"]["code"] == "ADMIN_REQUIRED", "R08_MEMBER_DENIAL", {"status":denied.value.status,"json":denied_json})
                require(snapshot(db_path) == member_before, "R08_MEMBER_WROTE_DB")
                member_page.locator("#toast", has_text="仅管理员可纠正初始日期").wait_for()
                require(not member_errors, "MEMBER_PAGE_ERRORS", member_errors)
                member_context.close(); browser.close()
                result.update({
                    "status":"PASS", "right_menu":menu_text, "remove_control":"independent",
                    "r06":{"post_count":1,"details":request["details"],"change_kinds":["date","status","create","remove"]},
                    "r07":"restored", "refresh":"persisted", "r03":"actor/change_rows visible",
                    "r08":{"admin":200,"member":403,"code":"ADMIN_REQUIRED"},
                    "conflict":{"status":409,"latest_view":True,"four_table_hash_unchanged":True},
                })
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
    if previous_password is None:
        os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)
    else:
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = previous_password
    after_guards = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in [real, *locks]}
    require(guards == after_guards, "LOCKED_FILE_CHANGED", {"before":guards,"after":after_guards})
    result["locked_files_unchanged"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
