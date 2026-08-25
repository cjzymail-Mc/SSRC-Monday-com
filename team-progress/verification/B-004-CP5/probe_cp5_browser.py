import base64
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import zipfile
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from flowboard.database import connect, migrate
from server import create_server

HEADERS = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
TABLES = ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes")


def require(value, key, detail=None):
    if not value:
        raise AssertionError(f"{key}: {detail!r}")


def fingerprint(path):
    return path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(path):
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    try:
        payload = {t: [dict(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY id")] for t in TABLES}
        return {t: {"count":len(v),"hash":hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()} for t,v in payload.items()}
    finally: db.close()


def col_name(index):
    out=""
    while index:
        index, rem = divmod(index-1,26); out=chr(65+rem)+out
    return out


def sheet_xml(rows):
    body=[]
    for rix,row in enumerate(rows,1):
        cells=[]
        for cix,value in enumerate(row,1):
            text=escape(str(value),quote=False)
            cells.append(f'<c r="{col_name(cix)}{rix}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        body.append(f'<row r="{rix}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(body)+'</sheetData></worksheet>'


def xlsx(rows, second_sheet=False, extras=None, headers=HEADERS):
    sheets='<sheet name="Timeline" sheetId="1" r:id="rId1"/>'
    rels='<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    overrides='<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    if second_sheet:
        sheets+='<sheet name="Ignored" sheetId="2" r:id="rId2"/>'; rels+='<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'; overrides+='<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    entries={
      '[Content_Types].xml':f'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>{overrides}</Types>',
      '_rels/.rels':'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml':f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets}</sheets></workbook>',
      'xl/_rels/workbook.xml.rels':f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
      'xl/worksheets/sheet1.xml':sheet_xml([headers,*rows]),
    }
    if second_sheet: entries['xl/worksheets/sheet2.xml']=sheet_xml([HEADERS,["不得导入","创意","main","X","2026-01-01","","",""]])
    entries.update(extras or {})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in entries.items(): z.writestr(name,data)
    return out.getvalue()


def formula_xlsx():
    raw=xlsx([["公式","创意","main","N","2026-08-01","","",""]])
    src=zipfile.ZipFile(io.BytesIO(raw)); entries={i.filename:src.read(i.filename) for i in src.infolist()}; src.close()
    xml=entries['xl/worksheets/sheet1.xml'].decode()
    xml=xml.replace('<c r="A2" t="inlineStr"><is><t xml:space="preserve">公式</t></is></c>','<c r="A2"><f>1+1</f><v>2</v></c>')
    entries['xl/worksheets/sheet1.xml']=xml
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,d in entries.items(): z.writestr(n,d)
    return out.getvalue()


def physical(page, locator, button='left'):
    locator.scroll_into_view_if_needed(); box=locator.bounding_box(); require(box,'FIXTURE_NO_BOX',str(locator))
    center={'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}; viewport=page.viewport_size
    require(viewport and 0<=center['x']<viewport['width'] and 0<=center['y']<viewport['height'],'FIXTURE_OFFVIEWPORT',{'center':center,'viewport':viewport})
    page.mouse.move(center['x'],center['y']); page.mouse.down(button=button); page.mouse.up(button=button)


def login(browser,base,user):
    context=browser.new_context(viewport={'width':1440,'height':900},accept_downloads=True); page=context.new_page(); console=[]; errors=[]
    page.on('console',lambda m:console.append(m.text) if m.type=='error' else None); page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base); page.locator('#loginUser').fill(user); page.locator('#loginPassword').fill('test-password'); physical(page,page.locator('#loginForm button[type=submit]')); page.locator('#loadState',has_text='刚刚同步').wait_for()
    require(len(console)==1 and '401' in console[0],'PRELOGIN_CONSOLE',console); console.clear()
    physical(page,page.locator('#timelineBtn')); page.locator('[data-timeline-page="home"]').wait_for()
    return context,page,console,errors


def upload(page,console,errors,name,raw,status,code=None):
    c0,e0=len(console),len(errors)
    with page.expect_response(lambda r:r.url.endswith('/timeline/imports/preview') and r.request.method=='POST') as pending:
        with page.expect_file_chooser() as chooser:
            physical(page,page.locator('.timeline-file-button'))
        chooser.value.set_files({'name':name,'mimeType':'text/csv' if name.endswith('.csv') else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':raw})
    response=pending.value; require(response.status==status,'R09_STATUS',{'name':name,'status':response.status,'json':response.json()})
    payload=response.json()
    if status==201:
        page.locator('[data-timeline-preview-id]').wait_for(); require(not errors[e0:],'R09_SUCCESS_PAGEERROR',errors[e0:])
    else:
        require(payload['error']['code']==code,'R09_ERROR_CODE',{'name':name,'payload':payload}); page.locator(f'[data-timeline-import-error="{code}"]').wait_for()
        page.wait_for_function('(args)=>args.console.length>=args.start+1',{'console':console,'start':c0}) if False else page.wait_for_timeout(30)
        require(len(console[c0:])==1 and '422' in console[c0] and 'Failed to load resource' in console[c0],'R09_422_CONSOLE_SEGMENT',{'name':name,'segment':console[c0:]})
        require(not errors[e0:],'R09_422_PAGEERROR_SEGMENT',errors[e0:]); del console[c0:]
        require(not page.locator('[data-timeline-import-commit]').is_enabled(),'R10_ENABLED_AFTER_422',name)
    return response,payload


def main():
    locked=[ROOT/'flowboard.db',ROOT/'.copilot-state.json',ROOT/'.copilot-task.md',ROOT/'.copilot-message.md']; guards={str(p):fingerprint(p) for p in locked}
    old=os.environ.get('FLOWBOARD_INITIAL_PASSWORD'); result={'status':'RUNNING'}
    with tempfile.TemporaryDirectory(prefix='planner-b004-cp5-') as temp:
        db_path=str(Path(temp)/'flowboard.db'); os.environ['FLOWBOARD_INITIAL_PASSWORD']='test-password'; migrate(db_path,initial_password='test-password')
        db=connect(db_path); now='2026-08-20T00:00:00+00:00'
        db.execute("INSERT INTO workspaces VALUES (2,'Planner 往返空间',?,30)",(now,)); db.execute("INSERT INTO users SELECT 'u4','u4','往返管理员',password_hash,NULL,NULL,1,? FROM users WHERE id='u1'",(now,)); db.execute("INSERT INTO workspace_memberships VALUES (2,'u4','admin')")
        pid=db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES(1,'已有项目','u1',1,?,?)",(now,now)).lastrowid
        for track,stage,name,date in [('main','创意','N2','2026-08-01'),('main','设计','N10','2026-08-03'),('parallel','测试','P1','2026-08-02')]: db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES(?,?,?,?,?,?,'',1,?,?)",(pid,track,stage,name,date,date,now,now))
        db.commit(); db.close()
        server=create_server('127.0.0.1',0,db_path); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start(); base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True); context,page,console,errors=login(browser,base,'u1'); requests=[]; responses=[]
                page.on('request',lambda r:requests.append((r.method,r.url,r.post_data_json if r.method=='POST' and r.post_data else None)))
                page.on('response',lambda r:responses.append(r) if r.url.endswith('/timeline/export') else None)

                # R09 -> R10 success, strict body and status recomputation.
                good=xlsx([["Planner 导入","创意","main","完成节点","2026-08-01","","已完成","保留"],["Planner 导入","设计","parallel","进行节点","2026-08-03","","进行中","重算"]])
                r09,preview=upload(page,console,errors,'planner.xlsx',good,201); text=page.locator('[data-timeline-preview-id]').inner_text()
                require(preview['batch_id'] and 'Planner 导入：2 个节点' in text and '仅『已完成』保留' in text,'R09_SUMMARY_WARNINGS',text)
                page.evaluate("()=>{window.__cp5commit=[];const b=document.querySelector('[data-timeline-import-commit]');for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>window.__cp5commit.push(t),{once:true})}")
                with page.expect_response(lambda r:r.url.endswith('/timeline/imports/commit')) as committed: physical(page,page.locator('[data-timeline-import-commit]'))
                require(committed.value.status==201 and page.evaluate('window.__cp5commit')==['mousedown','mouseup','click'],'R10_COMMIT_EVENT_STATUS')
                commit_requests=[r for r in requests if r[1].endswith('/timeline/imports/commit')]; require(commit_requests[-1][2]=={'batch_id':preview['batch_id']},'R10_BODY',commit_requests[-1])
                page.locator('.timeline-import-success').wait_for(); db=connect(db_path); states=[r[0] for r in db.execute("SELECT done_at FROM timeline_nodes n JOIN timeline_projects p ON p.id=n.project_id WHERE p.name='Planner 导入' ORDER BY n.id")]; db.close(); require(states[0] and states[1] is None,'STATUS_RECALC',states)

                # Warning and row-level/actionable errors. Every 422 forbids R10 and is zero-write.
                multi=xlsx([["多表项目","创意","main","A","2026-08-01","","未开始",""]],second_sheet=True); upload(page,console,errors,'multi.xlsx',multi,201)
                warnings=page.locator('.timeline-import-warnings').inner_text(); require('仅导入第一个 sheet' in warnings and '仅『已完成』保留' in warnings,'MULTISHEET_WARNING',warnings)
                negative_baseline=snapshot(db_path); commits_before=len([r for r in requests if r[1].endswith('/timeline/imports/commit')])
                csv=(',' .join(HEADERS)+'\nCSV日期,创意,main,A,46234,,,\n').encode(); upload(page,console,errors,'dates.csv',csv,422,'VALIDATION_ERROR'); require('改用 .xlsx 导入' in page.locator('.timeline-import-error').inner_text(),'CSV_DATE_HINT')
                cases=[
                  ('conflict.xlsx',xlsx([["已有项目","创意","main","A","2026-08-01","","",""] ,["新项目","设计","main","B","2026-08-02","","",""] ,["已有项目","测试","parallel","C","2026-08-03","","",""]]),'NAME_CONFLICT'),
                  ('duplicate.xlsx',xlsx([["重复","创意","main","N","2026-08-01","","",""] ,["重复","创意","main","N","2026-08-01","","",""]]),'VALIDATION_ERROR'),
                  ('enum.xlsx',xlsx([["枚举","未知","main","N","2026-08-01","","",""]]),'VALIDATION_ERROR'),
                  ('date.xlsx',xlsx([["日期","创意","main","N","bad-date","","",""]]),'VALIDATION_ERROR'),
                ]
                row_evidence={}
                for name,raw,code in cases:
                    _,payload=upload(page,console,errors,name,raw,422,code); row_evidence[name]=payload['error'].get('details',{}); require(page.locator('[data-import-error-row]').count()>0,'ROW_DETAILS_NOT_RENDERED',name); require(snapshot(db_path)==negative_baseline,'ROW_ERROR_WROTE_DB',name)
                require(page.locator('[data-timeline-import-error="NAME_CONFLICT"] [data-import-error-row]').count()==0 or len(row_evidence['conflict.xlsx'].get('rows',[]))==2,'NAME_CONFLICT_ALL_ROWS',row_evidence['conflict.xlsx'])
                require(len([r for r in requests if r[1].endswith('/timeline/imports/commit')])==commits_before,'R10_SENT_AFTER_422')

                # R11 POST, server bytes, WebCrypto and actual browser download.
                page.evaluate("()=>{window.__cp5export=[];const b=document.querySelector('[data-timeline-export]');for(const t of ['mousedown','mouseup','click'])b.addEventListener(t,()=>window.__cp5export.push(t),{once:true})}")
                with page.expect_response(lambda r:r.url.endswith('/timeline/export')) as exported_response: physical(page,page.locator('[data-timeline-export]'))
                exported=exported_response.value.json(); require(exported_response.value.status==200 and exported_response.value.request.method=='POST','R11_METHOD_STATUS')
                raw=base64.b64decode(exported['content_base64']); pyhash=hashlib.sha256(raw).hexdigest(); webhash=page.evaluate("""async b64=>{const s=atob(b64),u=Uint8Array.from(s,c=>c.charCodeAt(0)),d=await crypto.subtle.digest('SHA-256',u);return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,'0')).join('')}""",exported['content_base64'])
                require(pyhash==exported['sha256']==webhash,'R11_HASH_MISMATCH',{'python':pyhash,'server':exported['sha256'],'web':webhash})
                link=page.locator('[data-timeline-download]'); link.wait_for()
                with page.expect_download() as dl: physical(page,link)
                downloaded=Path(dl.value.path()).read_bytes(); require(downloaded==raw,'R11_DOWNLOAD_BYTES_DIFFER')

                # Real downloaded file -> new workspace R09/R10 -> R01 refreshed semantic view.
                context.close(); context2,page2,console2,errors2=login(browser,base,'u4'); req2=[]; get2=[]
                page2.on('request',lambda r:req2.append((r.method,r.url,r.post_data_json if r.method=='POST' and r.post_data else None)))
                page2.on('response',lambda r:get2.append(r) if r.url.endswith('/api/workspaces/2/timeline') and r.request.method=='GET' else None)
                _,round_preview=upload(page2,console2,errors2,'roundtrip.xlsx',downloaded,201)
                with page2.expect_response(lambda r:r.url.endswith('/timeline/imports/commit')) as round_commit: physical(page2,page2.locator('[data-timeline-import-commit]'))
                require(round_commit.value.status==201 and req2[-1][2]=={'batch_id':round_preview['batch_id']},'ROUNDTRIP_R10')
                page2.locator('.timeline-import-success').wait_for(); page2.wait_for_timeout(100); require(get2,'ROUNDTRIP_R01_MISSING')
                view=get2[-1].json(); require(any(p['name']=='已有项目' and len(p['nodes'])==3 for p in view['projects']) and any(p['name']=='Planner 导入' and len(p['nodes'])==2 for p in view['projects']),'ROUNDTRIP_R01_SEMANTICS',view)
                context2.close()

                # Return as admin for B38 real-file safety boundaries.
                context,page,console,errors=login(browser,base,'u1'); page_requests=[]; page.on('request',lambda r:page_requests.append((r.method,r.url)))
                safety_base=snapshot(db_path)
                boundary=[[f"边界{i}","创意","main","N","2026-08-01","x"*10000 if i==0 else "","",""] for i in range(1000)]
                upload(page,console,errors,'boundary.xlsx',xlsx(boundary),201); require('1000 行' in page.locator('[data-timeline-preview-id]').inner_text(),'B38_1000_NOT_ACCEPTED')
                valid=xlsx([["安全","创意","main","N","2026-08-01","","",""]]); bomb=xlsx([["安全","创意","main","N","2026-08-01","","",""]],extras={'padding.bin':b'x'*12_000_001})
                safety=[
                  ('large.csv',b'x'*1_500_001,'IMPORT_FILE_TOO_LARGE'),('bomb.xlsx',bomb,'IMPORT_XLSX_BOMB'),
                  ('rows.xlsx',xlsx([[f"P{i}","创意","main","N","2026-08-01","","",""] for i in range(1001)]),'IMPORT_TOO_MANY_ROWS'),
                  ('cell.xlsx',xlsx([["长格","创意","main","N","2026-08-01","","","x"*10001]]),'IMPORT_CELL_TOO_LONG'),
                  ('formula.xlsx',formula_xlsx(),'IMPORT_FORMULA_FORBIDDEN'),
                  ('macro.xlsx',xlsx([["安全","创意","main","N","2026-08-01","","",""]],extras={'xl/vbaProject.bin':b'macro'}),'IMPORT_XLSX_UNSAFE'),
                  ('external.xlsx',xlsx([["安全","创意","main","N","2026-08-01","","",""]],extras={'xl/externalLinks/externalLink1.xml':b'<x/>'}),'IMPORT_XLSX_UNSAFE'),
                  ('headers.xlsx',xlsx([["","","","","2026-08-01","main","创意","错序"]],headers=HEADERS[::-1]),'IMPORT_HEADERS_MISMATCH'),
                  ('duplicate-header.xlsx',xlsx([["重复表头","创意","main","N","2026-08-01","","",""]],headers=[*HEADERS[:-1],HEADERS[-2]]),'IMPORT_DUPLICATE_HEADER'),
                ]
                for name,data,code in safety:
                    upload(page,console,errors,name,data,422,code); require(snapshot(db_path)==safety_base,'B38_NEGATIVE_WROTE_DB',name)
                require(not [r for r in page_requests if r[1].endswith('/timeline/imports/commit')],'B38_COMMIT_SENT')

                # Physical click canary only.
                canary=context.new_page(); canary.set_content('<style>button{position:fixed;top:20px;width:100px;height:50px;z-index:2147483647}#bad{left:20px}#good{left:140px}</style><button id=bad>bad</button><button id=good>good</button><script>window.e=[];window.a={bad:0,good:0};for(const id of ["bad","good"]){const b=document.getElementById(id);for(const t of ["mousedown","mouseup","click"])b.addEventListener(t,()=>e.push(id+":"+t));b.addEventListener("click",()=>a[id]++)}bad.addEventListener("mousedown",()=>bad.hidden=true)</script>')
                bad_locator,good_locator=canary.locator('#bad'),canary.locator('#good')
                require(bad_locator.is_visible() and good_locator.is_visible() and bad_locator.bounding_box() and good_locator.bounding_box(),'CANARY_FIXTURE_NOT_HITTABLE')
                physical(canary,bad_locator); bad=canary.evaluate('window.e'); bad_action=canary.evaluate('window.a.bad'); require(bad==['bad:mousedown'] and bad_action==0,'CANARY_BAD',{'events':bad,'action':bad_action})
                canary.evaluate('window.e=[]'); physical(canary,good_locator); good=canary.evaluate('window.e'); good_action=canary.evaluate('window.a.good'); require(good==['good:mousedown','good:mouseup','good:click'] and good_action==1,'CANARY_GOOD',{'events':good,'action':good_action}); canary.close()
                require(not console and not errors,'FINAL_BROWSER_ERRORS',{'console':console,'pageerror':errors}); context.close(); browser.close()
                result.update({'status':'PASS','r09':{'status':201,'summary':True,'warnings':True},'r10':{'status':201,'body':['batch_id'],'refresh':True},'rows':row_evidence,
                  'warnings':{'multi_sheet':True,'csv_date':True,'status_recalc':True},'r11':{'method':'POST','sha256':pyhash,'webcrypto':True,'download_equal':True},
                  'roundtrip':{'workspace':2,'r09':201,'r10':201,'r01':True},'safety':{'boundary_1000':True,'negative_count':len(safety),'zero_write':True},
                  'canary':{'bad':bad,'good':good},'temporary_db_final':snapshot(db_path)})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
    if old is None: os.environ.pop('FLOWBOARD_INITIAL_PASSWORD',None)
    else: os.environ['FLOWBOARD_INITIAL_PASSWORD']=old
    require({str(p):fingerprint(p) for p in locked}==guards,'LOCKED_FILES_CHANGED'); result['locked_files_unchanged']=True
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
