import difflib
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
TEAM=OUT.parent/'20261009-team-hide-admin'

def digest(data):return hashlib.sha256(data).hexdigest()
def read(name):return (ROOT/name).read_bytes()
def wheel(data):return next(line for line in data.decode('utf-8').splitlines() if "portfolioScroll.addEventListener('wheel'" in line)

original=read('team-progress/verification/20261009-timeline-wheel/baseline/timeline-ui.js')
assert wheel(original)==wheel(read('timeline-ui.js'))
proof={'wheel_handler_unchanged':True,'wheel_sha256':digest(wheel(original).encode())}
for filename in ['index.html','timeline-ui.js','app.js']:
    url='http://127.0.0.1:8083/'+(filename if filename!='index.html' else '')
    with urllib.request.urlopen(url,timeout=10) as response:body=response.read()
    assert body==read(filename),filename+' serving stale source'
    proof[filename]={'source_sha256':digest(body),'http_status':200}
assert b'timeline-ui.js?v=20261009-period-mask' in read('index.html')
with urllib.request.urlopen('http://127.0.0.1:8083/api/health',timeout=10) as response:proof['health']=json.load(response)
(OUT/'http-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')

checks=[]
for args in [['node','--check','timeline-ui.js'],['node','--check','app.js'],['python','-m','py_compile','flowboard/service.py','tests/test_timeline_period_mask_e2e.py','tests/test_team_cards_e2e.py','tests/test_team_cards_http.py'],['git','diff','--check']]:
    result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,encoding='utf-8')
    checks.append({'command':args,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    assert result.returncode==0,args
(OUT/'static-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')

for folder,mapping in [(OUT,{'timeline-ui.js':'timeline-ui.js','index.html':'index.html'}),(TEAM,{'timeline-ui.js':'timeline-ui.js','app.js':'app.js','flowboard_service.py':'flowboard/service.py','index.html':'index.html','tests_timeline_ui.test.js':'tests/timeline_ui.test.js'})]:
    diff=[]
    for before,after in mapping.items():
        baseline=folder/'baseline'/before
        diff.extend(difflib.unified_diff(baseline.read_text(encoding='utf-8').splitlines(True),(ROOT/after).read_text(encoding='utf-8').splitlines(True),fromfile=str(baseline.relative_to(ROOT)),tofile=after))
    (folder/'source.diff').write_text(''.join(diff),encoding='utf-8')

files=[ROOT/name for name in ['timeline-ui.js','app.js','flowboard/service.py','index.html','tests/timeline_ui.test.js','tests/timeline_team_cards.test.js','tests/test_team_cards_http.py','tests/test_team_cards_e2e.py','tests/timeline_period_mask.test.js','tests/test_timeline_period_mask_e2e.py','team-progress/20261009-team-cards-and-period-mask.md','STATE.md','feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md','feature-02-进阶仪表盘/04-UX_DELIVERY.md']]
for folder in [OUT,TEAM]:files.extend(path for path in folder.rglob('*') if path.is_file() and path.name!='artifact-manifest.json' and '__pycache__' not in path.parts)
manifest={str(path.relative_to(ROOT)).replace('\\','/'):{'sha256':digest(path.read_bytes()),'size':path.stat().st_size} for path in files}
(OUT/'artifact-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'http_source_match':True,'wheel_unchanged':True,'static_checks':len(checks),'manifest_files':len(manifest),'health':proof['health']},ensure_ascii=False))
