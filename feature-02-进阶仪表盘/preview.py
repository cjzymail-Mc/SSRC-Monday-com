"""Feature02 human preview. Fixed local path; never uses FLOWBOARD_DB from shell."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from flowboard.database import connect
from flowboard_dev_seed import seed_database
from overview_fixtures import seed_overview
from server import create_server


def main():
    directory = (ROOT / 'local-test-data' / 'feature02-preview').resolve()
    if not directory.is_relative_to((ROOT / 'local-test-data').resolve()):
        raise RuntimeError('Preview directory escaped local-test-data')
    database = directory / 'flowboard.db'
    os.environ['FLOWBOARD_ATTACHMENT_DIR'] = str(directory / 'attachments')
    os.environ['FLOWBOARD_BACKUP_DIR'] = str(directory / 'backups')
    os.environ['FLOWBOARD_DB'] = str(database)
    os.environ.pop('FLOWBOARD_SECURE_COOKIE', None)
    seed_database(database)
    marker = directory / '.feature02-seeded'
    if not marker.exists():
        seed_overview(database, datetime.now(timezone(timedelta(hours=8))).date())
        conn = connect(database)
        fixture_names = ('疾风跑鞋 · 二代研发','轻羽竞速 · 本周成果','越野探索 · 远期项目','新季概念 · 待录入')
        conn.executemany("UPDATE timeline_projects SET created_by='dev' WHERE name=? AND created_by='u1'", [(name,) for name in fixture_names])
        conn.commit();conn.close()
        marker.write_text(datetime.now(timezone.utc).isoformat(), encoding='utf-8')
    print(f'PREVIEW_DATABASE={database}', flush=True)
    print('URL=http://127.0.0.1:8083 | admin=test/test | member=u2/localtest', flush=True)
    print('Open My Work > Project Overview. Ctrl+C stops this isolated service.', flush=True)
    if '--check' in sys.argv:
        print('FEATURE02_PREVIEW_READY', flush=True)
        return
    service = create_server('127.0.0.1', 8083, str(database))
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server_close()


if __name__ == '__main__':
    main()
