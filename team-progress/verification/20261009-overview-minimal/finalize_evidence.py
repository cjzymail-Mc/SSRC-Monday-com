import ast
import difflib
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
EARLY=ROOT/'team-progress/verification/20261009-overview-avatar/baseline'
mapping={
    'overview-ui.js':EARLY/'overview-ui.js','overview.css':EARLY/'overview.css','index.html':EARLY/'index.html',
    'tests/overview_ui.test.js':EARLY/'tests_overview_ui.test.js',
    'tests/test_overview_ux_e2e.py':EARLY/'tests_test_overview_ux_e2e.py',
    'tests/test_overview_e2e.py':EARLY/'tests_test_overview_e2e.py',
    'timeline-ui.js':OUT/'baseline/timeline-ui.js',
    'tests/timeline_ui.test.js':OUT/'baseline/tests_timeline_ui.test.js',
    'STATE.md':EARLY/'STATE.md',
    'feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md':EARLY/'feature-02-进阶仪表盘_03-UX_OPTIMIZATION_CONTRACT.md',
    'feature-02-进阶仪表盘/04-UX_DELIVERY.md':EARLY/'feature-02-进阶仪表盘_04-UX_DELIVERY.md',
}
new=['tests/timeline_feed.test.js','tests/test_overview_minimal_e2e.py','team-progress/20261009-overview-minimal-and-feed.md']
checks=[]
for name in ['overview-ui.js','timeline-ui.js','tests/overview_ui.test.js','tests/timeline_feed.test.js','tests/timeline_ui.test.js']:
    r=subprocess.run([shutil.which('node'),'--check',name],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    checks.append('PASS node --check '+name)
for name in ['tests/test_overview_e2e.py','tests/test_overview_ux_e2e.py','tests/test_overview_minimal_e2e.py']:
    ast.parse((ROOT/name).read_text(encoding='utf-8'))
    checks.append('PASS Python AST '+name)
r=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
assert r.returncode==0,r.stdout+r.stderr
checks.append('PASS git diff --check')
diff=[]
for name,baseline in mapping.items():
    before=baseline.read_text(encoding='utf-8-sig');after=(ROOT/name).read_text(encoding='utf-8-sig')
    assert all(line==line.rstrip() for line in after.splitlines()),name
    diff.extend(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='before/'+name,tofile='after/'+name))
for name in new:
    after=(ROOT/name).read_text(encoding='utf-8-sig')
    assert all(line==line.rstrip() for line in after.splitlines()),name
    diff.extend(difflib.unified_diff([],after.splitlines(keepends=True),fromfile='/dev/null',tofile='after/'+name))
checks.append('PASS scoped whitespace and combined round baseline diff')
log=(OUT/'node.log').read_text(encoding='utf-8-sig')
assert 'pass 16' in log and 'fail 0' in log
checks.append('PASS Node 16/16 (overview 11, feed 5)')
assert 'not ok -' not in (OUT/'timeline-node.log').read_text(encoding='utf-8-sig')
checks.append('PASS original timeline Node script; process exit 0')
first=(OUT/'browser.log').read_bytes().decode('utf-8',errors='replace')
assert 'Ran 20 tests' in first and 'FAILED (errors=1)' in first
assert first.count('... ERROR')==1 and 'test_actual_history_completion_and_reopening_are_human_readable' in first
assert 'FAIL:' not in first and 'skipped=' not in first
recheck=(OUT/'feed-browser-recheck.log').read_text(encoding='utf-8-sig')
assert 'Ran 1 test' in recheck and '\nOK' in recheck
checks.append('PASS browser coverage 20: 19 initial PASS + feed locator repair/recheck PASS; initial error retained')
live=json.loads((OUT/'live-feed-proof.json').read_text(encoding='utf-8'))
assert live['access']=='mode=ro' and live['checked']==19 and all(row['passed'] for row in live['checks'])
checks.append('PASS 19 live history encodings read-only rendered without program tokens')
base='http://127.0.0.1:8083'
html=urllib.request.urlopen(base+'/',timeout=5).read().decode('utf-8')
ui=urllib.request.urlopen(base+'/overview-ui.js?v=20261009-f02-minimal-feed',timeout=5).read().decode('utf-8')
feed=urllib.request.urlopen(base+'/timeline-ui.js?v=20261009-f02-minimal-feed',timeout=5).read().decode('utf-8')
assert '20261009-f02-minimal-feed' in html and 'const secondaryControlsEnabled = false;' in ui
assert '<col style="width:20.8%">' in ui and '<col style="width:16.3%">' in ui and 'ov-result' not in ui
assert '标记为已完成' in feed and '恢复为未完成' in feed
health=json.load(urllib.request.urlopen(base+'/api/health',timeout=5));assert health['status']=='ok'
proof={'health':health,'asset_version':'20261009-f02-minimal-feed','secondary_controls':False,'heading':'shared tl-home-head','project_width_percent':20.8,'progress_width_percent':16.3,'summary_row':False,'live_database_connection':'unchanged'}
(OUT/'http-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
checks.append('PASS live HTTP assets/current configuration and health')
for name in ['overview-minimal-ready.png','home-feed-readable.png']:assert (OUT/name).is_file()
(OUT/'static-checks.log').write_text('\n'.join(checks)+'\n',encoding='utf-8')
(OUT/'source.diff').write_text(''.join(diff),encoding='utf-8')
paths={ROOT/name for name in mapping}|{ROOT/name for name in new}|set(mapping.values())
paths|={p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'}
files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
(OUT/'artifact-manifest.json').write_text(json.dumps({'date':'2026-10-09','scope':'combined overview feedback and readable activity','tests':{'node':16,'timeline_node':'PASS','browser':'19 initial + 1 repaired/rechecked','live_readonly_encodings':19},'files':files},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('\n'.join(checks));print(f'Bound {len(files)} artifacts.')
