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
ok(!/class="timeline-dashboard-node[^>]*\stitle=/.test(html),'dashboard nodes avoid a duplicate native title tooltip');
const projectB={...project,project_id:2,name:'项目 B',metrics:{...project.metrics,start_date:'2026-07-15',current_stage:'开发',upcoming:[{date:'2026-08-02'}],overdue_count:5,this_week_count:0}};
const all=Timeline.renderAll([project,projectB],{project_ids:[2],sort_key:'overdue',today:'2026-08-04'});
ok(all.includes('data-shared-calendar="true"')&&!all.includes('data-dashboard-project="1"')&&all.includes('data-dashboard-project="2"'),'all dashboard keeps internal project shaping on one shared chart');
ok((all.match(/class="timeline-portfolio-chart"/g)||[]).length===1&&(all.match(/class="timeline-calendar"/g)||[]).length===1&&(all.match(/class="timeline-today-line"/g)||[]).length===1&&!all.includes('timeline-project-card'),'all dashboard is one shared chart with one calendar and one today line instead of per-project cards');
ok((all.match(/data-timeline-context/g)||[]).length===1&&(all.match(/role="menuitem"/g)||[]).length===4,'all dashboard reuses one context controller');
const portfolio=Timeline.renderAll([project,projectB],{today:'2026-08-04',viewport:{center:'2026-08-05',days:2,scrollTop:31},fullscreen:true});
ok(portfolio.includes('data-calendar-start="2026-07-02"')&&portfolio.includes('data-calendar-end="2026-09-09"'),'portfolio calendar uses all node data bounds plus 30 days on both sides');
ok(portfolio.includes('data-viewport-days="14"')&&portfolio.includes('· 14 天'),'portfolio viewport clamps to the approved 14-day minimum');
ok(portfolio.includes('timeline-portfolio-card is-fullscreen')&&portfolio.includes('data-portfolio-visible-range')&&portfolio.includes('data-portfolio-scroll'),'portfolio renders the shared range and canvas required by wheel zoom and direct panning');
ok(portfolio.includes('timeline-e-years')&&portfolio.includes('timeline-e-quarters')&&portfolio.includes('timeline-e-months')&&portfolio.includes('timeline-e-days'),'portfolio renders the approved E year, quarter, month and day hierarchy');
ok(portfolio.includes('data-portfolio-drag-guides')&&portfolio.includes('class="corridor"')&&portfolio.includes('class="target-label"'),'portfolio renders the approved D4 transient drag reinforcement layer');
ok(/data-node-id="1"[^>]*z-index:1000/.test(portfolio),'dense fit keeps deterministic node hit priority');
ok(portfolio.includes('data-portfolio-fullscreen')&&portfolio.includes('退出全屏'),'portfolio keeps the restored fullscreen action');
ok((Timeline.renderSingle(project,{today:'2026-08-04'}).match(/timeline-past-mask/g)||[]).length===2,'running project masks today-left on both tracks');
ok(!Timeline.renderSingle(project,{today:'2026-09-04'}).includes('timeline-past-mask'),'expired project does not receive the running-project mask');
const denseProject={...project,project_id:7,nodes:[{id:71,track:'main',stage:'设计',name:'白圈一',date:'2026-08-01'},{id:72,track:'main',stage:'设计',name:'白圈二',date:'2026-08-02'}],stage_intervals:[],segments:[]};
const denseCollapsed=Timeline.renderAll([denseProject],{today:'2026-07-01',viewport:{center:'2026-08-01',days:61},viewportWidth:760});
const denseExpanded=Timeline.renderAll([denseProject],{today:'2026-07-01',viewport:{center:'2026-08-01',days:14},viewportWidth:760});
ok((denseCollapsed.match(/timeline-node-cluster/g)||[]).length===1&&!denseCollapsed.includes('data-node-id="71"'),'overlapping all-dashboard nodes collapse to one small-dot surrogate');
ok(!denseExpanded.includes('timeline-node-cluster')&&denseExpanded.includes('data-node-id="71"')&&denseExpanded.includes('data-node-id="72"'),'zoom restores normal nodes once their pixels no longer overlap');
ok(html.includes('data-single-scroll')&&html.includes('timeline-single-chart')&&html.includes('data-viewport-days'),'single dashboard exposes horizontal wheel-zoom and pan canvas state');
const customAll=Timeline.renderAll([projectB,project],{sort_key:'custom',today:'2026-08-04',tagCatalog:{virtual:[{context_type:'all',name:'全部',project_count:2},{context_type:'uncategorized',name:'未分类',project_count:1}],tags:[{tag_id:8,name:'喜爱',project_count:1}]},orderContext:{context_type:'tag',tag_id:8}});
ok(customAll.indexOf('data-dashboard-project="2"')<customAll.indexOf('data-dashboard-project="1"')&&customAll.includes('我的自定义顺序')&&customAll.includes('data-timeline-tag-context="tag"')&&customAll.includes('class="active">喜爱'),'custom all-dashboard preserves personal input order and renders one active tag');
ok((customAll.match(/data-order-project=/g)||[]).length===2&&(customAll.match(/class="tl-order-grip" draggable="true"/g)||[]).length===2&&!/data-order-project="[^"]+"[^>]*draggable/.test(customAll),'custom unfiltered all-dashboard makes the handle the only personal-order drag source');
const autoAll=Timeline.renderAll([project,projectB],{sort_key:'start',project_ids:[],tagCatalog:{virtual:[],tags:[]}});ok(!autoAll.includes('data-order-project="1" draggable="true"')&&autoAll.includes('自动排序为只读'),'automatic sorting disables personal dragging without writing order');
const home=Timeline.renderWorkspace([project],{mode:'home',write:true,admin:true,members:[{id:'u1',name:'林晓'}],currentUser:{id:'u1',name:'林晓'},review:[]});
ok(home.includes('class="tl-home-head"')&&home.includes('<h1>我的工作</h1>')&&home.includes('data-timeline-create')&&home.includes('data-timeline-import-file'),'home matches the approved screen A header and keeps create/import hooks');
ok(!home.includes('class="timeline-toolbar"')&&!home.includes('class="timeline-transfer"'),'home hides the legacy mode toolbar and inactive transfer card');
const owned={...project,created_by:'u1'},ownedB={...projectB,created_by:'u1'};
const orderedHome=Timeline.renderWorkspace([owned,ownedB],{mode:'home',write:true,currentUser:{id:'u1',name:'林晓'},mineOrder:{order_version:3,project_ids:[2,1]}});
ok(orderedHome.indexOf('data-order-project="2"')<orderedHome.indexOf('data-order-project="1"')&&orderedHome.includes('data-order-list="mine"'),'my projects renders the current user personal order with drag hooks');
const tagsHtml=Timeline.renderTags({catalog:{role:'admin',tags:[{tag_id:9,name:'重点',version:2,project_count:1}]},selectedId:9,membership:{included:[{project_id:1,name:'项目 A'}],excluded:[{project_id:2,name:'项目 B'}]},undo:{projectId:2,included:true}});
ok(tagsHtml.includes('<h1>标签</h1>')&&tagsHtml.includes('影响所有成员')&&tagsHtml.includes('data-tag-drop="excluded"')&&tagsHtml.includes('data-tag-drop="included"'),'scheme A tag page renders shared-warning dual columns');
ok((tagsHtml.match(/data-tag-project=/g)||[]).length===2&&tagsHtml.includes('data-tag-delete="9"')&&tagsHtml.includes('data-tag-undo'),'tag page exposes drag membership, admin delete and immediate undo');
const archived={...project,project_id:9,name:'归档项目',archived_at:'2026-08-25T09:30:00',read_only:true,can_archive:false,can_unarchive:true};
const archivedPage=Timeline.renderWorkspace([archived],{mode:'archived',write:true,currentUser:{id:'u1',name:'林晓'}});
ok(archivedPage.includes('<h1>已归档</h1>')&&archivedPage.includes('<strong>归档项目</strong>')&&archivedPage.includes('data-timeline-unarchive="9"')&&!archivedPage.includes('timeline-portfolio-chart'),'home archived page is a name-only lightweight list with unarchive');
const archivedAll=Timeline.renderAll([archived],{archived:true,today:'2026-08-04',editable:()=>true,tagCatalog:{virtual:[{context_type:'archived',name:'已归档项目',project_count:1}],tags:[]},orderContext:{context_type:'archived',tag_id:null}});
ok(archivedAll.includes('<h2>已归档项目</h2>')&&archivedAll.includes('已归档 · 只读')&&!archivedAll.includes('data-dashboard-submit')&&!archivedAll.includes('role="menuitem"'),'archived all-dashboard is an independent read-only canvas');
const archiveMenu=Timeline.renderWorkspace([{...owned,can_archive:true}],{mode:'single',selectedId:1,write:true,currentUser:{id:'u1',name:'林晓'},filters:{}});
ok(archiveMenu.includes('data-timeline-archive="1"')&&archiveMenu.includes('归档项目'),'project page exposes the permission-backed archive menu');
const busyHome=Timeline.renderWorkspace([project],{mode:'home',write:true,currentUser:{id:'u1',name:'林晓'},transfer:{busy:true}});ok(busyHome.includes('class="timeline-transfer"')&&(busyHome.match(/data-timeline-import-file/g)||[]).length===1&&(busyHome.match(/data-timeline-export/g)||[]).length===1,'active transfer appears without duplicating home starter controls');
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
const editorHtml=Timeline.renderEditor(state.project,{state,editable:true,admin:true});
ok(editorHtml.includes('时间表编辑器')&&editorHtml.includes('class="timeline-sheet"')&&editorHtml.includes('项目阶段')&&editorHtml.includes('时间间隔（天）')&&editorHtml.includes('状态')&&editorHtml.includes('备注'),'editor renders the frozen Excel-like table and fixed business columns');
ok(!editorHtml.includes('timeline-canvas')&&!editorHtml.includes('class="timeline-node')&&!editorHtml.includes('timeline-zoom-band')&&!editorHtml.includes('data-timeline-context'),'editor does not retain the rejected timeline canvas, drag nodes, zoom band or context menu');
ok(editorHtml.includes('2 项草稿')&&editorHtml.includes('保存（触发计算＋顺延）'),'table editor exposes draft count and cascade-save contract');
const readonlyHtml=Timeline.renderEditor(project,{state:Timeline.editorState(project),editable:false,admin:false});
ok(readonlyHtml.includes('只读：只有项目创建者或工作区管理员可修改')&&!readonlyHtml.includes('data-timeline-add')&&!readonlyHtml.includes('data-timeline-correct'),'project-level read-only editor hides write/admin actions');
Timeline.discard(state);ok(!state.dirty&&state.draft.size===0&&state.project.nodes[1].date==='2026-08-05','discard restores original locally');
Timeline.moveNode(state,1,'2026-08-03','cascade');Timeline.toggleDone(state,2,true);Timeline.createNode(state,{track:'parallel',stage:'测试',name:'新节点',date:'2026-08-12'});Timeline.removeNode(state,3);
const request=Timeline.batchRequest(state);ok(request.base_version===1&&request.details.mode==='cascade'&&request.details.magnet==='standard'&&request.details.zoom_band==='±10d×8','batch carries version and interaction details');
ok(request.changes.some(change=>change.node_id===1&&change.set.date)&&request.changes.some(change=>change.node_id===2&&change.set.done_at===true)&&request.changes.some(change=>change.create?.name==='新节点')&&request.changes.some(change=>change.node_id===3&&change.remove),'batch combines date status create and remove changes');
ok(request.trigger_source==='editor'&&Timeline.batchRequest(state,{triggerSource:'drag'}).trigger_source==='drag','editor and dashboard batches preserve distinct audit sources');
const tableState=Timeline.editorState(project);
Timeline.updateNode(tableState,2,'date','2026-08-06');Timeline.updateNode(tableState,2,'interval_days',5);Timeline.updateNode(tableState,2,'stage','开发');Timeline.updateNode(tableState,2,'name','方案修订');Timeline.updateNode(tableState,2,'remark','表内备注');Timeline.updateNode(tableState,2,'done_at',true);
const tableChange=Timeline.batchRequest(tableState).changes.find(change=>change.node_id===2).set;
ok(tableChange.date==='2026-08-06'&&tableChange.interval_days===5&&tableChange.stage==='开发'&&tableChange.name==='方案修订'&&tableChange.remark==='表内备注'&&tableChange.done_at===true,'table row edits preserve date-priority mixed intent and all editable fields');
Timeline.updateNode(tableState,2,'track','parallel');ok(!Object.prototype.hasOwnProperty.call(tableState.draft.get(2).set,'interval_days'),'changing track clears the incompatible interval intent');
const temp=Timeline.createNode(tableState,{track:'main',stage:'创意',name:'新节点',date:'2026-08-11',remark:''});Timeline.updateNode(tableState,temp.id,'name','新节点已编辑');Timeline.updateNode(tableState,temp.id,'remark','新行备注');
const createChange=Timeline.batchRequest(tableState).changes.find(change=>change.create?.name==='新节点已编辑');ok(createChange?.create.remark==='新行备注'&&!Object.prototype.hasOwnProperty.call(createChange.create,'interval_days'),'temporary row edits stay inside create and never emit interval_days');
Timeline.removeNode(tableState,temp.id);ok(!Timeline.batchRequest(tableState).changes.some(change=>change.create?.name==='新节点已编辑'),'deleting an unsaved row cancels its create draft');
if(failures)process.exit(1);
