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


def require(condition, key, detail=None):
    if not condition:
        raise AssertionError(f"{key}: {detail!r}")


def content_hash(db_path):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        payload = {}
        for table in ("timeline_projects", "timeline_nodes", "audit_log"):
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
            require(columns, "PROBE_CONTENT_HASH_TABLE_MISSING", table)
            order = "id" if "id" in columns else columns[0]
            payload[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}")]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest(), {key: len(value) for key, value in payload.items()}
    finally:
        db.close()


def install_observers(page):
    evidence = {"console": [], "pageerror": [], "responses": [], "events": []}
    page.on("console", lambda msg: evidence["console"].append({"type": msg.type, "text": msg.text}))
    page.on("pageerror", lambda error: evidence["pageerror"].append(str(error)))
    page.on("response", lambda response: evidence["responses"].append({
        "method": response.request.method,
        "url": response.url,
        "status": response.status,
    }))
    return evidence


def assert_expected_prelogin(evidence):
    sessions = [item for item in evidence["responses"] if item["url"].endswith("/api/session")]
    require([item["status"] for item in sessions] == [401], "PRELOGIN_SESSION_NOT_EXACT_401", sessions)
    errors = [item for item in evidence["console"] if item["type"] == "error"]
    require(len(errors) == 1 and "401" in errors[0]["text"], "PRELOGIN_CONSOLE_NOT_STRUCTURED", errors)
    require(not evidence["pageerror"], "PRELOGIN_PAGEERROR", evidence["pageerror"])
    evidence["console"].clear()
    evidence["pageerror"].clear()
    evidence["responses"].clear()


def login(browser, base, username):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    evidence = install_observers(page)
    login_payload = {}
    page.on("response", lambda response: login_payload.update(response.json())
            if response.url.endswith("/api/auth/login") and response.status == 200 else None)
    page.goto(base)
    page.locator("#loginUser").fill(username)
    page.locator("#loginPassword").fill("test-password")
    page.locator("#loginForm button[type=submit]").click()
    identity = page.locator("#currentUser > span:not(.avatar)")
    identity.wait_for()
    require(identity.inner_text() == {"u1": "管理员", "u2": "成员", "u3": "只读"}[username],
            "LOGIN_IDENTITY", identity.inner_text())
    page.locator("#loadState", has_text="刚刚同步").wait_for()
    assert_expected_prelogin(evidence)
    require(login_payload.get("csrf_token"), "LOGIN_CSRF_MISSING", login_payload)
    return context, page, evidence, login_payload["csrf_token"]


def record_click(page, selector, label):
    page.evaluate("""([selector, label]) => {
      window.__cp1Events ||= [];
      const target = document.querySelector(selector);
      for (const type of ['mousedown', 'mouseup', 'click']) {
        target.addEventListener(type, event => window.__cp1Events.push({
          label, type, target: event.target.getAttribute('id') || event.target.getAttribute('data-timeline-mode-target') || event.target.tagName
        }), {once: true});
      }
    }""", [selector, label])
    page.locator(selector).click()


def clean_browser(evidence, key):
    errors = [item for item in evidence["console"] if item["type"] == "error"]
    require(not errors, f"{key}_CONSOLE", errors)
    require(not evidence["pageerror"], f"{key}_PAGEERROR", evidence["pageerror"])


def click_canary(browser):
    page = browser.new_page()
    page.set_content("<button id='bad'>bad</button><button id='good'>good</button><script>window.ev=[];window.actions={bad:0,good:0};for(const id of ['bad','good']){const b=document.getElementById(id);for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>ev.push(id+':'+t));b.addEventListener('click',()=>actions[id]++);}bad.addEventListener('mousedown',()=>bad.remove());</script>")
    try:
        page.locator("#bad").click(timeout=1000)
    except Exception:
        pass
    bad_events = page.evaluate("window.ev")
    require(bad_events and bad_events[0] == "bad:mousedown", "CANARY_BAD_START", bad_events)
    require(not any(event.endswith(":click") for event in bad_events), "CANARY_BAD_CLICK_LEAK", bad_events)
    require("bad:mouseup" not in bad_events, "CANARY_BAD_MOUSEUP_ON_REMOVED_TARGET", bad_events)
    require(page.evaluate("window.actions.bad") == 0, "CANARY_BAD_ACTION_FIRED", page.evaluate("window.actions"))
    page.evaluate("window.ev=[]")
    page.locator("#good").click()
    require(page.evaluate("window.ev") == ["good:mousedown", "good:mouseup", "good:click"],
            "CANARY_GOOD_SEQUENCE", page.evaluate("window.ev"))
    require(page.evaluate("window.actions.good") == 1, "CANARY_GOOD_ACTION_MISSING", page.evaluate("window.actions"))
    page.close()
    return {"bad": ["mousedown"], "good": ["mousedown", "mouseup", "click"]}


