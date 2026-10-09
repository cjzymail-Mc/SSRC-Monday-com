import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flowboard.database import connect
import test_overview_e2e as overview

EVIDENCE=Path(__file__).resolve().parents[1]/'team-progress/verification/20261009-stage-badge'

class StageBadgeE2E(unittest.TestCase):
    secondary_controls_for_test=False
    setUpClass=classmethod(overview.OverviewE2E.setUpClass.__func__)
    tearDownClass=classmethod(overview.OverviewE2E.tearDownClass.__func__)
    setUp=overview.OverviewE2E.setUp
    tearDown=overview.OverviewE2E.tearDown
    login=overview.OverviewE2E.login
    seed=overview.OverviewE2E.seed
    open_overview=overview.OverviewE2E.open_overview
    assert_clean_browser=overview.OverviewE2E.assert_clean_browser

    def test_approved_badges_all_stages_empty_hover_and_narrow_layout(self):
        ids=self.seed();now=datetime.now(timezone.utc).isoformat()
        today=datetime.now(timezone(timedelta(hours=8))).date()
        colors={'创意':'rgb(171, 95, 232)','设计':'rgb(23, 70, 176)','开发':'rgb(10, 166, 126)','测试':'rgb(217, 140, 0)','量产':'rgb(100, 188, 70)','应用迭代':'rgb(143, 106, 16)'}
        stageProjects={}
        db=connect(self.db_path)
        with db:
            for stage in colors:
                project=db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)",(f'圆角标签验证 · {stage}',now,now)).lastrowid
                stageProjects[stage]=project
                for node_date in [today-timedelta(days=2),today+timedelta(days=7)]:
                    value=node_date.isoformat()
                    db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,'main',?,'阶段节点',?,?,'标签不改变节点',1,?,?)",(project,stage,value,value,now,now))
        db.close()
        context,page=self.login('u1');self.open_overview(page)
        for width in [1480,794]:
            page.set_viewport_size({'width':width,'height':900})
            page.mouse.move(0,0)
            for stage,project in stageProjects.items():
                row=page.locator(f'[data-overview-project="{project}"]')
                cell=row.locator('.ov-stage');badge=cell.locator('.ov-stage-badge')
                self.assertEqual(badge.inner_text(),stage)
                self.assertEqual(badge.evaluate('el=>getComputedStyle(el).backgroundColor'),colors[stage])
                self.assertEqual(badge.evaluate('el=>getComputedStyle(el).borderRadius'),'6px')
                self.assertEqual(badge.evaluate('el=>el.getBoundingClientRect().height'),26)
                self.assertLess(badge.bounding_box()['width'],cell.bounding_box()['width'])
                self.assertEqual(cell.evaluate('el=>getComputedStyle(el).backgroundColor'),row.locator('td').first.evaluate('el=>getComputedStyle(el).backgroundColor'))
                self.assertEqual(row.locator('.ov-status').evaluate('el=>getComputedStyle(el).backgroundColor'),'rgb(246, 51, 101)')
                row.locator('.ov-open').hover()
                self.assertEqual(cell.evaluate('el=>getComputedStyle(el).backgroundColor'),'rgb(238, 235, 250)')
                self.assertEqual(badge.evaluate('el=>getComputedStyle(el).backgroundColor'),colors[stage])
            empty=page.locator('.ov-stage-badge',has_text='未录入节点')
            self.assertGreaterEqual(empty.count(),1)
            self.assertEqual(empty.first.evaluate('el=>getComputedStyle(el).backgroundColor'),'rgb(181, 175, 195)')
            self.assertEqual(page.locator('.ov-table colgroup').first.locator('col').count(),7)
            page.mouse.move(0,0)
            page.screenshot(path=str(EVIDENCE/f'overview-stage-badge-{width}.png'),full_page=True)
        page.locator(f'[data-overview-expand="{ids["risk"]}"]').click()
        self.assertTrue(page.locator(f'#ov-detail-{ids["risk"]}').is_visible())
        self.assertGreater(page.locator(f'#ov-detail-{ids["risk"]} .ov-nodes tbody tr').count(),0)
        self.assert_clean_browser(page);context.close()

if __name__=='__main__':unittest.main()
