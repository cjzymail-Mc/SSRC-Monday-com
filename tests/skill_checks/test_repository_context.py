"""Compatibility entrypoint for the portable repository skill tests."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

_test_file = Path(__file__).resolve().parents[2] / '.agents/skills/sync-main/tests/test_repository_context.py'
_spec = spec_from_file_location('portable_test_repository_context', _test_file)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
RepositoryContextTests = _module.RepositoryContextTests

if __name__ == '__main__':
    unittest.main()
