"""Read-only CP4 hit-target diagnostics. This is not an acceptance probe."""

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from flowboard.database import migrate
from server import create_server

PROBE_PATH = ROOT / "team-progress" / "verification" / "B-004-CP4" / "probe_cp4_browser.py"
spec = importlib.util.spec_from_file_location("cp4_probe_fixture", PROBE_PATH)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def require(value, key, detail=None):
    if not value:
        raise AssertionError(f"{key}: {detail!r}")


def fp(path):
    return path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def physical(page, locator, button="left"):
    box = locator.bounding_box()
    require(box, "RC_NO_BOUNDING_BOX", str(locator))
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y); page.mouse.down(button=button); page.mouse.up(button=button)
    return {"x": x, "y": y, "box": box}


JS_DIAGNOSE = r"""
({projectId, key}) => {
  const target = document.querySelector(`[data-dashboard-project="${projectId}"] .timeline-dashboard-node`);
  if (!target) throw new Error('RC_TARGET_MISSING');
  const rect = target.getBoundingClientRect(), x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
  const compact = el => {
    if (!el) return null;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return {tag:el.tagName,id:el.id||null,class:el.className||null,node_id:el.dataset?.nodeId||null,
      stage:el.dataset?.stage||null,pointer_events:s.pointerEvents,z_index:s.zIndex,position:s.position,
      isolation:s.isolation,overflow:s.overflow,transform:s.transform,opacity:s.opacity,visibility:s.visibility,
      rect:{x:r.x,y:r.y,width:r.width,height:r.height}};
  };
  const ancestors=[]; for(let el=target;el;el=el.parentElement) ancestors.push(compact(el));
  const intervals=[...target.closest('[data-dashboard-project]').querySelectorAll('[data-stage-interval]')].map(compact);
  const layers=document.elementsFromPoint(x,y).slice(0,12).map(compact);
  const top=document.elementFromPoint(x,y);
  window[key]=[];
  for(const type of ['mousedown','mouseup','contextmenu']) document.addEventListener(type,e=>window[key].push({
    type,target:compact(e.target),closest_node:e.target.closest('.timeline-dashboard-node')?.dataset.nodeId||null,
    path:e.composedPath().slice(0,10).filter(v=>v instanceof Element).map(compact)
  }),{capture:true,once:true});
  return {node_id:target.dataset.nodeId,outer_html:target.outerHTML.slice(0,800),center:{x,y},target:compact(target),
    ancestors,intervals,layers,element_from_point:compact(top),top_contains_target:top?.contains(target)||false,
    target_contains_top:target.contains(top),top_closest_node:top?.closest('.timeline-dashboard-node')?.dataset.nodeId||null};
}
"""


JS_GRID = r"""
projectId => {
  const target=document.querySelector(`[data-dashboard-project="${projectId}"] .timeline-dashboard-node`),r=target.getBoundingClientRect(),out=[];
  for(let iy=0;iy<5;iy++)for(let ix=0;ix<5;ix++){
    const x=r.left+(ix+.5)*r.width/5,y=r.top+(iy+.5)*r.height/5,top=document.elementFromPoint(x,y);
    out.push({ix,iy,x,y,tag:top?.tagName||null,class:top?.className||null,node_id:top?.closest('.timeline-dashboard-node')?.dataset.nodeId||null});
  }
  return out;
}
"""


def diagnose_state(page, project_id, label, requests):
    key = f"__rc_{label}"
    before = page.evaluate(JS_DIAGNOSE, {"projectId": project_id, "key": key})
    target = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node').first
    click = physical(page, target, "right")
    events = page.evaluate(f"window.{key}")
    menu = page.locator('.timeline-all > [data-timeline-context]')
    menu_visible = not menu.is_hidden()
    menu_items = menu.locator('[role="menuitem"]').all_inner_texts()
    action = None
    if menu_visible:
        physical(page, menu.locator('[data-draft-action="done"]'))
        action = {"data": target.get_attribute("data-dashboard-action"), "class": target.get_attribute("class")}
    return {"label": label, "before_right_click": before, "physical": click, "events": events,
            "after_right_click": {"menu_visible": menu_visible, "menu_items": menu_items, "action": action},
            "grid": page.evaluate(JS_GRID, project_id), "request_count": len(requests)}


def dashboard_state(page):
    return page.evaluate("""() => ({
      cards:[...document.querySelectorAll('[data-dashboard-project]')].map(card=>({
        project_id:Number(card.dataset.dashboardProject),node_count:card.querySelectorAll('.timeline-dashboard-node').length
      })),
      filter:{options:[...document.querySelector('[data-timeline-filter]').options].map(o=>({value:Number(o.value),selected:o.selected,text:o.textContent})),
              selected:[...document.querySelector('[data-timeline-filter]').selectedOptions].map(o=>Number(o.value))},
      sort:document.querySelector('[data-timeline-sort-key]').value
    })""")


