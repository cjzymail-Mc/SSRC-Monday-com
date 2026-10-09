"""Freeze source diff, static checks and hashes without changing runtime data."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
MAPPING = {
    'app.js': 'app.js', 'index.html': 'index.html',
    'overview-ui.js': 'overview-ui.js', 'overview.css': 'overview.css',
    'flowboard_overview.py': 'flowboard/overview.py',
    'timeline-ui.js': 'timeline-ui.js',
    'tests_overview_ui.test.js': 'tests/overview_ui.test.js',
    'tests_test_overview.py': 'tests/test_overview.py',
    'tests_test_overview_e2e.py': 'tests/test_overview_e2e.py',
    'tests_timeline_ui.test.js': 'tests/timeline_ui.test.js',
    'STATE.md': 'STATE.md',
    'feature-02-进阶仪表盘_01-PROJECT_OVERVIEW_CONTRACT.md': 'feature-02-进阶仪表盘/01-PROJECT_OVERVIEW_CONTRACT.md',
    'feature-02-进阶仪表盘_02-DELIVERY.md': 'feature-02-进阶仪表盘/02-DELIVERY.md',
}
NEW = ['tests/test_overview_ux_e2e.py',
       'feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md',
       'feature-02-进阶仪表盘/04-UX_DELIVERY.md',
       'team-progress/20261008-feature02-ux-optimization.md']
checks = []
for name in ('app.js', 'overview-ui.js', 'timeline-ui.js',
             'tests/overview_ui.test.js', 'tests/timeline_ui.test.js'):
    result = subprocess.run([shutil.which('node'), '--check', name], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr)
    checks.append(f'PASS node --check {name}')
for name in ('flowboard/overview.py', 'tests/test_overview.py',
             'tests/test_overview_e2e.py', 'tests/test_overview_ux_e2e.py',
             'tests/test_timeline_e2e.py'):
    ast.parse((ROOT/name).read_text(encoding='utf-8-sig'), filename=name)
    checks.append(f'PASS Python AST {name}')
result = subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True,
                        text=True, encoding='utf-8')
if result.returncode:
    raise RuntimeError(result.stdout + result.stderr)
checks.append('PASS git diff --check (tracked worktree)')
for name in sorted(set(MAPPING.values()) | set(NEW)):
    for index, line in enumerate((ROOT/name).read_text(encoding='utf-8-sig').splitlines(), 1):
        if line.rstrip() != line:
            raise RuntimeError(f'Trailing whitespace: {name}:{index}')
checks.append('PASS scoped source/docs whitespace (includes untracked files)')
if (ROOT/'temp.md').stat().st_size:
    raise RuntimeError('temp.md is not empty')
checks.append('PASS temp.md length = 0')
live = json.loads((OUT/'live-walkthrough.json').read_text(encoding='utf-8'))
assert live['final']['projectRows'] == 37
assert len(live['final']['modules']) == 5
assert not live['final']['advancedVisible']
assert live['final']['search'] == ''
checks.append('PASS live final: 37 rows, 5 modules, collapsed advanced, empty search')
log = (OUT/'final-browser.log').read_bytes().decode('utf-8', errors='replace')
assert 'Ran 19 tests' in log and '\nOK' in log
checks.append('PASS final browser log contains 19 tests and OK; process exit 0 captured in tool result')
(OUT/'static-checks.log').write_text('\n'.join(checks)+'\n', encoding='utf-8')
diff = []
for before, name in MAPPING.items():
    diff.extend(difflib.unified_diff(
        (OUT/'baseline'/before).read_text(encoding='utf-8-sig').splitlines(keepends=True),
        (ROOT/name).read_text(encoding='utf-8-sig').splitlines(keepends=True),
        fromfile='before/'+name, tofile='after/'+name))
for name in NEW:
    diff.extend(difflib.unified_diff([], (ROOT/name).read_text(encoding='utf-8-sig').splitlines(keepends=True),
                                     fromfile='/dev/null', tofile='after/'+name))
diff.append('\n# README.md and tests/test_timeline_e2e.py lack a UX-round source baseline;\n'
            '# their current hashes are bound below. Existing Git diff includes pre-UX changes.\n')
(OUT/'ux-source.diff').write_text(''.join(diff), encoding='utf-8')
required = ['backend.log', 'node.log', 'timeline-node.log', 'final-browser.log',
            'overview-ready.jpg', 'category-filter.jpg', 'dense-detail.jpg', 'canvas-scopes.jpg',
            'live-walkthrough.json', 'demo-tags.json', 'static-checks.log', 'ux-source.diff']
for name in required:
    assert (OUT/name).is_file() and (OUT/name).stat().st_size > 0, name
paths = set(ROOT/name for name in MAPPING.values()) | set(ROOT/name for name in NEW)
paths |= {ROOT/'README.md', ROOT/'tests/test_timeline_e2e.py', Path(__file__)}
paths |= {p for p in OUT.rglob('*') if p.is_file()
          and p.name not in ('artifact-manifest.json', 'preview-stdout.log', 'preview-stderr.log')
          and '__pycache__' not in p.parts}
manifest = {
    'date': '2026-10-08', 'status': 'DEVELOPMENT_READY',
    'human_acceptance': 'PENDING', 'deployment': 'NOT_DEPLOYED',
    'tests': {'backend': '7/7 PASS', 'browser': '19/19 PASS',
              'overview_node': '6/6 PASS', 'timeline_node': 'PASS'},
    'diff_note': 'UX-round saved baselines only; README/timeline E2E current hashes included. Preexisting dirty changes retained.',
    'excluded_mutable_logs': ['preview-stdout.log', 'preview-stderr.log'],
    'files': [{ 'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest() }
              for p in sorted(paths)]}
(OUT/'artifact-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('\n'.join(checks))
print(f'Artifact manifest: {len(paths)} files; all required evidence exists.')
