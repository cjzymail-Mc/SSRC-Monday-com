(function(root,factory){const value=factory(typeof module==='object'&&module.exports?require('./timeline-ui.js'):root.FlowboardTimeline);if(typeof module==='object'&&module.exports)module.exports=value;else root.FlowboardOverview=value})(typeof globalThis!=='undefined'?globalThis:this,function(FlowboardTimeline){
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stages=['创意','设计','开发','测试','量产','应用迭代'];
  const stageClasses=['idea','design','develop','test','production','iteration'];
  const stageClass=stage=>stageClasses[stages.indexOf(stage)]||'empty';
  // 用户暂时隐藏搜索、日期下拉、高级筛选和工具栏刷新；改为 true 即可恢复。
  const secondaryControlsEnabled = false;
  const choices={period:[['all','全部日期'],['week','本周'],['month','本月'],['next30','未来30天']],scope:[['all','全部项目'],['mine','我的项目']],completion:[['all','全部节点'],['open','未完成'],['done','已完成']],stage:[['all','全部阶段'],...stages.map(s=>[s,s])],track:[['all','双轨'],['main','主线'],['parallel','并行']],focus:[['all','全部'],['attention','需关注'],['overdue','逾期'],['today','今日'],['done','已完成']],search_in:[['all','项目与事项'],['project','仅项目'],['node','仅事项']]};
  const defaults=()=>({period:'all',scope:'all',q:'',stage:'all',track:'all',completion:'all',focus:'all',search_in:'all',tag_id:'all'});
  function createState(){return {filters:defaults(),payload:null,status:'loading',error:'',expanded:new Set(),collapsed:new Set(),scrollTop:0,scrollLeft:0,request:0,advanced:false,tags:[]}}
  function preferences(filters,{admin=true,newLogin=false}={}){const result=defaults();result.scope=admin?'all':'mine';for(const key of Object.keys(choices)){if(choices[key].some(([value])=>value===filters?.[key]))result[key]=filters[key]}if(newLogin)result.scope=admin?'all':'mine';const tag=String(filters?.tag_id||'all');if(tag==='all'||tag==='uncategorized'||(tag.length<=18&&/^[1-9]\d*$/.test(tag)))result.tag_id=tag;if(result.focus==='done'){result.focus='all';result.completion='all'}if(!secondaryControlsEnabled){const visible=defaults();visible.scope=result.scope;applyFocus({filters:visible},result.focus==='all'&&['week','month'].includes(result.period)?result.period:['attention','overdue','today'].includes(result.focus)?result.focus:'all');return visible}return result}
  const quickChoices=[...choices.focus.filter(([value])=>value!=='done'),['week','本周'],['month','本月']];
  function quickSelected(filters,value){return ['week','month'].includes(value)?filters.focus==='all'&&filters.period===value:value==='all'?filters.focus==='all'&&!['week','month'].includes(filters.period):filters.focus===value}
  function applyFocus(state,value){const dated=['week','month'].includes(value);state.filters.period=dated?value:'all';state.filters.focus=dated?'all':value;state.filters.completion=dated||value==='all'?'all':value==='done'?'done':'open'}
  function toggleExpansion(state,id){const wasExpanded=state.expanded.has(id);state.expanded.clear();if(!wasExpanded)state.expanded.add(id)}
  function select(key,label,items,filters){return `<label class="ov-filter"><span>${label}</span><select data-overview-filter="${key}" aria-label="${label}">${items.map(([value,text])=>`<option value="${esc(value)}"${filters[key]===value?' selected':''}>${esc(text)}</option>`).join('')}</select></label>`}
  function status(p){const overdue=p.total_overdue_count??p.overdue_count,today=p.total_today_count??p.today_count;return overdue?['late',`逾期 ${overdue}`]:today?['today',`今日 ${today}`]:!p.total_node_count?['empty','待录入节点']:p.total_done_count===p.total_node_count?['done','全部完成']:p.done_count===p.node_count&&p.node_count?['done','已完成事项']:['upcoming','推进中']}
  function nextLabel(p){return p.next_nodes.length?p.next_nodes.map(n=>`${n.name} · ${n.date} · ${n.track==='main'?'主线':'并行'}`).join('\n'):p.total_node_count?'暂无未完成节点':'尚未录入节点'}
  /* 2026-10-22 用户要求：旧节点表先注释保留，未来可恢复。保留源码供未来恢复，当前改用紧凑时间轴。
  function detail(p){
    const upcomingIds=new Set((p.upcoming_nodes||[]).map(n=>n.id));
    const action=`<button type="button" data-timeline-open="editor" data-project-id="${p.project_id}">${p.can_edit?'编辑时间表':'查看时间表 · 只读'}</button>`;
    return `<tr class="ov-detail" id="ov-detail-${p.project_id}"><td colspan="7"><div class="ov-detail-meta"><span>创建者：${esc(p.creator_name)}</span><span>显示 ${p.node_count} / ${p.total_node_count} 个节点</span><span>项目已完成 ${p.total_done_count} / ${p.total_node_count}</span>${action}</div>${p.matched_nodes.length?`<table class="ov-nodes" aria-label="${esc(p.name)}节点"><thead><tr><th>节点</th><th>轨道</th><th>节点阶段</th><th>节点日期</th><th>状态</th><th>备注</th></tr></thead><tbody>${p.matched_nodes.map(n=>`<tr data-overview-node="${n.id}"${upcomingIds.has(n.id)?` class="ov-current-node" aria-label="当前进展 · 下一个时间节点：${esc(n.name)}"`:''}><td>${esc(n.name)}</td><td>${n.track==='main'?'主线':'并行'}</td><td><span class="ov-tag ov-${stageClass(n.stage)}">${esc(n.stage)}</span></td><td class="ov-date">${esc(n.date)}</td><td><span class="ov-node-status ${n.done_at?'done':n.overdue?'late':n.is_today?'today':'upcoming'}">${n.done_at?'已完成':n.overdue?'逾期未完成':n.is_today?'今日到期':esc(n.status)}</span></td><td class="ov-node-remark">${esc(n.remark||'—')}</td></tr>`).join('')}</tbody></table>`:'<p class="ov-empty-nodes">尚未录入节点，可进入时间表维护。</p>'}</td></tr>`;
  }
  */

  // 用户最新反馈：全部逾期未完成节点，双轨合并计算视野；单点居中、多点留白。
  function overdueSlice(project,today){
    return fitSlice((project.nodes||[]).filter(n=>!n.done_at&&n.date&&n.date<today),today);
  }
  function recentSlice(project,today){
    const distance=node=>Math.abs(new Date(node.date+'T00:00:00Z')-new Date(today+'T00:00:00Z'));
    const nodes=(project.nodes||[]).filter(n=>n.date).slice().sort((a,b)=>distance(a)-distance(b)||a.date.localeCompare(b.date)||Number(a.id)-Number(b.id)).slice(0,5);
    return fitSlice(nodes,today);
  }
  function fitSlice(nodes,today){
    const dates=nodes.map(n=>n.date).sort(),first=dates[0]||today,last=dates.at(-1)||today;
    const days=Math.round((new Date(last+'T00:00:00Z')-new Date(first+'T00:00:00Z'))/86400000);
    const padding=nodes.length<=1||days===0?7:Math.max(2,Math.ceil(days*.5));
    const start=FlowboardTimeline.addDays(first,-padding),end=FlowboardTimeline.addDays(last,padding);
    return {start,end,today,nodes};
  }
  function detail(p,state){
    const draft=state.draftStates?.get(Number(p.project_id));
    const project=draft?.project||(state.timelineProjects||[]).find(item=>Number(item.project_id)===Number(p.project_id))||{...p,nodes:p.matched_nodes};
    const recent=p.group==='recent',range=(recent?recentSlice:overdueSlice)(project,state.payload.server_today);
    return `<tr class="ov-detail ov-inline-detail" id="ov-detail-${p.project_id}"><td colspan="7"><section class="ov-inline-panel" aria-label="${esc(p.name)}${recent?'近期':'逾期'}节点时间轴">${range.nodes.length||draft?.dirty?FlowboardTimeline.renderOverviewSlice(project,range,draft,Boolean(state.canEditProject?.(p.project_id))):`<div class="ov-inline-empty">${recent?'尚未录入带日期的节点':'没有逾期未完成的节点'}</div>`}</section></td></tr>`;
  }
  function row(p,state){
    const expanded=state.expanded.has(p.project_id),[kind,label]=status(p),next=p.next_nodes[0],progress=p.total_progress,avatarClass=['avatar-blue','avatar-pink','avatar-green','avatar-purple','avatar-orange'].includes(p.creator_avatar_class)?p.creator_avatar_class:'avatar-purple';
    return `<tr class="ov-project" data-overview-project="${p.project_id}" data-overview-row-expand="${p.project_id}" tabindex="0" aria-expanded="${expanded}" aria-controls="ov-detail-${p.project_id}"><td><div class="ov-project-name"><button type="button" class="ov-expand" data-overview-expand="${p.project_id}" aria-expanded="${expanded}"${expanded?` aria-controls="ov-detail-${p.project_id}"`:''} aria-label="${expanded?'收起':'展开'} ${esc(p.name)}"><svg class="ov-expand-chevron" aria-hidden="true" viewBox="0 0 16 16" focusable="false"><path d="M6 3 11 8 6 13" /></svg></button><button type="button" class="ov-open ov-project-link" data-timeline-open="single" data-project-id="${p.project_id}" title="${esc(p.name)}" aria-label="${esc(p.name)}"><span class="ov-project-title">${esc(p.name)}</span><span class="ov-node-count">${p.total_node_count} 节点</span></button></div></td><td class="ov-owner" title="${esc(p.creator_name)}" aria-label="${esc(p.creator_name)}"><span class="ov-avatar ${avatarClass}" aria-hidden="true">${esc(p.creator_name&&p.creator_name!=='成员已不可用'?Array.from(p.creator_name.trim())[0]||'—':'—')}</span></td><td class="ov-status ${kind}">${label}</td><td class="ov-stage"><span class="ov-stage-badge ov-${stageClass(p.current_stage)}">${esc(p.current_stage)}</span></td><td class="ov-next"><span title="${esc(nextLabel(p))}">${next?`${esc(next.name)}${p.next_nodes.length>1?` <b>+${p.next_nodes.length-1}</b>`:''}`:esc(nextLabel(p))}</span>${next?`<small class="ov-date">${esc(next.date)} · ${next.track==='main'?'主线':'并行'}</small>`:''}</td><td class="ov-main-remark"><span title="${esc(next?.remark||'')}">${esc(next?.remark||'—')}</span></td><td><div class="ov-progress"><span class="ov-progress-track" role="progressbar" aria-label="全项目有效节点完成比例" aria-valuemin="0" aria-valuemax="100"${progress==null?'':` aria-valuenow="${progress}"`}><i style="width:${progress||0}%"></i></span><small>${p.total_node_count?`${p.total_done_count}/${p.total_node_count}`:'—'}</small></div></td></tr>${expanded?detail(p,state):''}`;
  }
  function group(key,title,projects,state){const collapsed=state.collapsed.has(key);return `<section class="ov-group ov-group-${key}"><h2><button type="button" data-overview-collapse="${key}" aria-expanded="${!collapsed}"><span>${collapsed?'›':'⌄'}</span>${title}<small>${projects.length}</small></button></h2>${collapsed?'':`<div class="ov-table-scroll" data-overview-scroll tabindex="0" aria-label="${title}项目表，可横向滚动；左右方向键查看"><table class="ov-table"><colgroup><col style="width:20.8%"><col style="width:44px"><col style="width:105px"><col style="width:105px"><col style="width:14%"><col><col style="width:16.3%"></colgroup><thead><tr><th>项目</th><th title="按项目创建者显示">负责人</th><th>关注状态</th><th>当前阶段</th><th>下一未完成节点</th><th>节点备注</th><th>项目进度</th></tr></thead><tbody>${projects.map(p=>row(p,state)).join('')}</tbody></table></div>`}</section>`}
  function render(state){
    const f=state.filters,payload=state.payload,tags=[['all','全部标签'],['uncategorized','未分类'],...(state.tags||[]).map(tag=>[String(tag.tag_id),tag.name])];
    let content='';
    if(state.status==='loading'&&!payload)content='<div class="ov-message" role="status">正在加载项目…</div>';
    else if(state.status==='error')content=`<div class="ov-message" role="alert"><strong>项目概览加载失败</strong><p>${esc(state.error)}</p><button type="button" data-overview-reload>重新加载</button></div>`;
    else if(!payload?.projects.length)content='<div class="ov-message"><strong>当前筛选下没有项目</strong><p>清除条件后可查看全部项目。</p><button type="button" data-overview-reset>查看全部项目</button></div>';
    else content=['attention','recent'].map(key=>{const projects=payload.projects.filter(p=>p.group===key);return projects.length?group(key,key==='attention'?'需要关注':'项目进展',projects,state):''}).join('');
    const hasConditions=Object.entries(defaults()).some(([key,value])=>f[key]!==value);
    const extras=[f.stage!=='all'?f.stage:'',f.track!=='all'?(f.track==='main'?'主线':'并行'):'',f.tag_id!=='all'?(tags.find(([id])=>id===f.tag_id)?.[1]||'标签'):'',f.search_in!=='all'?(f.search_in==='project'?'仅项目搜索':'仅事项搜索'):'',f.focus==='all'&&f.completion!=='all'?(f.completion==='done'?'已完成节点':'未完成节点'):''].filter(Boolean);
    return `<section class="ov-board" data-timeline-page="overview" aria-busy="${state.status==='loading'}"><header class="ov-header tl-home-head"><div><h1>项目概览</h1><small>今天 ${payload?esc(payload.server_today):''}</small></div></header><div class="ov-toolbar"><div class="ov-scope" aria-label="项目归属">${choices.scope.map(([value,text])=>`<button type="button" data-overview-scope="${value}" aria-pressed="${f.scope===value}" class="${f.scope===value?'on':''}">${text}</button>`).join('')}</div>${secondaryControlsEnabled?`<label class="ov-search"><span aria-hidden="true">⌕</span><input data-overview-search type="search" aria-label="搜索项目、创建者、节点或备注" placeholder="搜索项目或事项" maxlength="100" value="${esc(f.q)}"></label>${select('period','日期范围',choices.period,f)}<button type="button" class="ov-filter-toggle" data-overview-advanced aria-expanded="${state.advanced}" aria-controls="ov-advanced">筛选${extras.length?` <b>${extras.length}</b>`:''}</button><button type="button" class="ov-refresh" data-overview-reload aria-label="刷新项目概览">↻</button>`:''}</div><div class="ov-quick" role="group" aria-label="事项快捷筛选">${quickChoices.map(([value,text])=>`<button type="button" data-overview-focus="${value}" aria-pressed="${quickSelected(f,value)}" class="${quickSelected(f,value)?'on':''}">${text}</button>`).join('')}<button type="button" class="ov-clear" data-overview-reset${hasConditions?'':' hidden'}>清除条件</button></div>${secondaryControlsEnabled?`<div class="ov-advanced" id="ov-advanced"${state.advanced?'':' hidden'}>${select('stage','节点阶段',choices.stage,f)}${select('track','节点轨道',choices.track,f)}${select('completion','节点状态',choices.completion,f)}${select('tag_id','项目标签',tags,f)}${select('search_in','搜索对象',choices.search_in,f)}<button type="button" data-overview-advanced>收起</button></div>`:''}<div class="ov-content">${content}</div><details class="ov-explain"><summary>进度与筛选说明</summary><p>项目按逾期、今日到期、未来节点排序；同类先看最早日期，同日按待处理数量排序。关注状态与分组取全项目风险，每个项目仅展示一次。负责人沿用项目创建者关系，用圆形姓氏头像显示姓名首字，悬停可读完整姓名。节点备注对应主表显示的下一节点。项目进度按项目全部有效节点计算。需要关注展开显示全部逾期未完成节点；项目进展展开显示距离今天最近的最多5个有日期节点，包含已完成和未来节点。主线与并行共用自动适配的日期范围；项目名进入完整时间轴。下一未完成节点取全项目最早未完成日期。</p></details></section>`;
  }
  function bind(root,state,{onChange,onReload,onRender}){
    const signal=root.__timelineAbort.signal;
    root.querySelectorAll('.ov-inline-panel').forEach(panel=>{
      const fit=()=>{panel.style.width=Math.max(260,panel.closest('[data-overview-scroll]').clientWidth-24)+'px'};
      fit();window.addEventListener('resize',fit,{signal});
    });
    root.addEventListener('keydown',event=>{
      if(!event.target.matches('[data-overview-row-expand]')||!['Enter',' '].includes(event.key))return;
      event.preventDefault();const id=Number(event.target.dataset.overviewRowExpand);toggleExpansion(state,id);onRender();
      root.querySelector(`[data-overview-row-expand="${id}"]`)?.focus({preventScroll:true});
    },{signal});
    root.addEventListener('change',event=>{const el=event.target.closest('[data-overview-filter]');if(!el)return;state.filters[el.dataset.overviewFilter]=el.value;if(el.dataset.overviewFilter==='completion')state.filters.focus='all';state.scrollLeft=0;onChange()},{signal});
    root.addEventListener('input',event=>{if(!event.target.matches('[data-overview-search]'))return;state.filters.q=event.target.value;clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>{state.searchTimer=null;onChange()},260)},{signal});
    root.addEventListener('keydown',event=>{if(event.target.matches('[data-overview-search]')&&event.key==='Enter'){event.preventDefault();clearTimeout(state.searchTimer);onChange()}},{signal});
    root.addEventListener('click',event=>{
      const expand=event.target.closest('[data-timeline-open]')?null:event.target.closest('[data-overview-expand],[data-overview-row-expand]'),collapse=event.target.closest('[data-overview-collapse]'),scope=event.target.closest('[data-overview-scope]'),focus=event.target.closest('[data-overview-focus]');
      if(expand){const id=Number(expand.dataset.overviewExpand||expand.dataset.overviewRowExpand);toggleExpansion(state,id);onRender();root.querySelector(`[data-overview-expand="${id}"]`)?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'})}
      else if(collapse){const key=collapse.dataset.overviewCollapse;state.collapsed.has(key)?state.collapsed.delete(key):state.collapsed.add(key);onRender()}
      else if(scope){state.filters.scope=scope.dataset.overviewScope;onChange()}
      else if(focus){applyFocus(state,focus.dataset.overviewFocus);onChange()}
      else if(event.target.closest('[data-overview-advanced]')){state.advanced=!state.advanced;onRender();root.querySelector(state.advanced?'#ov-advanced select':'[data-overview-advanced]')?.focus({preventScroll:true})}
      else if(event.target.closest('[data-overview-reload]'))onReload();
      else if(event.target.closest('[data-overview-reset]')){state.filters=defaults();state.advanced=false;state.scrollLeft=0;state.expanded.clear();state.collapsed.clear();onChange();root.querySelector('[data-overview-focus=all]')?.focus({preventScroll:true})}
    },{signal});
    root.querySelectorAll('[data-overview-scroll]').forEach(el=>{el.scrollLeft=state.scrollLeft;el.addEventListener('scroll',()=>{state.scrollLeft=el.scrollLeft},{signal,passive:true});el.addEventListener('keydown',event=>{if(event.target!==el||!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();el.scrollLeft+=(event.key==='ArrowRight'?1:-1)*120},{signal})});
  }
  return {createState,preferences,applyFocus,toggleExpansion,overdueSlice,recentSlice,render,bind,status,nextLabel};
});
