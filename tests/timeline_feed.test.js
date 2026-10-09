const test=require('node:test');
const assert=require('node:assert/strict');
const Timeline=require('../timeline-ui.js');
function feed(rows,kind='direct_edit',source='manual'){
  const html=Timeline.renderWorkspace([],{mode:'home',currentUser:{id:'u1',name:'林晓'},review:[{name:'项目A',batches:[{batch_id:1,created_at:'2026-10-09T05:30:00+00:00',change_kind:kind,trigger_source:source,actor:{name:'林晓'},change_rows:rows}]}]});
  return html.match(/<article class="tl-feed-item">[\s\S]*?<\/article>/)[0];
}
test('completion and reopening use action words for historical boolean encodings',()=>{
  for(const value of ['True','true',true,1,'1','2026-10-09T05:30:00+00:00']){
    const html=feed([{node_name:'量产上市',field:'done_at',old_value:'False',new_value:value}],'status_toggle');
    assert.match(html,/量产上市 · 标记为已完成/);assert.doesNotMatch(html,/False|True|done_at|status_toggle/);
  }
  for(const value of ['False','false',false,0,'0',null])assert.match(feed([{node_name:'量产上市',field:'done_at',old_value:'True',new_value:value}],'status_toggle'),/恢复为未完成/);
});
test('tracks, cascaded dates, added and cleared remarks describe actual edits',()=>{
  assert.match(feed([{node_name:'节点A',field:'track',old_value:'main',new_value:'parallel'}]),/主线 → 并行/);
  assert.match(feed([{node_name:'节点A',field:'date',change_role:'cascaded',old_value:'2026-10-09',new_value:'2026-10-12'}]),/联动调整日期：2026-10-09 → 2026-10-12/);
  assert.match(feed([{node_name:'节点A',field:'remark',old_value:'',new_value:'材料待确认'}]),/添加备注：材料待确认/);
  assert.match(feed([{node_name:'节点A',field:'remark',old_value:'材料待确认',new_value:''}]),/清空备注/);
  assert.match(feed([{node_name:'节点A',field:'stage',old_value:'设计',new_value:'开发'}]),/调整阶段：设计 → 开发/);
});
test('create, delete and their undo never show raw snapshots or deleted tokens',()=>{
  const create={node_name:'节点A',field:'created',old_value:null,new_value:'{"name":"节点A","track":"main"}'};
  assert.match(feed([create]),/新建节点/);assert.doesNotMatch(feed([create]),/track|&quot;name&quot;/);
  assert.match(feed([create],'undo'),/撤销新建节点/);
  const remove={node_name:'节点A',field:'deleted',old_value:null,new_value:'deleted'};
  assert.match(feed([remove]),/删除节点/);assert.doesNotMatch(feed([remove]),/deleted/);
  assert.match(feed([remove],'undo'),/恢复节点/);
  assert.match(feed([create],'direct_edit','import'),/导入节点/);
});
test('batch tooltip includes every action and unknown fields never expose code',()=>{
  const html=feed([{node_name:'节点A',field:'done_at',new_value:'True'},{node_name:'节点B',field:'done_at',new_value:'False'}],'status_toggle');
  assert.match(html,/共 2 项修改/);assert.match(html,/节点B · 恢复为未完成/);assert.doesNotMatch(html,/True|False/);
  const unknown=feed([{node_name:'节点A',field:'internal_flag',old_value:'False',new_value:'True'}],'internal_change');
  assert.match(unknown,/更新节点信息/);assert.doesNotMatch(unknown,/internal_flag|internal_change|False|True/);
});
test('names and note text remain escaped in both summaries and tooltip',()=>{
  const html=feed([{node_name:'<img src=x onerror=bad()>',field:'remark',old_value:'',new_value:'<script>bad()</script>'}]);
  assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;script&gt;/);
});
