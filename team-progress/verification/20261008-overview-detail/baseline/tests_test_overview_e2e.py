import json
import unittest
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import test_timeline_e2e as harness
from overview_fixtures import seed_overview
from flowboard.database import connect

EVIDENCE = Path(__file__).resolve().parents[1] / 'team-progress/verification/20261008-feature02-ux'


class OverviewE2E(unittest.TestCase):
    setUpClass = classmethod(harness.TimelineProductionE2E.setUpClass.__func__)
    tearDownClass = classmethod(harness.TimelineProductionE2E.tearDownClass.__func__)
    setUp = harness.TimelineProductionE2E.setUp
    tearDown = harness.TimelineProductionE2E.tearDown
    login = harness.TimelineProductionE2E.login
    assert_clean_browser = harness.TimelineProductionE2E.assert_clean_browser

    def seed(self, long_list=False):
        return seed_overview(self.db_path, datetime.now(timezone(timedelta(hours=8))).date(), long_list=long_list)

    def open_overview(self, page):
        page.locator('#timelineOverviewBtn').click()
        page.locator('[data-timeline-page="overview"][aria-busy="false"]').wait_for()
        page.locator('.ov-project').first.wait_for()

    def select(self, page, key, value):
        if key not in ('period','scope') and not page.locator('#ov-advanced').is_visible():
            page.locator('[data-overview-advanced][aria-controls]').click()
        if key!='scope':page.locator(f'[data-overview-filter="{key}"]').focus()
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and parse_qs(urlparse(r.url).query).get(key)==[value] and r.status==200):
            if key=='scope':page.locator(f'[data-overview-scope="{value}"]').click()
            else:page.locator(f'[data-overview-filter="{key}"]').select_option(value)
        page.locator('[data-timeline-page="overview"][aria-busy="false"]').wait_for()

    def test_filters_expansion_counts_search_and_real_navigation(self):
        ids=self.seed();context,page=self.login('u1')
        page.set_viewport_size({'width':1600,'height':1000})
        self.open_overview(page)
        self.assertEqual(page.locator('.ov-project').count(),6)
        for secret in ['归档项目机密','删除项目机密','删除节点机密']:
            self.assertNotIn(secret,page.locator('.ov-board').inner_text())
        self.select(page,'completion','all')
        risk=page.locator(f'[data-overview-project="{ids["risk"]}"]')
        self.assertIn('1/5',risk.inner_text())
        self.assertIn('20%',risk.locator('[role="progressbar"]').get_attribute('aria-valuenow')+'%')
        page.locator(f'[data-overview-expand="{ids["risk"]}"]').click()
        self.assertEqual(page.locator(f'#ov-detail-{ids["risk"]} .ov-nodes tbody tr').count(),5)
        self.assertIn('主线',page.locator(f'#ov-detail-{ids["risk"]}').inner_text())
        self.assertIn('并行',page.locator(f'#ov-detail-{ids["risk"]}').inner_text())
        self.select(page,'track','parallel')
        self.assertEqual(page.locator(f'#ov-detail-{ids["risk"]} .ov-nodes tbody tr').count(),1)
        self.select(page,'period','all');self.select(page,'scope','mine');self.select(page,'track','all')
        self.assertNotIn('跃动篮球鞋',page.locator('.ov-board').inner_text())
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and 'q=' in r.url and r.status==200):
            page.locator('[data-overview-search]').fill('材料')
        page.locator('.ov-project').first.wait_for()
        self.assertEqual(page.locator('.ov-project').count(),1)
        self.assertEqual(page.locator('.ov-nodes tbody tr').count(),1)
        page.locator(f'[data-timeline-open="single"][data-project-id="{ids["risk"]}"]').click()
        page.locator('[data-timeline-page="single"]').wait_for()
        self.assertIn('返回项目概览',page.locator('[data-timeline-mode-target="overview"]').inner_text())
        page.locator('[data-timeline-mode-target="overview"]').click()
        page.locator('.ov-project').first.wait_for()
        self.assertEqual(page.locator('[data-overview-search]').input_value(),'材料')
        self.assertEqual(page.locator('[data-overview-scope="mine"]').get_attribute('aria-pressed'),'true')
        self.assertTrue(page.locator(f'#ov-detail-{ids["risk"]}').is_visible())
        self.assert_clean_browser(page);context.close()

    def test_edit_save_return_and_draft_leave_cancel(self):
        ids=self.seed();context,page=self.login('u1');self.open_overview(page)
        page.locator(f'[data-overview-expand="{ids["risk"]}"]').click()
        page.locator(f'#ov-detail-{ids["risk"]} [data-timeline-open="editor"]').click()
        page.locator('[data-timeline-page="editor"]').wait_for()
        remark=page.locator(f'[data-editor-field="remark"][data-node-id="{ids["today_node"]}"]')
        remark.fill('总览返回后可见的实际保存备注');remark.press('Tab')
        page.once('dialog',lambda dialog:dialog.dismiss())
        page.locator('[data-timeline-mode-target="overview"]').click()
        self.assertTrue(page.locator('[data-timeline-page="editor"]').is_visible())
        self.assertEqual(remark.input_value(),'总览返回后可见的实际保存备注')
        with page.expect_response(lambda r:'/timeline/batches' in r.url and r.status==200):
            page.locator('[data-timeline-submit]').click()
        page.locator('[data-timeline-mode-target="overview"]').click()
        page.locator('.ov-project').first.wait_for()
        self.assertIn('总览返回后可见的实际保存备注',page.locator(f'#ov-detail-{ids["risk"]}').inner_text())
        conn=connect(self.db_path)
        self.assertEqual(conn.execute('SELECT remark FROM timeline_nodes WHERE id=?',(ids['today_node'],)).fetchone()[0],'总览返回后可见的实际保存备注')
        self.assertGreater(conn.execute('SELECT count(*) FROM timeline_node_changes').fetchone()[0],0)
        conn.close();self.assert_clean_browser(page);context.close()

    def test_member_readonly_and_logout_resets_overview_state(self):
        ids=self.seed();context,page=self.login('u2');self.open_overview(page)
        page.locator(f'[data-overview-expand="{ids["risk"]}"]').click()
        button=page.locator(f'#ov-detail-{ids["risk"]} [data-timeline-open="editor"]')
        self.assertIn('只读',button.inner_text());button.click()
        page.locator('[data-timeline-page="editor"]').wait_for()
        self.assertEqual(page.locator('[data-timeline-submit]').count(),0)
        self.assertTrue(page.locator('[data-editor-field="remark"]').first.is_disabled())
        page.locator('[data-timeline-mode-target="overview"]').click()
        page.locator('.ov-project').first.wait_for()
        self.select(page,'scope','mine')
        self.assertEqual(page.locator('.ov-project').count(),2)
        page.locator('#logoutBtn').click()
        page.locator('#loginUser').fill('u1');page.locator('#loginPassword').fill('test-password')
        page.locator('#loginForm button[type=submit]').click()
        page.locator('[data-timeline-page="home"]').wait_for()
        self.open_overview(page)
        self.assertEqual(page.locator('[data-overview-scope="mine"]').get_attribute('aria-pressed'),'false')
        self.assertEqual(page.locator('.ov-detail').count(),0)
        self.assert_clean_browser(page);context.close()

    def test_loading_error_retry_empty_and_response_order(self):
        self.seed();context,page=self.login('u1')
        pending=[]
        page.route('**/timeline/overview?*',lambda route:pending.append(route))
        page.locator('#timelineOverviewBtn').click()
        page.locator('.ov-message',has_text='正在加载').wait_for()
        page.wait_for_function('document.querySelector("[data-overview-filter=period]") !== null')
        pending[0].fulfill(status=500,content_type='application/json',body=json.dumps({'error':{'message':'隔离网络故障'}}))
        page.locator('.ov-message',has_text='加载失败').wait_for()
        self.assertIn('隔离网络故障',page.locator('.ov-message').inner_text())
        page.unroute('**/timeline/overview?*')
        page.locator('.ov-message [data-overview-reload]').click()
        page.locator('.ov-project').first.wait_for()
        pending.clear();page.route('**/timeline/overview?*',lambda route:pending.append(route))
        page.locator('[data-overview-filter="period"]').select_option('all')
        page.locator('[data-overview-scope="mine"]').click()
        page.wait_for_timeout(100)
        self.assertEqual(len(pending),2)
        newer=pending[1].fetch();pending[1].fulfill(response=newer)
        page.locator('.ov-project').first.wait_for()
        older=pending[0].fetch();pending[0].fulfill(response=older)
        page.wait_for_timeout(100)
        self.assertNotIn('跃动篮球鞋',page.locator('.ov-board').inner_text())
        page.unroute('**/timeline/overview?*')
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and r.status==200):
            page.locator('[data-overview-search]').fill('没有这个项目')
        page.locator('.ov-message',has_text='没有项目').wait_for()
        page.locator('.ov-message [data-overview-reset]').click()
        page.locator('.ov-project').first.wait_for()
        self.assertEqual(page.locator('[data-overview-filter="period"]').input_value(),'all')
        self.assertEqual(page.flowboard_page_errors,[])
        self.assertTrue(all('500' in error for error in page.flowboard_console_errors))
        context.close()

    def test_initial_home_load_cannot_override_user_navigation(self):
        self.seed();context=self.browser.new_context();page=context.new_page();pending=[]
        page.route('**/timeline/review',lambda route:pending.append(route))
        page.goto(self.base)
        page.locator('#loginUser').fill('u1');page.locator('#loginPassword').fill('test-password')
        page.locator('#loginForm button[type=submit]').click()
        page.locator('#loadState',has_text='刚刚同步').wait_for()
        self.open_overview(page)
        self.assertEqual(len(pending),1)
        pending[0].fulfill(response=pending[0].fetch())
        page.wait_for_timeout(100)
        self.assertTrue(page.locator('[data-timeline-page="overview"]').is_visible())
        self.assertTrue(page.locator('#timelineOverviewBtn').evaluate('el=>el.classList.contains("active")'))
        context.close()

    def test_search_pending_during_filter_response_is_not_lost(self):
        self.seed();context,page=self.login('u1');self.open_overview(page)
        pending=[]
        page.route('**/timeline/overview?*',lambda route:pending.append(route) if not pending else route.continue_())
        page.locator('[data-overview-filter="period"]').select_option('all')
        page.wait_for_timeout(80)
        self.assertEqual(len(pending),1)
        response=pending[0].fetch()
        page.locator('[data-overview-search]').fill('鞋面材料')
        pending[0].fulfill(response=response)
        page.locator('.ov-result',has_text='1 个项目 · 1 个节点').wait_for()
        self.assertEqual(page.locator('.ov-project').count(),1)
        self.assertEqual(page.locator('[data-overview-search]').input_value(),'鞋面材料')
        self.assertIn('疾风跑鞋',page.locator('.ov-project').inner_text())
        # Local expand rerenders must also retain an already scheduled search.
        page.unroute('**/timeline/overview?*')
        page.locator('[data-overview-search]').fill('没有此项目')
        page.locator('[data-overview-expand]').click()
        page.locator('.ov-message',has_text='没有项目').wait_for()
        self.assertEqual(page.locator('[data-overview-search]').input_value(),'没有此项目')
        self.assert_clean_browser(page);context.close()

    def test_response_from_previous_login_cannot_replace_new_session(self):
        self.seed();context,page=self.login('u1');pending=[]
        def hold_first(route):
            if not pending:pending.append(route)
            else:route.continue_()
        page.route('**/timeline/overview?*',hold_first)
        page.locator('#timelineOverviewBtn').click()
        page.locator('.ov-message',has_text='正在加载').wait_for()
        page.wait_for_timeout(100)
        response=pending[0].fetch();old_payload=response.json()
        old_payload['projects'][0]['name']='上一会话旧响应'
        page.locator('#logoutBtn').click()
        page.locator('#loginUser').fill('u1');page.locator('#loginPassword').fill('test-password')
        page.locator('#loginForm button[type=submit]').click()
        page.locator('[data-timeline-page="overview"]').wait_for()
        self.open_overview(page)
        pending[0].fulfill(status=200,content_type='application/json',body=json.dumps(old_payload))
        page.wait_for_timeout(100)
        self.assertNotIn('上一会话旧响应',page.locator('.ov-board').inner_text())
        self.assert_clean_browser(page);context.close()

    def test_desktop_visual_long_list_and_narrow_table_scroll(self):
        ids=self.seed(long_list=True);context,page=self.login('u1')
        page.set_viewport_size({'width':1600,'height':1000});self.open_overview(page)
        self.select(page,'completion','all')
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(EVIDENCE/'overview-desktop.png'))
        page.locator('.ov-board').screenshot(path=str(EVIDENCE/'overview-content.png'))
        self.assertGreater(page.locator('.ov-project').count(),30)
        name=page.locator(f'[data-overview-project="{ids["long"]}"] .ov-open')
        self.assertGreater(len(name.get_attribute('title')),100)
        page.locator(f'[data-overview-expand="{ids["long"]}"]').click()
        detail=page.locator(f'#ov-detail-{ids["long"]}')
        self.assertIn('复杂工艺说明与材料沟通记录',detail.inner_text())
        page.set_viewport_size({'width':760,'height':850})
        scroller=page.locator('.ov-table-scroll').first
        self.assertTrue(scroller.evaluate('el=>el.scrollWidth>el.clientWidth'))
        scroller.evaluate('el=>el.scrollLeft=el.scrollWidth')
        self.assertTrue(scroller.evaluate('el=>el.scrollLeft>0'))
        self.assertTrue(scroller.evaluate('el=>getComputedStyle(el).scrollbarWidth==="none"'))
        self.assertTrue(page.locator('.ov-date').first.evaluate('el=>getComputedStyle(el).whiteSpace==="nowrap"'))
        page.screenshot(path=str(EVIDENCE/'overview-narrow.png'))
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),762)
        self.select(page,'period','all');self.select(page,'scope','mine')
        page.locator(f'[data-overview-expand="{ids["empty"]}"]').click()
        self.assertIn('尚未录入节点',page.locator(f'#ov-detail-{ids["empty"]}').inner_text())
        self.assert_clean_browser(page);context.close()


if __name__=='__main__':unittest.main()
