const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const Timeline=require('../timeline-ui.js');
const Overview=require('../overview-ui.js');

function project(){return {project_id:7,name:'双轨项目',version:3,nodes:[
  {id:1,name:'早期主线',track:'main',stage:'设计',date:'2026-01-02',remark:'材料备注'},
  {id:2,name:'近期并行',track:'parallel',stage:'测试',date:'2026-10-17',remark:''},
  {id:3,name:'今天',track:'main',stage:'测试',date:'2026-10-22'},
  {id:4,name:'未来',track:'main',stage:'量产',date:'2026-11-01'},
  {id:5,name:'已完成',track:'main',stage:'设计',date:'2026-01-01',done_at:true},
  {id:6,name:'无日期',track:'parallel',stage:'测试',date:null}
],stage_intervals:[
  {track:'main',stage:'设计',start_date:'2026-01-01',end_date:'2026-10-22',row_index:0,node_ids:[5,1,3]},
  {track:'parallel',stage:'测试',start_date:'2026-10-17',end_date:'2026-11-01',row_index:0,node_ids:[2,4]}
]}}

test('auto fit includes all old and parallel overdue nodes while excluding done, today, future and undated',()=>{
  const p=project(),slice=Overview.overdueSlice(p,'2026-10-22');
  assert.deepEqual(slice.nodes.map(n=>n.id),[1,2]);
  assert.ok(slice.start<'2026-01-02');assert.ok(slice.end>'2026-10-17');
  const single=Overview.overdueSlice({...p,nodes:[p.nodes[1]]},'2026-10-22');
  assert.equal(single.start,'2026-10-10');assert.equal(single.end,'2026-10-24');
  const html=Timeline.renderOverviewSlice(p,single,Timeline.editorState(p),true);
  assert.match(html,/data-node-id="2"[^>]*style="left:50%;/);
});

test('slice preserves both rails, stage bands and original menu without exposing hidden nodes',()=>{
  const p=project(),slice=Overview.overdueSlice(p,'2026-10-22');
  const html=Timeline.renderOverviewSlice(p,slice,Timeline.editorState(p),true);
  assert.match(html,/data-track="main"/);assert.match(html,/data-track="parallel"/);
  assert.match(html,/timeline-stage stage-design/);assert.match(html,/timeline-stage stage-test/);
  const rendered=[...html.matchAll(/class="timeline-dashboard-node[^>]*data-node-id="(\d+)"/g)].map(m=>Number(m[1]));
  assert.deepEqual(rendered,[1,2]);
  const menu=html.match(/<div[^>]*data-timeline-context[^]*?<\/div>/)[0];
  assert.equal((menu.match(/role="menuitem"/g)||[]).length,6);
  for(const action of ['single','cascade','done','undone','remark','remove'])assert.ok(menu.includes(`data-draft-action="${action}"`));
  const readonly=Timeline.renderOverviewSlice(p,slice,Timeline.editorState(p),false);
  assert.doesNotMatch(readonly,/data-timeline-context|data-dashboard-submit/);
});

test('pending changes make the chart inert and discard restores editable clean rendering',()=>{
  const p=project(),draft=Timeline.editorState(p);Timeline.toggleDone(draft,1,true);
  const html=Timeline.renderOverviewSlice(draft.project,Overview.overdueSlice(draft.project,'2026-10-22'),draft,true);
  assert.match(html,/data-portfolio-scroll inert/);assert.match(html,/ov-inline-draft-overlay/);
  assert.match(html,/data-dashboard-discard="7"/);assert.match(html,/data-dashboard-submit="7"[^>]*>更新 1/);
  Timeline.discard(draft);
  const restored=Timeline.renderOverviewSlice(draft.project,Overview.overdueSlice(draft.project,'2026-10-22'),draft,true);
  assert.doesNotMatch(restored,/inert|ov-inline-draft-overlay/);assert.match(restored,/data-node-id="1"/);
});

function savingHarness(api,editable=true){
  const p=project(),drafts=new Map([[7,Timeline.editorState(p)]]),timelineState={projects:[p]};
  const source=fs.readFileSync(require.resolve('../app.js'),'utf8');
  const start=source.indexOf('async function saveOverviewRemark('),end=source.indexOf('function renderOverview()',start);
  const context={FlowboardTimeline:Timeline,timelineDraftStates:drafts,timelineState,timelineProjectEditable:()=>editable,state:{workspace_id:1},api};
  vm.createContext(context);vm.runInContext(source.slice(start,end),context);
  return {save:context.saveOverviewRemark,drafts,timelineState};
}

test('remark confirmation submits only the chosen remark with the original version and leaves drafts clean',async()=>{
  let request;
  const harness=savingHarness(async(path,method,body)=>{request={path,method,body};return {results:[{view:project(),batch_id:10}]}});
  const result=await harness.save({projectId:7,nodeId:2,remark:'直接保存'});
  assert.equal(result.batch_id,10);assert.equal(request.method,'POST');assert.match(request.path,/\/timeline\/batches$/);
  const batch=request.body.requests[0];assert.equal(batch.base_version,3);
  assert.deepEqual(batch.changes,[{node_id:2,set:{remark:'直接保存'}}]);
  assert.equal(harness.drafts.get(7).dirty,false);assert.equal(harness.drafts.get(7).project.nodes[1].remark,'');
});

test('remark save rejects readonly, missing node and unrelated dirty drafts before sending requests',async()=>{
  let calls=0;const api=async()=>{calls++};
  await assert.rejects(savingHarness(api,false).save({projectId:7,nodeId:2,remark:'x'}),/无法编辑/);
  const clean=savingHarness(api);await assert.rejects(clean.save({projectId:7,nodeId:999,remark:'x'}),/不可用/);
  const dirty=savingHarness(api);Timeline.toggleDone(dirty.drafts.get(7),1,true);
  await assert.rejects(dirty.save({projectId:7,nodeId:2,remark:'x'}),/其他修改/);assert.equal(calls,0);
});

test('conflict retry uses latest project version without losing another node change',async()=>{
  let calls=0,retry;const latest=project();latest.version=4;latest.nodes[0].remark='别人刚保存的备注';
  const harness=savingHarness(async(path,method,body)=>{
    if(!calls++){const error=new Error('conflict');error.status=409;error.details={conflicts:[{view:latest}]};throw error}
    retry=body.requests[0];return {results:[{view:latest,batch_id:11}]};
  });
  await assert.rejects(harness.save({projectId:7,nodeId:2,remark:'保留输入'}),/输入已保留/);
  assert.equal(harness.drafts.get(7).dirty,false);assert.equal(harness.timelineState.projects[0].version,4);
  await harness.save({projectId:7,nodeId:2,remark:'保留输入'});
  assert.equal(retry.base_version,4);assert.deepEqual(retry.changes,[{node_id:2,set:{remark:'保留输入'}}]);
  assert.equal(harness.drafts.get(7).project.nodes[0].remark,'别人刚保存的备注');
});
