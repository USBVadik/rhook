"""Capsules are local data, not executable code or consensus certificates."""
from pathlib import Path
import tempfile
import unittest
from rhook_alpha.cases.capsule import seal, validate
from rhook_alpha.cases.registry import Registry
from developer.files import canonical, digest, save
H = '0x' + '12' * 32

def fixture(case='one', block=11):
    package = b'{"synthetic":true}\n'
    d = {'schema': 'rhook/case-capsule/0.1', 'caseId': case, 'checkpoint': {'chainId': 4663, 'blockNumber': block - 1, 'blockHash': H, 'stateRoot': H}, 'target': {'blockNumber': block, 'blockHash': H, 'stateRoot': H, 'receiptsRoot': H}, 'arrivals': [H], 'assets': {'BLOCK_PACKAGE.json': {'sha256': digest(package), 'bytes': len(package)}}, 'execution': {'profile': 'nitro-hookr-lp/0.1', 'inputCommitment': 'ab' * 32, 'witnessCommitment': 'cd' * 32}, 'adapter': {'id': 'test.unavailable/1', 'config': {}}, 'provenance': {'kind': 'USER_SUPPLIED', 'description': 'Synthetic fixture; no chain claim'}, 'coverage': {'reads': 'UNKNOWN', 'writes': 'UNKNOWN'}}
    return (seal(d), package)

class Capsules(unittest.TestCase):

    def test_two_cases_have_independent_content_and_workspaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            r = Registry(root / 'home')
            for case, block in [('one', 11), ('two', 12)]:
                d, p = fixture(case, block)
                src = root / case
                src.mkdir()
                save(src / 'CAPSULE.json', d)
                (src / 'BLOCK_PACKAGE.json').write_bytes(p)
                info = r.import_case(src)
                self.assertEqual(info['authentication'], 'UNAUTHENTICATED')
                self.assertEqual(info['witnessClosure'], 'NOT_EVALUATED')
                self.assertFalse(info['nativeSupported'])
            self.assertNotEqual(r.resolve('one')[0], r.resolve('two')[0])
            self.assertEqual(len(r.list_cases()), 2)

    def test_hashes_do_not_authenticate_chain_or_coverage(self):
        d, p = fixture()
        validate(d, p)
        d['coverage']['writes'] = 'COMPLETE'
        with self.assertRaisesRegex(ValueError, 'COVERAGE'):
            validate(seal(d), p)

    def test_tamper_and_checkpoint_parent_mismatch(self):
        d, p = fixture()
        d['target']['blockNumber'] = 12
        with self.assertRaises(ValueError):
            validate(d, p)
        with self.assertRaises(ValueError):
            validate(fixture()[0], b'changed')

    def test_canonical_content_address_ignores_object_insertion_order(self):
        d, _ = fixture()
        r = seal(dict(reversed(list(d.items()))))
        self.assertEqual(d['capsuleId'], r['capsuleId'])

    def test_alias_cannot_silently_replace_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            r = Registry(root / 'home')
            d, p = fixture()
            src = root / 'src'
            src.mkdir()
            save(src / 'CAPSULE.json', d)
            (src / 'BLOCK_PACKAGE.json').write_bytes(p)
            r.import_case(src)
            (src / 'CAPSULE.json').unlink()
            save(src / 'CAPSULE.json', fixture(block=12)[0])
            with self.assertRaisesRegex(ValueError, 'CASE_ID_ALREADY_REGISTERED'):
                r.import_case(src)

    def test_import_rejects_symlink_special_files_and_unknown_asset_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            d, p = fixture()
            src = root / 'src'
            src.mkdir()
            save(src / 'CAPSULE.json', d)
            (root / 'data').write_bytes(p)
            (src / 'BLOCK_PACKAGE.json').symlink_to(root / 'data')
            with self.assertRaises(ValueError):
                Registry(root / 'home').import_case(src)
        d, p = fixture()
        d['assets']['../escape'] = d['assets'].pop('BLOCK_PACKAGE.json')
        with self.assertRaises(ValueError):
            validate(seal(d), p)

    def test_separate_homes_do_not_share_imported_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            d, p = fixture()
            src = root / 'src'
            src.mkdir()
            save(src / 'CAPSULE.json', d)
            (src / 'BLOCK_PACKAGE.json').write_bytes(p)
            first, second = Registry(root / 'first'), Registry(root / 'second')
            first.import_case(src)
            second.import_case(src)
            first_path, _ = first.resolve('one')
            second_path, _ = second.resolve('one')
            self.assertNotEqual(first_path, second_path)
            (first_path / 'BLOCK_PACKAGE.json').write_bytes(b'corrupt only first home')
            with self.assertRaises(ValueError):
                first.resolve('one')
            self.assertEqual(second.resolve('one')[1]['capsuleId'], d['capsuleId'])
if __name__ == '__main__':
    unittest.main()
