import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_overview_e2e as overview
from test_overview_ux_e2e import OverviewUXE2E
overview.EVIDENCE=Path(__file__).resolve().parent
suite=unittest.TestSuite([overview.OverviewE2E('test_desktop_visual_long_list_and_narrow_table_scroll'),
                         overview.OverviewE2E('test_member_readonly_and_logout_resets_overview_state'),
                         OverviewUXE2E('test_compact_next_note_column_urgency_and_unique_groups')])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
