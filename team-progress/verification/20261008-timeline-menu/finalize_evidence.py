from pathlib import Path
import ast
import difflib
import hashlib
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
names=['app.js','index.html','timeline-ui.js','overview.css',
       'tests/test_overview_ux_e2e.py','tests/test_timeline_e2e.py','README.md','STATE.md',
       'feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md',
       'feature-02-进阶仪表盘/04-UX_DELIVERY.md']
checks=[]
for name in ['app.js','timeline-ui.js']:
    r=subprocess.run([shutil.which('node'),'--check',name],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    checks.append('PASS node --check '+name)
for name in ['tests/test_overview_ux_e2e.py','tests/test_timeline_e2e.py']:
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
log=(OUT/'browser.log').read_text(encoding='utf-8-sig')
assert 'Ran 5 tests' in log and '\nOK' in log
checks.append('PASS browser 5/5; process exit 0')
assert 'not ok -' not in (OUT/'timeline-node.log').read_text(encoding='utf-8-sig')
checks.append('PASS timeline Node; process exit 0')
proof=json.loads((OUT/'live-proof.json').read_text(encoding='utf-8'))['result']
assert proof['page']=='all' and proof['parentLabel']=='项目时间轴' and not proof['rangeRow']
assert all(x['pressed']=='false' for x in proof['children'])
checks.append('PASS actual 8083 month => parent => all; no top range row')
(OUT/'static-checks.log').write_text('\n'.join(checks)+'\n',encoding='utf-8')
(OUT/'source.diff').write_text(''.join(diff),encoding='utf-8')
paths={ROOT/name for name in names}|{ROOT/'team-progress/20261008-timeline-menu-feedback.md'}
paths|={p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'}
files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
(OUT/'artifact-manifest.json').write_text(json.dumps({'date':'2026-10-08','scope':'timeline menu feedback','files':files},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('\n'.join(checks));print(f'Bound {len(files)} artifacts.')
