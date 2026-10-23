"""Descriptor admission tests with disposable files and bounded Python children."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from plan_native import core


class FileReads(unittest.TestCase):
    def test_regular_file_bounds(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            path = Path(d) / 'input'; path.write_bytes(b'1234')
            self.assertEqual(core.read(path, 4), b'1234')
            with self.assertRaises(ValueError): core.read(path, 3)

    def test_existing_fifo_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            p = Path(d); (p / 'target').write_bytes(b'ordinary')
            os.mkfifo(p / 'fifo'); (p / 'link').symlink_to(p / 'target')
            for path in [p / 'fifo', p / 'link']:
                with self.subTest(path=path), self.assertRaises((ValueError, OSError)): core.read(path)

    def test_substitution_at_open_is_nonblocking_and_no_follow(self):
        code = textwrap.dedent('''
            import os, sys
            from pathlib import Path
            from unittest.mock import patch
            from plan_native import core
            target, kind = Path(sys.argv[1]), sys.argv[2]
            original_path_open, original_os_open = Path.open, os.open
            swapped = False
            def swap():
                global swapped
                if not swapped:
                    swapped = True; target.unlink()
                    if kind == 'fifo': os.mkfifo(target)
                    else: target.symlink_to(target.parent / 'substitute')
            def path_open(self, *args, **kwargs):
                if self == target: swap()
                return original_path_open(self, *args, **kwargs)
            def fd_open(path, flags, *args, **kwargs):
                if Path(path) == target: swap()
                return original_os_open(path, flags, *args, **kwargs)
            with patch.object(Path, 'open', path_open), patch.object(os, 'open', fd_open):
                try: core.read(target, 32)
                except (ValueError, OSError):
                    assert swapped; print('REJECTED'); sys.exit(0)
                raise AssertionError('SUBSTITUTED_INPUT_ACCEPTED')
        ''')
        for kind in ['fifo', 'symlink']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir='/private/tmp') as d:
                path = Path(d) / 'input'; path.write_bytes(b'original')
                (Path(d) / 'substitute').write_bytes(b'substituted')
                try:
                    result = subprocess.run([sys.executable, '-B', '-c', code, str(path), kind],
                                            cwd=core.ROOT, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC'},
                                            capture_output=True, timeout=2)
                except subprocess.TimeoutExpired:
                    self.fail('Substituted input blocked read beyond the two-second test bound')
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout, b'REJECTED\n')


if __name__ == '__main__': unittest.main()
