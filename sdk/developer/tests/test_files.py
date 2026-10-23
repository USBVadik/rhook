import os
from pathlib import Path
import tempfile
import unittest

from developer import files

class FileBoundaryTests(unittest.TestCase):
    def test_duplicate_keys_non_utf8_and_deep_json_fail(self):
        for raw in [b'{"x":1,"x":2}', b'"\xff"', b'[' * 65 + b'0' + b']' * 65, b'NaN']:
            with self.assertRaises((ValueError, UnicodeError)):
                files.strict(raw)

    def test_read_rejects_fifo_symlink_and_oversize_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            regular = root / 'regular'; regular.write_bytes(b'12345')
            fifo = root / 'fifo'; os.mkfifo(fifo)
            link = root / 'link'; link.symlink_to(regular)
            for path, maximum in [(fifo, 10), (link, 10), (regular, 4)]:
                with self.assertRaises(ValueError): files.read(path, maximum)

    def test_archive_paths_reject_aliases_and_escape(self):
        for name in ['../x', '/x', './x', 'x/../y', 'x//y', '', '.']:
            with self.assertRaises(ValueError): files.relative(name)
        self.assertEqual(str(files.relative('node_modules/viem/package.json')), 'node_modules/viem/package.json')

    def test_artifact_manifest_is_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); (root / 'developer').mkdir()
            (root / 'developer/artifacts.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_MANIFEST_DRIFT'):
                files.artifact_pins(root)

    def test_save_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'result.json'
            files.save(path, {'status': 'PLANNED'})
            with self.assertRaises(FileExistsError): files.save(path, {'status': 'COMPLETED'})
            self.assertEqual(files.load(path), {'status': 'PLANNED'})
