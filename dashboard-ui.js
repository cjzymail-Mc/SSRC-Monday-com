(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.FlowboardDashboard=api})(typeof self!=='undefined'?self:this,function(){
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function clamp(layout){const width=Math.max(1,Math.min(12,Number(layout.width)||4)),height=Math.max(1,Math.min(12,Number(layout.height)||3)),x=Math.max(0,Math.min(12-width,Number(layout.x)||0)),y=Math.max(0,Math.min(200,Number(layout.y)||0));return{x,y,width,height}}
  function collides(a,b){return a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y}
  function place(layout,others=[]){const next=clamp(layout);while(others.some(item=>collides(next,clamp(item))))next.y++;return next}
  function table(model){const headers=model.categories||[],series=model.series||[];return `<table class="chart-data"><caption>图表数据</caption><thead><tr><th>分类</th>${series.map(item=>`<th>${esc(item.name)}</th>`).join('')}</tr></thead><tbody>${headers.map((label,index)=>`<tr><th>${esc(label)}</th>${series.map(item=>`<td>${esc(item.values[index]??0)}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
  function chart(model,type='bar'){
    if(model.empty)return '<div class="empty-state compact">没有可聚合的数据</div>';
    const categories=model.categories||[],series=model.series||[],values=series.flatMap(item=>item.values||[]),max=Math.max(1,...values.map(Number));let visual='';
    if(type==='pie'){const total=values.reduce((sum,value)=>sum+Number(value),0)||1;let offset=0;visual=`<div class="pie-chart" role="img" aria-label="饼图">${categories.map((label,index)=>{const value=Number(series[0]?.values[index]||0),start=offset;offset+=value/total*100;return `<i style="--start:${start};--end:${offset}" title="${esc(label)} ${value}"></i>`}).join('')}</div>`}
    else if(type==='line'){visual=`<svg class="line-chart" viewBox="0 0 600 220" role="img" aria-label="折线图">${series.map((item,sindex)=>`<polyline class="series-${sindex}" points="${item.values.map((value,index)=>`${20+index*(560/Math.max(1,categories.length-1))},${200-Number(value)/max*170}`).join(' ')}"/>`).join('')}</svg>`}
    else visual=`<div class="bar-chart ${type==='stacked_bar'?'stacked':''}" role="img" aria-label="${type==='stacked_bar'?'堆叠':''}柱状图">${categories.map((label,index)=>`<div class="bar-group"><div>${series.map((item,sindex)=>`<i class="series-${sindex}" style="height:${Math.max(2,Number(item.values[index]||0)/max*170)}px" title="${esc(item.name)} ${esc(item.values[index]||0)}"></i>`).join('')}</div><small>${esc(label)}</small></div>`).join('')}</div>`;
    return `<div class="chart-visual">${visual}</div><div class="chart-legend">${series.map((item,index)=>`<span class="series-${index}">● ${esc(item.name)}</span>`).join('')}</div>${table(model)}`
  }
  return{clamp,collides,place,table,chart};
});
