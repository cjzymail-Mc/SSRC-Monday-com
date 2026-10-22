"""Mirror accepted product assets into the isolated review frontend."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'local-test-data' / 'feature02-interaction-preview'
ASSETS = TARGET / 'frontend'


def build():
    ASSETS.mkdir(parents=True, exist_ok=True)
    tree = ast.parse((ROOT / 'server.py').read_text(encoding='utf-8'))
    paths = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'PUBLIC_PATHS' for t in node.targets))
    hashes = {}
    for name in sorted({path.lstrip('/') for path in paths if path != '/'}):
        data = (ROOT / name).read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        (ASSETS / name).write_bytes(data)
    index = (ASSETS / 'index.html').read_text(encoding='utf-8')
    index = index.replace('<title>Flowboard · 团队工作空间</title>', '<title>Flowboard · 交互预览</title>')
    (ASSETS / 'index.html').write_text(index, encoding='utf-8')
    (TARGET / 'source-manifest.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'ISOLATED_FRONTEND={ASSETS}')
    print(f'COPIED_PUBLIC_ASSETS={len(hashes)}')


if __name__ == '__main__':
    build()
