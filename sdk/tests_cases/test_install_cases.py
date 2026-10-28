from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]

class Installation(unittest.TestCase):

    def test_source_only_install_lists_cases_without_runtime_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            prefix = root / 'nested/opt/installed'
            home = root / 'home'
            p = subprocess.run([sys.executable, '-B', str(ROOT / 'install_cases.py'), '--prefix', str(prefix)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            command = prefix / 'bin/rhook-cases'
            p = subprocess.run([str(command), '--home', str(home), 'cases'], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout), {'status': 'CASES_LISTED', 'cases': []})
            self.assertFalse(home.exists())
            p = subprocess.run([sys.executable, '-B', str(ROOT / 'install_cases.py'), '--prefix', str(prefix)], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
if __name__ == '__main__':
    unittest.main()
