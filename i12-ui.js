(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.FlowboardI12=api})(typeof window!=='undefined'?window:globalThis,function(){
  function shouldRefresh(events,userId){return (events||[]).some(event=>!event.actor_user_id||event.actor_user_id!==userId)}
  return {shouldRefresh}
});
