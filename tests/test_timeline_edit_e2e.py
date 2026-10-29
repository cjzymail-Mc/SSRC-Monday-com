import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import test_timeline_e2e as harness
from flowboard.database import connect


class SharedTimelineEditE2E(unittest.TestCase):
    setUpClass = classmethod(harness.TimelineProductionE2E.setUpClass.__func__)
    tearDownClass = classmethod(harness.TimelineProductionE2E.tearDownClass.__func__)
    setUp = harness.TimelineProductionE2E.setUp
    tearDown = harness.TimelineProductionE2E.tearDown
    login = harness.TimelineProductionE2E.login

    def seed(self, name='共用编辑测试', dates=None):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        dates = dates or [today - timedelta(days=1), today]
        db = connect(self.db_path)
        stamp = '2026-10-29T00:00:00+00:00'
        pid = db.execute('INSERT INTO timeline_projects(workspace_id,name,created_by,created_at,updated_at) VALUES (1,?,?,?,?)', (name, 'u1', stamp, stamp)).lastrowid
        ids = []
        for i, date in enumerate(dates):
            ids.append(db.execute('INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)', (pid, 'main' if i == 0 else 'parallel', '设计', f'节点{i+1}', date.isoformat(), date.isoformat(), f'原备注{i+1}', stamp, stamp)).lastrowid)
        db.commit(); db.close()
        return pid, ids

    def row(self, nid):
        db=connect(self.db_path)
        try:return dict(db.execute('SELECT * FROM timeline_nodes WHERE id=?',(nid,)).fetchone())
        finally:db.close()

    def concurrent(self, pid, nid):
        db=connect(self.db_path)
        db.execute('UPDATE timeline_projects SET version=version+1 WHERE id=?',(pid,))
        db.execute("UPDATE timeline_nodes SET remark='其他人的备注' WHERE id=?",(nid,))
        db.commit();db.close()

    def open(self, page, scope, pid):
        if scope in ('single','editor'):
            page.locator('#timelineBtn').click()
            page.locator(f'[data-timeline-open="{scope}"][data-project-id="{pid}"]').click()
        else:
            page.locator({'all':'#timelineAllBtn','week':'#timelineWeekBtn','month':'#timelineMonthBtn','overview':'#timelineOverviewBtn'}[scope]).click()
            if scope=='overview':
                page.locator('[data-timeline-page="overview"][aria-busy="false"]').wait_for()
                page.locator(f'[data-overview-expand="{pid}"]').click()
        page.locator(f'[data-timeline-page="{scope}"]').wait_for()

    def action(self, page, nid, action):
        page.locator(f'.timeline-dashboard-node[data-node-id="{nid}"]').click(button='right')
        page.locator(f'[data-draft-action="{action}"]').click()

    def evidence(self, page, name):
        path=Path(__file__).resolve().parents[1]/'team-progress/verification/20261029-shared-edit'
        path.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(path/f'{name}.png'),full_page=True)

    def buttons_in_view(self,page):
        page.wait_for_function("""() => [...document.querySelectorAll('[data-dashboard-pending] button')].every(b=>{const r=b.getBoundingClientRect(),s=b.closest('[data-dashboard-pending]').getBoundingClientRect(),v=b.closest('[data-portfolio-scroll]')?.getBoundingClientRect()||s;return r.top>=s.top&&r.bottom<=s.bottom+1&&r.left>=v.left&&r.right<=v.right+1})""")

    def test_remark_confirm_direct_save_cancel_and_reload_in_all_five_canvases(self):
        pid,ids=self.seed()
        for scope in ('overview','single','all','week','month'):
            with self.subTest(scope=scope):
                context,page=self.login('u1');self.open(page,scope,pid)
                nid=ids[0] if scope=='overview' else ids[1]
                node=page.locator(f'.timeline-dashboard-node[data-node-id="{nid}"]')
                old=self.row(nid)['remark'];node.dblclick()
                popup=page.locator('[data-dashboard-remark]');editor=popup.locator('textarea')
                editor.fill('取消输入');popup.locator('[data-remark-cancel]').click()
                self.assertEqual(self.row(nid)['remark'],old)
                node.dblclick();editor.fill(f'{scope}已保存')
                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:
                    popup.locator('[data-remark-save]').click()
                self.assertEqual(response.value.status,200)
                page.locator('#toast',has_text='备注已保存').wait_for()
                self.assertEqual(self.row(nid)['remark'],f'{scope}已保存')
                self.assertEqual(page.locator('[data-dashboard-pending]').count(),0)
                page.reload();page.locator('#loadState',has_text='刚刚同步').wait_for()
                self.assertEqual(self.row(nid)['remark'],f'{scope}已保存')
                self.assertEqual(page.flowboard_page_errors,[])
                context.close()

    def test_week_month_last_node_pending_stays_blocked_until_discard_or_update(self):
        today=datetime.now(timezone(timedelta(hours=8))).date()
        for scope in ('week','month'):
            for action in ('done','remove'):
                with self.subTest(scope=scope,action=action):
                    pid,ids=self.seed(f'{scope}-{action}',[today]);nid=ids[0]
                    context,page=self.login('u1');self.open(page,scope,pid)
                    self.action(page,nid,action)
                    overlay=page.locator(f'[data-dashboard-pending="{pid}"]');overlay.wait_for()
                    self.assertTrue(page.locator(f'[data-dashboard-project="{pid}"]').is_visible())
                    self.assertEqual(page.locator(f'[data-dashboard-project="{pid}"] .timeline-stage-lanes[inert]').count(),1)
                    overlay.click(button='right',position={'x':5,'y':5})
                    self.assertTrue(page.locator('[data-timeline-context]').is_hidden())
                    self.assertEqual(overlay.locator('[data-dashboard-submit]').evaluate('e=>getComputedStyle(e).borderTopColor'),'rgb(255, 255, 255)')
                    self.buttons_in_view(page)
                    if scope=='week' and action=='done':self.evidence(page,'weekly-pending-overlay')
                    overlay.locator('[data-dashboard-discard]').click()
                    self.assertEqual(page.locator(f'[data-dashboard-pending="{pid}"]').count(),0)
                    self.assertIsNone(self.row(nid)['done_at']);self.assertIsNone(self.row(nid)['deleted_at'])
                    self.action(page,nid,action)
                    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:
                        page.locator(f'[data-dashboard-submit="{pid}"]').click()
                    self.assertEqual(response.value.status,200)
                    field='done_at' if action=='done' else 'deleted_at'
                    self.assertIsNotNone(self.row(nid)[field])
                    self.assertEqual(page.flowboard_page_errors,[]);context.close()

    def test_editor_net_changes_date_validation_leave_and_tab_shared_draft(self):
        pid,ids=self.seed();nid=ids[0];context,page=self.login('u1');self.open(page,'editor',pid)
        remark=page.locator(f'[data-editor-field="remark"][data-node-id="{nid}"]')
        remark.fill('更改');remark.press('Tab');self.assertTrue(page.locator('[data-timeline-submit]').is_enabled())
        remark.fill('原备注1');remark.press('Tab');self.assertTrue(page.locator('[data-timeline-submit]').is_disabled())
        self.assertNotIn('is-draft',page.locator(f'[data-editor-row="{nid}"]').get_attribute('class'))
        date=page.locator(f'[data-editor-field="date"][data-node-id="{nid}"]');original=date.input_value()
        date.fill('');date.press('Tab');self.assertEqual(date.get_attribute('aria-invalid'),'true')
        self.assertTrue(page.locator('[data-timeline-submit]').is_disabled());date.fill(original);date.press('Tab')
        remark.fill('跨页保留');remark.press('Tab');page.locator('[data-timeline-mode-target="single"]').click()
        page.locator(f'[data-dashboard-pending="{pid}"]').wait_for()
        page.locator('[data-timeline-mode-target="editor"]').click()
        self.assertEqual(remark.input_value(),'跨页保留')
        page.once('dialog',lambda d:d.dismiss());page.locator('#timelineAllBtn').click()
        self.assertEqual(page.locator('[data-timeline-page="editor"]').count(),1)
        page.once('dialog',lambda d:d.accept());page.locator('#timelineAllBtn').click()
        page.locator('[data-timeline-page="all"]').wait_for()
        self.assertEqual(page.locator('[data-dashboard-pending]').count(),0)
        self.assertEqual(self.row(nid)['remark'],'原备注1');context.close()

    def test_editor_500_retry_duplicate_click_and_inflight_lock(self):
        pid,ids=self.seed();context,page=self.login('u1');self.open(page,'editor',pid)
        remark=page.locator(f'[data-editor-field="remark"][data-node-id="{ids[0]}"]')
        remark.fill('失败后重试');remark.press('Tab');pending=[]
        def hold(route):
            if route.request.method=='POST':pending.append(route)
            else:route.continue_()
        page.route('**/timeline/batches',hold)
        page.locator('[data-timeline-submit]').click()
        page.wait_for_function("document.querySelector('[data-timeline-submit]').disabled")
        page.locator('[data-timeline-submit]').dispatch_event('click')
        self.assertEqual(len(pending),1)
        page.locator('#timelineAllBtn').click();page.locator('#toast',has_text='正在保存').wait_for()
        pending[0].fulfill(status=500,content_type='application/json',body=json.dumps({'error':{'code':'TEST_FAILURE','message':'测试保存失败'}}))
        page.wait_for_function("!document.querySelector('[data-timeline-submit]').disabled")
        self.assertEqual(remark.input_value(),'失败后重试')
        page.unroute('**/timeline/batches',hold)
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-timeline-submit]').click()
        self.assertEqual(response.value.status,200);self.assertEqual(self.row(ids[0])['remark'],'失败后重试');context.close()

    def test_conflict_retains_inputs_requires_confirmation_and_preserves_other_node(self):
        for scope in ('editor','single'):
            with self.subTest(scope=scope):
                pid,ids=self.seed('冲突-'+scope);context,page=self.login('u1');self.open(page,scope,pid)
                if scope=='editor':
                    field=page.locator(f'[data-editor-field="name"][data-node-id="{ids[0]}"]');field.fill('本地节点名');field.press('Tab')
                else:self.action(page,ids[0],'done')
                self.concurrent(pid,ids[1]);selector='[data-timeline-submit]' if scope=='editor' else f'[data-dashboard-submit="{pid}"]'
                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator(selector).click()
                self.assertEqual(response.value.status,409)
                page.locator('.timeline-draft-conflict').wait_for()
                self.buttons_in_view(page)
                if scope=='editor':self.assertEqual(field.input_value(),'本地节点名')
                if scope=='single':self.evidence(page,'single-conflict-preserves-draft')
                page.once('dialog',lambda d:d.dismiss());page.locator(selector).click()
                self.assertTrue(page.locator('.timeline-draft-conflict').is_visible())
                page.once('dialog',lambda d:d.accept())
                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator(selector).click()
                self.assertEqual(response.value.status,200)
                self.assertEqual(response.value.request.post_data_json['requests'][0]['base_version'],2)
                self.assertEqual(self.row(ids[1])['remark'],'其他人的备注')
                if scope=='editor':self.assertEqual(self.row(ids[0])['name'],'本地节点名')
                else:self.assertIsNotNone(self.row(ids[0])['done_at'])
                self.assertEqual(page.flowboard_page_errors,[]);context.close()

    def test_remark_failed_save_and_conflict_preserve_text_for_explicit_retry(self):
        pid,ids=self.seed();context,page=self.login('u1');self.open(page,'single',pid)
        node=page.locator(f'.timeline-dashboard-node[data-node-id="{ids[0]}"]');node.dblclick()
        editor=page.locator('[data-remark-form] textarea');editor.fill('需保留的输入')
        def fail(route):route.fulfill(status=500,content_type='application/json',body=json.dumps({'error':{'code':'TEST_FAILURE','message':'测试保存失败'}}))
        page.route('**/timeline/batches',fail);page.locator('[data-remark-save]').click()
        page.locator('[data-remark-save-error]').wait_for();self.assertEqual(editor.input_value(),'需保留的输入')
        page.unroute('**/timeline/batches',fail);self.concurrent(pid,ids[1])
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-remark-save]').click()
        self.assertEqual(response.value.status,409);self.assertEqual(editor.input_value(),'需保留的输入')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-remark-save]').click()
        self.assertEqual(response.value.status,200);self.assertEqual(self.row(ids[0])['remark'],'需保留的输入');self.assertEqual(self.row(ids[1])['remark'],'其他人的备注')
        self.assertEqual(page.locator('[data-dashboard-pending]').count(),0);context.close()

    def test_real_drag_zoomed_overlay_is_visible_and_save_roundtrips(self):
        pid,ids=self.seed();nid=ids[0];context,page=self.login('u1');self.open(page,'single',pid)
        initial=float(page.locator('.timeline-portfolio-chart').get_attribute('data-viewport-days'))
        plot_box=page.locator('.timeline-stage-plot').first.bounding_box()
        page.mouse.move(plot_box['x']+plot_box['width']/2,plot_box['y']+plot_box['height']-5);page.mouse.wheel(0,-500)
        page.wait_for_function("before=>Number(document.querySelector('.timeline-portfolio-chart').dataset.viewportDays)<before",arg=initial)
        old=self.row(nid)['date'];node=page.locator(f'.timeline-dashboard-node[data-node-id="{nid}"]')
        self.action(page,nid,'single');r=node.bounding_box()
        chart=page.locator('.timeline-portfolio-chart');plot=node.locator('xpath=..').bounding_box()
        span=(datetime.fromisoformat(chart.get_attribute('data-calendar-end'))-datetime.fromisoformat(chart.get_attribute('data-calendar-start'))).days
        x,y=r['x']+r['width']/2,r['y']+r['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+plot['width']/span*2,y,steps=12);page.mouse.up()
        page.locator('[data-dashboard-pending]').wait_for();self.buttons_in_view(page)
        self.assertEqual(self.row(nid)['date'],old);self.evidence(page,'zoomed-drag-pending-overlay')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-dashboard-submit]').click()
        self.assertEqual(response.value.status,200)
        self.assertEqual(self.row(nid)['date'],(datetime.fromisoformat(old)+timedelta(days=2)).date().isoformat());context.close()

    def test_other_project_remark_can_save_while_one_project_has_pending_changes(self):
        pid,ids=self.seed('草稿项目');other,other_ids=self.seed('其他项目')
        context,page=self.login('u1');self.open(page,'all',pid);self.action(page,ids[0],'done')
        node=page.locator(f'.timeline-dashboard-node[data-node-id="{other_ids[0]}"]');node.dblclick()
        page.locator('[data-remark-form] textarea').fill('独立保存')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-remark-save]').click()
        self.assertEqual(response.value.status,200);self.assertEqual(self.row(other_ids[0])['remark'],'独立保存')
        self.assertTrue(page.locator(f'[data-dashboard-pending="{pid}"]').is_visible());self.assertIsNone(self.row(ids[0])['done_at']);context.close()


    def quick_insert(self,page,pid,name):
        plot=page.locator(f'[data-dashboard-project="{pid}"] .timeline-stage-plot').first
        plot.wait_for(state='visible');box=plot.bounding_box()
        plot.click(button='right',position={'x':box['width']*.65,'y':box['height']-5})
        page.locator('[data-dashboard-insert-action]').click()
        popup=page.locator('[data-dashboard-node-editor]');popup.wait_for(state='visible')
        popup.locator('input[name="name"]').fill(name)
        return popup

    def named_nodes(self,pid,name):
        db=connect(self.db_path)
        try:return [dict(row) for row in db.execute('SELECT * FROM timeline_nodes WHERE project_id=? AND name=? AND deleted_at IS NULL',(pid,name)).fetchall()]
        finally:db.close()

    def test_quick_insert_saves_at_checkmark_and_delete_stays_pending_in_five_canvases(self):
        pid,ids=self.seed('插入五入口')
        for scope in ('overview','single','all','week','month'):
            with self.subTest(scope=scope):
                context,page=self.login('u1');self.open(page,scope,pid)
                name='直接插入-'+scope;popup=self.quick_insert(page,pid,name)
                self.assertEqual(self.named_nodes(pid,name),[])
                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:popup.locator('button[type="submit"]').click()
                self.assertEqual(response.value.status,200);popup.wait_for(state='hidden')
                request=response.value.request.post_data_json['requests'][0]
                self.assertEqual(len(request['changes']),1);self.assertEqual(request['changes'][0]['create']['name'],name)
                rows=self.named_nodes(pid,name);self.assertEqual(len(rows),1);self.assertGreater(rows[0]['id'],0)
                self.assertEqual(page.locator('[data-dashboard-pending]').count(),0)
                self.action(page,ids[0],'remove');page.locator(f'[data-dashboard-pending="{pid}"]').wait_for()
                self.assertIsNone(self.row(ids[0])['deleted_at']);page.locator(f'[data-dashboard-discard="{pid}"]').click()
                self.assertIsNone(self.row(ids[0])['deleted_at'])
                page.reload();page.locator('#loadState',has_text='刚刚同步').wait_for()
                self.assertEqual(len(self.named_nodes(pid,name)),1);self.assertEqual(page.flowboard_page_errors,[]);context.close()

    def test_quick_insert_failure_conflict_retry_and_duplicate_guard(self):
        pid,ids=self.seed('插入重试');context,page=self.login('u1');self.open(page,'single',pid)
        name='插入输入保留';popup=self.quick_insert(page,pid,name);input=popup.locator('input[name="name"]');submit=popup.locator('button[type="submit"]');pending=[]
        def hold(route):pending.append(route)
        page.route('**/timeline/batches',hold);submit.click()
        page.wait_for_function("document.querySelector('[data-dashboard-node-editor-form] button[type=submit]').disabled")
        submit.dispatch_event('click');popup.locator('[data-dashboard-node-editor-cancel]').first.dispatch_event('click')
        self.assertEqual(len(pending),1);self.assertTrue(popup.is_visible());self.assertEqual(self.named_nodes(pid,name),[])
        page.locator('#timelineAllBtn').click();page.locator('#toast',has_text='正在保存').wait_for()
        pending[0].fulfill(status=500,content_type='application/json',body=json.dumps({'error':{'code':'TEST_FAILURE','message':'插入保存失败'}}))
        popup.locator('[data-insert-save-error]').wait_for();self.assertEqual(input.input_value(),name);self.assertTrue(submit.is_enabled())
        error_box=popup.locator('[data-insert-save-error]').bounding_box();input_box=input.bounding_box()
        self.assertGreaterEqual(error_box['y'],input_box['y']+input_box['height']-1)
        path=Path(__file__).resolve().parents[1]/'team-progress/verification/20261029-insert-flags'
        path.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(path/'insert-failure-retains-input.png'),full_page=True)
        page.unroute('**/timeline/batches',hold);self.concurrent(pid,ids[1])
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:submit.click()
        self.assertEqual(response.value.status,409);self.assertEqual(input.input_value(),name);self.assertEqual(self.named_nodes(pid,name),[])
        self.assertIn('再次点击确认',popup.locator('[data-insert-save-error]').inner_text())
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:submit.click()
        self.assertEqual(response.value.status,200);self.assertEqual(response.value.request.post_data_json['requests'][0]['base_version'],2)
        popup.wait_for(state='hidden');self.assertEqual(len(self.named_nodes(pid,name)),1);self.assertEqual(self.row(ids[1])['remark'],'其他人的备注')
        self.assertEqual(page.locator('[data-dashboard-pending]').count(),0);self.assertEqual(page.flowboard_page_errors,[]);context.close()

    def test_quick_insert_other_project_keeps_existing_draft_and_same_project_stays_blocked(self):
        pid,ids=self.seed('仍需更新的项目');other,other_ids=self.seed('插入目标项目')
        context,page=self.login('u1');self.open(page,'all',pid);self.action(page,ids[0],'remove')
        overlay=page.locator(f'[data-dashboard-pending="{pid}"]');overlay.wait_for()
        overlay.click(button='right',position={'x':5,'y':5});self.assertTrue(page.locator('[data-dashboard-insert-menu]').is_hidden())
        popup=self.quick_insert(page,other,'只保存目标插入')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:popup.locator('button[type="submit"]').click()
        self.assertEqual(response.value.status,200);popup.wait_for(state='hidden')
        self.assertEqual(response.value.request.post_data_json['requests'][0]['project_id'],other)
        self.assertEqual(len(self.named_nodes(other,'只保存目标插入')),1);self.assertTrue(overlay.is_visible());self.assertIsNone(self.row(ids[0])['deleted_at']);self.assertEqual(page.flowboard_page_errors,[]);context.close()


    def test_overdue_flag_review_matrix_reuses_drag_style_and_keeps_other_flags_masked(self):
        from PIL import Image
        today=datetime.now(timezone(timedelta(hours=8))).date()
        pid,ids=self.seed('旗标范围与蒙版',[today-timedelta(days=3),today-timedelta(days=2),today,today+timedelta(days=1),today+timedelta(days=2)])
        db=connect(self.db_path)
        db.execute("UPDATE timeline_nodes SET track='main' WHERE id IN (?,?)",(ids[1],ids[2]))
        db.execute("UPDATE timeline_nodes SET done_at='2026-10-29T00:00:00Z' WHERE id IN (?,?)",(ids[1],ids[4]))
        db.commit();db.close()
        context,page=self.login('u1');self.open(page,'single',pid);page.set_default_timeout(5000);page.mouse.move(10,10)
        flags=page.locator('.timeline-node-flag');flags.first.wait_for(state='visible')
        def style(nid):
            return page.locator(f'.timeline-node-flag[data-node-id="{nid}"]').evaluate("e=>{const s=getComputedStyle(e);return {classes:e.className,left:s.borderLeftColor,top:s.borderTopColor,fill:s.backgroundColor,shadow:s.boxShadow,filter:s.filter,z:Number(s.zIndex)}}")
        baseline={nid:style(nid) for nid in ids};mask_z=page.locator('.timeline-past-mask').first.evaluate('e=>Number(getComputedStyle(e).zIndex)')
        self.assertEqual(page.locator('.timeline-node-flag.is-overdue').count(),1)
        self.assertIn('is-overdue',baseline[ids[0]]['classes']);self.assertGreater(baseline[ids[0]]['z'],mask_z)
        for nid in ids[1:]:
            self.assertNotIn('is-overdue',baseline[nid]['classes']);self.assertLess(baseline[nid]['z'],mask_z)
            self.assertEqual(baseline[nid]['left'],'rgb(139, 150, 168)');self.assertEqual(baseline[nid]['fill'],'rgba(255, 255, 255, 0.97)')
        path=Path(__file__).resolve().parents[1]/'team-progress/verification/20261029-flag-review';path.mkdir(parents=True,exist_ok=True)
        shot=path/'overdue-only-normal.png';page.screenshot(path=str(shot),full_page=True)
        r=page.locator(f'.timeline-node-flag[data-node-id="{ids[0]}"]').bounding_box();image=Image.open(shot).convert('RGB')
        crop=image.crop((int(r['x']),int(r['y']),int(r['x']+r['width']),int(r['y']+r['height'])))
        self.assertGreater(sum(1 for red,green,blue in crop.getdata() if red>160 and green<130 and blue<150),15)
        hover_box=page.locator(f'.timeline-node-flag[data-node-id="{ids[1]}"]').bounding_box();page.mouse.move(hover_box['x']+hover_box['width']/2,hover_box['y']+hover_box['height']/2)
        self.assertLess(style(ids[1])['z'],mask_z);self.assertEqual(style(ids[1])['left'],'rgb(139, 150, 168)')
        self.action(page,ids[3],'single')
        page.wait_for_function("args=>getComputedStyle(document.querySelector(`.timeline-node-flag[data-node-id=\"${args.id}\"]`)).boxShadow===args.shadow",arg={'id':ids[3],'shadow':baseline[ids[0]]['shadow']})
        drag=style(ids[3])
        for key in ['left','shadow','filter']:self.assertEqual(baseline[ids[0]][key],drag[key],f'overdue reminder must reuse actual drag emphasis: {key}')
        self.assertIn('is-armed',drag['classes']);self.assertNotIn('is-overdue',drag['classes'])
        page.screenshot(path=str(path/'explicit-drag-style-comparison.png'),full_page=True)
        self.assertEqual(page.flowboard_page_errors,[]);context.close()

    def test_related_insert_remark_delete_and_drag_review_with_escape_save_lock(self):
        pid,ids=self.seed('相关交互集中检查');context,page=self.login('u1');self.open(page,'single',pid);page.set_default_timeout(5000)
        page.locator(f'.timeline-dashboard-node[data-node-id="{ids[0]}"]').dblclick()
        page.locator('[data-remark-form] textarea').fill('备注直接保存复核')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-remark-save]').click()
        self.assertEqual(response.value.status,200);self.assertEqual(self.row(ids[0])['remark'],'备注直接保存复核');self.assertEqual(page.locator('[data-dashboard-pending]').count(),0)
        page.locator('[data-dashboard-remark]').wait_for(state='hidden');page.locator('#toast',has_text='备注已保存').wait_for()
        page.locator('[data-portfolio-fullscreen]').click();page.locator('.timeline-portfolio-card.is-fullscreen').wait_for()
        popup=self.quick_insert(page,pid,'新增直接保存复核');pending=[]
        def hold(route):pending.append(route)
        page.route('**/timeline/batches',hold);popup.locator('button[type="submit"]').click()
        page.wait_for_function("document.querySelector('[data-dashboard-node-editor-form] button[type=submit]').disabled")
        page.keyboard.press('Escape');self.assertTrue(popup.is_visible());self.assertTrue(page.locator('.timeline-portfolio-card.is-fullscreen').is_visible());self.assertEqual(len(pending),1)
        pending[0].fulfill(status=500,content_type='application/json',body=json.dumps({'error':{'code':'TEST_FAILURE','message':'定向失败重试'}}))
        popup.locator('[data-insert-save-error]').wait_for();self.assertEqual(popup.locator('input').input_value(),'新增直接保存复核')
        page.unroute('**/timeline/batches',hold)
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:popup.locator('button[type="submit"]').click()
        self.assertEqual(response.value.status,200);popup.wait_for(state='hidden');self.assertEqual(len(self.named_nodes(pid,'新增直接保存复核')),1);self.assertEqual(page.locator('[data-dashboard-pending]').count(),0)
        self.action(page,ids[0],'remove');overlay=page.locator('[data-dashboard-pending]');overlay.wait_for();self.assertIsNone(self.row(ids[0])['deleted_at'])
        overlay.click(position={'x':5,'y':5});self.assertTrue(overlay.is_visible());overlay.locator('[data-dashboard-discard]').click();self.assertIsNone(self.row(ids[0])['deleted_at'])
        self.action(page,ids[0],'remove')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/timeline/batches')) as response:page.locator('[data-dashboard-submit]').click()
        self.assertEqual(response.value.status,200);self.assertIsNotNone(self.row(ids[0])['deleted_at'])
        old_date=self.row(ids[1])['date'];self.action(page,ids[1],'single')
        node=page.locator(f'.timeline-dashboard-node[data-node-id="{ids[1]}"]');box=node.bounding_box();plot=node.locator('xpath=..').bounding_box();chart=page.locator('.timeline-portfolio-chart')
        span=(datetime.fromisoformat(chart.get_attribute('data-calendar-end'))-datetime.fromisoformat(chart.get_attribute('data-calendar-start'))).days
        x,y=box['x']+box['width']/2,box['y']+box['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+plot['width']/span*2,y,steps=8);page.mouse.up()
        page.locator('[data-dashboard-pending]').wait_for();self.assertEqual(self.row(ids[1])['date'],old_date)
        page.locator('[data-dashboard-discard]').click();self.assertEqual(self.row(ids[1])['date'],old_date)
        self.assertEqual(page.flowboard_page_errors,[]);context.close()


if __name__=='__main__':unittest.main()
