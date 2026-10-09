from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'timeline-ui.js';s=p.read_text(encoding='utf-8')
start=s.index('  function feedKind(');end=s.index('  function ownedBy(',start)
s=s[:start]+'''  function feedDone(value){if(value===true||value===1)return true;if(value===false||value===0||value==null)return false;const text=String(value).trim().toLowerCase();if(['true','1'].includes(text)||/^\\d{4}-\\d{2}-\\d{2}/.test(text))return true;if(['false','0','','none','null'].includes(text))return false;return null}
  function feedKind(kind,changes=[],source=''){const fields=new Set(changes.map(row=>row.field));if(kind==='undo')return '撤销修改';if(source==='import'||kind==='import')return '导入节点';if(kind==='initial_correction')return '纠正初始日期';if(fields.size===1&&fields.has('done_at')){const values=changes.map(row=>feedDone(row.new_value));return values.every(value=>value===true)?'标记完成':values.every(value=>value===false)?'恢复未完成':'调整完成状态'}if(fields.has('created'))return '新增节点';if(fields.has('deleted'))return '删除节点';if(fields.size===1)return ({date:'调整日期',initial_date:'纠正初始日期',stage:'调整阶段',track:'调整轨道',name:'修改名称',remark:'修改备注',status:'调整状态'})[changes[0].field]||'更新节点';return '更新节点'}
  function feedTime(stamp){const parts=shanghaiTimestampParts(stamp);if(!parts)return '时间未知';const today=shanghaiToday();if(parts.date===today)return `今天 ${parts.clock}`;if(parts.date===addDays(today,-1))return `昨天 ${parts.clock}`;return `${parts.date.slice(5)} ${parts.clock}`}
  function feedValue(value){if(value===null||value===undefined||typeof value==='object')return '';const text=String(value).trim();return /^[\\[{]/.test(text)||['None','null','undefined'].includes(text)?'':text}
  function feedRowSummary(row,kind=''){const node=String(row?.node_name||'节点'),field=String(row?.field||''),oldValue=feedValue(row?.old_value),newValue=feedValue(row?.new_value),prefix=`${node} · `;
    if(field==='created')return prefix+(kind==='undo'?'撤销新建节点':'新建节点');
    if(field==='deleted')return prefix+(kind==='undo'?'恢复节点':'删除节点');
    if(field==='done_at'||field==='status'&&['true','false','1','0'].includes(newValue.toLowerCase())){const done=feedDone(row?.new_value);return prefix+(done===true?'标记为已完成':done===false?'恢复为未完成':'更新完成状态')}
    if(field==='remark')return prefix+(!newValue?'清空备注':!oldValue?`添加备注：${newValue}`:`修改备注：${oldValue} → ${newValue}`);
    const labels={date:row?.change_role==='cascaded'?'联动调整日期':'调整日期',initial_date:'纠正初始日期',status:'调整状态',stage:'调整阶段',track:'调整轨道',name:'修改名称'};
    if(!labels[field])return prefix+'更新节点信息';
    const readable=value=>field==='track'?({main:'主线',parallel:'并行'})[value]||'未设置':value||'未设置';
    return prefix+labels[field]+`：${readable(oldValue)} → ${readable(newValue)}`;
  }
  function feedRows(review,currentUser,scope){const limit=scope==='mine'?6:20,flat=(review||[]).flatMap(project=>(project.batches||[]).map(batch=>({project:project.name,batch}))).filter(item=>scope!=='mine'||item.batch.actor?.name===currentUser).sort((a,b)=>String(b.batch.created_at||'').localeCompare(String(a.batch.created_at||''))||b.batch.batch_id-a.batch.batch_id).slice(0,limit);if(!flat.length)return '<p class="tl-feed-empty">暂无动态</p>';return flat.map(item=>{const batch=item.batch,actor=batch.actor?.name||'成员',changes=batch.change_rows||[],details=changes.map(row=>feedRowSummary(row,batch.change_kind)),summary=details.length?`${details[0]}${details.length>1?`（共 ${details.length} 项修改）`:''}`:'';return `<article class="tl-feed-item"><span class="tl-feed-avatar" aria-hidden="true">${esc(actor.slice(0,1))}</span><span class="tl-feed-copy"><span><b>${esc(actor)}</b> ${esc(feedKind(batch.change_kind,changes,batch.trigger_source))} · ${esc(item.project)}</span>${summary?`<small title="${esc(details.join('\\n'))}">${esc(summary)}</small>`:''}</span><time>${esc(feedTime(batch.created_at))}</time></article>`}).join('')}
''' + s[end:]
p.write_text(s,encoding='utf-8')
p=ROOT/'tests/timeline_ui.test.js';s=p.read_text(encoding='utf-8').replace('鞋底转图 · 新建节点（共 2 项）','鞋底转图 · 新建节点（共 2 项修改）');p.write_text(s,encoding='utf-8')
