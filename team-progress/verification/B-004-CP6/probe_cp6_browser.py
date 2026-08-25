"""B-004 CP6 independent closeout: three journeys, one fresh database."""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]; sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from flowboard.database import connect,migrate
from server import create_server


def load_planner(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


# Planner-owned fixture utilities only; no coder test class/helper is imported.
P4=load_planner('planner_cp4_fixture',ROOT/'team-progress/verification/B-004-CP4/probe_cp4_browser.py')
P5=load_planner('planner_cp5_fixture',ROOT/'team-progress/verification/B-004-CP5/probe_cp5_browser.py')


def require(v,key,detail=None):
    if not v: raise AssertionError(f'{key}: {detail!r}')


def seed_project(db_path,name='CP6 编辑项目',created_by='u1'):
    db=connect(db_path); now='2026-08-20T00:00:00+00:00'
    try:
        pid=db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES(1,?,?,1,?,?)",(name,created_by,now,now)).lastrowid; ids=[]
        for track,stage,n,date in [('main','创意','A1','2026-08-01'),('main','设计','A2','2026-08-05'),('main','开发','A3','2026-08-09'),('parallel','测试','P1','2026-08-03')]:
            ids.append(db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES(?,?,?,?,?,?,'',1,?,?)",(pid,track,stage,n,date,date,now,now)).lastrowid)
        db.commit(); return pid,ids
    finally: db.close()


def open_editor(page,pid):
    P5.physical(page,page.locator('#timelineBtn')); page.locator('[data-timeline-page="home"]').wait_for(); P5.physical(page,page.locator(f'[data-timeline-open="editor"][data-project-id="{pid}"]')); page.locator('.timeline-node').first.wait_for()


def mixed_draft(page,ids,label):
    first=page.locator(f'.timeline-node[data-node-id="{ids[0]}"]'); P5.physical(page,first,'right'); P5.physical(page,page.locator('[data-draft-action="cascade"]'))
    first=page.locator(f'.timeline-node[data-node-id="{ids[0]}"]'); box=first.bounding_box(); page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2); page.mouse.down(); page.mouse.move(box['x']+box['width']/2+170,box['y']+box['height']/2,steps=8); page.mouse.up()
    P5.physical(page,page.locator(f'.timeline-node[data-node-id="{ids[1]}"]'),'right'); P5.physical(page,page.locator('[data-draft-action="done"]')); P5.physical(page,page.locator('[data-timeline-remove-last]'))
    answers=iter([label,'2026-08-15','测试','parallel']); handler=lambda d:d.accept(next(answers)); page.on('dialog',handler); P5.physical(page,page.locator('[data-timeline-add]')); page.remove_listener('dialog',handler); page.locator('.timeline-node',has_text='测试 · 2026-08-15').wait_for()


def clear_expected_console(page,console,errors,status,c0,e0,key):
    page.wait_for_timeout(30); seg=console[c0:]; require(len(seg)==1 and str(status) in seg[0] and 'Failed to load resource' in seg[0],key,seg); require(not errors[e0:],key+'_PAGEERROR',errors[e0:]); del console[c0:]


def main():
    locked=[ROOT/'flowboard.db',ROOT/'.copilot-state.json',ROOT/'.copilot-task.md',ROOT/'.copilot-message.md',ROOT/'app.js',ROOT/'timeline-ui.js',ROOT/'timeline.css']
    guards={str(p):P5.fingerprint(p) for p in locked}; old=os.environ.get('FLOWBOARD_INITIAL_PASSWORD'); result={'status':'RUNNING','database_instances':1}
    with tempfile.TemporaryDirectory(prefix='planner-b004-cp6-') as temp:
        db_path=str(Path(temp)/'flowboard.db'); os.environ['FLOWBOARD_INITIAL_PASSWORD']='test-password'; migrate(db_path,initial_password='test-password')
        db=connect(db_path); now='2026-08-20T00:00:00+00:00'
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,? FROM users WHERE id='u1'",(now,)); db.execute("INSERT INTO workspace_memberships VALUES(1,'u2','member')")
        db.execute("INSERT INTO workspaces VALUES(2,'CP6 往返空间',?,30)",(now,)); db.execute("INSERT INTO users SELECT 'u4','u4','往返管理员',password_hash,NULL,NULL,1,? FROM users WHERE id='u1'",(now,)); db.execute("INSERT INTO workspace_memberships VALUES(2,'u4','admin')"); db.commit(); db.close()
        pid,ids=seed_project(db_path); member_pid,_=seed_project(db_path,'CP6 成员项目','u2')
        server=create_server('127.0.0.1',0,db_path); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start(); base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)

                # J1: discard -> submit -> refresh -> undo -> reload, then 409/member denial zero-write.
                context,page,console,errors=P5.login(browser,base,'u1'); requests=[]; page.on('request',lambda r:requests.append((r.method,r.url,r.post_data_json if r.method=='POST' and r.post_data else None)))
                open_editor(page,pid); j1_start=P5.snapshot(db_path); network_start=len(requests); mixed_draft(page,ids,'CP6 放弃节点')
                require(len(requests)==network_start,'J1_DRAFT_NETWORK_LEAK',requests[network_start:]); P5.physical(page,page.locator('[data-timeline-discard]')); require(P5.snapshot(db_path)==j1_start,'J1_DISCARD_DB_CHANGED')
                mixed_draft(page,ids,'CP6 提交节点'); batch_before=len([r for r in requests if r[1].endswith('/timeline/batches')])
                with page.expect_response(lambda r:r.url.endswith('/timeline/batches') and r.request.method=='POST') as submitted: P5.physical(page,page.locator('[data-timeline-submit]'))
                require(submitted.value.status==200,'J1_R06_STATUS'); batches=[r for r in requests if r[1].endswith('/timeline/batches')]; require(len(batches)==batch_before+1,'J1_R06_NOT_EXACTLY_ONE')
                req=batches[-1][2]['requests'][0]; require(all([any('date' in c.get('set',{}) for c in req['changes']),any('done_at' in c.get('set',{}) for c in req['changes']),any('create' in c for c in req['changes']),any(c.get('remove') for c in req['changes'])]),'J1_R06_NOT_MIXED',req)
                page.locator('.timeline-node',has_text='测试 · 2026-08-15').wait_for(); require(page.locator('[data-timeline-draft-count]').inner_text()=='0 项草稿' and not page.locator('[data-timeline-undo]').is_disabled(),'J1_R06_SERVER_VIEW_OR_UNDO_LIFETIME')
                db=connect(db_path); require(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND name='CP6 提交节点' AND deleted_at IS NULL",(pid,)).fetchone()[0]==1,'J1_R06_NOT_PERSISTED'); db.close()
                with page.expect_response(lambda r:r.url.endswith('/timeline/batches/undo')) as undone: P5.physical(page,page.locator('[data-timeline-undo]'))
                require(undone.value.status==200,'J1_R07_STATUS'); undo_requests=len([r for r in requests if r[1].endswith('/timeline/batches/undo')]); page.reload(); open_editor(page,pid); db=connect(db_path); require(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL",(pid,)).fetchone()[0]==4 and db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND name='CP6 提交节点' AND deleted_at IS NULL",(pid,)).fetchone()[0]==0,'J1_UNDO_NOT_RESTORED'); db.close(); require(page.locator('[data-timeline-undo]').is_disabled() and len([r for r in requests if r[1].endswith('/timeline/batches/undo')])==undo_requests,'J1_UNDO_LIFETIME')
                P5.physical(page,page.locator(f'.timeline-node[data-node-id="{ids[1]}"]'),'right'); P5.physical(page,page.locator('[data-draft-action="done"]')); db=connect(db_path); db.execute('UPDATE timeline_projects SET version=version+1 WHERE id=?',(pid,)); db.commit(); db.close(); stable409=P5.snapshot(db_path); c0,e0=len(console),len(errors)
                with page.expect_response(lambda r:r.url.endswith('/timeline/batches')) as conflict: P5.physical(page,page.locator('[data-timeline-submit]'))
                require(conflict.value.status==409 and P5.snapshot(db_path)==stable409,'J1_409_WROTE_OR_STATUS'); clear_expected_console(page,console,errors,409,c0,e0,'J1_409_CONSOLE'); context.close()
                mctx,mpage,mconsole,merrors=P5.login(browser,base,'u2'); open_editor(mpage,member_pid); mpage.once('dialog',lambda d:d.accept('2026-07-20')); stable403=P5.snapshot(db_path); c0,e0=len(mconsole),len(merrors)
                with mpage.expect_response(lambda r:r.url.endswith('/timeline/batches/initial-correction')) as denied: P5.physical(mpage,mpage.locator('[data-timeline-correct]'))
                require(denied.value.status==403 and denied.value.json()['error']['code']=='ADMIN_REQUIRED' and P5.snapshot(db_path)==stable403,'J1_PERMISSION_ZERO_WRITE'); clear_expected_console(mpage,mconsole,merrors,403,c0,e0,'J1_403_CONSOLE'); mctx.close(); j1_end=P5.snapshot(db_path)

                # J2: seed dashboard fixtures into the same DB and prove read-only UI.
                dashboard_projects,today=P4.seed(db_path)
                require(isinstance(dashboard_projects,list) and dashboard_projects,'CP6_PLANNER_DASHBOARD_SEED_RETURN_SHAPE',dashboard_projects)
                require(all(isinstance(item,tuple) and len(item)==2 and isinstance(item[0],int) and isinstance(item[1],list) and item[1] and all(isinstance(node_id,int) for node_id in item[1]) for item in dashboard_projects),'CP6_PLANNER_DASHBOARD_SEED_RETURN_SHAPE',dashboard_projects)
                dashboard_ids=[project_id for project_id,_ in dashboard_projects]
                context,page,console,errors=P5.login(browser,base,'u1'); traffic=[]; page.on('request',lambda r:traffic.append((r.method,r.url)))
                single_open=page.locator(f'[data-timeline-open="single"][data-project-id="{dashboard_ids[0]}"]')
                require(single_open.count()==1,'J2_DASHBOARD_PROJECT_DOM_MISSING',dashboard_ids)
                P5.physical(page,single_open); card=page.locator(f'[data-dashboard-project="{dashboard_ids[0]}"]'); card.wait_for(); j2_start=P5.snapshot(db_path)
                require(card.locator('[data-track="main"]').count()==1 and card.locator('[data-track="parallel"]').count()==1 and '今天' in card.locator('.timeline-today-line').inner_text(),'J2_SINGLE_STRUCTURE')
                require(card.locator('[data-stage-interval]').count()>0 and card.locator('[data-row-index="1"]').count()>0,'J2_STAGE_OVERLAP'); P5.physical(page,card.locator('[data-timeline-expand]').first)
                node=card.locator('.timeline-dashboard-node').first; P5.physical(page,node,'right'); menu=card.locator('[data-timeline-context]'); require(menu.locator('[role=menuitem]').all_inner_texts()==['拖拽—仅此节点','拖拽（顺延）','已完成','未完成'],'J2_SINGLE_MENU'); P5.physical(page,menu.locator('[data-draft-action="done"]'))
                P5.physical(page,page.locator('[data-timeline-mode-target="all"]')); page.locator('[data-timeline-page="all"] [data-dashboard-project]').first.wait_for(); cards=page.locator('[data-dashboard-project]'); ranges=cards.evaluate_all("els=>els.map(e=>[e.querySelector('[data-calendar-start]').dataset.calendarStart,e.querySelector('[data-calendar-end]').dataset.calendarEnd])"); require(len({tuple(x) for x in ranges})==1,'J2_SHARED_RANGE')
                markers=page.locator(f'[data-dashboard-project="{dashboard_ids[0]}"] .timeline-risk-markers').inner_text(); require('逾期' in markers and '本周' in markers,'J2_RISK_MARKERS')
                sort=page.locator('[data-timeline-sort-key]'); P5.physical(page,sort); page.keyboard.press('End'); page.keyboard.press('Enter'); require(sort.input_value()=='overdue','J2_FOUR_SORT')
                filt=page.locator('[data-timeline-filter]'); P5.physical(page,filt); page.keyboard.press('Home'); page.keyboard.press('Space'); page.wait_for_timeout(100); require(page.locator('[data-dashboard-project]').count()==1,'J2_FILTER')
                page.locator('[data-timeline-filter]').select_option([]); page.wait_for_timeout(100); allnode=page.locator(f'[data-dashboard-project="{dashboard_ids[0]}"] .timeline-dashboard-node').first; P5.physical(page,allnode,'right'); allmenu=page.locator('.timeline-all > [data-timeline-context]'); require(not allmenu.is_hidden(),'J2_ALL_CONTEXT'); P5.physical(page,allmenu.locator('[data-draft-action="done"]'))
                writes=[r for r in traffic if r[0] in ('POST','PUT','PATCH','DELETE') and '/timeline/' in r[1]]; reads=[r for r in traffic if r[0]=='GET' and '/timeline' in r[1]]; require(reads and not writes and P5.snapshot(db_path)==j2_start,'J2_READONLY_GUARD',{'reads':reads,'writes':writes}); context.close(); j2_end=P5.snapshot(db_path)

                # J3: real file -> commit -> export/download -> workspace2 reimport/R01; 422 zero-write.
                context,page,console,errors=P5.login(browser,base,'u1'); transfer=[]; exports=[]; page.on('request',lambda r:transfer.append((r.method,r.url,r.post_data_json if r.method=='POST' and r.post_data else None))); page.on('response',lambda r:exports.append(r) if r.url.endswith('/timeline/export') else None)
                raw=P5.xlsx([["CP6 往返项目","创意","main","完成","2026-08-01","","已完成",""],["CP6 往返项目","设计","parallel","进行","2026-08-03","","进行中",""]]); _,preview=P5.upload(page,console,errors,'cp6.xlsx',raw,201)
                with page.expect_response(lambda r:r.url.endswith('/timeline/imports/commit')) as commit: P5.physical(page,page.locator('[data-timeline-import-commit]'))
                require(commit.value.status==201 and [r for r in transfer if r[1].endswith('/timeline/imports/commit')][-1][2]=={'batch_id':preview['batch_id']},'J3_R10')
                page.locator('.timeline-import-success').wait_for(); with_snapshot=P5.snapshot(db_path); c0,e0=len(console),len(errors); bad=P5.xlsx([["坏日期","创意","main","N","invalid","","",""]]); P5.upload(page,console,errors,'bad.xlsx',bad,422,'VALIDATION_ERROR'); require(not page.locator('[data-timeline-import-commit]').is_enabled() and P5.snapshot(db_path)==with_snapshot,'J3_422_ZERO_WRITE')
                with page.expect_response(lambda r:r.url.endswith('/timeline/export')) as ex: P5.physical(page,page.locator('[data-timeline-export]'))
                payload=ex.value.json(); server_bytes=__import__('base64').b64decode(payload['content_base64']); digest=hashlib.sha256(server_bytes).hexdigest(); web=page.evaluate("""async b=>{const u=Uint8Array.from(atob(b),c=>c.charCodeAt(0)),d=await crypto.subtle.digest('SHA-256',u);return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,'0')).join('')}""",payload['content_base64']); require(ex.value.request.method=='POST' and digest==payload['sha256']==web,'J3_R11_HASH')
                link=page.locator('[data-timeline-download]'); link.wait_for();
                with page.expect_download() as dl: P5.physical(page,link)
                downloaded=Path(dl.value.path()).read_bytes(); require(downloaded==server_bytes,'J3_DOWNLOAD_BYTES'); context.close()
                ctx2,p2,c2,e2=P5.login(browser,base,'u4'); r2=[]; g2=[]; p2.on('request',lambda r:r2.append((r.method,r.url,r.post_data_json if r.method=='POST' and r.post_data else None))); p2.on('response',lambda r:g2.append(r) if r.url.endswith('/api/workspaces/2/timeline') and r.request.method=='GET' else None)
                _,pre2=P5.upload(p2,c2,e2,'reimport.xlsx',downloaded,201)
                with p2.expect_response(lambda r:r.url.endswith('/timeline/imports/commit')) as co2: P5.physical(p2,p2.locator('[data-timeline-import-commit]'))
                require(co2.value.status==201 and r2[-1][2]=={'batch_id':pre2['batch_id']},'J3_WS2_R10'); p2.locator('.timeline-import-success').wait_for(); p2.wait_for_timeout(100); view=g2[-1].json(); require(any(p['name']=='CP6 往返项目' and len(p['nodes'])==2 for p in view['projects']),'J3_WS2_R01',view); ctx2.close(); j3_end=P5.snapshot(db_path)

                # Independent physical click canary.
                canary=browser.new_page(viewport={'width':400,'height':200}); canary.set_content('<style>button{position:fixed;top:20px;width:100px;height:50px}#bad{left:20px}#good{left:140px}</style><button id=bad>bad</button><button id=good>good</button><script>window.e=[];window.a={bad:0,good:0};for(const id of ["bad","good"]){const b=document.getElementById(id);for(const t of ["mousedown","mouseup","click"])b.addEventListener(t,()=>e.push(id+":"+t));b.addEventListener("click",()=>a[id]++)}bad.addEventListener("mousedown",()=>bad.hidden=true)</script>'); P5.physical(canary,canary.locator('#bad')); bad_events=canary.evaluate('e'); require(bad_events==['bad:mousedown'] and canary.evaluate('a.bad')==0,'CP6_CANARY_BAD',bad_events); canary.evaluate('e=[]'); P5.physical(canary,canary.locator('#good')); good_events=canary.evaluate('e'); require(good_events==['good:mousedown','good:mouseup','good:click'] and canary.evaluate('a.good')==1,'CP6_CANARY_GOOD',good_events); canary.close(); browser.close()
                result.update({'status':'PASS','journeys':{'J1':{'start':j1_start,'end':j1_end,'discard_zero_write':True,'r06_once':True,'refresh':True,'undo_reload':True,'409_zero_write':True,'permission_zero_write':True},'J2':{'start':j2_start,'end':j2_end,'shared':True,'writes':0,'db_unchanged':True},'J3':{'end':j3_end,'r09_r10_r01':True,'r11_hash_download':True,'workspace2_roundtrip':True,'422_zero_write':True}},'canary':{'bad':bad_events,'good':good_events}})
        finally: server.shutdown(); server.server_close(); thread.join(timeout=2)
    if old is None: os.environ.pop('FLOWBOARD_INITIAL_PASSWORD',None)
    else: os.environ['FLOWBOARD_INITIAL_PASSWORD']=old
    require({str(p):P5.fingerprint(p) for p in locked}==guards,'CP6_LOCKED_OR_PRODUCT_CHANGED'); result['locked_and_product_hashes_unchanged']=True; print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
