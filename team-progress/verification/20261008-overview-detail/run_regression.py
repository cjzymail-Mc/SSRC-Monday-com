import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_overview_e2e as overview
from test_overview_ux_e2e import OverviewUXE2E
overview.EVIDENCE=Path(__file__).resolve().parent
suite=unittest.defaultTestLoader.loadTestsFromTestCase(overview.OverviewE2E)
for name in ('test_single_expansion_and_upcoming_red_dashed_rows',
             'test_advanced_search_object_and_keyboard_horizontal_access',
             'test_browser_reload_cancel_keeps_unsaved_editor_draft'):
    suite.addTest(OverviewUXE2E(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
