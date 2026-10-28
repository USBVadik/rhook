from pathlib import Path
import tempfile
import unittest
from test_capsules import fixture, H
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.adapters import get_adapter
from rhook_alpha.cases.capsule import seal
from developer.files import save

def hookr(case='hookr-one', block=11):
    d, p = fixture(case, block)
    d['arrivals'] = ['0x' + '90' * 32, H]
    d['adapter'] = {'id': 'hookr-1.lp-bps/1', 'config': {'account': '0x4a71c270b1520f94064268102aebd744b0de7942', 'slot': '0x1ad7756ae873b72ee7b85d116a86b7b2c5244640095753f73687752bed4705aa', 'pool': '0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780', 'expectedOldWord': f'0x{100 << 160:064x}', 'rulesRuntimeHash': '0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b', 'subject': H, 'ordinal': 1, 'sender': '0x' + '56' * 20, 'router': '0x' + '78' * 20, 'observation': {'accounts': ['0x' + '56' * 20], 'storage': [{'account': '0x4a71c270b1520f94064268102aebd744b0de7942', 'slot': '0x1ad7756ae873b72ee7b85d116a86b7b2c5244640095753f73687752bed4705aa'}], 'subject': H, 'nativeOrdinal': 1}}}
    return (seal(d), p)

class Plans(unittest.TestCase):

    def test_multiple_interventions_without_case_constants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            sdk = CaseSDK(root / 'home')
            for case, block in [('first', 11), ('second', 12)]:
                d, p = hookr(case, block)
                src = root / case
                src.mkdir()
                save(src / 'CAPSULE.json', d)
                (src / 'BLOCK_PACKAGE.json').write_bytes(p)
                sdk.import_case(src)
                for value in (0, 50, 99):
                    r = sdk.plan(case, {'rule': 'lpBps', 'value': value})
                    self.assertEqual(r['status'], 'PLANNED')
                    self.assertIsNone(r['branchResult'])
                    self.assertFalse(r['executionAuthorized'])
                    plan = sdk.describe(r['planId'])
                    self.assertEqual(plan['capsuleId'], d['capsuleId'])
                    self.assertEqual(plan['runtimePlan']['blockNumber'], block)
                    self.assertEqual(int(plan['runtimePlan']['intervention']['newWord'], 16) >> 160 & 65535, value)

    def test_unknown_adapter_is_importable_but_never_implicitly_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            d, p = fixture()
            src = root / 'src'
            src.mkdir()
            save(src / 'CAPSULE.json', d)
            (src / 'BLOCK_PACKAGE.json').write_bytes(p)
            sdk = CaseSDK(root / 'home')
            sdk.import_case(src)
            with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_ADAPTER'):
                sdk.plan('one', {'rule': 'lpBps', 'value': 50})

    def test_adapter_rejects_extra_bits_bad_range_bad_subject(self):
        d, _ = hookr()
        adapter = get_adapter(d)
        for bad in [True, -1, 100, 0.5, '50']:
            with self.assertRaises(ValueError):
                adapter.plan(d, {'rule': 'lpBps', 'value': bad})
        d['adapter']['config']['ordinal'] = 0
        with self.assertRaises(ValueError):
            adapter.plan(d, {'rule': 'lpBps', 'value': 50})

    def test_planning_needs_no_native_runtime_or_host_admission(self):
        d, _ = hookr()
        r = get_adapter(d).plan(d, {'rule': 'lpBps', 'value': 50})
        self.assertEqual(r['transactions'], 2)
        self.assertNotIn('binarySha256', r)

    def test_core_does_not_select_a_hardcoded_block_or_rule(self):
        from rhook_alpha.cases import api, registry
        for module in (api, registry):
            source = Path(module.__file__).read_text()
            for token in ('93251803', 'lpBps', 'buyerRhook', 'hookr-pair03'):
                self.assertNotIn(token, source)

class PackageCase(unittest.TestCase):

    def test_packaging_declares_data_without_claiming_authentication(self):
        from developer.files import canonical
        d, _ = hookr()
        c = d['adapter']['config']
        pkg = {'checkpoint': d['checkpoint'], 'block': {'number': '0xb', 'hash': H, 'stateRoot': H, 'receiptsRoot': H, 'transactions': [{'hash': '0x' + '90' * 32, 'from': c['sender'], 'to': c['router']}, {'hash': H, 'from': c['sender'], 'to': c['router']}]}, 'proofs': [{'address': c['account'], 'proof': {'storageProof': [{'key': c['slot'], 'value': hex(100 << 160)}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            raw = canonical(pkg)
            (root / 'package').write_bytes(raw)
            sdk = CaseSDK(root / 'home')
            r = sdk.package_case(root / 'package', root / 'out', case_id='my-case', adapter='hookr-1.lp-bps/1', subject_index=1, input_commitment='ab' * 32, witness_commitment='cd' * 32)
            self.assertEqual(r['authentication'], 'UNAUTHENTICATED')
            imported = sdk.import_case(root / 'out')
            self.assertEqual(imported['arrivals'], 2)
            self.assertEqual(imported['witnessClosure'], 'NOT_EVALUATED')

class NativeAdapterCompatibility(unittest.TestCase):

    def test_native_system_arrival_is_not_a_user_subject(self):
        d, _ = hookr()
        d['adapter']['config']['ordinal'] = 0
        d['adapter']['config']['observation']['nativeOrdinal'] = 0
        d['adapter']['config']['subject'] = d['arrivals'][0]
        d['adapter']['config']['observation']['subject'] = d['arrivals'][0]
        with self.assertRaises(ValueError):
            get_adapter(d).plan(d, {'rule': 'lpBps', 'value': 50})

    def test_observation_budget_matches_native_observer(self):
        d, _ = hookr()
        d['adapter']['config']['observation']['accounts'] = [f'0x{i:040x}' for i in range(17)]
        with self.assertRaises(ValueError):
            get_adapter(d).plan(d, {'rule': 'lpBps', 'value': 50})
if __name__ == '__main__':
    unittest.main()
