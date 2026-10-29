import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from flowboard.database import connect
import test_timeline_edit_e2e as helpers

class RowClickE2E(unittest.TestCase):
    setUpClass=classmethod(helpers.SharedTimelineEditE2E.setUpClass.__func__)
    tearDownClass=classmethod(helpers.SharedTimelineEditE2E.tearDownClass.__func__)
    setUp=helpers.SharedTimelineEditE2E.setUp
    tearDown=helpers.SharedTimelineEditE2E.tearDown
    login=helpers.SharedTimelineEditE2E.login
    seed=helpers.SharedTimelineEditE2E.seed
    open=helpers.SharedTimelineEditE2E.open

    def test_graph_click_targets_expand_rows_and_keep_doubleclick_and_overview(self):
        today=datetime.now(timezone(timedelta(hours=8))).date()
        pid,ids=self.seed('整片时间轴点击',[today-timedelta(days=1),today+timedelta(days=2),today+timedelta(days=1)])
        other,_=self.seed('第二项目',[today])
        db=connect(self.db_path);db.execute("UPDATE timeline_nodes SET track='main' WHERE id=?",(ids[1],));db.commit();db.close()
        context,page=self.login('u1');page.set_default_timeout(5000)
        for scope in ('all','week','month'):
            self.open(page,scope,pid)
            row=page.locator(f'[data-dashboard-project="{pid}"]')
            if 'is-focused' in row.get_attribute('class'):
                row.locator('.timeline-portfolio-meta strong').click()
            plot=row.locator('.timeline-stage-plot').first
            r=plot.bounding_box();plot.click(position={'x':r['width']*.8,'y':r['height']-3})
            page.wait_for_function('id=>document.querySelector(`[data-dashboard-project="${id}"]`).classList.contains("is-focused")',arg=pid)
            self.assertGreaterEqual(row.bounding_box()['height'],167)
            row.locator('.timeline-portfolio-meta strong').click()
            row.locator('.timeline-dashboard-node i').first.click()
            page.wait_for_function('id=>document.querySelector(`[data-dashboard-project="${id}"]`).classList.contains("is-focused")',arg=pid)
            flag_box=row.locator('.timeline-node-flag b').first.bounding_box()
            page.mouse.click(flag_box['x']+flag_box['width']/2,flag_box['y']+flag_box['height']/2)
            page.wait_for_function('id=>!document.querySelector(`[data-dashboard-project="${id}"]`).classList.contains("is-focused")',arg=pid)
            row.locator('.timeline-dashboard-node').first.dblclick()
            popup=page.locator('[data-dashboard-remark]');popup.wait_for(state='visible')
            page.wait_for_timeout(550)
            self.assertNotIn('is-focused',row.get_attribute('class'))
            popup.locator('[data-remark-cancel]').click()
            stage=row.locator('.timeline-stage').first
            stage_box=stage.bounding_box();page.mouse.click(stage_box['x']+stage_box['width']/2,stage_box['y']+stage_box['height']/2)
            page.wait_for_function('id=>document.querySelector(`[data-dashboard-project="${id}"]`).classList.contains("is-focused")',arg=pid)
            self.assertEqual(page.locator('.timeline-portfolio-project.is-focused').count(),1)
        path=Path(__file__).resolve().parents[1]/'team-progress/verification/20261029-row-click'
        path.mkdir(exist_ok=True,parents=True);page.mouse.move(10,10);page.screenshot(path=str(path/'whole-row-expanded.png'),full_page=True)
        self.open(page,'overview',pid)
        inline=page.locator('.ov-inline-timeline');before=inline.bounding_box()['height']
        inline.locator('.timeline-stage-plot').first.click(position={'x':40,'y':3})
        self.assertEqual(inline.bounding_box()['height'],before)
        self.assertEqual(inline.locator('[data-portfolio-focus-project]').count(),0)
        self.assertEqual(page.flowboard_page_errors,[]);context.close()

if __name__=='__main__':unittest.main()
