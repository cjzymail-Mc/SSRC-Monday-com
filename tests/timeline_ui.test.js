const Timeline=require('../timeline-ui.js');
let failures=0;
function ok(condition,message){if(condition)console.log('ok - '+message);else{failures++;console.error('not ok - '+message)}}
const project={project_id:1,name:'项目 A',version:1,metrics:{start_date:'2026-08-01',current_stage:'设计',upcoming:[],overdue_count:2,this_week_count:3},nodes:[
  {id:1,track:'main',stage:'创意',name:'概念',date:'2026-08-01'},
  {id:2,track:'main',stage:'设计',name:'方案',date:'2026-08-05'},
  {id:3,track:'parallel',stage:'测试',name:'兼容',date:'2026-08-10'}
],segments:[],stage_intervals:[
  {track:'main',stage:'创意',start_date:'2026-08-01',end_date:'2026-08-05',row_index:0,node_ids:[1,2]},
  {track:'main',stage:'设计',start_date:'2026-08-03',end_date:'2026-08-05',row_index:1,node_ids:[2]},
  {track:'parallel',stage:'测试',start_date:'2026-08-10',end_date:'2026-08-10',row_index:0,node_ids:[3]}
]};
const bounds=Timeline.bounds([project]);ok(bounds.min==='2026-08-01'&&bounds.max==='2026-08-10','bounds use both tracks');
const html=Timeline.renderSingle(project,{today:'2026-08-04'});ok(html.includes('data-dashboard-project="1"')&&html.includes('主线')&&html.includes('并行'),'single project renders direction A card and both tracks');
const dashboard=Timeline.renderDashboard({...project,stage_intervals:[{track:'main',stage:'创意',start:'2026-08-01',end:'2026-08-05',node_ids:[1,2]},{track:'parallel',stage:'测试',start:'2026-08-10',end:'2026-08-10',node_ids:[3]}]});ok(dashboard.includes('stage-idea')&&dashboard.includes('stage-test'),'dashboard renders semantic stage intervals');
ok(Timeline.stageClass('量产')==='stage-production','stage class maps semantic token');
ok([['创意','idea'],['设计','design'],['开发','develop'],['测试','test'],['量产','production'],['应用迭代','iteration']].every(([stage,token])=>Timeline.stageClass(stage)===`stage-${token}`),'all frozen stages map to stable semantic classes');
ok(html.includes('共享绝对日历')&&html.includes('今天 2026-08-04'),'single dashboard renders absolute calendar and redundant today label');
ok(html.includes('data-row-index="1"')&&html.includes('data-overlap-split="true"')&&html.includes('展开重叠'),'collapsed overlap uses server row_index and offers expansion');
ok(html.includes('data-stage="设计"')&&html.includes('class="timeline-stage stage-design')&&html.includes('aria-label="阶段 设计'),'stage interval carries matching data, class and redundant label');
const expanded=Timeline.renderSingle(project,{today:'2026-08-04',expanded:new Set(['1:main'])});
ok(expanded.includes('is-expanded')&&expanded.includes('收起重叠'),'expanded overlap splits deterministic server rows');
ok(html.indexOf('timeline-risk overdue')<html.indexOf('timeline-risk this-week')&&html.includes('逾期 2')&&html.includes('本周 3'),'risk markers are red-left orange-right with text');
ok((html.match(/role="menuitem"/g)||[]).length===4,'single dashboard exposes shared four-action controller menu');
ok(html.includes('data-dashboard-hit-target="node"')&&html.includes('aria-label="节点 概念'),'dashboard nodes expose an explicit physical hit target and redundant label');
const projectB={...project,project_id:2,name:'项目 B',metrics:{...project.metrics,start_date:'2026-07-15',current_stage:'开发',upcoming:[{date:'2026-08-02'}],overdue_count:5,this_week_count:0}};
const all=Timeline.renderAll([project,projectB],{project_ids:[2],sort_key:'overdue',today:'2026-08-04'});
ok(all.includes('data-shared-calendar="true"')&&all.includes('value="overdue" selected')&&!all.includes('data-dashboard-project="1"')&&all.includes('data-dashboard-project="2"'),'all dashboard filters projects and reflects one of four sorts');
ok((all.match(/data-timeline-context/g)||[]).length===1&&(all.match(/role="menuitem"/g)||[]).length===4,'all dashboard reuses one context controller');
const transferPreview=Timeline.renderTransfer({filename:'timeline.xlsx',preview:{batch_id:'preview-1',row_count:2,projects:[{name:'导入项目',node_count:2}],warnings:['状态将按日期重算，仅『已完成』保留']}});
ok(transferPreview.includes('data-timeline-preview-id="preview-1"')&&transferPreview.includes('导入项目：2 个节点')&&transferPreview.includes('状态将按日期重算')&&!transferPreview.includes('data-timeline-import-commit disabled'),'import preview exposes server summary/warnings and enables commit');
const transferError=Timeline.renderTransfer({filename:'bad.xlsx',error:{code:'NAME_CONFLICT',message:'项目名称唯一',details:{rows:[{row:2,project:'已有'},{row:4,project:'已有'}]}}});
ok(transferError.includes('data-timeline-import-error="NAME_CONFLICT"')&&(transferError.match(/data-import-error-row=/g)||[]).length===2&&transferError.includes('data-timeline-import-commit disabled'),'import errors render actionable rows and keep commit disabled');
const transferExport=Timeline.renderTransfer({exportReady:{filename:'timeline.xlsx',sha256:'abc123',url:'blob:test'}});
ok(transferExport.includes('data-timeline-download')&&transferExport.includes('href="blob:test"')&&transferExport.includes('SHA-256 abc123'),'export view links only the verified server blob');
const state=Timeline.editorState(project);
ok(Timeline.moveNode(state,1,'2026-08-20','single')==='2026-08-05','single clamps at next same-track node');
Timeline.discard(state);Timeline.moveNode(state,1,'2026-08-03','cascade');
ok(state.project.nodes.find(node=>node.id===2).date==='2026-08-07'&&state.project.nodes.find(node=>node.id===3).date==='2026-08-10','cascade shifts only the same track');
Timeline.toggleDone(state,2,true);ok(state.draft.get(2).set.done_at===true&&state.draft.get(2).set.date==='2026-08-07','date and status share one draft row');
ok(Timeline.renderEditor(state.project,{state}).includes('2 项草稿')&&Timeline.renderEditor(state.project,{state}).includes('±10 天 ×8'),'editor exposes draft count and zoom band');
Timeline.discard(state);ok(!state.dirty&&state.draft.size===0&&state.project.nodes[1].date==='2026-08-05','discard restores original locally');
Timeline.moveNode(state,1,'2026-08-03','cascade');Timeline.toggleDone(state,2,true);Timeline.createNode(state,{track:'parallel',stage:'测试',name:'新节点',date:'2026-08-12'});Timeline.removeNode(state,3);
const request=Timeline.batchRequest(state);ok(request.base_version===1&&request.details.mode==='cascade'&&request.details.magnet==='standard'&&request.details.zoom_band==='±10d×8','batch carries version and interaction details');
ok(request.changes.some(change=>change.node_id===1&&change.set.date)&&request.changes.some(change=>change.node_id===2&&change.set.done_at===true)&&request.changes.some(change=>change.create?.name==='新节点')&&request.changes.some(change=>change.node_id===3&&change.remove),'batch combines date status create and remove changes');
if(failures)process.exit(1);
