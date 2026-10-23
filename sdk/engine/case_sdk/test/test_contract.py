import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from case_sdk import common as c, contract as p
ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(os.environ['RHOOK_PACKAGE']).read_bytes()
NODE = os.environ['RHOOK_NODE']

class ContractTest(unittest.TestCase):

    def test_all_100_values_cross_language(self):
        script = "import {planCase} from './adapters/hookr-case/runtime.ts';import fs from 'node:fs';const raw=fs.readFileSync(process.argv[1]);console.log(JSON.stringify(Array.from({length:100},(_,i)=>planCase(raw,{expectedOld:'100',newValue:String(i)}))));"
        result = subprocess.run([NODE, '--import', './adapters/hookr-case/test/no-network.mjs', '--input-type=module', '-e', script, os.environ['RHOOK_PACKAGE']], cwd=ROOT, capture_output=True, check=True)
        for n, semantic in enumerate(json.loads(result.stdout)):
            checked = p.validate_semantic(PACKAGE, semantic)
            runtime = c.strict(checked.runtime_bytes)
            self.assertEqual(checked.new_value, str(n))
            old = int(runtime['plan']['intervention']['expectedOldWord'], 16)
            new = int(runtime['plan']['intervention']['newWord'], 16)
            self.assertEqual(new >> 160 & 65535, n)
            self.assertEqual((old ^ new) & ~(65535 << 160), 0)
            self.assertEqual(p.validate_runtime(PACKAGE, checked.runtime_bytes), checked)
            self.assertIsNone(semantic['branchResult'])

    def test_protocol_rejects_rehashed_changes(self):
        valid = p.make_plan(PACKAGE, '100', '50')
        for field in ['caseId', 'packageSha256', 'caseDescriptorSha256', 'ruleId']:
            v = c.strict(valid.semantic_bytes)
            v[field] = 'wrong'
            v['planCommitment'] = c.commit('rhook/hookr-plan/0.2', {k: x for k, x in v.items() if k != 'planCommitment'})
            with self.assertRaises(ValueError):
                p.validate_semantic(PACKAGE, v)
        for field in ['checkpoint', 'arrivals', 'intervention', 'observation']:
            v = c.strict(valid.runtime_bytes)
            v['plan'][field] = {}
            with self.assertRaises(ValueError):
                p.validate_runtime(PACKAGE, c.canonical(v) + b'\n')
        for n in ['100', '101', '-1', '00', '01', '1e1', True, 50, '9' * 5000]:
            with self.assertRaises(ValueError):
                p.make_plan(PACKAGE, '100', n)

    def test_bounded_input_rejects_invalid_json_and_special_files(self):
        for raw in [b'{"a":1,"a":2}', b'"\xff"', b'1e1', b'NaN', b'[' * 65 + b'0' + b']' * 65]:
            with self.assertRaises(ValueError):
                c.strict(raw)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d).resolve() / 'input'
            f.write_bytes(b'{}')
            self.assertEqual(c.read(f, 2), b'{}')
            with self.assertRaises(ValueError):
                c.read(f, 1)
            link = Path(d).resolve() / 'link'
            link.symlink_to(f)
            with self.assertRaises(ValueError):
                c.read(link, 10)
            fifo = Path(d).resolve() / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                c.read(fifo, 10)

class ResultTest(unittest.TestCase):

    def test_result_status_keeps_missing_state_separate_from_revert(self):
        self.assertEqual(p.normalize_result('HOST_STOP', None, {'dispatched': False})['nativeInvocations'], {'ACTUAL': 0, 'BRANCH': 0, 'B': 0})
        self.assertEqual(p.normalize_result('GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED', None, {'verified': False})['status'], 'INTERRUPTED_UNVERIFIED')
        self.assertEqual(p.normalize_result('BRANCH_HOST_STOP', {'classification': 'HOST_STOP_MISSING_STATE', 'code': 'CODE_SOURCE_UNAVAILABLE'}, {'typedFailureVerified': True})['status'], 'MISSING_WITNESS')
        self.assertEqual(p.normalize_result('BRANCH_HOST_STOP', {'classification': 'HOST_STOP_MISSING_STATE'}, {})['status'], 'HOST_STOP')
        self.assertEqual(p.normalize_result('GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED', None, {'verified': True, 'cleanupConfirmed': True, 'resourcesVerified': True, 'counts': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'subjectStatus': 'REVERT'})['status'], 'COMPLETED')

class CompletionBoundaryTest(unittest.TestCase):

    def test_completed_requires_confirmed_pair_counts(self):
        evidence = {'verified': True, 'cleanupConfirmed': True, 'resourcesVerified': True, 'counts': None}
        self.assertEqual(p.normalize_result('GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED', None, evidence)['status'], 'INTERRUPTED_UNVERIFIED')

    def test_known_runtime_resource_stop_is_host_stop(self):
        self.assertEqual(p.normalize_result('RUNTIME_OR_RESOURCE_STOP', None, {'counts': {'ACTUAL': 1, 'BRANCH': 0, 'B': 0}})['status'], 'HOST_STOP')
