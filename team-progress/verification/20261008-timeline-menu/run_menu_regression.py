import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_overview_ux_e2e import OverviewUXE2E
from test_timeline_e2e import TimelineProductionE2E
suite=unittest.TestSuite()
for name in ('test_menu_five_modules_and_focus_progress_never_resets_to_zero',
             'test_canvas_ranges_workbench_team_tab_and_archive_return'):
    suite.addTest(OverviewUXE2E(name))
for name in ('test_week_and_month_are_shared_portfolio_scopes',
             'test_week_and_month_focused_flags_are_not_vertically_clipped',
             'test_week_and_month_reorder_visible_subset_updates_full_personal_order'):
    suite.addTest(TimelineProductionE2E(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
