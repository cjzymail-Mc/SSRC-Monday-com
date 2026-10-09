import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_overview_e2e as overview
from test_overview_ux_e2e import OverviewUXE2E
overview.EVIDENCE=Path(__file__).resolve().parent
suite=unittest.TestSuite()
for name in ('test_desktop_visual_long_list_and_narrow_table_scroll',
             'test_member_readonly_and_logout_resets_overview_state'):
    suite.addTest(overview.OverviewE2E(name))
for name in ('test_menu_five_modules_and_focus_progress_never_resets_to_zero',
             'test_single_expansion_and_upcoming_red_dashed_rows',
             'test_compact_next_note_column_urgency_and_unique_groups'):
    suite.addTest(OverviewUXE2E(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
