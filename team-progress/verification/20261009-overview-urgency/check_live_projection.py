"""Verify the new projection on live data via read-only SQLite connections."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from flowboard.timeline import TimelineService
from flowboard.overview import project_overview
URI=(ROOT/'flowboard.db').as_uri()+'?mode=ro'
def reader():
    conn=sqlite3.connect(URI,uri=True);conn.row_factory=sqlite3.Row
    return conn
def data_hash(conn):
    return {table:hashlib.sha256(json.dumps([tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY id')],ensure_ascii=False,default=str).encode()).hexdigest() for table in ['timeline_projects','timeline_nodes']}
conn=reader()
account=conn.execute("SELECT m.user_id,m.workspace_id FROM workspace_memberships m JOIN users u ON u.id=m.user_id WHERE m.role='admin' AND u.is_active=1 ORDER BY m.workspace_id,m.user_id LIMIT 1").fetchone()
assert account is not None,'No active administrator for read-only projection verification'
before=data_hash(conn)
service=TimelineService(str(ROOT/'flowboard.db'));service._db=reader
payload=project_overview(service,{'id':account['user_id']},account['workspace_id'],{'period':['all'],'completion':['all']})
projects=payload['projects'];ids=[p['project_id'] for p in projects]
assert len(ids)==len(set(ids))
attention={p['project_id'] for p in projects if p['group']=='attention'}
recent={p['project_id'] for p in projects if p['group']=='recent'}
assert not attention.intersection(recent) and attention|recent==set(ids)
keys=[];rows=[]
for p in projects:
    next_node=p['next_nodes'][0] if p['next_nodes'] else None
    rank=0 if p['total_overdue_count'] else 1 if p['total_today_count'] else 2 if next_node else 3 if p['total_node_count'] else 4
    date=next_node['date'] if next_node else '9999'
    keys.append((rank,date,-p['total_overdue_count'],-p['total_today_count'],p['project_id']))
    if next_node:
        stored=conn.execute('SELECT remark FROM timeline_nodes WHERE id=?',(next_node['id'],)).fetchone()[0]
        assert stored==next_node['remark']
    rows.append({'project_id':p['project_id'],'group':p['group'],'urgency_rank':rank,'next_date':date,
                 'next_node_id':next_node['id'] if next_node else None,'note_present':bool(next_node and next_node['remark'])})
assert keys==sorted(keys)
after=data_hash(conn);assert before==after
conn.close()
record={'database':str(ROOT/'flowboard.db'),'access':'mode=ro','server_today':payload['server_today'],
        'counts':payload['counts'],'groups':{'attention':len(attention),'recent':len(recent)},
        'unique_projects':len(set(ids)),'sort_check':'PASS','note_correspondence':'PASS',
        'business_tables_unchanged':before==after,'table_hashes':after,'ordered_rows':rows}
(OUT/'live-projection.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k not in ('table_hashes','ordered_rows')},ensure_ascii=False))
