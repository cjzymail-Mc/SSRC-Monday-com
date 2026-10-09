"""Temporary 8083 connection to the live database; never seeds or migrates it."""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATABASE = ROOT / 'flowboard.db'


def preflight():
    if not DATABASE.is_file():
        raise RuntimeError('Live database is missing; no database was created')
    with sqlite3.connect(DATABASE.as_uri() + '?mode=ro', uri=True) as conn:
        from flowboard.database import SCHEMA_VERSION
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        violations = len(conn.execute('PRAGMA foreign_key_check').fetchall())
        if version != SCHEMA_VERSION or integrity != 'ok' or violations:
            raise RuntimeError('Live database preflight failed; migrations are disabled here')
        projects = conn.execute('SELECT COUNT(*) FROM timeline_projects WHERE deleted_at IS NULL AND archived_at IS NULL').fetchone()[0]
        nodes = conn.execute('SELECT COUNT(*) FROM timeline_nodes n JOIN timeline_projects p ON p.id=n.project_id WHERE n.deleted_at IS NULL AND p.deleted_at IS NULL AND p.archived_at IS NULL').fetchone()[0]
    return version, projects, nodes


def main():
    version, projects, nodes = preflight()
    os.environ['FLOWBOARD_DB'] = str(DATABASE)
    os.environ['FLOWBOARD_ATTACHMENT_DIR'] = str(ROOT / 'flowboard-attachments')
    os.environ['FLOWBOARD_BACKUP_DIR'] = str(ROOT / 'backups')
    os.environ.pop('FLOWBOARD_SECURE_COOKIE', None)
    os.environ.pop('FLOWBOARD_INITIAL_PASSWORD', None)
    print(f'PREVIEW_MODE=LIVE_PRODUCTION_DATABASE', flush=True)
    print(f'PREVIEW_DATABASE={DATABASE}', flush=True)
    print(f'PREFLIGHT=OK | schema={version} | active_projects={projects} | active_nodes={nodes}', flush=True)
    print('URL=http://127.0.0.1:8083 | Use existing production account credentials.', flush=True)
    print('NOTICE: saves through 8083 write to the live production database.', flush=True)
    if '--check' in sys.argv:
        return
    import server
    # Keep the preview login cookie independent of the normal 8080 login.
    server.SESSION_COOKIE = 'flowboard_production_preview_session'
    # Reuse the normal services/handler, bypassing create_server's migration hook.
    handler = type('ProductionPreviewHandler', (server.Handler,), {
        'service': server.FlowboardService(str(DATABASE)),
        'timeline': server.TimelineService(str(DATABASE)),
    })
    service = server.FlowboardHTTPServer(('127.0.0.1', 8083), handler)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server_close()


if __name__ == '__main__':
    main()
