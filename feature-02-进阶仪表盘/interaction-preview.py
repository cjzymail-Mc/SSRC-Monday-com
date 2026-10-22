"""Serve an isolated frontend at 8083 with the existing isolated preview DB."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'local-test-data' / 'feature02-interaction-preview' / 'frontend'
DATA = ROOT / 'local-test-data' / 'feature02-preview'
sys.path.insert(0, str(ROOT))


def main():
    if not (ASSETS / 'index.html').is_file() or not (DATA / 'flowboard.db').is_file():
        raise RuntimeError('Prepare the isolated frontend and existing preview data first.')
    os.environ['FLOWBOARD_ATTACHMENT_DIR'] = str(DATA / 'attachments')
    os.environ['FLOWBOARD_BACKUP_DIR'] = str(DATA / 'backups')
    os.environ.pop('FLOWBOARD_SECURE_COOKIE', None)
    import server
    server.ROOT = ASSETS  # Process-local static directory; product files remain untouched.
    if '--check' in sys.argv:
        print(f'ISOLATED_FRONTEND={ASSETS}')
        print(f'PREVIEW_DATABASE={DATA / "flowboard.db"}')
        return
    service = server.create_server('127.0.0.1', 8083, str(DATA / 'flowboard.db'))
    print(f'ISOLATED_FRONTEND={ASSETS}', flush=True)
    print(f'PREVIEW_DATABASE={DATA / "flowboard.db"}', flush=True)
    print('URL=http://127.0.0.1:8083/ | test/test', flush=True)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server_close()


if __name__ == '__main__':
    main()
