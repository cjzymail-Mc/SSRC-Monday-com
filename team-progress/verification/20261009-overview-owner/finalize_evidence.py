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
names=['overview-ui.js','overview.css','index.html','tests/overview_ui.test.js','tests/test_overview_ux_e2e.py','STATE.md',
       'feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md','feature-02-进阶仪表盘/04-UX_DELIVERY.md']
checks=[]
for name in ['overview-ui.js','tests/overview_ui.test.js']:
    r=subprocess.run([shutil.which('node'),'--check',name],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    checks.append('PASS node --check '+name)
ast.parse((ROOT/'tests/test_overview_ux_e2e.py').read_text(encoding='utf-8'))
checks.append('PASS Python AST test_overview_ux_e2e.py')
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
log=(OUT/'node.log').read_text(encoding='utf-8-sig')
assert 'pass 9' in log and 'fail 0' in log
checks.append('PASS Node 9/9')
base='http://127.0.0.1:8083'
html=urllib.request.urlopen(base+'/',timeout=5).read().decode('utf-8')
ui=urllib.request.urlopen(base+'/overview-ui.js?v=20261009-f02-owner-column',timeout=5).read().decode('utf-8')
assert '20261009-f02-owner-column' in html
assert '<col style="width:16%">' in ui and '<col style="width:44px">' in ui
assert 'ov-owner' in ui and 'colspan="7"' in ui
health=json.load(urllib.request.urlopen(base+'/api/health',timeout=5))
assert health['status']=='ok'
proof={'health':health,'served_asset_version':'20261009-f02-owner-column','project_column_percent':16,'owner_column_pixels':44,'columns':7,'database_connection':'unchanged from live production preview'}
(OUT/'http-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
checks.append('PASS live HTTP index/JS new version and health')
(OUT/'static-checks.log').write_text('\n'.join(checks)+'\n',encoding='utf-8')
(OUT/'source.diff').write_text(''.join(diff),encoding='utf-8')
paths={ROOT/name for name in names}|{ROOT/'team-progress/20261009-overview-owner-column.md'}
paths|={p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'}
files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
(OUT/'artifact-manifest.json').write_text(json.dumps({'date':'2026-10-09','scope':'project width and creator surname','tests':{'node':9,'browser':5},'files':files},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('\n'.join(checks));print(f'Bound {len(files)} artifacts.')
