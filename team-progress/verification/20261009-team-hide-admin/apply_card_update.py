from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'timeline-ui.js';s=p.read_text(encoding='utf-8')
s=s.replace("${orderedMembers.length?orderedMembers.map(strip).join(''):", "${visibleMembers.length?visibleMembers.map(strip).join(''):")
assert 'orderedMembers.map(strip)' not in s
anchor='  function renderHomeView('
helper="  function mergeVisibleMemberOrder(fullIds,visibleIds){const full=fullIds.map(String),visible=visibleIds.map(String),shown=new Set(visible);let index=0;return [...full.map(id=>shown.has(id)?visible[index++]:id),...visible.filter(id=>!full.includes(id))]}\n"
s=s.replace(anchor,helper+anchor)
s=s.replace('return {bounds,dashboardRange,','return {mergeVisibleMemberOrder,bounds,dashboardRange,')
p.write_text(s,encoding='utf-8')
p=ROOT/'app.js';s=p.read_text(encoding='utf-8')
old="if(intent.scope==='team'){setTimeout(()=>saveMemberOrder(visible),0);return}"
assert old in s
s=s.replace(old,"if(intent.scope==='team'){const full=FlowboardTimeline.mergeVisibleMemberOrder(intent.fullIds||intent.originalIds,visible);setTimeout(()=>saveMemberOrder(full),0);return}")
p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261009-f02-minimal-feed','20261009-f02-team-cards');p.write_text(s,encoding='utf-8')
p=ROOT/'tests/timeline_ui.test.js';s=p.read_text(encoding='utf-8')
s=s.replace('name:`成员项目 ${index+1}`,created_by:\'u1\'', 'name:`成员项目 ${index+1}`,created_by:\'u2\'')
s=s.replace("members:[{id:'u1',name:'林晓'}],currentUser:{id:'u1',name:'林晓'},review:[{name:'成员项目 1'", "members:[{id:'u1',name:'林晓',role:'admin'},{id:'u2',name:'周然',role:'member'}],currentUser:{id:'u1',name:'林晓'},review:[{name:'成员项目 1'")
p.write_text(s,encoding='utf-8')
