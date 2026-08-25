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


def require(value, key, detail=None):
    if not value:
        raise AssertionError(f"{key}: {detail!r}")


def db_snapshot(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        payload = {}
        for table in ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes"):
            cols = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
            payload[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode()).hexdigest(), {k: len(v) for k, v in payload.items()}
    finally:
        db.close()


def physical(page, locator, button="left"):
    box = locator.bounding_box()
    require(box, "HIT_TARGET_HAS_NO_BOX", locator)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down(button=button)
    page.mouse.up(button=button)


def choose(page, node_id, action, events=None):
    node = page.locator(f'.timeline-node[data-node-id="{node_id}"]')
    physical(page, node, "right")
    menu = page.locator('[data-timeline-context]')
    require(not menu.is_hidden(), "CONTEXT_MENU_NOT_VISIBLE", node_id)
    if events is not None:
        page.evaluate("""action => {window.__cp2Menu=[];const b=document.querySelector(`[data-draft-action="${action}"]`);for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>window.__cp2Menu.push(t),{once:true})}""", action)
    physical(page, menu.locator(f'[data-draft-action="{action}"]'))


def drag_days(page, node_id, raw_days):
    node = page.locator(f'.timeline-node[data-node-id="{node_id}"]')
    canvas = page.locator('.timeline-canvas')
    box, cbox = node.bounding_box(), canvas.bounding_box()
    span = page.evaluate("""() => {const c=document.querySelector('.timeline-canvas');return Math.max(1,Math.round((new Date(c.dataset.end+'T00:00:00Z')-new Date(c.dataset.start+'T00:00:00Z'))/86400000))}""")
    delta_x = raw_days * cbox["width"] / span
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + delta_x, box["y"] + box["height"] / 2, steps=8)
    zoom_visible = not page.locator('.timeline-zoom-band').is_hidden()
    page.mouse.up()
    return zoom_visible


