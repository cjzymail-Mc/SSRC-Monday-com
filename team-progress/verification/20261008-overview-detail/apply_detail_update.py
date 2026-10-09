from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js'
s=p.read_text(encoding='utf-8')
start=s.index('  function detail(p){')
end=s.index('\n  function row(p,state)',start)
s=s[:start]+'''  function detail(p){
    const upcomingIds=new Set((p.upcoming_nodes||[]).map(n=>n.id));
    const action=`<button type="button" data-timeline-open="editor" data-project-id="${p.project_id}">${p.can_edit?'编辑时间表':'查看时间表 · 只读'}</button>`;
    return `<tr class="ov-detail" id="ov-detail-${p.project_id}"><td colspan="5"><div class="ov-detail-meta"><span>创建者：${esc(p.creator_name)}</span><span>显示 ${p.node_count} / ${p.total_node_count} 个节点</span><span>项目已完成 ${p.total_done_count} / ${p.total_node_count}</span>${action}</div>${p.matched_nodes.length?`<table class="ov-nodes" aria-label="${esc(p.name)}节点"><thead><tr><th>节点</th><th>轨道</th><th>节点阶段</th><th>节点日期</th><th>状态</th><th>备注</th></tr></thead><tbody>${p.matched_nodes.map(n=>`<tr data-overview-node="${n.id}"${upcomingIds.has(n.id)?` class="ov-current-node" aria-label="当前进展 · 下一个时间节点：${esc(n.name)}"`:''}><td>${esc(n.name)}</td><td>${n.track==='main'?'主线':'并行'}</td><td><span class="ov-tag ov-${stageClass(n.stage)}">${esc(n.stage)}</span></td><td class="ov-date">${esc(n.date)}</td><td><span class="ov-node-status ${n.done_at?'done':n.overdue?'late':n.is_today?'today':'upcoming'}">${n.done_at?'已完成':n.overdue?'逾期未完成':n.is_today?'今日到期':esc(n.status)}</span></td><td class="ov-node-remark">${esc(n.remark||'—')}</td></tr>`).join('')}</tbody></table>`:'<p class="ov-empty-nodes">尚未录入节点，可进入时间表维护。</p>'}</td></tr>`;
  }''' + s[end:]
s=s.replace('近期范围同时纳入更早逾期节点。</p>','红色虚线标出今天起最近的未完成时间节点，同日节点一起标记；筛选隐藏该节点时不标记其他节点。近期范围同时纳入更早逾期节点。</p>')
p.write_text(s,encoding='utf-8')
p=ROOT/'overview.css';s=p.read_text(encoding='utf-8')
s=re.sub(r'\.ov-detail-head\{[^}]*\}|\.ov-detail-head strong\{[^}]*\}|\.ov-detail-head>span\{[^}]*\}','',s)
s=s.replace('.ov-detail-head button,.ov-message button','.ov-detail-meta button,.ov-message button')
s=re.sub(r'\.ov-next-list[^{}]*\{[^}]*\}','',s)
s+='\n.ov-detail-meta{align-items:center}.ov-nodes tr.ov-current-node{outline:2px dashed #e03258;outline-offset:-1px}\n'
p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261008-f02-timeline-menu','20261008-f02-detail-focus');p.write_text(s,encoding='utf-8')
