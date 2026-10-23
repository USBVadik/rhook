#!/usr/bin/env python3
"""Relocate only the preserved regression fixture's SDK path; never run history."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import test_dispatcher

test_dispatcher.SDK = REPO
if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_dispatcher)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