def main():
    real = ROOT / "flowboard.db"
    locked = [ROOT / ".copilot-state.json", ROOT / ".copilot-task.md", ROOT / ".copilot-message.md"]
    guard_before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in [real, *locked]}
    old_password = os.environ.get("FLOWBOARD_INITIAL_PASSWORD")
    result = {"status": "RUNNING"}
    with tempfile.TemporaryDirectory(prefix="planner-b004-cp2-") as temp:
        db_path = str(Path(temp) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(db_path, initial_password="test-password")
        db = connect(db_path)
        now = "2026-08-20T00:00:00+00:00"
        project_id = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES(1,'Planner CP2','u1',1,?,?)", (now, now)).lastrowid
        ids = []
        # Deliberately make stage order differ from date order so the browser
        # assertion detects a non-working sort rather than comparing an
        # accidentally pre-sorted fixture.
        for track, stage, name, date in (("main","开发","A1","2026-08-01"),("main","创意","A2","2026-08-05"),("main","设计","A3","2026-08-09"),("parallel","测试","P1","2026-08-03")):
            ids.append(db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES(?,?,?,?,?,?,'',1,?,?)", (project_id,track,stage,name,date,date,now,now)).lastrowid)
        db.commit(); db.close()
        before = db_snapshot(db_path)
        server = create_server("127.0.0.1", 0, db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()
                console, pageerrors, requests = [], [], []
                page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: pageerrors.append(str(e)))
                page.on("request", lambda r: requests.append((r.method, r.url)))
                page.goto(base)
                page.locator("#loginUser").fill("u1"); page.locator("#loginPassword").fill("test-password")
                page.locator('#loginForm button[type="submit"]').click(); page.locator("#loadState", has_text="刚刚同步").wait_for()
                require(len(console) == 1 and "401" in console[0], "PRELOGIN_CONSOLE", console); console.clear()
                physical(page, page.locator("#timelineBtn")); page.locator('[data-timeline-page="home"]').wait_for()
                physical(page, page.locator(f'[data-timeline-open="editor"][data-project-id="{project_id}"]'))
                page.locator('.timeline-node').first.wait_for()
                baseline = len(requests)

                # Production context menu and true hit-testing sequences.
                page.evaluate("""id=>{window.__cp2Ctx=[];const n=document.querySelector(`[data-node-id="${id}"]`);for(const t of ['mousedown','mouseup','contextmenu'])n.addEventListener(t,()=>window.__cp2Ctx.push(t),{once:true})}""", ids[0])
                choose(page, ids[0], "cascade", True)
                require(page.evaluate("window.__cp2Ctx") == ["mousedown","mouseup","contextmenu"], "CONTEXT_EVENT_SEQUENCE", page.evaluate("window.__cp2Ctx"))
                require(page.evaluate("window.__cp2Menu") == ["mousedown","mouseup","click"], "MENU_EVENT_SEQUENCE", page.evaluate("window.__cp2Menu"))
                require(page.locator('[role="menuitem"]').all_inner_texts() == ["拖拽—仅此节点","拖拽（顺延）","已完成","未完成"], "CONTEXT_FOUR_ACTIONS")

                # Enlarged band: raw 8px-days becomes one day; cascade moves only later same-track nodes.
                require(drag_days(page, ids[0], 8), "ZOOM_BAND_NOT_VISIBLE")
                dates = {i: page.locator(f'[data-node-id="{i}"]').get_attribute("data-node-date") for i in ids}
                require(dates == {ids[0]:"2026-08-02", ids[1]:"2026-08-06", ids[2]:"2026-08-10", ids[3]:"2026-08-03"}, "CASCADE_OR_ZOOM_WRONG", dates)
                require(len(requests) == baseline, "DRAG_NETWORK_LEAK", requests[baseline:])

                # Armed mode is consumed; then single clamps against both neighbours.
                stale = dates[ids[1]]; drag_days(page, ids[1], 20)
                require(page.locator(f'[data-node-id="{ids[1]}"]').get_attribute("data-node-date") == stale, "ARMED_NOT_CONSUMED")
                choose(page, ids[1], "single"); drag_days(page, ids[1], -50)
                require(page.locator(f'[data-node-id="{ids[1]}"]').get_attribute("data-node-date") == "2026-08-02", "SINGLE_PREDECESSOR_CLAMP")
                choose(page, ids[1], "single"); drag_days(page, ids[1], 50)
                require(page.locator(f'[data-node-id="{ids[1]}"]').get_attribute("data-node-date") == "2026-08-10", "SINGLE_SUCCESSOR_CLAMP")

                # Mixed status/date draft, display-only sorting, navigation and beforeunload guards.
                choose(page, ids[1], "done")
                require("项草稿" in page.locator('[data-timeline-draft-count]').inner_text(), "MIXED_DRAFT_COUNT")
                date_order = page.locator('.timeline-track[data-track="main"] .timeline-node').evaluate_all("els=>els.map(e=>e.dataset.nodeId)")
                physical(page, page.locator('[data-timeline-sort="stage"]'))
                stage_order = page.locator('.timeline-track[data-track="main"] .timeline-node').evaluate_all("els=>els.map(e=>e.dataset.nodeId)")
                require(date_order == [str(ids[0]), str(ids[1]), str(ids[2])], "DATE_SORT_WRONG", date_order)
                require(stage_order == [str(ids[1]), str(ids[2]), str(ids[0])], "STAGE_SORT_WRONG", stage_order)
                beforeunload = page.evaluate("""() => {const e=new Event('beforeunload',{cancelable:true});const dispatched=window.dispatchEvent(e);return {dispatched,defaultPrevented:e.defaultPrevented,returnValue:e.returnValue}}""")
                require(beforeunload["defaultPrevented"] and not beforeunload["dispatched"], "BEFOREUNLOAD_NOT_GUARDED", beforeunload)
                page.once("dialog", lambda d: d.dismiss())
                physical(page, page.locator('[data-timeline-mode-target="home"]'))
                require(page.locator('[data-timeline-page="editor"]').count() == 1, "DISMISSED_LEAVE_LOST_DRAFT")

                # Network instrumentation positive control without mutating timeline state.
                positive = len(requests); page.evaluate("() => fetch('/api/session').then(r=>r.json())")
                page.wait_for_timeout(100)
                require(len(requests) == positive + 1 and requests[-1][1].endswith('/api/session'), "NETWORK_PROBE_BLIND", requests[positive:])
                before_discard_dom = page.locator('.timeline-editor').inner_text()
                physical(page, page.locator('[data-timeline-discard]'))
                require(page.locator('[data-timeline-draft-count]').inner_text() == "0 项草稿", "DISCARD_DRAFT_REMAINS")
                require([page.locator(f'[data-node-id="{i}"]').get_attribute('data-node-date') for i in ids] == ["2026-08-01","2026-08-05","2026-08-09","2026-08-03"], "DISCARD_DOM_NOT_RESTORED")
                require(before_discard_dom != page.locator('.timeline-editor').inner_text(), "DISCARD_DOM_CANARY_BLIND")

                # Canary runs on an isolated, unobscured page.  Prove both that
                # physical hit-testing works and that the exact bad pattern is
                # rejected (hidden on mousedown => no mouseup/click/action).
                canary = context.new_page()
                canary.set_content("""<style>button{position:fixed;top:20px;width:100px;height:50px;z-index:2147483647}#bad{left:20px}#good{left:140px}</style><button id=bad>bad</button><button id=good>good</button><script>window.ev=[];window.actions={bad:0,good:0};for(const id of ['bad','good']){const b=document.getElementById(id);for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>ev.push(id+':'+t));b.addEventListener('click',()=>actions[id]++)}bad.addEventListener('mousedown',()=>bad.hidden=true)</script>""")
                bad, good = canary.locator('#bad'), canary.locator('#good')
                require(bad.is_visible() and good.is_visible() and bad.bounding_box() and good.bounding_box(), "CANARY_NOT_HITTABLE")
                physical(canary, bad)
                bad_events = canary.evaluate("window.ev")
                require(bad_events == ["bad:mousedown"] and canary.evaluate("window.actions.bad") == 0, "SWALLOWED_CLICK_CANARY_BLIND", {"events":bad_events,"actions":canary.evaluate("window.actions")})
                canary.evaluate("window.ev=[]")
                physical(canary, good)
                good_events = canary.evaluate("window.ev")
                require(good_events == ["good:mousedown","good:mouseup","good:click"] and canary.evaluate("window.actions.good") == 1, "GOOD_CLICK_CANARY_BLIND", {"events":good_events,"actions":canary.evaluate("window.actions")})
                canary.close()
                require(not pageerrors and not console, "BROWSER_ERRORS", {"page":pageerrors,"console":console})
                context.close(); browser.close()
                after = db_snapshot(db_path)
                require(before == after, "LOCAL_DRAFT_DB_CHANGED", {"before":before,"after":after})
                result.update({"status":"PASS", "project_id":project_id, "node_ids":ids, "cascade_dates":dates,
                               "event_sequences":{"context":["mousedown","mouseup","contextmenu"],"menu":["mousedown","mouseup","click"],"bad_canary":bad_events,"good_canary":good_events},
                               "sort":{"date":date_order,"stage":stage_order}, "beforeunload":beforeunload,
                               "network":{"drag_phase_delta":0,"positive_control":"GET /api/session"},
                               "temporary_db":{"before":before,"after":after,"unchanged":True}})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
            if old_password is None: os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)
            else: os.environ["FLOWBOARD_INITIAL_PASSWORD"] = old_password
    guard_after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in [real, *locked]}
    require(guard_before == guard_after, "LOCKED_ARTIFACT_CHANGED", {"before":guard_before,"after":guard_after})
    result["locked_artifacts_unchanged"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
