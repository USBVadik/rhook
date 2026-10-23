"""Synthetic admission tests only: no saved block, sensor, EVM or provider."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / 'repro/portable_pair03.py'


def load():
    if not MODULE.is_file():
        raise AssertionError('Portable launcher not implemented')
    spec = importlib.util.spec_from_file_location('portable_pair03', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableAdmission(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def fixture(self):
        spec = self.m.specification(REPO)
        cp = spec['checkpoint']
        rules = spec['intervention']
        package = {
            'checkpoint': cp,
            'parent': {'number': hex(cp['blockNumber']), 'hash': cp['blockHash'], 'stateRoot': cp['stateRoot']},
            'block': {'number': hex(spec['blockNumber']), 'hash': spec['blockHash'],
                      'parentHash': cp['blockHash'], 'stateRoot': spec['stateRoot'],
                      'receiptsRoot': spec['receiptsRoot'],
                      'transactions': [{'hash': h, 'transactionIndex': hex(i),
                                        'chainId': hex(4663), 'blockHash': spec['blockHash'],
                                        'blockNumber': hex(spec['blockNumber'])}
                                       for i, h in enumerate(spec['arrivals'])]},
            'rawTransactions': ['0x01'] * 7, 'state': ['0x01'], 'codes': ['0x01'],
            'proofs': [{'address': rules['account'], 'slots': [rules['slot']],
                        'proof': {'codeHash': self.m.RULES_CODE_HASH,
                                  'storageProof': [{'key': rules['slot'], 'value': rules['expectedOldWord']}]}}],
        }
        return spec, package

    def encoded(self, spec, package):
        raw = json.dumps(package).encode()
        spec['packageSha256'] = hashlib.sha256(raw).hexdigest()
        return raw

    def test_explicit_local_package_validates_without_network(self):
        spec, package = self.fixture()
        raw = self.encoded(spec, package)
        with patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            self.m.validate_package(raw, spec)

    def test_package_hash_mismatch(self):
        spec, package = self.fixture()
        raw = self.encoded(spec, package)
        with self.assertRaisesRegex(ValueError, 'PACKAGE_SHA256'):
            self.m.validate_package(raw + b' ', spec)

    def test_all_seven_arrivals_and_order_required(self):
        for change in ('missing', 'reordered', 'raw-missing'):
            with self.subTest(change=change):
                spec, package = self.fixture()
                if change == 'missing':
                    package['block']['transactions'].pop()
                elif change == 'raw-missing':
                    package['rawTransactions'].pop()
                else:
                    package['block']['transactions'].reverse()
                raw = self.encoded(spec, package)
                with self.assertRaisesRegex(ValueError, 'ARRIVALS'):
                    self.m.validate_package(raw, spec)

    def test_checkpoint_chain_header_and_rules_fail_closed(self):
        for change in ('chain', 'parent', 'block', 'rules-code', 'rules-slot', 'rules-conflict'):
            with self.subTest(change=change):
                spec, package = self.fixture()
                package = copy.deepcopy(package)
                if change == 'chain': package['checkpoint']['chainId'] = 1
                if change == 'parent': package['parent']['stateRoot'] = '0x00'
                if change == 'block': package['block']['parentHash'] = '0x00'
                if change == 'rules-code': package['proofs'][0]['proof']['codeHash'] = '0x00'
                if change == 'rules-slot': package['proofs'][0]['proof']['storageProof'][0]['value'] = '0x01'
                if change == 'rules-conflict':
                    other = copy.deepcopy(package['proofs'][0])
                    other['proof']['storageProof'][0]['value'] = '0x01'
                    package['proofs'].append(other)
                raw = self.encoded(spec, package)
                with self.assertRaises(ValueError): self.m.validate_package(raw, spec)

    def test_missing_directory_and_symlink_input_rejected(self):
        with self.assertRaises(ValueError): self.m.local_file(self.root / 'missing')
        with self.assertRaises(ValueError): self.m.local_file(self.root)
        real = self.root / 'real'; real.write_text('data')
        link = self.root / 'link'; link.symlink_to(real)
        with self.assertRaises(ValueError): self.m.local_file(link)
        with self.assertRaises(ValueError): self.m.local_file('https://example.invalid/package')

    def test_output_is_fresh_and_disjoint(self):
        source = self.root / 'package'; source.write_text('data')
        out = self.root / 'new'
        self.assertEqual(self.m.fresh_output(out, [source]), out)
        out.mkdir()
        with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_USED'):
            self.m.fresh_output(out, [source])
        with self.assertRaises(ValueError): self.m.fresh_output(self.root / 'absent' / 'out', [source])

    def binding(self):
        b = {'operationCommitment': 'a'*64, 'binarySha256': 'b'*64,
             'packagePath': str(self.root/'package'), 'outputPath': str(self.root/'output'),
             'nodePath': str(self.root/'node'), 'executionContext': 'require_escalated'}
        now = int(time.time())
        a = dict(b, domain='PORTABLE_SAVED_PAIR03', founderApproved=True,
                 maximumInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, RPC=0, WSS=0,
                 notBeforeUnix=now-1, expiresUnix=now+200, macOnPowerOpenLid=True, noRetry=True)
        return b, a, now

    def test_missing_unapproved_expired_or_wrong_scope_authority_rejected(self):
        b, a, now = self.binding()
        self.m.authority(json.dumps(a).encode(), b, now)
        for field, value in [('founderApproved', False), ('operationCommitment', 'c'*64),
                             ('expiresUnix', now), ('RPC', 1), ('WSS', 1),
                             ('noRetry', False), ('executionContext', 'default'),
                             ('maximumInvocations', {'ACTUAL': 2, 'BRANCH': 1, 'B': 0}),
                             ('packagePath', '/different'), ('outputPath', '/different')]:
            with self.subTest(field=field):
                bad = dict(a); bad[field] = value
                with self.assertRaises(ValueError): self.m.authority(json.dumps(bad).encode(), b, now)

    def test_absent_authority_rejected_before_host_or_worker_and_no_output(self):
        with patch.object(self.m, 'host_admission', side_effect=AssertionError('SENSOR_FORBIDDEN')), \
             patch.object(self.m.guards, 'monitored', side_effect=AssertionError('WORKER_FORBIDDEN')):
            with self.assertRaises(ValueError):
                self.m.replay(REPO, self.root/'missing-bindings', self.root/'missing-authority',
                              self.root/'package', self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_preserved_engine_and_guard_functions(self):
        report = self.m.verify_preserved(REPO)
        self.assertEqual(report['nativeFiles'], 65)
        self.assertEqual(report['guardFunctions'], 8)

    def workflow(self):
        spec, package = self.fixture()
        raw = self.encoded(spec, package)
        source = self.root/'package.json'; source.write_bytes(raw)
        binary = self.root/'worker'; binary.write_bytes(b'synthetic artifact'); binary.chmod(0o700)
        node = self.root/'node'; node.write_bytes(b'not executable')
        out = self.root/'output'; proposal = self.root/'proposal'
        record = self.root/'BUILD_RESULT.json'
        record.write_text(json.dumps({'status':'PORTABLE_ADAPTER_BUILD_ONLY_PASS', 'binaryPath':str(binary),
            'binarySha256':self.m.sha(binary), 'planSha256':self.m.sha(REPO/'repro/portable/plan.json'),
            'sourceFiles':self.m.source_closure(REPO), 'nativeInvocations':{'ACTUAL':0,'BRANCH':0,'B':0}}))
        return spec, source, binary, node, out, proposal, record

    def test_build_provenance_rejects_unrelated_binary_and_source_drift(self):
        spec, source, binary, node, out, proposal, record = self.workflow()
        binary.write_bytes(b'unrelated worker')
        with self.assertRaisesRegex(ValueError, 'BUILD_BINARY'):
            self.m.verify_build(REPO, binary, record)
        value = json.loads(record.read_text()); value['binarySha256'] = self.m.sha(binary)
        value['sourceFiles']['repro/portable/main.go'] = 'wrong'
        record.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'BUILD_SOURCE'):
            self.m.verify_build(REPO, binary, record)

    def test_host_stop_closes_operation_without_worker_or_retry(self):
        spec, source, binary, node, out, proposal, record = self.workflow()
        with patch.object(self.m, 'specification', return_value=copy.deepcopy(spec)):
            # verify_preserved compares the real embedded plans; keep that
            # contract separate from this synthetic file/latch workflow test.
            with patch.object(self.m, 'verify_preserved', return_value={'nativeFiles':65, 'guardFunctions':8}):
                b = self.m.prepare(REPO, binary, source, out, node, proposal, record)
                a = json.loads((proposal/'AUTHORIZATION_TEMPLATE_NOT_GRANTED.json').read_text())
                self.assertFalse(a['founderApproved'])
                a.update(founderApproved=True, notBeforeUnix=int(time.time())-1,
                         expiresUnix=int(time.time())+250, macOnPowerOpenLid=True)
                authority = self.root/'authority'; authority.write_text(json.dumps(a))
                with patch.object(self.m, 'host_admission', return_value=(False, {'status':'SYNTHETIC_HOST_STOP'})), \
                     patch.object(self.m.guards, 'monitored', side_effect=AssertionError('WORKER_FORBIDDEN')):
                    result = self.m.replay(REPO, proposal/'AUTHORIZATION_BINDINGS.json', authority, source, out)
                    self.assertEqual(result['terminal'], 'HOST_STOP')
                    self.assertEqual(result['nativeInvocations'], {'ACTUAL':0, 'BRANCH':0, 'B':0})
                    self.assertTrue(result['authorityPermanentlyClosed'])
                    self.assertTrue((out/'runtime/FINAL_RESULT.json').is_file())
                    with self.assertRaisesRegex(ValueError, 'OUTPUT_ALREADY_USED'):
                        self.m.replay(REPO, proposal/'AUTHORIZATION_BINDINGS.json', authority, source, out)

    def test_reliably_recorded_native_stop_keeps_counts_and_exact_cause(self):
        result = {'terminal':'BRANCH_HOST_STOP', 'cause':'CODE_SOURCE_UNAVAILABLE',
                  'nativeInvocations':{'ACTUAL':1,'BRANCH':1,'B':0}, 'actualCanonicalValid':True}
        final = {'terminal':'INTERRUPTED_UNVERIFIED'}
        measured = {'stop':None,'resourcesReliable':True,'workerReaped':True,'exitCode':1}
        self.m.reconcile_completion(final, measured, {'result':result})
        self.assertEqual(final, result)
        measured['stop'] = 'SAMPLED_WORKER_RSS_LIMIT'
        final = {'terminal':'INTERRUPTED_UNVERIFIED'}
        self.m.reconcile_completion(final, measured, {'result':result})
        self.assertEqual(final['terminal'], 'INTERRUPTED_UNVERIFIED')

    def test_success_with_nonzero_exit_remains_unverified(self):
        final = {'terminal':'INTERRUPTED_UNVERIFIED'}
        measured = {'stop':None,'resourcesReliable':True,'workerReaped':True,'exitCode':1}
        self.m.reconcile_completion(final, measured, {'result':{'terminal':'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'}})
        self.assertEqual(final['terminal'], 'INTERRUPTED_UNVERIFIED')

    def test_missing_baseline_records_cannot_report_success(self):
        final = {'terminal':'INTERRUPTED_UNVERIFIED'}
        measured = {'stop':None,'resourcesReliable':True,'workerReaped':True,'exitCode':0}
        native = {'result':{'terminal':'GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'}}
        with self.assertRaises(FileNotFoundError):
            self.m.accept_native_completion(REPO, self.root, final, measured, native)
        self.assertEqual(final['terminal'], 'INTERRUPTED_UNVERIFIED')

    def test_consumption_fsyncs_ancestors_before_host(self):
        out = self.root/'output'
        calls = []
        actual_sync = self.m.sync_directory
        def observed_sync(path):
            calls.append(Path(path)); actual_sync(path)
        with patch.object(self.m, 'sync_directory', side_effect=observed_sync):
            rt = self.m.consume_output(out)
        self.assertEqual(calls, [out.parent, out])
        self.assertEqual(rt, out/'runtime')
        self.assertTrue(rt.is_dir())

    def test_exact_baseline_comparison_preserves_mismatch(self):
        # Synthetic records with all compared fields. No historical file access.
        repo = self.root/'repo'; (repo/'repro/portable').mkdir(parents=True)
        rt = self.root/'runtime'; rt.mkdir()
        fields = ['world','inputCommitment','witnessCommitment','stateRoot','receiptsRoot',
                  'blockHash','transactions','gasUsed','receipts','observation']
        baseline = {}
        for world in ['ACTUAL', 'BRANCH']:
            result = {k: 7 for k in fields}; result.update(world=world, observation={'output':'123', 'fees':'0'})
            baseline[world] = {'projectionSha256':self.m.commitment(result)}
            (rt/(world+'.json')).write_text(json.dumps({'result':result,'error':'','missingLookupAttempts':None}))
        (repo/'repro/portable/baseline.json').write_text(json.dumps(baseline))
        self.assertEqual(self.m.compare_baseline(repo, rt)['status'], 'PASS')
        file = rt/'BRANCH.json'; changed = json.loads(file.read_text())
        changed['result']['observation']['output'] = '124'; file.write_text(json.dumps(changed))
        self.assertEqual(self.m.compare_baseline(repo, rt)['status'], 'PAIR03_BASELINE_MISMATCH')
        self.assertEqual(json.loads(file.read_text())['result']['observation']['output'], '124')


if __name__ == '__main__':
    unittest.main()
