import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from flowboard.database import connect, migrate
from server import create_server

TABLES = ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes")
STAGES = {
    "创意": "stage-idea", "设计": "stage-design", "开发": "stage-develop",
    "测试": "stage-test", "量产": "stage-production", "应用迭代": "stage-iteration",
}


def require(value, key, detail=None):
    if not value:
        raise AssertionError(f"{key}: {detail!r}")


def fingerprint(path):
    return path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(path):
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    try:
        rows = {table: [dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY id")] for table in TABLES}
        return {
            table: {"count": len(value), "hash": hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()}
            for table, value in rows.items()
        }
    finally:
        db.close()


def physical(page, locator, button="left"):
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box(); require(box, "FIXTURE_NO_HIT_BOX", str(locator))
    center = {"x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2}
    viewport = page.viewport_size
    require(viewport and 0 <= center["x"] < viewport["width"] and 0 <= center["y"] < viewport["height"],
            "FIXTURE_HIT_CENTER_OUTSIDE_VIEWPORT", {"box": box, "center": center, "viewport": viewport})
    page.mouse.move(center["x"], center["y"])
    page.mouse.down(button=button); page.mouse.up(button=button)


def seed(db_path):
    today = datetime.now(timezone(timedelta(hours=8))).date()
    db = connect(db_path); now = "2026-08-20T00:00:00+00:00"; projects = []
    try:
        fixtures = (
            ("Planner 重叠项目", (
                ("main", "创意", "较早逾期", today - timedelta(days=2)),
                ("main", "创意", "逾期", today - timedelta(days=1)),
                ("main", "设计", "主重叠一", today), ("main", "开发", "主重叠二", today),
                ("parallel", "测试", "并重叠一", today), ("parallel", "量产", "并重叠二", today),
            )),
            ("Planner 较早项目", (("main", "创意", "较早开始", today - timedelta(days=20)), ("main", "设计", "下周", today + timedelta(days=8)))),
            ("Planner 临近项目", (("main", "创意", "今天启动", today), ("parallel", "应用迭代", "稍后", today + timedelta(days=2)))),
        )
        for name, nodes in fixtures:
            pid = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES(1,?,'u1',1,?,?)", (name, now, now)).lastrowid
            ids = []
            for track, stage, node_name, date in nodes:
                ids.append(db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES(?,?,?,?,?,?,'',1,?,?)", (pid, track, stage, node_name, date.isoformat(), date.isoformat(), now, now)).lastrowid)
            projects.append((pid, ids))
        db.commit(); return projects, today.isoformat()
    finally:
        db.close()


def main():
    locked = [ROOT / "flowboard.db", ROOT / ".copilot-state.json", ROOT / ".copilot-task.md", ROOT / ".copilot-message.md"]
    guard_before = {str(p): fingerprint(p) for p in locked}
    old_password = os.environ.get("FLOWBOARD_INITIAL_PASSWORD")
    result = {"status": "RUNNING", "fixture_keys": ["CP4_OVERLAP_BOTH_TRACKS", "CP4_ALL_SIX_STAGES", "CP4_THREE_SORTABLE_PROJECTS"]}
    with tempfile.TemporaryDirectory(prefix="planner-b004-cp4-") as temp:
        db_path = str(Path(temp) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(db_path, initial_password="test-password")
        projects, today = seed(db_path); primary = projects[0][0]
        db_before = snapshot(db_path)
        server = create_server("127.0.0.1", 0, db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page(); console = []; pageerrors = []; requests = []
                page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: pageerrors.append(str(e)))
                page.on("request", lambda r: requests.append((r.method, r.url)))
                page.goto(base); page.locator("#loginUser").fill("u1"); page.locator("#loginPassword").fill("test-password")
                physical(page, page.locator('#loginForm button[type="submit"]')); page.locator("#loadState", has_text="刚刚同步").wait_for()
                require(len(console) == 1 and "401" in console[0], "FIXTURE_PRELOGIN_CONSOLE", console); console.clear()

                # Positive read control from the production entry.
                physical(page, page.locator("#timelineBtn")); page.locator('[data-timeline-page="home"]').wait_for()
                reads = [r for r in requests if r[0] == "GET" and r[1].endswith("/api/workspaces/1/timeline")]
                require(reads, "FIXTURE_NETWORK_PROBE_BLIND", requests)
                writes_at_interaction_start = len([r for r in requests if r[0] in ("POST", "PUT", "PATCH", "DELETE") and "/timeline/" in r[1]])

                # Single dashboard direction A and first-screen hierarchy.
                button = page.locator(f'[data-timeline-open="single"][data-project-id="{primary}"]')
                page.evaluate("""id=>{window.__cp4single=[];const b=document.querySelector(`[data-timeline-open="single"][data-project-id="${id}"]`);for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>window.__cp4single.push(t),{once:true})}""", primary)
                physical(page, button); card = page.locator(f'[data-dashboard-project="{primary}"]'); card.wait_for()
                require(page.evaluate("window.__cp4single") == ["mousedown", "mouseup", "click"], "SINGLE_ENTRY_EVENT_SEQUENCE")
                card_style = card.evaluate("e=>({bg:getComputedStyle(e).backgroundColor,h:getComputedStyle(e.querySelector('h2')).fontSize,k:getComputedStyle(e.querySelector('.timeline-summary')).fontSize})")
                dashboard_box = card.locator('.timeline-dashboard').bounding_box(); summary_box = card.locator('.timeline-summary').bounding_box()
                require(card_style["bg"] == "rgb(255, 255, 255)" and float(card_style["h"][:-2]) > float(card_style["k"][:-2]), "DIRECTION_A_HIERARCHY", card_style)
                require(dashboard_box and dashboard_box["y"] < 900 and dashboard_box["height"] > summary_box["height"], "TIMELINE_NOT_FIRST_SCREEN_VISUAL", {"dashboard":dashboard_box,"summary":summary_box})

                # Shared absolute calendar/today, two tracks and overlap folding/expansion.
                require(card.locator('[data-calendar-start]').count() == 1 and card.locator('.timeline-today-line').get_attribute('data-today') == today, "SINGLE_CALENDAR_TODAY")
                require("今天" in card.locator('.timeline-today-line').inner_text(), "TODAY_COLOR_ONLY")
                require(card.locator('[data-track="main"]').count() == 1 and card.locator('[data-track="parallel"]').count() == 1, "DUAL_TRACK_MISSING")
                for track in ("main", "parallel"):
                    lane = card.locator(f'[data-track="{track}"]')
                    require(lane.get_attribute("data-overlap-rows") == "2", "OVERLAP_ROW_INDEX_MISSING", track)
                    require(lane.locator('[data-row-index="1"][data-overlap-split="true"]').count() > 0, "OVERLAP_NOT_SPLIT", track)
                expand = card.locator('[data-timeline-expand]').first
                page.evaluate("""()=>{window.__cp4expand=[];const b=document.querySelector('[data-timeline-expand]');for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>window.__cp4expand.push(t),{once:true})}""")
                physical(page, expand); card = page.locator(f'[data-dashboard-project="{primary}"]')
                require(page.evaluate("window.__cp4expand") == ["mousedown","mouseup","click"], "EXPAND_EVENT_SEQUENCE")
                require(card.locator('[data-track="main"]').get_attribute("class").find("is-expanded") >= 0, "OVERLAP_NOT_EXPANDED")
                require(card.locator('[data-track="main"] [data-row-index="1"]').first.get_attribute("data-overlap-split") == "false", "EXPANDED_ROW_NOT_SEPARATE")

                # Stage semantic redundancy and continuous interval geometry.
                seen = {}
                for element in card.locator('[data-stage-interval]').all():
                    stage = element.get_attribute("data-stage"); seen[stage] = element.get_attribute("class")
                    require(STAGES[stage] in seen[stage], "STAGE_TOKEN_MISMATCH", {stage:seen[stage]})
                    require(element.locator("b").inner_text() == stage and f"阶段 {stage}" in element.get_attribute("aria-label"), "STAGE_REDUNDANCY_MISSING", stage)
                    require(element.get_attribute("data-node-ids") and float(element.evaluate("e=>getComputedStyle(e).borderRadius")[:-2]) == 2, "INTERVAL_GEOMETRY_OR_NODE_IDS", stage)
                    require(element.bounding_box()["width"] > 0, "INTERVAL_NOT_CONTINUOUS", stage)

                # Single context menu physical sequence and exactly four actions.
                single_node = card.locator('.timeline-dashboard-node').first
                page.evaluate("""()=>{window.__cp4ctx1=[];const n=document.querySelector('[data-dashboard-project] .timeline-dashboard-node');for(const t of ['mousedown','mouseup','contextmenu'])n.addEventListener(t,()=>window.__cp4ctx1.push(t),{once:true})}""")
                physical(page, single_node, "right")
                menu1 = card.locator('[data-timeline-context] [role="menuitem"]').all_inner_texts()
                require(page.evaluate("window.__cp4ctx1") == ["mousedown","mouseup","contextmenu"], "SINGLE_CONTEXT_SEQUENCE")
                require(menu1 == ["拖拽—仅此节点","拖拽（顺延）","已完成","未完成"], "SINGLE_CONTEXT_NOT_FOUR", menu1)
                physical(page, card.locator('[data-draft-action="done"]'))

                # All dashboard: shared range, all six stages, risk order/text, native filter/sort interaction.
                physical(page, page.locator('[data-timeline-mode-target="all"]')); page.locator('[data-timeline-page="all"] [data-dashboard-project]').first.wait_for()
                cards = page.locator('[data-dashboard-project]')
                ranges = cards.evaluate_all("els=>els.map(e=>[e.querySelector('[data-calendar-start]').dataset.calendarStart,e.querySelector('[data-calendar-end]').dataset.calendarEnd])")
                require(len({tuple(x) for x in ranges}) == 1, "ALL_CALENDAR_NOT_SHARED", ranges)
                require(set(cards.locator('.timeline-today-line').evaluate_all("els=>els.map(e=>e.dataset.today)")) == {today}, "ALL_TODAY_NOT_SHARED")
                all_stages = set(cards.locator('[data-stage-interval]').evaluate_all("els=>els.map(e=>e.dataset.stage)"))
                require(all_stages == set(STAGES), "SIX_STAGE_COVERAGE", all_stages)
                markers = page.locator(f'[data-dashboard-project="{primary}"] .timeline-risk-markers')
                require(markers.locator('.timeline-risk').all_inner_texts()[0].startswith("逾期") and markers.locator('.timeline-risk').all_inner_texts()[1].startswith("本周"), "RISK_ORDER_OR_TEXT", markers.inner_text())

                sort = page.locator('[data-timeline-sort-key]'); require(sort.locator('option').count() == 4, "FOUR_SORTS_MISSING")
                physical(page, sort); page.keyboard.press("End"); page.keyboard.press("Enter")
                require(page.locator('[data-timeline-sort-key]').input_value() == "overdue", "SORT_NATIVE_CHANGE_FAILED")
                order = page.locator('[data-dashboard-project]').evaluate_all("els=>els.map(e=>Number(e.dataset.dashboardProject))")
                require(order[0] == primary, "OVERDUE_SORT_WRONG", order)
                filt = page.locator('[data-timeline-filter]'); physical(page, filt); page.keyboard.press("Home"); page.keyboard.press("Space")
                page.wait_for_timeout(100)
                require(page.locator('[data-dashboard-project]').count() == 1, "MULTI_FILTER_NATIVE_CHANGE_FAILED", page.locator('[data-dashboard-project]').count())

                # Return to all projects and verify same context controller behavior in all mode.
                filt = page.locator('[data-timeline-filter]'); physical(page, filt); page.keyboard.press("Control+A"); page.keyboard.press("Space"); page.wait_for_timeout(100)
                if page.locator('[data-dashboard-project]').count() != 3:
                    # Fixture-only recovery: native multi-select behavior varies by platform;
                    # this path is recorded as a fixture key, never as product PASS.
                    raise AssertionError(f"FIXTURE_MULTISELECT_RESTORE: {page.locator('[data-dashboard-project]').count()}")
                all_node = page.locator(f'[data-dashboard-project="{primary}"] .timeline-dashboard-node').first
                page.evaluate("""()=>{window.__cp4ctx2=[];for(const t of ['mousedown','mouseup','contextmenu'])document.addEventListener(t,e=>window.__cp4ctx2.push({type:e.type,node:e.target.closest('.timeline-dashboard-node')?.dataset.nodeId||null}),{capture:true,once:true})}""")
                physical(page, all_node, "right"); menu2 = page.locator('.timeline-all > [data-timeline-context] [role="menuitem"]').all_inner_texts()
                all_events = page.evaluate("window.__cp4ctx2")
                require([row["type"] for row in all_events] == ["mousedown","mouseup","contextmenu"] and all(row["node"] for row in all_events), "ALL_CONTEXT_SEQUENCE", all_events)
                require(not page.locator('.timeline-all > [data-timeline-context]').is_hidden(), "ALL_CONTEXT_MENU_NOT_VISIBLE")
                require(menu2 == menu1, "DASHBOARDS_CONTEXT_CONTROLLER_DIVERGED", {"single":menu1,"all":menu2})
                physical(page, page.locator('.timeline-all > [data-timeline-context] [data-draft-action="done"]'))
                require(all_node.get_attribute("data-dashboard-action") == "done" and "is-context-target" in all_node.get_attribute("class"), "ALL_CONTEXT_ACTION_NOT_APPLIED")

                write_count = len([r for r in requests if r[0] in ("POST", "PUT", "PATCH", "DELETE") and "/timeline/" in r[1]])
                require(write_count == writes_at_interaction_start, "READONLY_DASHBOARD_NETWORK_WRITE", requests)
                require(snapshot(db_path) == db_before, "READONLY_DASHBOARD_DB_WRITE", {"before":db_before,"after":snapshot(db_path)})
                require(not console and not pageerrors, "BROWSER_ERRORS", {"console":console,"pageerror":pageerrors})

                # Independent swallowed-click canary; isolated set_content is permitted only for the canary.
                canary = context.new_page(); canary.set_content("""<style>button{position:fixed;top:20px;width:90px;height:45px}#bad{left:20px}#good{left:130px}</style><button id=bad>bad</button><button id=good>good</button><script>window.ev=[];window.hit={bad:0,good:0};for(const id of ['bad','good']){const b=document.getElementById(id);for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>ev.push(id+':'+t));b.addEventListener('click',()=>hit[id]++)}bad.addEventListener('mousedown',()=>bad.hidden=true)</script>""")
                physical(canary, canary.locator('#bad')); bad = canary.evaluate("window.ev"); require(bad == ["bad:mousedown"] and canary.evaluate("window.hit.bad") == 0, "FIXTURE_CLICK_CANARY_BLIND", bad)
                canary.evaluate("window.ev=[]"); physical(canary, canary.locator('#good')); good = canary.evaluate("window.ev"); require(good == ["good:mousedown","good:mouseup","good:click"] and canary.evaluate("window.hit.good") == 1, "FIXTURE_GOOD_CLICK_BLIND", good)
                canary.close(); context.close(); browser.close()
                result.update({"status":"PASS", "direction_a":card_style, "shared_range":ranges[0], "today":today,
                    "tracks":["main","parallel"], "overlap":"split_then_expanded", "stages":sorted(all_stages),
                    "context_actions":menu1, "sorts":4, "filter":"one_of_three", "risk_order":["overdue","this-week"],
                    "network":{"read_positive":len(reads),"timeline_writes":0}, "temporary_db_unchanged":True,
                    "events":{"single_entry":["mousedown","mouseup","click"],"single_context":["mousedown","mouseup","contextmenu"],"all_context":["mousedown","mouseup","contextmenu"],"bad_canary":bad,"good_canary":good}})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
    if old_password is None: os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)
    else: os.environ["FLOWBOARD_INITIAL_PASSWORD"] = old_password
    require({str(p): fingerprint(p) for p in locked} == guard_before, "LOCKED_FILE_CHANGED")
    result["locked_files_unchanged"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
