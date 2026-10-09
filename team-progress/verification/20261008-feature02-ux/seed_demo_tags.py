"""Add shared categories to the owned preview samples; preserve timeline contents."""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from flowboard.database import connect
from flowboard.timeline import TimelineService

DB=ROOT/'local-test-data/feature02-preview/flowboard.db'
assert DB.is_file() and DB.resolve()!=(ROOT/'flowboard.db').resolve()
stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
backup=DB.parent/'backups'/f'preview-before-ux-tags-{stamp}.db'
conn=connect(DB)
def content_hash():
    return hashlib.sha256(json.dumps([dict(r) for r in conn.execute('SELECT * FROM timeline_nodes ORDER BY id')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
before=content_hash()
with sqlite3.connect(backup) as restored:
    conn.backup(restored)
    assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
service=TimelineService(DB);user={'id':'dev'}
catalog=service.list_tags(user,1)['tags'];result=[]
for name,prefixes in [('跑步与训练',('凌云','轻风')),('球类运动',('跃影','霜羽')),('休闲与户外',('晨曦','拓野'))]:
    tag=next((t for t in catalog if t['name']==name),None) or service.create_tag(user,1,{'name':name})
    membership=service.get_tag_projects(user,1,tag['tag_id'])
    included={p['project_id'] for p in membership['included']}
    targets=[dict(p) for p in conn.execute("SELECT id,name FROM timeline_projects WHERE deleted_at IS NULL AND archived_at IS NULL") if p['name'].endswith('（演示）') and p['name'].startswith(prefixes)]
    for p in targets:
        if p['id'] not in included:
            membership=service.set_tag_project(user,1,tag['tag_id'],p['id'],{'base_tag_version':membership['tag']['version']},included=True)
    assert len(targets)==10
    result.append({'name':name,'tag_id':tag['tag_id'],'projects':len(targets)})
assert content_hash()==before
conn.close()
report={'database':str(DB),'backup':str(backup),'categories':result,'timeline_contents_unchanged':True}
(Path(__file__).parent/'demo-tags.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
