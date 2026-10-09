const {test}=require('node:test');
const assert=require('node:assert/strict');
const Timeline=require('../timeline-ui.js');

const spanning={project_id:101,name:'跨期双轨项目',nodes:[
  {id:1,track:'main',stage:'测试',name:'测试启动',date:'2026-07-22'},
  {id:2,track:'main',stage:'量产',name:'量产确认',date:'2026-10-11'},
  {id:3,track:'parallel',stage:'开发',name:'并行启动',date:'2026-08-01'},
  {id:4,track:'parallel',stage:'测试',name:'并行交付',date:'2026-10-11'}
],stage_intervals:[
  {track:'main',stage:'测试',node_ids:[1],start_date:'2026-07-22',end_date:'2026-10-11'},
  {track:'parallel',stage:'开发',node_ids:[3],start_date:'2026-08-01',end_date:'2026-10-11'}
],segments:[{start_node_id:1,end_node_id:2},{start_node_id:3,end_node_id:4}]};

for(const timeScope of ['week','month'])test(`${timeScope}: cross-period bars keep past masks when only future nodes are visible`,()=>{
  const html=Timeline.renderAll([spanning],{timeScope,today:'2026-10-09'});
  assert.equal((html.match(/timeline-past-mask/g)||[]).length,2);
  assert.ok(html.includes('data-stage-interval'));
  assert.ok(!html.includes('data-node-date="2026-07-22"'));
  assert.ok(!html.includes('data-node-date="2026-08-01"'));
  assert.ok(html.includes('data-node-date="2026-10-11"'));
});

test('future-only project remains unmasked in both period views',()=>{
  const future={...spanning,nodes:spanning.nodes.map(node=>({...node,date:'2026-10-11'}))};
  for(const timeScope of ['week','month'])assert.ok(!Timeline.renderAll([future],{timeScope,today:'2026-10-09'}).includes('timeline-past-mask'));
});
