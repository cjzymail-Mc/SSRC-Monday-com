import unittest
import test_overview_e2e as overview_harness
from flowboard.timeline import TimelineService
from playwright.sync_api import Error as PlaywrightError
from flowboard.database import connect


class OverviewUXE2E(unittest.TestCase):
    setUpClass=classmethod(overview_harness.OverviewE2E.setUpClass.__func__)
    tearDownClass=classmethod(overview_harness.OverviewE2E.tearDownClass.__func__)
    setUp=overview_harness.OverviewE2E.setUp
    tearDown=overview_harness.OverviewE2E.tearDown
    login=overview_harness.OverviewE2E.login
    assert_clean_browser=overview_harness.OverviewE2E.assert_clean_browser
    seed=overview_harness.OverviewE2E.seed
    open_overview=overview_harness.OverviewE2E.open_overview
    select=overview_harness.OverviewE2E.select

    def ready(self,page):page.locator('[data-timeline-page="overview"][aria-busy="false"]').wait_for()

    def focus(self,page,key):
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and f'focus={key}' in r.url and r.status==200):
            page.locator(f'[data-overview-focus="{key}"]').click()
        self.ready(page)

    def test_menu_five_modules_and_focus_progress_never_resets_to_zero(self):
        ids=self.seed();context,page=self.login('u1');self.open_overview(page)
        self.assertEqual(page.locator('.main-nav > button:not([hidden]) .nav-label').all_inner_texts(),['我的工作','项目概览','时间画布','标签','已归档'])
        self.assertFalse(page.locator('#timelineCanvasNav').is_visible())
        self.assertEqual(page.locator('.ov-tabs').count(),0)
        self.assertEqual(page.locator('.ov-table').first.locator('thead th').all_inner_texts(),['项目','关注状态','当前阶段','下一未完成节点','项目进度'])
        self.assertEqual(page.locator('.ov-project').count(),6)
        risk=page.locator(f'[data-overview-project="{ids["risk"]}"]')
        self.assertEqual(risk.locator('[role=progressbar]').get_attribute('aria-valuenow'),'20')
        for key,projects,nodes in [('attention',1,3),('overdue',1,1),('today',1,2),('done',3,3),('all',6,10)]:
            self.focus(page,key)
            self.assertIn(f'{projects} 个项目 · {nodes} 个节点',page.locator('.ov-result').inner_text())
            self.assertEqual(risk.locator('[role=progressbar]').get_attribute('aria-valuenow'),'20')
        self.assert_clean_browser(page);context.close()

    def test_early_overview_navigation_receives_late_tag_catalog(self):
        ids=self.seed();service=TimelineService(self.db_path);user={'id':'u1'}
        tag=service.create_tag(user,1,{'name':'竞速类'})
        service.set_tag_project(user,1,tag['tag_id'],ids['risk'],{'base_tag_version':tag['version']},included=True)
        pending=[];context=self.browser.new_context();page=context.new_page()
        page.route('**/timeline/tags',lambda route:pending.append(route))
        page.goto(self.base);page.locator('#loginUser').fill('u1');page.locator('#loginPassword').fill('test-password');page.locator('#loginForm button[type=submit]').click()
        page.locator('#loadState',has_text='刚刚同步').wait_for();self.open_overview(page)
        page.locator('[data-overview-advanced][aria-controls]').click()
        self.assertEqual(len(pending),1)
        pending[0].fulfill(response=pending[0].fetch())
        page.locator('[data-overview-filter=tag_id] option',has_text='竞速类').wait_for(state='attached')
        self.select(page,'tag_id',str(tag['tag_id']))
        self.assertEqual(page.locator('.ov-project').count(),1)
        self.assertEqual(page.locator('.ov-project').get_attribute('data-overview-project'),str(ids['risk']))
        context.close()

    def test_browser_reload_cancel_keeps_unsaved_editor_draft(self):
        ids=self.seed();context,page=self.login('u1');self.open_overview(page)
        page.locator(f'[data-overview-expand="{ids["risk"]}"]').click()
        page.locator(f'#ov-detail-{ids["risk"]} [data-timeline-open=editor]').click()
        page.locator('[data-timeline-page=editor]').wait_for()
        field=page.locator(f'[data-editor-field=remark][data-node-id="{ids["today_node"]}"]')
        original=field.input_value();field.fill('取消刷新后保留的草稿');field.press('Tab')
        dialogs=[]
        def cancel(dialog):dialogs.append(dialog.type);dialog.dismiss()
        page.once('dialog',cancel)
        try:page.reload(timeout=1500)
        except PlaywrightError:
            # Chromium may keep waiting for load after a dismissed beforeunload.
            # Cancellation is proven by the dialog, unchanged editor and database below.
            self.assertEqual(dialogs,['beforeunload'])
        self.assertEqual(dialogs,['beforeunload'])
        self.assertTrue(page.locator('[data-timeline-page=editor]').is_visible())
        self.assertEqual(field.input_value(),'取消刷新后保留的草稿')
        conn=connect(self.db_path)
        self.assertEqual(conn.execute('SELECT remark FROM timeline_nodes WHERE id=?',(ids['today_node'],)).fetchone()[0],original)
        conn.close();context.close()

    def test_account_preferences_refresh_and_clear_without_persisting_search(self):
        self.seed();context,page=self.login('u1');self.open_overview(page)
        self.select(page,'scope','mine');self.focus(page,'overdue');self.select(page,'stage','创意');self.select(page,'track','main')
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and 'q=' in r.url and r.status==200):
            page.locator('[data-overview-search]').fill('鞋面材料')
        self.ready(page);page.reload();self.ready(page)
        self.assertEqual(page.locator('[data-overview-search]').input_value(),'')
        self.assertEqual(page.locator('[data-overview-scope=mine]').get_attribute('aria-pressed'),'true')
        self.assertEqual(page.locator('[data-overview-focus=overdue]').get_attribute('aria-pressed'),'true')
        self.assertIn('创意',page.locator('.ov-result').inner_text());self.assertIn('主线',page.locator('.ov-result').inner_text())
        self.assertTrue(page.locator('#timelineOverviewBtn').evaluate('el=>el.classList.contains("active")'))
        page.locator('[data-overview-reset]').first.click();self.ready(page)
        self.assertEqual(page.locator('.ov-project').count(),6)
        # Save a restrictive state again, then verify another account starts clean.
        self.select(page,'scope','mine');self.focus(page,'overdue')
        page.locator('#logoutBtn').click();page.locator('#loginUser').fill('u2');page.locator('#loginPassword').fill('test-password');page.locator('#loginForm button[type=submit]').click()
        page.locator('[data-timeline-page="home"]').wait_for();self.open_overview(page)
        self.assertEqual(page.locator('[data-overview-scope=all]').get_attribute('aria-pressed'),'true')
        self.assertEqual(page.locator('[data-overview-focus=all]').get_attribute('aria-pressed'),'true')
        self.assertEqual(page.locator('.ov-project').count(),6)
        self.assert_clean_browser(page);context.close()

    def test_canvas_ranges_workbench_team_tab_and_archive_return(self):
        ids=self.seed();context,page=self.login('u1')
        self.assertEqual(page.locator('.tl-home-actions [data-timeline-mode-target=overview]').count(),0)
        page.locator('#timelineAllBtn').click();page.locator('#timelineCanvasNav').wait_for()
        for key,mode in [('timelineWeekBtn','week'),('timelineMonthBtn','month')]:
            page.locator('#'+key).click();page.locator(f'[data-timeline-page="{mode}"]').wait_for()
            self.assertEqual(page.locator('#'+key).get_attribute('aria-pressed'),'true')
            self.assertTrue(page.locator('#timelineAllBtn').evaluate('el=>el.classList.contains("active")'))
        page.locator('#timelineBtn').click();page.locator('[data-timeline-page=home]').wait_for()
        page.locator('#timelineAllBtn').click();page.locator('[data-timeline-page=month]').wait_for()
        page.locator('#timelineCanvasAllBtn').click();page.locator('[data-timeline-page=all]').wait_for()
        page.reload();page.locator('[data-timeline-page="all"]').wait_for()
        page.locator('#timelineBtn').click();page.locator('[data-timeline-tab=team]').click()
        page.locator(f'[data-timeline-member-open="{ids["team"]}"]').click();page.locator('[data-timeline-page=single]').wait_for()
        page.locator('[data-timeline-mode-target=home]').click();page.locator('[data-timeline-section=team]').wait_for()
        self.assertEqual(page.locator('[data-timeline-tab=team]').get_attribute('class'),'on')
        page.locator('#archivedBtn').click();page.locator('[data-timeline-page=archived]').wait_for()
        page.locator(f'[data-timeline-open=single][data-project-id="{ids["archived"]}"]').click();page.locator('[data-timeline-page=single]').wait_for()
        self.assertIn('返回已归档',page.locator('[data-timeline-mode-target=archived]').inner_text())
        page.locator('[data-timeline-mode-target=archived]').click();page.locator('[data-timeline-page=archived]').wait_for()
        self.assert_clean_browser(page);context.close()

    def test_advanced_search_object_and_keyboard_horizontal_access(self):
        ids=self.seed(long_list=True);context,page=self.login('u1');page.set_viewport_size({'width':760,'height':850});self.open_overview(page)
        self.select(page,'search_in','project')
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and r.status==200):
            page.locator('[data-overview-search]').fill('鞋面材料')
        self.ready(page);self.assertEqual(page.locator('.ov-project').count(),0)
        self.select(page,'search_in','node');self.assertEqual(page.locator('.ov-project').count(),1)
        self.assertEqual(page.locator('[data-overview-filter=search_in]').evaluate('el=>document.activeElement===el'),True)
        page.locator('[data-overview-reset]').first.click();self.ready(page)
        scroller=page.locator('.ov-table-scroll').first;scroller.focus();scroller.press('ArrowRight')
        self.assertGreater(scroller.evaluate('el=>el.scrollLeft'),0)
        self.assertEqual(scroller.evaluate('el=>getComputedStyle(el).scrollbarWidth'),'none')
        page.locator('#sidebarToggle').click()
        self.assertTrue(page.locator('#appSidebar').evaluate('el=>el.classList.contains("is-collapsed")'))
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),762)
        page.locator(f'[data-overview-expand="{ids["long"]}"]').click()
        self.assertIn('复杂工艺说明与材料沟通记录',page.locator(f'#ov-detail-{ids["long"]}').inner_text())
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),762)
        self.assert_clean_browser(page);context.close()


if __name__=='__main__':unittest.main()
