import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from developer import files, install

class ArchiveBoundaryTests(unittest.TestCase):
    def make(self, root, *, payload=b'bytes', size=None, extras=(), missing=False):
        item = {'sha256': files.digest(payload), 'bytes': len(payload) if size is None else size}
        manifest = {'schema': 'rhook/private-alpha-inputs/0.1', 'files': {'worker': item}}
        bundle = root / 'assets.tgz'
        with tarfile.open(bundle, 'w:gz', format=tarfile.USTAR_FORMAT) as archive:
            raw = files.canonical(manifest)
            header = tarfile.TarInfo('ASSETS.json'); header.size = len(raw)
            archive.addfile(header, io.BytesIO(raw))
            if not missing:
                header = tarfile.TarInfo('worker'); header.size = len(payload)
                archive.addfile(header, io.BytesIO(payload))
            for header, data in extras: archive.addfile(header, io.BytesIO(data) if data else None)
        return bundle, {'files': {'worker': item}}

    def extract(self, bundle, target, pins):
        with patch.object(install, 'dependencies', return_value={}):
            return install.extract(bundle, target, pins)

    def test_exact_regular_file_extracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); target = root / 'out'; target.mkdir()
            bundle, pins = self.make(root)
            self.extract(bundle, target, pins)
            self.assertEqual((target / 'worker').read_bytes(), b'bytes')

    def test_symlink_and_directory_headers_rejected(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); target = root / 'out'; target.mkdir()
                header = tarfile.TarInfo('node_modules/bad'); header.type = kind; header.linkname = '/tmp/unrelated'
                bundle, pins = self.make(root, extras=[(header, b'')])
                with self.assertRaises(ValueError): self.extract(bundle, target, pins)

    def test_extra_duplicate_missing_and_wrong_size_fail(self):
        header = tarfile.TarInfo('worker'); header.size = 0
        extra = tarfile.TarInfo('../outside'); extra.size = 0
        for kwargs in [{'extras': [(header, b'')]}, {'extras': [(extra, b'')]}, {'missing': True}, {'size': 100}]:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); target = root / 'out'; target.mkdir()
                bundle, pins = self.make(root, **kwargs)
                with self.assertRaises(ValueError): self.extract(bundle, target, pins)
                self.assertFalse((root / 'outside').exists())

    def test_wrong_pinned_hash_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); target = root / 'out'; target.mkdir()
            bundle, pins = self.make(root)
            pins['files']['worker']['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'REQUIRED_ASSET_PIN'):
                self.extract(bundle, target, pins)

    def test_pax_header_rejected_before_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); target = root / 'out'; target.mkdir()
            bundle, pins = self.make(root)
            with tarfile.open(bundle, 'w:gz', format=tarfile.PAX_FORMAT) as archive:
                header = tarfile.TarInfo('ASSETS.json'); header.pax_headers = {'comment': 'reject'}
                header.size = 0; archive.addfile(header, io.BytesIO(b''))
            with self.assertRaisesRegex(ValueError, 'REGULAR_USTAR_FILES_ONLY'):
                self.extract(bundle, target, pins)

    def test_failed_install_keeps_existing_prefix_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); prefix = root / 'existing'; prefix.mkdir()
            sentinel = prefix / 'keep'; sentinel.write_text('untouched')
            with patch.object(install, 'accepted_source', return_value={}), patch.object(install, 'artifact_pins', return_value={}), patch.object(install.platform, 'machine', return_value='arm64'), patch.object(install.sys, 'platform', 'darwin'):
                with self.assertRaisesRegex(ValueError, 'FRESH_INSTALL_PREFIX_REQUIRED'):
                    install.install(prefix, root / 'missing.tgz')
            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_incomplete_bundle_cleans_private_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); prefix = root / 'new'
            bundle, pins = self.make(root, missing=True)
            with patch.object(install, 'accepted_source', return_value={}), patch.object(install, 'artifact_pins', return_value=pins), patch.object(install.platform, 'machine', return_value='arm64'), patch.object(install.sys, 'platform', 'darwin'):
                with self.assertRaises(ValueError): install.install(prefix, bundle)
            self.assertFalse(prefix.exists())
            self.assertFalse(list(root.glob('.rhook-install-*')))
