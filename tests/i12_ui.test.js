const test=require('node:test');const assert=require('node:assert/strict');const {shouldRefresh,shouldFallbackPoll}=require('../i12-ui.js');
test('realtime self echo advances without refresh while remote/system/mixed refresh',()=>{
  assert.equal(shouldRefresh([{actor_user_id:'u1'}],'u1'),false);
  assert.equal(shouldRefresh([{actor_user_id:'u2'}],'u1'),true);
  assert.equal(shouldRefresh([{actor_user_id:'u1'},{actor_user_id:'u2'}],'u1'),true);
  assert.equal(shouldRefresh([{actor_user_id:null}],'u1'),true);
});
test('full polling only runs while realtime is unavailable',()=>{
  assert.equal(shouldFallbackPoll(true),false);
  assert.equal(shouldFallbackPoll(false),true);
});
