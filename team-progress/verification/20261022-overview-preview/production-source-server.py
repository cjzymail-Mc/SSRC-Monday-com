"""Serve product static files against a disposable SQLite copy for review."""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = Path(tempfile.mkdtemp(prefix='production-source-', dir=ROOT / 'local-test-data' / 'feature02-interaction-preview'))
DB = DATA / 'flowboard.db'
SOURCE = ROOT / 'local-test-data' / 'feature02-preview' / 'flowboard.db'
with sqlite3.connect(SOURCE.as_uri() + '?mode=ro', uri=True) as source:
    with sqlite3.connect(DB) as destination:
        source.backup(destination)
os.environ['FLOWBOARD_ATTACHMENT_DIR'] = str(DATA / 'attachments')
os.environ['FLOWBOARD_BACKUP_DIR'] = str(DATA / 'backups')
os.environ.pop('FLOWBOARD_SECURE_COOKIE', None)
sys.path.insert(0, str(ROOT))
import server

service = server.create_server('127.0.0.1', 0, str(DB))
metadata = {'url': f'http://localhost:{service.server_address[1]}/', 'database': str(DB), 'static_root': str(server.ROOT)}
(DATA / 'verification-server.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(metadata, ensure_ascii=False), flush=True)
try:
    service.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    service.server_close()
