const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const T=require('../timeline-ui.js');
function project(id=7,version=1){return {project_id:id,version,name:'项目',nodes:[{id:id*10,name:'原节点',track:'main',stage:'设计',date:'2026-10-29',remark:'原备注',done_at:null}],stage_intervals:[]}}
function harness(api){
  const p=project(),other=T.editorState(project(8));T.updateNode(other,80,'remark','其他项目待更新');
  const draft=T.editorState(p),c={FlowboardTimeline:T,timelineDraftStates:new Map([[7,draft],[8,other]]),timelineState:{projects:[p,other.original]},state:{workspace_id:1},timelineProjectEditable:()=>true,api};
  const source=fs.readFileSync(require.resolve('../app.js'),'utf8');
  vm.createContext(c);vm.runInContext(source.slice(source.indexOf('async function saveTimelineInsert('),source.indexOf('function renderOverview()')),c);
  return {c,draft,other,save:()=>c.saveTimelineInsert({projectId:7,values:{name:'新节点',track:'parallel',stage:'测试',date:'2026-10-30',remark:''}})};
}
test('insertion sends only one create without submitting or clearing other project drafts',async()=>{
  let request;const h=harness(async(_,method,payload)=>{assert.equal(method,'POST');request=payload;return {results:[{view:project(7,2),batch_id:5}]}});
  const result=await h.save();assert.equal(result.batch_id,5);assert.equal(request.requests.length,1);
  const r=request.requests[0];assert.equal(r.project_id,7);assert.equal(r.base_version,1);assert.equal(r.changes.length,1);assert.equal(r.changes[0].create.name,'新节点');assert.equal(r.changes[0].create.track,'parallel');
  assert.equal(h.draft.dirty,false);assert.equal(h.draft.submitting,false);assert.equal(h.other.dirty,true);assert.equal(h.other.project.nodes[0].remark,'其他项目待更新');
});
test('an existing same-project draft prevents immediate insertion with zero requests',async()=>{
  let calls=0;const h=harness(async()=>{calls++});T.removeNode(h.draft,70);
  await assert.rejects(h.save(),/先更新或放弃/);assert.equal(calls,0);assert.equal(h.draft.dirty,true);assert.equal(h.draft.draft.get(70).remove,true);
});
test('inflight insertion rejects duplicates and releases the save lock after failure',async()=>{
  let reject,calls=0;const h=harness(()=>{calls++;return new Promise((_,r)=>reject=r)});
  const pending=h.save();assert.equal(h.draft.submitting,true);await assert.rejects(h.save(),/正在保存/);assert.equal(calls,1);
  reject(new Error('500'));await assert.rejects(pending,/500/);assert.equal(h.draft.submitting,false);assert.equal(h.draft.dirty,false);
});
test('409 changes the baseline for an explicit retry and preserves unrelated drafts',async()=>{
  let calls=0,last;const latest=project(7,2);latest.nodes[0].remark='其他人的更新';
  const h=harness(async(_,__,payload)=>{last=payload.requests[0];if(++calls===1)throw {status:409,details:{conflicts:[{view:latest}]}};return {results:[{view:project(7,3),batch_id:6}]}});
  await assert.rejects(h.save(),/插入内容已保留/);assert.equal(calls,1);assert.equal(h.c.timelineDraftStates.get(7).original.version,2);assert.equal(h.other.dirty,true);
  await h.save();assert.equal(calls,2);assert.equal(last.base_version,2);assert.equal(last.changes.length,1);assert.equal(last.changes[0].create.name,'新节点');assert.equal(h.c.timelineDraftStates.get(7).original.nodes[0].remark,'其他人的更新');
});

test('only overdue unfinished flags get reminders; completed, today and future nodes stay normal',()=>{
  const p=project();p.server_today='2026-10-29';p.nodes=[{...p.nodes[0],id:1,date:'2026-10-20'}, {...p.nodes[0],id:2,date:'2026-11-01'}, {...p.nodes[0],id:3,date:'2026-10-20',done_at:'2026-10-29T00:00:00Z'}, {...p.nodes[0],id:4,date:'2026-10-29'}];
  const html=T.renderSingle(p,{today:p.server_today});
  assert.match(html,/class="timeline-node-flag is-overdue"[^>]*data-node-id="1"/);
  for(const id of [2,3,4])assert.match(html,new RegExp('class="timeline-node-flag"[^>]*data-node-id="'+id+'"'));
  assert.doesNotMatch(html,/is-incomplete|unfinished-flag/);
});
