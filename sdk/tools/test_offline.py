#!/usr/bin/env python3
"""Run synthetic SDK tests without assets, sensors or native execution."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if sys.version_info < (3, 12) or sys.flags.optimize:
        raise SystemExit('Python 3.12+ without optimization is required')
    # Separate discovery roots preserve imports used by the accepted tests.
    suite = unittest.TestSuite()
    for relative in ('tests_alpha', 'developer/tests', 'tools/tests'):
        loader = unittest.TestLoader()
        suite.addTests(loader.discover(str(ROOT / relative)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == '__main__':
    raise SystemExit(main())
