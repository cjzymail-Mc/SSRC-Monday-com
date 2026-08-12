const D=require('../dashboard-ui.js');let n=0;const ok=(value,message)=>{if(!value)throw Error(message);n++};
let value=D.clamp({x:11,y:-2,width:4,height:99});ok(value.x===8&&value.y===0&&value.width===4&&value.height===12,'layout clamp');
ok(D.collides({x:0,y:0,width:3,height:2},{x:2,y:1,width:3,height:2}),'collision true');ok(!D.collides({x:0,y:0,width:2,height:2},{x:2,y:0,width:2,height:2}),'touching is not collision');
value=D.place({x:0,y:0,width:3,height:2},[{x:0,y:0,width:3,height:2}]);ok(value.y===2,'collision placement');
const model={categories:['待开始','已完成'],series:[{name:'count',values:[2,1]}],empty:false};
for(const type of ['bar','line','pie','stacked_bar']){const html=D.chart(model,type);ok(html.includes('图表数据')&&html.includes('待开始')&&html.includes('2'),`${type} accessible projection`)}
ok(D.chart({empty:true},'bar').includes('没有可聚合的数据'),'empty state');console.log(`dashboard-ui assertions: ${n}`);
