const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const T=require('../timeline-ui.js');
const O=require('../overview-ui.js');
function project(){return {project_id:7,name:'测试项目',version:1,server_today:'2026-10-29',nodes:[
  {id:1,name:'节点一',date:'2026-10-29',track:'main',stage:'设计',remark:'原备注',done_at:null},
  {id:2,name:'节点二',date:'2026-10-30',track:'main',stage:'测试',remark:'另一备注',done_at:'2026-10-20T00:00:00Z'}
],stage_intervals:[]}}
function harness(api,{mode='editor',confirm=()=>true}={}){
  const p=project(),draft=T.editorState(p),renders=[],messages=[];
  T.updateNode(draft,1,'remark','本地输入');
  const c={FlowboardTimeline:T,timelineDraftStates:new Map([[7,draft]]),timelineState:{projects:[p],mode,selectedId:7,editor:mode==='editor'?draft:null},state:{workspace_id:1},api,confirm,timelineProjectEditable:()=>true,toast:x=>messages.push(x),showError:e=>messages.push(e.message),$:()=>({querySelector:()=>null}),loadOverview:()=>{},renderTimeline:()=>{const s=c.timelineDraftStates.get(7);renders.push(mode==='editor'?T.renderEditor(s.project,{state:s}):T.renderSingle(s.project,{state:s}))}};
  const source=fs.readFileSync(require.resolve('../app.js'),'utf8');
  const accept=source.split(/\r?\n/).find(line=>line.startsWith('function acceptTimelineView('));
  vm.createContext(c);vm.runInContext(accept+'\n'+source.slice(source.indexOf('function conflictRetrySummary('),source.indexOf('async function undoTimelineDashboardBatch(')),c);
  return {c,draft,renders,messages,submit:()=>mode==='editor'?c.submitTimelineDraft():c.submitTimelineDashboardDraft(7)};
}
test('net changes normalize dates, remarks, completion timestamps and canceled creates',()=>{
  for(const [field,value,baseline] of [['date','2026-11-01','2026-10-29'],['remark','','原备注'],['done_at',true,false]]){
    const s=T.editorState(project());T.updateNode(s,1,field,value);assert.equal(s.dirty,true);T.updateNode(s,1,field,baseline);assert.equal(s.dirty,false);assert.equal(s.draft.size,0);
  }
  const s=T.editorState(project());T.toggleDone(s,2,false);T.toggleDone(s,2,true);assert.equal(s.dirty,false);assert.equal(s.project.nodes[1].done_at,s.original.nodes[1].done_at);
  const n=T.createNode(s,{name:'临时',date:'2026-11-01',track:'parallel',stage:'设计'});T.removeNode(s,n.id);assert.equal(s.dirty,false);
});
test('reverting a drag restores pushed dates while preserving another field edit',()=>{
  const s=T.editorState(project());T.updateNode(s,2,'remark','保留');T.moveNode(s,1,'2026-10-31','single');assert.equal(s.project.nodes[1].date,'2026-11-01');T.moveNode(s,1,'2026-10-29','single');assert.equal(s.project.nodes[1].date,'2026-10-30');assert.equal(s.project.nodes[1].remark,'保留');assert.deepEqual(T.batchRequest(s).changes,[{node_id:2,set:{remark:'保留'}}]);
});
test('pending weekly and monthly projects survive completion, removal, period boundaries and project filters',()=>{
  for(const scope of ['week','month'])for(const action of ['done','remove','move']){
    const p=project();p.nodes=p.nodes.slice(0,1);const s=T.editorState(p);
    if(action==='done')T.toggleDone(s,1,true);else if(action==='remove')T.removeNode(s,1);else T.moveNode(s,1,scope==='week'?'2026-11-02':'2026-11-01','single');
    const html=T.renderAll([p],{states:new Map([[7,s]]),timeScope:scope,project_ids:[999]});
    assert.match(html,/data-dashboard-project="7"/);assert.match(html,/data-dashboard-submit="7"/);assert.match(html,/timeline-stage-lanes" inert/);
  }
});
test('all canvases share pending and submitting controls with readonly respected',()=>{
  const p=project(),s=T.editorState(p);T.toggleDone(s,1,true);s.submitting=true;
  for(const html of [T.renderSingle(p,{state:s}),T.renderAll([p],{states:new Map([[7,s]])}),T.renderOverviewSlice(s.project,O.overdueSlice(s.project,'2026-11-01'),s,true)]){
    assert.match(html,/data-dashboard-submit="7" disabled>更新中/);assert.match(html,/data-dashboard-discard="7" disabled/);assert.match(html,/data-dashboard-pending="7"/);
  }
  assert.doesNotMatch(T.renderSingle(p,{state:s,editable:false}),/data-dashboard-submit/);
});
test('editor failure retains input and rerenders an enabled retry button',async()=>{
  const h=harness(async()=>{throw new Error('保存失败')});await h.submit();assert.equal(h.draft.dirty,true);assert.equal(h.draft.submitting,false);assert.equal(h.draft.project.nodes[0].remark,'本地输入');assert.doesNotMatch(h.renders.at(-1),/data-timeline-submit disabled/);
});
test('409 preserves local input until explicit retry, which preserves unrelated server changes',async()=>{
  let calls=0,confirmed=false,request;const latest=project();latest.version=2;latest.nodes[1].remark='其他人的输入';
  const h=harness(async(path,method,body)=>{calls++;if(calls===1){const error=new Error('conflict');error.status=409;error.details={conflicts:[{view:latest}]};throw error}request=body.requests[0];return {results:[{view:latest,batch_id:4}]}},{confirm:()=>confirmed});
  await h.submit();assert.equal(calls,1);assert.equal(h.draft.project.nodes[0].remark,'本地输入');assert.equal(h.draft.dirty,true);assert.match(h.renders.at(-1),/确认并重试/);
  await h.submit();assert.equal(calls,1);confirmed=true;await h.submit();assert.equal(calls,2);assert.equal(request.base_version,2);assert.deepEqual(request.changes,[{node_id:1,set:{remark:'本地输入'}}]);
  const fresh=T.rebaseDraft(h.draft,latest);assert.equal(fresh.project.nodes[1].remark,'其他人的输入');
});
test('retry handles server-side deletion without losing local text and discard adopts latest',async()=>{
  const latest=project();latest.version=2;latest.nodes.shift();const h=harness(async()=>{const e=new Error('conflict');e.status=409;e.details={conflicts:[{view:latest}]};throw e});await h.submit();await h.submit();assert.equal(h.draft.project.nodes[0].remark,'本地输入');assert.ok(h.messages.some(x=>x.includes('已被删除')));h.c.discardTimelineDashboardDraft(7);assert.equal(h.c.timelineDraftStates.get(7).original.version,2);assert.equal(h.c.timelineDraftStates.get(7).dirty,false);
  const removed=T.editorState(project());T.removeNode(removed,1);assert.equal(T.rebaseDraft(removed,latest).dirty,false);
});
test('repeated submission during a pending request posts once',async()=>{
  let calls=0,finish;const h=harness(()=>{calls++;return new Promise(resolve=>finish=resolve)},{mode:'single'});const pending=h.submit();await h.submit();assert.equal(calls,1);finish({results:[{view:project(),batch_id:1}]});await pending;
});
