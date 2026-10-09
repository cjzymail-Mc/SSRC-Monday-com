import hashlib
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent
DB=ROOT/'flowboard.db'
SOURCES=['server.py','flowboard/service.py','flowboard/overview.py','flowboard/timeline.py','flowboard/database.py','timeline-ui.js','app.js','index.html','overview-ui.js','overview.css','timeline.css','start-flowboard.cmd']

def sha(data):return hashlib.sha256(data).hexdigest()
def ro(path=DB):
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn
def profile(conn):
    conn.execute('BEGIN')
    try:
        schema=[tuple(row) for row in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        tables={}
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            table=row['name'];quoted='"'+table.replace('"','""')+'"'
            rows=sorted(json.dumps(tuple(item),ensure_ascii=False,default=repr) for item in conn.execute('SELECT * FROM '+quoted))
            tables[table]={'count':len(rows),'sha256':sha('\n'.join(rows).encode())}
        return {'version':conn.execute('PRAGMA user_version').fetchone()[0],'schema_sha256':sha(json.dumps(schema,ensure_ascii=False).encode()),'integrity':conn.execute('PRAGMA integrity_check').fetchone()[0],'foreign_keys':len(conn.execute('PRAGMA foreign_key_check').fetchall()),'tables':tables}
    finally:conn.rollback()
def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def source_hashes():return {name:sha((ROOT/name).read_bytes()) for name in SOURCES}

if sys.argv[1]=='before':
    from flowboard.database import SCHEMA_VERSION
    with ro() as source:
        current=profile(source)
        assert current['version']==SCHEMA_VERSION==20 and current['integrity']=='ok' and current['foreign_keys']==0
        stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S-%f')
        backup=ROOT/'backups'/f'flowboard-before-lan-test-{stamp}.db'
        with sqlite3.connect(backup) as destination:source.backup(destination)
    with ro(backup) as snapshot:backup_profile=profile(snapshot)
    assert backup_profile['integrity']=='ok' and backup_profile['foreign_keys']==0 and backup_profile['version']==20
    save('before.json',{'time':stamp,'database':str(DB),'profile':current,'backup':{'path':str(backup),'sha256':sha(backup.read_bytes()),'profile':backup_profile},'sources':source_hashes()})
    print(json.dumps({'preflight':'PASS','backup':str(backup),'schema':20,'backup_integrity':'ok'},ensure_ascii=False))
elif sys.argv[1]=='after':
    before=json.loads((OUT/'before.json').read_text(encoding='utf-8'))
    assert before['sources']==source_hashes(),'Release source changed during restart'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    http={}
    for host in ['127.0.0.1','192.168.3.39']:
        entry={}
        for endpoint in ['/api/health','/','/timeline-ui.js?v=20261009-period-mask','/app.js?v=20261009-f02-team-cards','/overview-ui.js?v=20261009-f02-team-cards','/api/bootstrap','/api/workspaces/1/timeline/overview?scope=all&period=all']:
            try:
                with opener.open(f'http://{host}:8080{endpoint}',timeout=10) as response:body=response.read();status=response.status
            except urllib.error.HTTPError as error:body=error.read();status=error.code
            if endpoint in ['/api/bootstrap','/api/workspaces/1/timeline/overview?scope=all&period=all']:
                assert status==401;entry[endpoint]={'status':status,'code':json.loads(body)['error']['code']}
            elif endpoint=='/api/health':
                assert status==200 and json.loads(body)=={'status':'ok','schema_version':20};entry[endpoint]={'status':status,'body':json.loads(body)}
            else:
                filename='index.html' if endpoint=='/' else endpoint.split('?')[0][1:]
                assert status==200 and body==(ROOT/filename).read_bytes()
                entry[endpoint]={'status':status,'source_sha256':sha(body)}
        http[host]=entry
    from flowboard.service import FlowboardService
    from flowboard.timeline import TimelineService
    from flowboard.overview import project_overview
    class ReadonlyService(FlowboardService):
        def _db(self):return ro()
    class ReadonlyTimeline(TimelineService):
        def _db(self):return ro()
    with ro() as conn:
        admin=dict(conn.execute("SELECT u.*,wm.workspace_id FROM users u JOIN workspace_memberships wm ON wm.user_id=u.id WHERE wm.role='admin' AND u.is_active=1 ORDER BY wm.workspace_id,u.id LIMIT 1").fetchone())
    bootstrap=ReadonlyService(str(DB)).bootstrap(admin)
    assert all(member['role'] in ['admin','member','viewer'] and 'password_hash' not in member for member in bootstrap['members'])
    overview=project_overview(ReadonlyTimeline(str(DB)),admin,admin['workspace_id'],{'scope':['all'],'period':['all'],'completion':['all']})
    ids=[item['project_id'] for item in overview['projects']]
    assert len(ids)==len(set(ids))
    for item in overview['projects']:
        incomplete=sorted((node for node in item['matched_nodes'] if not node['done_at']),key=lambda node:node['date'])
        assert not incomplete or item['next_nodes'][0]['date']==incomplete[0]['date']
    with ro() as conn:after=profile(conn)
    assert after['schema_sha256']==before['profile']['schema_sha256']
    assert after['tables']['schema_migrations']==before['profile']['tables']['schema_migrations']
    changed=[name for name,value in after['tables'].items() if value!=before['profile']['tables'].get(name)]
    save('after.json',{'time':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'http':http,'profile':after,'changed_tables_since_backup':changed,'readonly_latest_projection':{'member_roles':dict(Counter(member['role'] for member in bootstrap['members'])),'project_count':len(ids),'node_count':overview['counts']['nodes'],'unique_projects':True,'earliest_incomplete_verified':True},'sources':source_hashes()})
    print(json.dumps({'http_local_and_lan':'PASS','latest_sources':'PASS','auth_negative':'PASS','live_projection_readonly':'PASS','schema_unchanged':True,'changed_tables':changed,'projects':len(ids),'nodes':overview['counts']['nodes']},ensure_ascii=False))
else:raise ValueError('before or after required')
