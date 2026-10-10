"""Compatibility entrypoint for the portable repository skill tests."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

_test_file = Path(__file__).resolve().parents[2] / '.agents/skills/sync-main/tests/test_sync_main.py'
_spec = spec_from_file_location('portable_test_sync_main', _test_file)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
SyncMainIntegrationTests = _module.SyncMainIntegrationTests

if __name__ == '__main__':
    unittest.main()
