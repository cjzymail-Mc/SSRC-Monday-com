import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_overview_e2e as overview
from test_overview_ux_e2e import OverviewUXE2E
overview.EVIDENCE=Path(__file__).resolve().parent
suite=unittest.defaultTestLoader.loadTestsFromTestCase(overview.OverviewE2E)
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(OverviewUXE2E))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
