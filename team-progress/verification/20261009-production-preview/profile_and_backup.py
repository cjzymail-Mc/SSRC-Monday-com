"""Read-only live snapshot/profile for the explicitly requested preview switch."""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
LIVE=ROOT/'flowboard.db'

def profile(conn):
    conn.execute('BEGIN')
    try:
        tables=['users','workspace_memberships','timeline_projects','timeline_nodes',
                'timeline_tags','timeline_project_tags','timeline_personal_orders','timeline_member_orders']
        existing={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        hashes={}
        for table in tables:
            if table not in existing:continue
            rows=conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            payload=json.dumps(rows,ensure_ascii=False,default=str,separators=(',',':')).encode('utf-8')
            hashes[table]={'rows':len(rows),'sha256':hashlib.sha256(payload).hexdigest()}
        return {'database':str(LIVE),'schema':conn.execute('PRAGMA user_version').fetchone()[0],
                'active_projects':conn.execute('SELECT COUNT(*) FROM timeline_projects WHERE deleted_at IS NULL AND archived_at IS NULL').fetchone()[0],
                'active_nodes':conn.execute('SELECT COUNT(*) FROM timeline_nodes n JOIN timeline_projects p ON p.id=n.project_id WHERE n.deleted_at IS NULL AND p.deleted_at IS NULL AND p.archived_at IS NULL').fetchone()[0],
                'active_test_account_exists':bool(conn.execute("SELECT 1 FROM users WHERE username='test' AND is_active=1").fetchone()),
                'table_hashes':hashes,'captured_at':datetime.now(timezone.utc).isoformat()}
    finally:conn.rollback()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    mode=sys.argv[1]
    with sqlite3.connect(LIVE.as_uri()+'?mode=ro',uri=True) as src:
        if mode=='before':
            backup_dir=ROOT/'local-test-data'/'production-preview-backups'
            backup_dir.mkdir(parents=True,exist_ok=True)
            target=backup_dir/('flowboard-before-8083-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db')
            with sqlite3.connect(target) as dst:
                src.backup(dst)
                assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                assert not dst.execute('PRAGMA foreign_key_check').fetchall()
                record=profile(dst)
            record['backup']={'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'integrity':'ok','foreign_key_violations':0}
        else:
            record=profile(src)
            before=json.loads((OUT/'before.json').read_text(encoding='utf-8'))
            record['changed_tables_since_backup']=[name for name,value in record['table_hashes'].items() if before['table_hashes'].get(name)!=value]
        (OUT/(mode+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in record.items() if k!='table_hashes'},ensure_ascii=False))

if __name__=='__main__':main()
