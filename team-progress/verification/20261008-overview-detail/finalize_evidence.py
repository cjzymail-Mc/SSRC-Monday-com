import ast
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
names=['overview-ui.js','overview.css','flowboard/overview.py','index.html',
       'tests/overview_ui.test.js','tests/test_overview.py','tests/test_overview_e2e.py',
       'tests/test_overview_ux_e2e.py','STATE.md',
       'feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md',
       'feature-02-进阶仪表盘/04-UX_DELIVERY.md']
checks=[]
for name in ['overview-ui.js','tests/overview_ui.test.js']:
    r=subprocess.run([shutil.which('node'),'--check',name],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    checks.append('PASS node --check '+name)
for name in ['flowboard/overview.py','tests/test_overview.py','tests/test_overview_ux_e2e.py']:
    ast.parse((ROOT/name).read_text(encoding='utf-8'))
    checks.append('PASS Python AST '+name)
r=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
assert r.returncode==0,r.stdout+r.stderr
checks.append('PASS git diff --check')
diff=[]
for name in names:
    before=(OUT/'baseline'/name.replace('/','_')).read_text(encoding='utf-8-sig')
    after=(ROOT/name).read_text(encoding='utf-8-sig')
    assert all(line==line.rstrip() for line in after.splitlines()),name
    diff.extend(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='before/'+name,tofile='after/'+name))
checks.append('PASS scoped whitespace')
for name,count in [('backend.log',8),('browser.log',11),('accordion-viewport.log',1)]:
    log=(OUT/name).read_text(encoding='utf-8-sig')
    assert f'Ran {count} test' in log and '\nOK' in log
    checks.append(f'PASS {name} {count} tests; process exit 0')
log=(OUT/'node.log').read_text(encoding='utf-8-sig')
assert 'pass 8' in log and 'fail 0' in log
checks.append('PASS Node 8/8')
proof=json.loads((OUT/'live-proof.json').read_text(encoding='utf-8'))
assert proof['first']['detailCount']==1 and proof['first']['duplicates']==0
assert proof['first']['highlighted'][0]['outline']=='dashed'
assert proof['second']['detailCount']==1 and proof['second']['firstExpanded']=='false'
checks.append('PASS actual 8083 dashed future row, no duplicates, accordion')
(OUT/'static-checks.log').write_text('\n'.join(checks)+'\n',encoding='utf-8')
(OUT/'source.diff').write_text(''.join(diff),encoding='utf-8')
paths={ROOT/name for name in names}|{ROOT/'team-progress/20261008-overview-detail-feedback.md'}
paths|={p for p in OUT.rglob('*') if p.is_file() and p.name not in ('artifact-manifest.json','preview-stdout.log','preview-stderr.log')}
files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
(OUT/'artifact-manifest.json').write_text(json.dumps({'date':'2026-10-08','scope':'overview detail feedback','tests':{'backend':8,'node':8,'browser':11,'additional_viewport':1},'files':files},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('\n'.join(checks));print(f'Bound {len(files)} artifacts.')
