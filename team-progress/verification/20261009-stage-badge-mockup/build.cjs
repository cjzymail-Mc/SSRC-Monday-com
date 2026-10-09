const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'../../..');
const Overview=require(path.join(root,'overview-ui.js'));
const stageNames=['创意','设计','开发','测试','量产','应用迭代'];
const samples=[
  ['轻羽 PRO','测试','张明','avatar-orange',7,12,'2026-09-23','二轮试穿报告',''],
  ['弹力背包','开发','延宁','avatar-blue',5,10,'2026-09-26','预览图稿','图稿转图'],
  ['轻跑 2.0GT','测试','徐林','avatar-blue',4,6,'2026-09-28','第二轮测试','完成测试并关闭问题'],
  ['晨光训练鞋 · 联名款','应用迭代','庄文','avatar-purple',9,12,'2026-10-08','上市使用反馈','整理首批用户反馈'],
  ['灵感轻跑 · 新季计划','创意','杨乐','avatar-green',1,12,'2026-10-15','创意方向确认',''],
  ['轻风 3.0','设计','徐林','avatar-blue',2,12,'2026-10-20','整体设计确认','补充外观方案'],
  ['风行 PB6.5','量产','张明','avatar-orange',9,11,'2026-10-11','量产上市',''],
  ['越野 5.0','开发','庄文','avatar-purple',4,12,'2026-10-28','整体开发完成','验证材料与工艺'],
  ['新季概念 · 待录入','未录入节点','杨乐','avatar-green',0,0,null,null,'']
];
const projects=samples.map(([name,current_stage,creator_name,creator_avatar_class,total_done_count,total_node_count,date,nodeName,remark],index)=>{
  const attention=index<4,next=date?[{name:nodeName,date,track:'main',remark}]:[];
  return {project_id:index+1,name,current_stage,creator_name,creator_avatar_class,created_by:'sample',group:attention?'attention':'recent',next_nodes:next,upcoming_nodes:next,matched_nodes:[],total_node_count,total_done_count,total_progress:total_node_count?Math.round(total_done_count/total_node_count*100):null,node_count:total_node_count,done_count:total_done_count,total_overdue_count:attention?(index===1?2:1):0,total_today_count:0};
});
const state=Overview.createState();state.status='ready';state.payload={server_today:'2026-10-09',projects};Overview.applyFocus(state,'month');
let board=Overview.render(state).replace(/<td class="ov-stage (ov-\w+)">([^<]*)<\/td>/g,(_,stage,text)=>`<td class="ov-stage"><span class="ov-stage-badge ${stage}">${text}</span></td>`);
board=board.replace(/<details class="ov-explain">[\s\S]*?<\/details>/,'');
const index=fs.readFileSync(path.join(root,'index.html'),'utf8');
let sidebar=index.match(/<aside class="sidebar"[\s\S]*?<\/aside>/)[0];
sidebar=sidebar.replace('id="timelineOverviewBtn"','id="timelineOverviewBtn" aria-current="page"').replace('id="timelineOverviewBtn" title=','id="timelineOverviewBtn" title=');
sidebar=sidebar.replace('class="nav-item nav-button" id="timelineOverviewBtn"','class="nav-item nav-button active" id="timelineOverviewBtn"');
sidebar=sidebar.replace('连接中','视觉预览').replace('自动同步','静态样张').replace('<div class="current-user" id="currentUser"></div>','<div class="current-user" id="currentUser"><span class="avatar avatar-blue">示</span><span>示例用户</span></div>');
const styles=['styles.css','timeline.css','overview.css'].map(name=>fs.readFileSync(path.join(root,name),'utf8').replace(/@import[^;]+;/g,'')).join('\n');
const badgeStyles=`
/* Only stage badges use the semantic stage palette; cells keep the row surface. */
.ov-project>td.ov-stage{color:inherit}
.ov-stage-badge{display:inline-flex;align-items:center;justify-content:center;min-width:56px;height:26px;padding:0 12px;border-radius:6px;color:#fff;font-size:12px;font-weight:500;line-height:1;white-space:nowrap;vertical-align:middle}
.ov-stage-badge.ov-idea{background:var(--stage-idea)}.ov-stage-badge.ov-design{background:var(--stage-design)}.ov-stage-badge.ov-develop{background:var(--stage-develop)}.ov-stage-badge.ov-test{background:var(--stage-test)}.ov-stage-badge.ov-production{background:var(--stage-production)}.ov-stage-badge.ov-iteration{background:var(--stage-iteration)}.ov-stage-badge.ov-empty{background:#b5afc3;min-width:0;padding:0 8px;font-size:10px}
.sample-caption{display:flex;align-items:center;gap:10px;padding:9px 24px;border-bottom:1px solid #e8e4f1;background:#fff;color:#8b8395;font-size:11px}.sample-caption b{color:#6253d8;font-weight:500}.sample-caption span{margin-left:auto}.sample-caption+.app-shell{min-height:calc(100vh - 34px)}
.ov-board button,.sidebar button{cursor:default}.ov-open:hover{text-decoration:none}
`;
const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Flowboard · 当前阶段圆角标签静态样张</title><style>${styles}\n${badgeStyles}</style></head><body><div class="sample-caption"><b>当前阶段 · 圆角标签样张</b><span>示例数据 · 仅供视觉确认</span></div><div class="app-shell">${sidebar}<main class="main-content"><section class="timeline-view"><div class="timeline-shell"><div id="timelineBody">${board}</div></div></section></main></div></body></html>`;
const target=path.join(root,'feature-02-进阶仪表盘/（静态样张）当前阶段-圆角标签.html');
fs.writeFileSync(target,html,'utf8');
console.log(JSON.stringify({artifact:target,rows:projects.length,stages:stageNames,standalone:true}));