def main():
    locked = [ROOT / "flowboard.db", ROOT / ".copilot-state.json", ROOT / ".copilot-task.md", ROOT / ".copilot-message.md"]
    guard_before = {str(p): fp(p) for p in locked}
    old_password = os.environ.get("FLOWBOARD_INITIAL_PASSWORD")
    output = {"diagnostic_failure_key": "CP4_RC_HIT_STACK_CAPTURE", "acceptance_failure_count_increment": 0}
    with tempfile.TemporaryDirectory(prefix="planner-b004-cp4-root-cause-") as temp:
        db_path = str(Path(temp) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(db_path, initial_password="test-password")
        projects, today = fixture.seed(db_path); primary = projects[0][0]
        db_before = fixture.snapshot(db_path)
        server = create_server("127.0.0.1", 0, db_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True); context = browser.new_context(viewport={"width":1440,"height":900})
                page = context.new_page(); requests=[]; console=[]; pageerrors=[]
                page.on("request", lambda r: requests.append((r.method,r.url)))
                page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: pageerrors.append(str(e)))
                page.goto(f"http://127.0.0.1:{server.server_address[1]}")
                page.locator("#loginUser").fill("u1"); page.locator("#loginPassword").fill("test-password")
                physical(page,page.locator('#loginForm button[type="submit"]')); page.locator("#loadState",has_text="刚刚同步").wait_for()
                require(len(console)==1 and "401" in console[0],"RC_PRELOGIN_CONSOLE",console); console.clear()
                physical(page,page.locator("#timelineBtn")); page.locator('[data-timeline-page="home"]').wait_for()
                physical(page,page.locator('[data-timeline-mode-target="all"]')); page.locator('[data-dashboard-project]').first.wait_for()

                expected_ids=[project[0] for project in projects]
                output["initial"]={"today":today,"primary":primary,"expected_ids":expected_ids,"dashboard":dashboard_state(page)}
                page.evaluate("id=>window.__rc_initial_ref=document.querySelector(`[data-dashboard-project=\"${id}\"] .timeline-dashboard-node`)",primary)

                # Deterministically select the primary option by value. This is
                # fixture preparation, not acceptance evidence; it avoids native
                # multi-select focus varying by platform.
                filt=page.locator('[data-timeline-filter]'); filt.select_option([str(primary)]); page.wait_for_timeout(100)
                one_state=dashboard_state(page); output["after_explicit_primary_filter"]={"selection_method":"select_option(primary value)","primary":primary,"dashboard":one_state}
                visible_with_nodes=[row["project_id"] for row in one_state["cards"] if row["node_count"]>0]
                require(visible_with_nodes==[primary],"RC_FILTER_PRIMARY_MISMATCH",{"primary":primary,"state":one_state})
                output["dom_refs_after_filter_one"]=page.evaluate("()=>({initial_connected:window.__rc_initial_ref.isConnected})")
                page.evaluate("id=>window.__rc_one_ref=document.querySelector(`[data-dashboard-project=\"${id}\"] .timeline-dashboard-node`)",primary)
                output["one_project_control"]=diagnose_state(page,primary,"one",requests)

                # No selected options means the product renders all projects.
                filt=page.locator('[data-timeline-filter]'); filt.select_option([]); page.wait_for_timeout(100)
                restored_state=dashboard_state(page); output["before_restored_diagnosis"]={"selection_method":"select_option(empty)","primary":primary,"dashboard":restored_state}
                restored_ids=[row["project_id"] for row in restored_state["cards"]]
                primary_rows=[row for row in restored_state["cards"] if row["project_id"]==primary]
                require(set(restored_ids)==set(expected_ids) and len(restored_ids)==3,"RC_RESTORE_IDS_MISMATCH",{"expected":expected_ids,"actual":restored_state})
                require(primary_rows and primary_rows[0]["node_count"]>0,"RC_RESTORED_PRIMARY_HAS_NO_NODE",restored_state)
                output["dom_refs_after_restore"]=page.evaluate("id=>({initial_connected:window.__rc_initial_ref.isConnected,one_connected:window.__rc_one_ref.isConnected,current_same_as_one:document.querySelector(`[data-dashboard-project=\"${id}\"] .timeline-dashboard-node`)===window.__rc_one_ref})",primary)
                output["restored"]={"primary":primary,"dashboard":restored_state,"render_html":page.locator('[data-timeline-page="all"]').get_attribute("data-timeline-page")}
                output["three_project_reproduction"]=diagnose_state(page,primary,"three",requests)

                writes=[r for r in requests if r[0] in ("POST","PUT","PATCH","DELETE") and "/timeline/" in r[1]]
                reads=[r for r in requests if r[0]=="GET" and "/timeline" in r[1]]
                output["network"]={"timeline_reads":reads,"timeline_writes":writes}
                output["temporary_db"]={"before":db_before,"after":fixture.snapshot(db_path),"unchanged":db_before==fixture.snapshot(db_path)}
                output["browser_errors"]={"console":console,"pageerror":pageerrors}
                require(not writes,"RC_TIMELINE_WRITE_DETECTED",writes); require(output["temporary_db"]["unchanged"],"RC_TEMP_DB_CHANGED")
                context.close(); browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
    if old_password is None: os.environ.pop("FLOWBOARD_INITIAL_PASSWORD",None)
    else: os.environ["FLOWBOARD_INITIAL_PASSWORD"]=old_password
    output["locked_files_unchanged"]={str(p):fp(p) for p in locked}==guard_before
    require(output["locked_files_unchanged"],"RC_LOCKED_FILE_CHANGED")
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
