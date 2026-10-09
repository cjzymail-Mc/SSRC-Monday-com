import unittest
from pathlib import Path
import test_overview_e2e as overview
from flowboard.timeline import TimelineService

EVIDENCE=Path(__file__).resolve().parents[1]/'team-progress/verification/20261009-team-hide-admin'

class TeamCardsE2E(unittest.TestCase):
    secondary_controls_for_test=False
    setUpClass=classmethod(overview.OverviewE2E.setUpClass.__func__)
    tearDownClass=classmethod(overview.OverviewE2E.tearDownClass.__func__)
    setUp=overview.OverviewE2E.setUp
    tearDown=overview.OverviewE2E.tearDown
    login=overview.OverviewE2E.login
    seed=overview.OverviewE2E.seed
    assert_clean_browser=overview.OverviewE2E.assert_clean_browser

    def test_admin_team_card_hidden_but_my_projects_and_timeline_unchanged(self):
        ids=self.seed();context,page=self.login('u1')
        page.locator('[data-timeline-page=home]').wait_for()
        self.assertGreater(page.locator('[data-timeline-section=mine] [data-order-project]').count(),0)
        page.locator('[data-timeline-tab=team]').click()
        self.assertEqual(page.locator('[data-order-member=u1]').count(),0)
        self.assertEqual(page.locator('[data-order-member=u2]').count(),1)
        page.locator('#timelineAllBtn').click()
        page.locator('[data-timeline-page=all] .timeline-portfolio-chart').wait_for()
        with page.expect_response(lambda r:'/timeline/order?' in r.url and 'context_type=all' in r.url and r.status==200):
            page.locator('[data-timeline-tag-context=all]').click()
        page.wait_for_function('document.querySelectorAll("[data-order-project]").length===6')
        self.assertTrue(page.locator(f'[data-order-project="{ids["risk"]}"]').is_visible())
        self.assertEqual(page.locator('[data-order-project]').count(),6)
        self.assert_clean_browser(page);context.close()

    def test_visible_drag_saves_full_roster_and_restores_order_after_reload(self):
        self.seed();service=TimelineService(self.db_path);user={'id':'u2'}
        service.put_member_order(user,1,{'base_order_version':0,'member_ids':['u2','u1','u3']})
        context,page=self.login('u2');page.locator('[data-timeline-tab=team]').click()
        self.assertEqual(page.locator('[data-order-member=u1]').count(),0)
        source=page.locator('[data-order-member=u3] .tl-order-grip')
        target=page.locator('[data-order-member=u2]')
        sourceBox=source.bounding_box();targetBox=target.bounding_box()
        self.assertIsNotNone(sourceBox);self.assertIsNotNone(targetBox)
        with page.expect_response(lambda r:r.request.method=='PUT' and r.url.endswith('/timeline/member-order')) as response:
            page.mouse.move(sourceBox['x']+sourceBox['width']/2,sourceBox['y']+sourceBox['height']/2)
            page.mouse.down();page.mouse.move(targetBox['x']+targetBox['width']/2,targetBox['y']+2,steps=12);page.mouse.up()
        self.assertEqual(response.value.status,200)
        self.assertEqual(response.value.json()['member_ids'],['u3','u1','u2'])
        page.locator('#toast',has_text='你的团队卡片顺序已保存').wait_for()
        self.assertEqual(page.locator('[data-order-member]').evaluate_all('items=>items.map(el=>el.dataset.orderMember)'),['u3','u2'])
        page.reload();page.locator('[data-timeline-page=home]').wait_for();page.locator('[data-timeline-tab=team]').click()
        self.assertEqual(page.locator('[data-order-member]').evaluate_all('items=>items.map(el=>el.dataset.orderMember)'),['u3','u2'])
        self.assertEqual(service.get_member_order({'id':'u1'},1)['order_version'],0)
        self.assertEqual(page.locator('[data-order-member=u1]').count(),0)
        page.screenshot(path=str(EVIDENCE/'team-cards-ready.png'))
        self.assert_clean_browser(page);context.close()

if __name__=='__main__':unittest.main()
