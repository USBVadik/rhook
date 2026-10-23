"""CLI boundary tests do not sample resources or execute the native worker."""
from pathlib import Path
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rhook_alpha import cli, install


class Commands(unittest.TestCase):
    def test_plan_argument_is_typed_before_sdk_use(self):
        for text in ['lpBps=100', 'lpBps=-1', 'fee=50', 'lpBps=5.0', 'lpBps=50;false', 'lpBps=050']:
            with self.subTest(text=text), patch.object(cli, 'SDK') as sdk, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['plan', '--set', text]), 1)
                sdk.assert_not_called()

    def test_authorize_requires_explicit_local_owner_and_power_flags(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parser().parse_args(['authorize', '--plan', 'b'*32])

    def test_launcher_quotes_paths_and_isolates_python(self):
        import shlex
        prefix = Path('/private/tmp/spaces Ω $(false)')
        words = shlex.split(install.launcher(prefix).splitlines()[1])
        self.assertEqual(words, ['exec', str(prefix/'python/bin/python'), '-I', '-B', '-m', 'rhook_alpha.cli', '$@'])


if __name__ == '__main__': unittest.main(verbosity=2)