def main():
    old_password = os.environ.get("FLOWBOARD_INITIAL_PASSWORD")
    real_db = ROOT / "flowboard.db"
    real_before = (real_db.stat().st_size, real_db.stat().st_mtime_ns, hashlib.sha256(real_db.read_bytes()).hexdigest())
    with tempfile.TemporaryDirectory(prefix="planner-b004-cp1-") as temp:
        db_path = str(Path(temp) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(db_path, initial_password="test-password")
        db = connect(db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
        db.commit()
        db.close()
        server = create_server("127.0.0.1", 0, db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        result = {"base": base, "temporary_db": db_path}
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                result["canary"] = click_canary(browser)

                # Admin: production entry, R04, R01, R02, all three modes, reload, R05.
                context, page, ev, admin_csrf = login(browser, base, "u1")
                page.evaluate("window.__cp1Events=[]")
                record_click(page, "#timelineBtn", "entry")
                page.locator('[data-timeline-page="home"]').wait_for()
                require(page.locator('[data-timeline-create]').count() == 1, "ADMIN_CREATE_CONTROL")
                page.locator('[data-timeline-create] input[name="name"]').fill("planner独立项目")
                with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/timeline/projects")) as created:
                    page.locator('[data-timeline-create] button[type="submit"]').click()
                require(created.value.status == 201, "R04_CREATE_STATUS", created.value.status)
                page.locator('[data-timeline-page="editor"] h2', has_text="planner独立项目").wait_for()
                record_click(page, '[data-timeline-mode-target="single"]', "single")
                page.locator('[data-timeline-page="single"] > .timeline-project-card > header h2', has_text="planner独立项目").wait_for()
                record_click(page, '[data-timeline-mode-target="all"]', "all")
                page.locator('[data-timeline-page="all"] .timeline-all').wait_for()
                sequences = page.evaluate("window.__cp1Events")
                for label in ("entry", "single", "all"):
                    require([x["type"] for x in sequences if x["label"] == label] == ["mousedown", "mouseup", "click"],
                            f"CLICK_SEQUENCE_{label.upper()}", sequences)
                require(any(x["status"] == 200 and "/api/timeline/projects/" in x["url"] for x in ev["responses"]), "R02_NOT_OBSERVED")
                page.reload()
                page.locator("#loadState", has_text="刚刚同步").wait_for()
                page.locator("#timelineBtn").click()
                card = page.locator('[data-project-choice]', has_text="planner独立项目")
                card.wait_for()
                require(card.locator('[data-timeline-delete]').count() == 1, "ADMIN_DELETE_CONTROL")
                page.on("dialog", lambda dialog: dialog.accept())
                with page.expect_response(lambda r: r.request.method == "DELETE" and "/timeline/projects/" in r.url) as deleted:
                    card.locator('[data-timeline-delete]').click()
                require(deleted.value.status == 200, "R05_DELETE_STATUS", deleted.value.status)
                card.wait_for(state="detached")
                clean_browser(ev, "ADMIN")
                context.close()

                # Member: create is visible; delete control absent and forced R05 is server-denied with zero state delta.
                context, page, ev, member_csrf = login(browser, base, "u2")
                page.locator("#timelineBtn").click()
                page.locator('[data-timeline-page="home"]').wait_for()
                require(page.locator('[data-timeline-create]').count() == 1, "MEMBER_CREATE_CONTROL")
                require(page.locator('[data-timeline-delete]').count() == 0, "MEMBER_DELETE_CONTROL_LEAK")
                page.locator('[data-timeline-create] input[name="name"]').fill("member项目")
                page.locator('[data-timeline-create] button[type="submit"]').click()
                page.locator('[data-timeline-page="editor"] h2', has_text="member项目").wait_for()
                project_id = page.locator('[data-timeline-page="editor"] .timeline-editor').get_attribute("data-timeline-project")
                require(project_id and project_id.isdigit(), "PROBE_MEMBER_PROJECT_ID_NULL", project_id)
                member_before_hash, member_before_counts = content_hash(db_path)
                forced = page.evaluate("""async ([id, csrf]) => {const r=await fetch(`/api/workspaces/1/timeline/projects/${id}`,{method:'DELETE',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({base_version:1})});return {status:r.status,body:await r.json()}}""", [project_id, member_csrf])
                member_after_hash, member_after_counts = content_hash(db_path)
                require(forced["status"] == 403 and forced["body"].get("error", {}).get("code") == "ADMIN_REQUIRED", "MEMBER_R05_DENIAL", forced)
                require((member_before_hash, member_before_counts) == (member_after_hash, member_after_counts), "MEMBER_R05_ZERO_WRITE", [member_before_hash, member_after_hash, member_before_counts, member_after_counts])
                member_errors = [x for x in ev["console"] if x["type"] == "error"]
                require(len(member_errors) == 1 and "403" in member_errors[0]["text"], "MEMBER_R05_CONSOLE_NOT_STRUCTURED", member_errors)
                require(not ev["pageerror"], "MEMBER_R05_PAGEERROR", ev["pageerror"])
                ev["console"].clear()
                clean_browser(ev, "MEMBER")
                context.close()

                # Viewer: production entry reaches real R01 403; no modal/controls and no DB content delta.
                context, page, ev, viewer_csrf = login(browser, base, "u3")
                viewer_before_hash, viewer_before_counts = content_hash(db_path)
                page.locator("#timelineBtn").click()
                page.locator("#toast", has_text="资源不存在或不可访问").wait_for()
                denied = [x for x in ev["responses"] if x["url"].endswith("/api/workspaces/1/timeline")]
                require([x["status"] for x in denied] == [403], "VIEWER_R01_NOT_EXACT_403", denied)
                require(page.locator("#timelineModal").evaluate("e => e.hidden"), "VIEWER_MODAL_OPEN")
                require(page.locator('[data-timeline-create], [data-timeline-delete]').count() == 0, "VIEWER_CONTROL_LEAK")
                viewer_after_hash, viewer_after_counts = content_hash(db_path)
                require((viewer_before_hash, viewer_before_counts) == (viewer_after_hash, viewer_after_counts), "VIEWER_R01_ZERO_WRITE", [viewer_before_hash, viewer_after_hash])
                viewer_errors = [x for x in ev["console"] if x["type"] == "error"]
                require(len(viewer_errors) == 1 and "403" in viewer_errors[0]["text"], "VIEWER_CONSOLE_NOT_STRUCTURED", viewer_errors)
                require(not ev["pageerror"], "VIEWER_PAGEERROR", ev["pageerror"])
                ev["console"].clear()
                clean_browser(ev, "VIEWER_AFTER_EXPECTED_403")
                context.close()
                browser.close()
                result.update({
                    "status": "PASS",
                    "click_events": sequences,
                    "member_forced_delete": forced,
                    "member_zero_write": {"before": member_before_hash, "after": member_after_hash, "counts": member_after_counts},
                    "viewer_r01": denied,
                    "viewer_zero_write": {"before": viewer_before_hash, "after": viewer_after_hash, "counts": viewer_after_counts},
                    "admin_csrf_present": bool(admin_csrf),
                    "viewer_csrf_present": bool(viewer_csrf),
                })
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            if old_password is None:
                os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)
            else:
                os.environ["FLOWBOARD_INITIAL_PASSWORD"] = old_password
        real_after = (real_db.stat().st_size, real_db.stat().st_mtime_ns, hashlib.sha256(real_db.read_bytes()).hexdigest())
        require(real_before == real_after, "REAL_DB_CHANGED", [real_before, real_after])
        result["real_db"] = {"before": real_before, "after": real_after, "unchanged": True}
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
