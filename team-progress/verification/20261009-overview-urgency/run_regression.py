import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_overview_e2e as overview
from test_overview_ux_e2e import OverviewUXE2E
overview.EVIDENCE=Path(__file__).resolve().parent
suite=unittest.defaultTestLoader.loadTestsFromTestCase(overview.OverviewE2E)
for name in ('test_menu_five_modules_and_focus_progress_never_resets_to_zero',
             'test_single_expansion_and_upcoming_red_dashed_rows',
             'test_advanced_search_object_and_keyboard_horizontal_access',
             'test_compact_next_note_column_urgency_and_unique_groups'):
    suite.addTest(OverviewUXE2E(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
