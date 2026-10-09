import json
import unittest
import test_overview_e2e as overview
from test_overview_ux_e2e import OverviewUXE2E
from flowboard.timeline import TimelineService


class OverviewMinimalE2E(unittest.TestCase):
    secondary_controls_for_test=False
    setUpClass=classmethod(overview.OverviewE2E.setUpClass.__func__)
    tearDownClass=classmethod(overview.OverviewE2E.tearDownClass.__func__)
    setUp=overview.OverviewE2E.setUp
    tearDown=overview.OverviewE2E.tearDown
    login=overview.OverviewE2E.login
    seed=overview.OverviewE2E.seed
    open_overview=overview.OverviewE2E.open_overview
    assert_clean_browser=overview.OverviewE2E.assert_clean_browser
    focus=OverviewUXE2E.focus
    ready=OverviewUXE2E.ready

    def test_hidden_toolbar_shared_heading_and_visible_shortcuts(self):
        self.seed();context,page=self.login('u1')
        page.locator('.tl-home-head h1').wait_for()
        style='el=>{const s=getComputedStyle(el);return [s.fontSize,s.fontWeight,s.fontFamily,s.lineHeight,s.letterSpacing,s.color]}'
        homeStyle=page.locator('.tl-home-head h1').evaluate(style)
        homeDateStyle=page.locator('.tl-home-head small').evaluate('el=>{const s=getComputedStyle(el);return [s.fontSize,s.fontFamily,s.color]}')
        self.open_overview(page)
        self.assertEqual(page.locator('.ov-header h1').evaluate(style),homeStyle)
        self.assertEqual(page.locator('.ov-header small').evaluate('el=>{const s=getComputedStyle(el);return [s.fontSize,s.fontFamily,s.color]}'),homeDateStyle)
        self.assertTrue(page.locator('.ov-header small').inner_text().startswith('今天 '))
        self.assertGreater(page.locator('.ov-header small').bounding_box()['y'],page.locator('.ov-header h1').bounding_box()['y'])
        self.assertEqual(page.locator('.ov-search,[data-overview-filter],.ov-filter-toggle,.ov-toolbar .ov-refresh,.ov-advanced,.ov-result,.ov-quick-label').count(),0)
        self.assertEqual(page.locator('.ov-quick [data-overview-focus]').all_inner_texts(),['全部','需关注','逾期','今日','本周','本月'])
        for key in ('week','month','today','all'):
            payload=self.focus(page,key)
            self.assertEqual(page.locator('.ov-project').count(),payload['counts']['projects'])
            self.assertEqual(page.locator('.ov-quick button[aria-pressed=true]').count(),1)
        page.locator('[data-overview-scope=mine]').click();self.ready(page)
        self.assertEqual(page.locator('[data-overview-scope=mine]').get_attribute('aria-pressed'),'true')
        self.assertTrue(page.locator('.ov-owner .ov-avatar').first.is_visible())
        page.screenshot(path=str(overview.EVIDENCE/'overview-minimal-ready.png'))
        self.assert_clean_browser(page);context.close()

    def test_hidden_old_filters_are_cleared_on_refresh(self):
        self.seed();context,page=self.login('u1');self.open_overview(page)
        page.evaluate("""()=>{const key=Object.keys(sessionStorage).find(k=>k.startsWith('flowboard:ux:overview:'));sessionStorage.setItem(key,JSON.stringify({scope:'all',period:'month',focus:'all',stage:'测试',track:'parallel',completion:'done',tag_id:'999',search_in:'node',q:'旧搜索'}))}""")
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and r.status==200) as response:
            page.reload()
        self.ready(page);filters=response.value.json()['filters']
        self.assertEqual(filters['period'],'month')
        for key in ('stage','track','completion','tag_id','search_in'):self.assertEqual(filters[key],'all')
        self.assertEqual(filters['q'],'')
        self.assertEqual(page.locator('[data-overview-focus=month]').get_attribute('aria-pressed'),'true')
        self.focus(page,'all');self.assertEqual(page.locator('.ov-project').count(),6)
        self.assert_clean_browser(page);context.close()

    def test_actual_history_completion_and_reopening_are_human_readable(self):
        ids=self.seed();service=TimelineService(self.db_path);user={'id':'u1'}
        def mark(value):
            version=service.get_project(user,ids['risk'])['version']
            service.submit_batches(user,1,{'requests':[{'project_id':ids['risk'],'base_version':version,'changes':[{'node_id':ids['today_node'],'set':{'done_at':value}}]}]})
        mark(True);context,page=self.login('u1')
        page.locator('[data-timeline-feed=mine] .tl-feed-item',has_text='标记为已完成').wait_for()
        self.assertNotIn('False',page.locator('.tl-feed').inner_text());self.assertNotIn('True',page.locator('.tl-feed').inner_text())
        mark(False);page.reload()
        page.locator('[data-timeline-feed=mine] .tl-feed-item',has_text='恢复为未完成').wait_for()
        self.assertNotIn('False',page.locator('.tl-feed').inner_text());self.assertNotIn('True',page.locator('.tl-feed').inner_text())
        page.screenshot(path=str(overview.EVIDENCE/'home-feed-readable.png'))
        self.assert_clean_browser(page);context.close()


if __name__=='__main__':unittest.main()
