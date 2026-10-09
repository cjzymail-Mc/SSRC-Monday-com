const fs=require('node:fs');
const path=require('node:path');
const Timeline=require('../../../timeline-ui.js');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'live-feed-encodings.json'),'utf8'));
const checks=data.changes.map((row,index)=>{
  const html=Timeline.renderWorkspace([],{mode:'home',currentUser:{id:'check',name:'校验人员'},review:[{name:'生产动态校验',batches:[{batch_id:index+1,created_at:row.created_at,change_kind:row.change_kind,trigger_source:row.trigger_source,actor:{name:'校验人员'},change_rows:[{...row,node_name:'校验节点'}]}]}]});
  const article=html.match(/<article class="tl-feed-item">[\s\S]*?<\/article>/)?.[0];
  if(!article||/False|True|done_at|status_toggle|main|parallel/.test(article))throw Error('Program tokens remain in real encoding '+row.id);
  return {change_id:row.id,field:row.field,passed:true};
});
fs.writeFileSync(path.join(__dirname,'live-feed-proof.json'),JSON.stringify({access:data.access,identities_omitted:true,checked:checks.length,checks},null,2)+'\n');
process.stdout.write('PASS real history encodings: '+checks.length+' rendered without program tokens.\n');
