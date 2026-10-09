const test=require('node:test');
const assert=require('node:assert/strict');
const Timeline=require('../timeline-ui.js');
const project={project_id:1,name:'管理员负责项目',created_by:'a1',version:1,metrics:{start_date:'2026-10-09',current_stage:'设计',upcoming:[],overdue_count:0},nodes:[{id:1,name:'确认方案',track:'main',stage:'设计',date:'2026-10-09'}],segments:[],stage_intervals:[]};
const members=[{id:'a1',name:'管理员',role:'admin'},{id:'a2',name:'另一管理员',role:'admin'},{id:'m1',name:'成员',role:'member'},{id:'v1',name:'只读成员',role:'viewer'}];
test('only team cards hide every admin while my projects and timeline keep their projects',()=>{
  const home=Timeline.renderWorkspace([project],{mode:'home',admin:true,write:true,currentUser:{id:'a1',name:'管理员'},members});
  assert.doesNotMatch(home,/data-order-member="a1"|data-order-member="a2"/);
  assert.match(home,/data-order-member="m1"/);assert.match(home,/data-order-member="v1"/);
  assert.match(home,/data-order-project="1"/);
  const portfolio=Timeline.renderWorkspace([project],{mode:'all',currentUser:{id:'m1',name:'成员'},members});
  assert.match(portfolio,/管理员负责项目/);
  const memberView=Timeline.renderWorkspace([project],{mode:'home',currentUser:{id:'m1',name:'成员'},members});
  assert.doesNotMatch(memberView,/data-order-member="a1"|data-order-member="a2"/);
});
test('visible member reorder preserves hidden admin positions and full roster',()=>{
  assert.deepEqual(Timeline.mergeVisibleMemberOrder(['m1','a1','m2'],['m2','m1']),['m2','a1','m1']);
  assert.deepEqual(Timeline.mergeVisibleMemberOrder(['a1','m1','a2','m2'],['m2','m1']),['a1','m2','a2','m1']);
  assert.deepEqual(Timeline.mergeVisibleMemberOrder(['m1','m2'],['m2','m1']),['m2','m1']);
});
