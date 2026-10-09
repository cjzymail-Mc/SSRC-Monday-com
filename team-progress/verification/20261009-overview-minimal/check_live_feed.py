"""Read only real completion/track encodings; omit people and project names."""
import json
import sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
conn=sqlite3.connect((ROOT/'flowboard.db').as_uri()+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
rows=conn.execute("SELECT c.id,c.field,c.old_value,c.new_value,b.change_kind,b.trigger_source,b.created_at FROM timeline_node_changes c JOIN timeline_change_batches b ON b.id=c.batch_id WHERE c.field IN ('done_at','track') ORDER BY c.id DESC LIMIT 30").fetchall()
conn.close()
(OUT/'live-feed-encodings.json').write_text(json.dumps({'access':'mode=ro','name_fields_omitted':True,'changes':[dict(row) for row in rows]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Read-only production history encodings: {len(rows)} rows; no login or writes.')
