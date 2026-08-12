const assert=require('assert'),S=require('../schedule-ui.js');let n=0;const eq=(actual,expected)=>{n++;assert.deepStrictEqual(actual,expected)};
eq(S.parseDay('2026-02-30'),null);eq(S.addDays('2026-12-31',1),'2027-01-01');eq(S.diffDays('2026-12-31','2027-01-02'),2);
const tasks=[{id:1,start:'2026-01-01',end:'2026-01-01',duration_days:1},{id:2,start:'2026-01-02',end:'2026-01-04',duration_days:3}];
eq(S.layout(tasks,{start:'2026-01-01'},'day').map(x=>[x.left,x.width]),[[0,36],[36,108]]);eq(S.ticks({start:'2026-01-01',end:'2026-01-15'},'week').map(x=>x.date),['2026-01-01','2026-01-08','2026-01-15']);
eq(S.criticalPath(tasks,[{predecessor_id:1,successor_id:2}]).task_ids,[1,2]);eq(S.criticalPath(tasks,[{predecessor_id:1,successor_id:2},{predecessor_id:2,successor_id:1}]).blocked,true);
console.log(`schedule-ui assertions: ${n}`);
