"""Publication adaptations must preserve the accepted runtime boundary."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from developer import files
from rhook_alpha import install

ROOT = Path(__file__).resolve().parents[2]


class PublicSourceBoundary(unittest.TestCase):
    def test_legacy_top_level_install_imports_without_portable_package(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory).resolve()
            lib = prefix / 'lib'
            package = lib / 'rhook_alpha'
            package.mkdir(parents=True)
            # Match rhook_alpha.install's preserved top-level-only copy exactly.
            for source in (ROOT / 'rhook_alpha').glob('*.py'):
                shutil.copyfile(source, package / source.name)
            shutil.copytree(ROOT / 'developer', lib / 'developer')
            probe = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import rhook_alpha.cli
from rhook_alpha import SDK
home = Path(sys.argv[2])
sdk = SDK(home)
assert not home.exists()
try:
    sdk.list_cases()
except ValueError as error:
    assert str(error) == 'PORTABLE_CASE_SDK_NOT_INSTALLED', str(error)
else:
    raise AssertionError('missing portable modules must fail explicitly')
assert not home.exists()
'''
            result = subprocess.run([sys.executable, '-I', '-B', '-c', probe,
                                     str(lib), str(prefix / 'unused-home')],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_public_source_is_not_accepted_native_source(self):
        with self.assertRaisesRegex(ValueError, 'ACCEPTED_SOURCE_DRIFT'):
            files.accepted_source(ROOT)

    def test_every_imported_file_matches_public_provenance(self):
        provenance = json.loads((ROOT / 'source-provenance.json').read_bytes())
        self.assertFalse(provenance['byteIdenticalNativeSource'])
        self.assertEqual(len(provenance['files']), 218)
        for row in provenance['files']:
            self.assertEqual(files.sha(ROOT / row['path']), row['publicSha256'], row['path'])

    def test_sdk_tree_contains_only_reviewed_source_and_publication_files(self):
        provenance = json.loads((ROOT / 'source-provenance.json').read_bytes())
        expected = {row['path'] for row in provenance['files']} | {
            'README.md', 'QUICKSTART.md', 'COMPATIBILITY.md', 'LICENSE_SCOPE.md',
            'DISTRIBUTION.md', 'RELEASE_NOTES.md', 'source-provenance.json',
            'tools/test_offline.py', 'tools/tests/test_public_source.py',
        }
        derived = json.loads((ROOT / 'case-source.json').read_bytes())
        self.assertEqual(derived['schema'], 'rhook/portable-case-source/0.1')
        for name, pin in derived['files'].items():
            self.assertEqual(files.sha(ROOT / name), pin, name)
        expected |= set(derived['files']) | {'case-source.json'}
        self.assertEqual(set(files.tree(ROOT)), expected)

    def test_explicit_engine_root_is_verified_not_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Path(directory).resolve()
            # A substituted source tree cannot inherit an accepted identity.
            (engine / '.gitignore').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'ACCEPTED_SOURCE_DRIFT'):
                files.accepted_source(ROOT, engine)

    def test_install_cli_requires_explicit_original_runtime_source(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            install.main(['--prefix', '/tmp/example-prefix', '--assets', '/tmp/example-inputs'])


if __name__ == '__main__':
    unittest.main()
