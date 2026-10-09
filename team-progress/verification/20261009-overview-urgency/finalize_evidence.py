import ast
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
names=['overview-ui.js','overview.css','flowboard/overview.py','index.html','tests/overview_ui.test.js',
       'tests/test_overview.py','tests/test_overview_ux_e2e.py','STATE.md',
       'feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md','feature-02-进阶仪表盘/04-UX_DELIVERY.md']
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
for name,count in [('backend.log',9),('browser.log',12)]:
    log=(OUT/name).read_text(encoding='utf-8-sig')
    assert f'Ran {count} tests' in log and '\nOK' in log
    checks.append(f'PASS {name} {count} tests; process exit 0')
log=(OUT/'node.log').read_text(encoding='utf-8-sig')
assert 'pass 9' in log and 'fail 0' in log
checks.append('PASS Node 9/9')
proof=json.loads((OUT/'live-projection.json').read_text(encoding='utf-8'))
assert proof['unique_projects']==proof['counts']['projects']==25
assert proof['groups']['attention']+proof['groups']['recent']==25
assert proof['business_tables_unchanged'] and proof['sort_check']=='PASS' and proof['note_correspondence']=='PASS'
checks.append('PASS live read-only projection: 25 unique, 9+16 groups, urgency/note correspondence, zero business changes')
(OUT/'static-checks.log').write_text('\n'.join(checks)+'\n',encoding='utf-8')
(OUT/'source.diff').write_text(''.join(diff),encoding='utf-8')
paths={ROOT/name for name in names}|{ROOT/'team-progress/20261009-overview-urgency-feedback.md'}
paths|={p for p in OUT.rglob('*') if p.is_file() and p.name not in ('artifact-manifest.json','runtime-stdout.log','runtime-stderr.log')}
files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
(OUT/'artifact-manifest.json').write_text(json.dumps({'date':'2026-10-09','scope':'overview urgency and notes','tests':{'backend':9,'node':9,'browser':12},'files':files},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('\n'.join(checks));print(f'Bound {len(files)} artifacts.')
