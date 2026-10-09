import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
import test_overview_e2e
import test_timeline_e2e

suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_overview_e2e.OverviewE2E)
for name in (
    'test_week_and_month_are_shared_portfolio_scopes',
    'test_week_and_month_focused_flags_are_not_vertically_clipped',
    'test_timeline_portfolio_e_d4_p1_canvas',
    'test_timeline_journey_edit_submit_refresh_undo',
    'test_timeline_cp2_table_editor_local_draft_sort_interval_and_discard',
):
    suite.addTest(test_timeline_e2e.TimelineProductionE2E(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
