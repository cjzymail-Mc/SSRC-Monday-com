import io
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from flowboard.database import connect
from flowboard.timeline import TimelineService
import test_timeline_e2e as harness

EVIDENCE=Path(__file__).resolve().parents[1]/'team-progress/verification/20261009-period-mask'

class PeriodMaskE2E(unittest.TestCase):
    setUpClass=classmethod(harness.TimelineProductionE2E.setUpClass.__func__)
    tearDownClass=classmethod(harness.TimelineProductionE2E.tearDownClass.__func__)
    tearDown=harness.TimelineProductionE2E.tearDown
    login=harness.TimelineProductionE2E.login
    assert_clean_browser=harness.TimelineProductionE2E.assert_clean_browser

    def setUp(self):
        clock=patch.object(TimelineService,'_server_today',return_value=date(2026,10,9))
        clock.start();self.addCleanup(clock.stop)
        harness.TimelineProductionE2E.setUp(self)
        db=connect(self.db_path)
        now='2026-10-09T00:00:00+00:00'
        with db:
            self.project=db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,'跨期双轨蒙版验证','u1',1,?,?)",(now,now)).lastrowid
            for track,stage,name,value in [('main','测试','测试启动','2026-07-22'),('main','量产','量产确认','2026-10-11'),('parallel','开发','并行启动','2026-08-01'),('parallel','测试','并行交付','2026-10-11')]:
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)",(self.project,track,stage,name,value,value,now,now))
        db.close()

    def open_period(self,page,period):
        page.locator('#timelineWeekBtn' if period=='week' else '#timelineMonthBtn').click()
        page.locator(f'[data-time-scope={period}] [data-dashboard-project="{self.project}"]').wait_for()
        return page.locator(f'[data-dashboard-project="{self.project}"]')

    def assert_mask_geometry(self,page,row):
        self.assertEqual(row.locator('.timeline-past-mask').count(),2)
        today=page.locator('.timeline-today-line').bounding_box()['x']
        for track in ['main','parallel']:
            plot=row.locator(f'[data-track={track}] .timeline-stage-plot')
            mask=plot.locator('.timeline-past-mask');box=mask.bounding_box()
            self.assertAlmostEqual(box['x']+box['width'],today,delta=1)
            style=mask.evaluate('el=>({z:Number(getComputedStyle(el).zIndex),background:getComputedStyle(el).backgroundColor,pointer:getComputedStyle(el).pointerEvents})')
            stage=plot.locator('.timeline-stage').first
            self.assertGreater(style['z'],stage.evaluate('el=>Number(getComputedStyle(el).zIndex)'))
            self.assertEqual(style['background'],'rgba(255, 255, 255, 0.7)')
            self.assertEqual(style['pointer'],'none')
        self.assertEqual(row.locator('[data-node-date="2026-07-22"],[data-node-date="2026-08-01"]').count(),0)
        return today

    def test_before_clipping_drops_masks_in_week_and_month(self):
        context,page=self.login('u1')
        context.route('**/timeline-ui.js*',lambda route:route.fulfill(status=200,content_type='text/javascript',body=(EVIDENCE/'baseline/timeline-ui.js').read_text(encoding='utf-8')))
        page.reload();page.locator('[data-timeline-page=home]').wait_for()
        for period in ['week','month']:
            row=self.open_period(page,period)
            self.assertEqual(row.locator('.timeline-stage').count(),2)
            self.assertEqual(row.locator('.timeline-past-mask').count(),0)
            self.assertEqual(row.locator('[data-node-date="2026-07-22"]').count(),0)
            page.screenshot(path=str(EVIDENCE/f'{period}-before.png'))
        self.assert_clean_browser(page);context.close()

    def test_cross_period_masks_visible_in_normal_hover_focus_and_fullscreen(self):
        context,page=self.login('u1')
        for period in ['week','month']:
            row=self.open_period(page,period)
            today=self.assert_mask_geometry(page,row)
            for track in ['main','parallel']:
                box=row.locator(f'[data-track={track}] .timeline-stage').first.bounding_box()
                past=int((box['x']+today)/2);future=int((today+box['x']+box['width'])/2);y=int(box['y']+box['height']/2)
                pixels=Image.open(io.BytesIO(page.screenshot())).convert('RGB')
                a=pixels.getpixel((past,y));b=pixels.getpixel((future,y))
                self.assertLess(max(a)-min(a),(max(b)-min(b))*.5,'past stage must visibly fade on both tracks')
            stage=row.locator('[data-track=main] .timeline-stage').first
            stage.hover();self.assert_mask_geometry(page,row)
            row.locator('.timeline-portfolio-meta strong').click()
            page.wait_for_function('document.querySelector("[data-dashboard-project].is-focused") !== null')
            self.assert_mask_geometry(page,row)
            page.locator('[data-portfolio-fullscreen]').click()
            page.locator('.timeline-portfolio-card.is-fullscreen').wait_for()
            self.assert_mask_geometry(page,row)
            page.screenshot(path=str(EVIDENCE/f'{period}-ready.png'))
            page.locator('[data-portfolio-fullscreen]').click()
        self.assert_clean_browser(page);context.close()

if __name__=='__main__':unittest.main()
