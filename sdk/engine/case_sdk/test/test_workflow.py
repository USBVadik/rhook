import contextlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from case_sdk import common as c, contract as p, workflow as w
PACKAGE = Path(os.environ['RHOOK_PACKAGE']).read_bytes()

class WorkflowTest(unittest.TestCase):

    def setup_case(self, root):
        root = Path(root).resolve()
        workspace = root / 'case'
        workspace.mkdir()
        (workspace / 'plans').mkdir()
        (workspace / 'runs').mkdir()
        ref = '0' * 32
        plans = workspace / 'plans' / ref
        plans.mkdir()
        pkg = workspace / 'BLOCK_PACKAGE.json'
        pkg.write_bytes(PACKAGE)
        plan = p.make_plan(PACKAGE, '100', '50')
        semantic = plans / 'semantic.json'
        semantic.write_bytes(plan.semantic_bytes)
        runtime = plans / 'runtime.json'
        runtime.write_bytes(plan.runtime_bytes)
        worker = root / 'worker'
        sensor = root / 'sensor'
        node = root / 'node'
        for f in [worker, sensor, node]:
            f.write_bytes(b'non-executable-fixture')
        files = c.sources()
        node = Path(os.environ['RHOOK_NODE'])
        build = {'schema': 'rhook/case-sdk-build/0.1', 'status': 'BUILD_ONLY_PASS', 'sourceCommitment': c.sha(c.canonical(files)), 'sourceFiles': files, 'caseDescriptorSha256': c.sha(c.read(c.HERE / 'case.json')), 'policySha256': c.sha(c.read(c.HERE / 'policy.json')), 'workerPath': str(worker), 'binarySha256': c.sha(worker.read_bytes()), 'sensorPath': str(sensor), 'sensorSha256': c.sha(sensor.read_bytes()), 'nodePath': str(node), 'nodeSha256': c.sha(node.read_bytes()), 'verifierDependenciesCommitment': p.dependencies_commitment(), 'productionWorkerLaunched': False}
        paths = {'workspace': str(workspace), 'planId': ref, 'outputPath': str(workspace / 'runs' / ref), 'packagePath': str(pkg), 'semanticPlanPath': str(semantic), 'runtimePlanPath': str(runtime)}
        binding = p.prepare_request(build, plan, paths)
        bp = plans / 'BINDINGS.json'
        bp.write_bytes(c.canonical(binding))
        buildp = root / 'BUILD.json'
        buildp.write_bytes(c.canonical(build))
        approval = dict(binding, founderApproved=True, macOnPowerOpenLid=True, noRetry=True, notBeforeUnix=int(time.time()) - 1, expiresUnix=int(time.time()) + 300)
        ap = root / 'APPROVAL.json'
        ap.write_bytes(c.canonical(approval))
        return (bp, ap, buildp, binding)

    def test_approval_rejects_substitution_and_short_window(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            bp, ap, buildp, b = self.setup_case(d)
            a = c.strict(ap.read_bytes())
            p.validate_approval(b, ap.read_bytes(), int(time.time()))
            for field, value in [('runtimePlanSha256', '0' * 64), ('domain', 'HOOKR_PLAN_NATIVE_0_1'), ('founderApproved', 1), ('expiresUnix', int(time.time()) + 10)]:
                bad = dict(a)
                bad[field] = value
                with self.assertRaises(ValueError):
                    p.validate_approval(b, c.canonical(bad), int(time.time()))

    def run_case(self, mode):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            bp, ap, buildp, b = self.setup_case(d)
            out = Path(b['outputPath'])

            def admission(sensor, directory):
                directory.mkdir()
                child = directory / 'sample-0'
                child.mkdir()
                c.store(child / 'RESULT.json', {'ownedChildReaped': True})
                if mode == 'low-ram':
                    raise ValueError('INSUFFICIENT_FREE_HEADROOM')
                return ({'status': 'PASS'}, [{}])

            def native(raw, output, sensor, previous):
                if mode == 'raise-native':
                    raise RuntimeError('SYNTHETIC_FAILURE')
                rt = output / 'runtime'
                if mode in ['full', 'deadline']:
                    import shutil
                    fixture = Path(os.environ['RHOOK_FIXTURE_50']) / 'runtime'
                    for name in ['ACTUAL.json', 'BRANCH.json', 'COMPARISON.json']:
                        shutil.copyfile(fixture / name, rt / name)
                    n = c.strict((fixture / 'NATIVE_COMPLETION.json').read_bytes())
                    n.update(operationCommitment=b['operationCommitment'], runtimePlanSha256=b['runtimePlanSha256'])
                    c.store(rt / 'NATIVE_COMPLETION.json', n)
                    previous = ''
                    lines = []
                    for line in (fixture / 'JOURNAL.jsonl').read_bytes().splitlines():
                        row = c.strict(line)
                        row['previousSha256'] = previous
                        row['utc'] = c.portable.guards.utc()
                        raw = c.canonical(row)
                        lines.append(raw)
                        previous = c.sha(raw)
                    (rt / 'JOURNAL.jsonl').write_bytes(b'\n'.join(lines) + b'\n')
                    measured = {'stop': None, 'workerReaped': True, 'exitCode': 0, 'resourcesReliable': True, 'wallSeconds': 1.25, 'workerAndObserverCpuSeconds': 0.25, 'sampledPeakWorkerRSS': 100, 'samples': 3, 'stdoutStderrBytes': 0}
                    c.store(rt / 'PROCESS_COMPLETION.json', measured)
                    return measured
                if mode == 'deep':
                    (rt / 'NATIVE_COMPLETION.json').write_bytes(b'[' * 65 + b'0' + b']' * 65)
                elif mode == 'missing':
                    result = {'terminal': 'BRANCH_HOST_STOP', 'nativeInvocations': {'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, 'canonicalActualValid': True, 'RPC': 0, 'WSS': 0, 'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED', 'externalDelivery': 'HOLD', 'cause': 'typed missing state'}
                    c.store(rt / 'NATIVE_COMPLETION.json', {'operationCommitment': b['operationCommitment'], 'runtimePlanSha256': b['runtimePlanSha256'], 'result': result, 'failureDetail': {'classification': 'HOST_STOP_MISSING_STATE', 'phase': 'BRANCH', 'code': 'CODE_SOURCE_UNAVAILABLE'}})
                return {'stop': None, 'workerReaped': mode != 'unreaped', 'exitCode': 1, 'resourcesReliable': True, 'wallSeconds': 1, 'workerAndObserverCpuSeconds': 1, 'sampledPeakWorkerRSS': 100}
            real_clock = time.monotonic
            real_verifier = w.run_verifier
            late = {'value': False}

            def verifier(*args):
                result = real_verifier(*args)
                late['value'] = mode == 'deadline'
                return result
            with patch.object(w, 'admission', side_effect=admission), patch.object(w, 'supervise', side_effect=native), patch.object(w, 'run_verifier', side_effect=verifier) if mode in ['full', 'deadline'] else patch.object(w, 'run_verifier', side_effect=AssertionError('unexpected verifier')), patch.object(w.time, 'monotonic', side_effect=lambda: real_clock() + (181 if late['value'] else 0)):
                result = w.execute(bp, ap, buildp)
                self.assertEqual(json.loads((out / 'runtime/FINAL_RESULT.json').read_text()), result)
                if mode == 'full':
                    self.assertEqual(result['status'], 'COMPLETED')
                    self.assertEqual(result['nativeInvocations'], {'ACTUAL': 1, 'BRANCH': 1, 'B': 0})
                elif mode == 'deadline':
                    self.assertEqual(result['status'], 'VERIFICATION_FAILED')
                    self.assertIn('WORKFLOW_DEADLINE', result['cause'])
                    self.assertEqual(result['nativeInvocations'], {'ACTUAL': 1, 'BRANCH': 1, 'B': 0})
                elif mode == 'low-ram':
                    self.assertEqual(result['status'], 'HOST_STOP')
                    self.assertEqual(result['nativeInvocations'], {'ACTUAL': 0, 'BRANCH': 0, 'B': 0})
                elif mode == 'missing':
                    self.assertEqual(result['status'], 'MISSING_WITNESS')
                    self.assertEqual(result['nativeInvocations']['BRANCH'], 1)
                else:
                    self.assertEqual(result['status'], 'INTERRUPTED_UNVERIFIED')
                    self.assertIsNone(result['nativeInvocations'])
                if mode in ['unreaped', 'raise-native']:
                    self.assertFalse((out / 'MANIFEST.json').exists())
                with self.assertRaises(ValueError):
                    w.execute(bp, ap, buildp)

    def test_mock_dispatch_with_real_recorded_verification(self):
        self.run_case('full')

    def test_low_ram_closes_without_dispatch(self):
        self.run_case('low-ram')

    def test_typed_missing_state_preserves_counts(self):
        self.run_case('missing')

    def test_deep_completion_stays_partial(self):
        self.run_case('deep')

    def test_uncertain_worker_cleanup_cannot_seal(self):
        self.run_case('unreaped')

    def test_supervisor_exception_cannot_invent_exit(self):
        self.run_case('raise-native')

    def test_process_mutex_rejects_nested_other_workspace(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root = Path(d)
            a = root / 'a'
            a.mkdir()
            b = root / 'b'
            b.mkdir()
            with w.operation_lock(a):
                with self.assertRaises(ValueError):
                    with w.operation_lock(b):
                        pass

    def test_malformed_sensor_cleanup_cannot_claim_confirmation(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            out = Path(d)
            child = out / 'runtime/HOST/sample-0'
            child.mkdir(parents=True)
            (child / 'RESULT.json').write_bytes(b'{')
            self.assertFalse(w.cleanup_confirmed(out, False, None, True))

    def test_deadline_failure_cannot_be_promoted_during_recovery(self):
        self.run_case('deadline')

    def test_bool_binding_substitutions_stop_before_consumption(self):
        for field in ['RPC', 'maximumInvocations']:
            with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
                bp, ap, buildp, b = self.setup_case(d)
                a = c.strict(ap.read_bytes())
                b[field] = False if field == 'RPC' else {'ACTUAL': True, 'BRANCH': 1, 'B': 0}
                a[field] = b[field]
                bp.write_bytes(c.canonical(b))
                ap.write_bytes(c.canonical(a))
                with patch.object(w, 'admission', side_effect=AssertionError('sensors reached')):
                    with self.assertRaisesRegex(ValueError, 'SEALED_BINDING_DRIFT'):
                        w.execute(bp, ap, buildp)
                self.assertFalse(Path(b['outputPath']).exists())

    def test_missing_authority_file_stops_without_consumption(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            bp, ap, buildp, b = self.setup_case(d)
            ap.unlink()
            with self.assertRaisesRegex(ValueError, 'NOT_AUTHORIZED'):
                w.execute(bp, ap, buildp)
            self.assertFalse(Path(b['outputPath']).exists())
