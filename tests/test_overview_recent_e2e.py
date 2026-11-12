import unittest
from pathlib import Path

import test_overview_e2e as overview


EVIDENCE = Path(__file__).resolve().parents[1] / 'team-progress/verification/20261112-overview-recent'


class OverviewRecentE2E(unittest.TestCase):
    secondary_controls_for_test = False
    setUpClass = classmethod(overview.OverviewE2E.setUpClass.__func__)
    tearDownClass = classmethod(overview.OverviewE2E.tearDownClass.__func__)
    setUp = overview.OverviewE2E.setUp
    tearDown = overview.OverviewE2E.tearDown
    login = overview.OverviewE2E.login
    seed = overview.OverviewE2E.seed
    open_overview = overview.OverviewE2E.open_overview
    assert_clean_browser = overview.OverviewE2E.assert_clean_browser

    def ready(self, page):
        page.locator('[data-timeline-page=overview][aria-busy=false]').wait_for()

    def scope(self, page, value):
        with page.expect_response(lambda r: '/timeline/overview?' in r.url and 'scope=' + value in r.url and r.status == 200):
            page.locator(f'[data-overview-scope={value}]').click()
        self.ready(page)

    def relogin(self, page, username):
        page.locator('#logoutBtn').click()
        page.locator('#loginUser').fill(username)
        page.locator('#loginPassword').fill('test-password')
        page.locator('#loginForm button[type=submit]').click()
        page.locator('#loginModal').wait_for(state='hidden')
        page.locator('#loadState', has_text='刚刚同步').wait_for()
        self.open_overview(page)

    def test_member_and_admin_reset_scope_on_login_but_keep_manual_choice_on_reload(self):
        self.seed()
        context, page = self.login('u2')
        self.open_overview(page)
        self.assertEqual(page.locator('[data-overview-scope=mine]').get_attribute('aria-pressed'), 'true')
        self.assertEqual(page.locator('.ov-project').count(), 2)
        self.scope(page, 'all')
        self.assertEqual(page.locator('.ov-project').count(), 6)
        page.reload(); self.ready(page)
        self.assertEqual(page.locator('[data-overview-scope=all]').get_attribute('aria-pressed'), 'true')
        self.relogin(page, 'u2')
        self.assertEqual(page.locator('[data-overview-scope=mine]').get_attribute('aria-pressed'), 'true')
        self.assertEqual(page.locator('.ov-project').count(), 2)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(EVIDENCE / 'member-login-mine.png'))
        self.relogin(page, 'u1')
        self.assertEqual(page.locator('[data-overview-scope=all]').get_attribute('aria-pressed'), 'true')
        self.scope(page, 'mine')
        self.relogin(page, 'u1')
        self.assertEqual(page.locator('[data-overview-scope=all]').get_attribute('aria-pressed'), 'true')
        self.assertEqual(page.locator('.ov-project').count(), 6)
        self.assert_clean_browser(page); context.close()

    def test_recent_future_completed_and_empty_projects_keep_today_axis_hidden(self):
        ids = self.seed()
        context, page = self.login('u1')
        page.set_viewport_size({'width': 850, 'height': 675})
        self.open_overview(page)
        for key, count in [('future', 1), ('team', 2), ('done', 1)]:
            page.locator(f'[data-overview-expand="{ids[key]}"]').click()
            detail = page.locator(f'#ov-detail-{ids[key]}')
            self.assertEqual(detail.locator('.timeline-dashboard-node').count(), count)
            self.assertFalse(detail.locator('.timeline-portfolio-today').is_visible())
            self.assertFalse(detail.locator('.timeline-past-mask').first.is_visible()) if detail.locator('.timeline-past-mask').count() else None
            self.assertEqual(detail.locator('.ov-inline-empty').count(), 0)
            self.assertLessEqual(detail.locator('.ov-inline-panel').bounding_box()['width'], 850)
            if key == 'future':
                self.assertIn('left:50%', detail.locator('.timeline-dashboard-node').get_attribute('style'))
                EVIDENCE.mkdir(parents=True, exist_ok=True)
                detail.scroll_into_view_if_needed()
                page.screenshot(path=str(EVIDENCE / 'future-node-preview.png'))
            if key == 'team':
                self.assertEqual(detail.locator('[data-timeline-context]').count(), 1)
        page.locator(f'[data-overview-expand="{ids["empty"]}"]').click()
        self.assertIn('尚未录入带日期的节点', page.locator(f'#ov-detail-{ids["empty"]}').inner_text())
        self.assert_clean_browser(page); context.close()

    def test_member_recent_other_project_stays_readonly(self):
        ids = self.seed()
        context, page = self.login('u2')
        self.open_overview(page); self.scope(page, 'all')
        page.locator(f'[data-overview-expand="{ids["future"]}"]').click()
        detail = page.locator(f'#ov-detail-{ids["future"]}')
        self.assertEqual(detail.locator('.timeline-dashboard-node').count(), 1)
        self.assertEqual(detail.locator('[data-timeline-context],[data-dashboard-submit]').count(), 0)
        self.assert_clean_browser(page); context.close()


if __name__ == '__main__':
    unittest.main()
