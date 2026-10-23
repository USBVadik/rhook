"""Synthetic lifecycle and fail-closed tests. All sensors and dispatch are mocked."""
import contextlib
import ast
import io
import json
import subprocess
from pathlib import Path
import tempfile
import sys
import time
import types
import unittest
from unittest.mock import patch
from plan_native import core, launch


class Workflow(unittest.TestCase):
    def test_cli_status_reflects_recorded_operation_result(self):
        # Execute the real CLI block; replace only the native-capable operation.
        tree = ast.parse(Path(launch.__file__).read_text())
        cli = compile(ast.Module(body=[tree.body[-1]], type_ignores=[]), launch.__file__, 'exec')
        for terminal, expected in [('HOST_STOP', 1), ('INTERRUPTED_UNVERIFIED', 1),
                                   ('GO_HOOKR_PLAN_PAIR_OBSERVED_UNQUALIFIED', 0)]:
            with self.subTest(terminal=terminal), patch.object(launch, 'execute', return_value={'terminal': terminal}), \
                 patch.object(sys, 'argv', ['launch', '--bindings', 'unused', '--authority', 'unused',
                                           '--build-record', 'unused', '--binary', 'unused']), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                namespace = dict(vars(launch), __name__='__main__')
                code = 0
                try: exec(cli, namespace)
                except SystemExit as error: code = error.code
                self.assertEqual(code, expected)
                self.assertEqual(json.loads(output.getvalue())['terminal'], terminal)

    def run_mock(self, failure=None, completion_payload=None, reaped=True,
                 expected_terminal='INTERRUPTED_UNVERIFIED', expected_counts=None):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root = Path(d); out = root / 'one-operation'
            package, binary, sensor, node = [root / n for n in ['package', 'binary', 'sensor', 'node']]
            package.write_bytes(b'synthetic-package'); binary.write_bytes(b'not-a-native-binary')
            sensor.write_bytes(b'not-a-sensor'); node.write_bytes(b'not-a-node')
            plan, policy = core.inputs(); plan = dict(plan, packageSha256=core.sha(package.read_bytes()))
            build = dict(status='BUILD_ONLY_PASS', sourceCommitment='synthetic-source', runtimePlanSha256=core.PLAN_SHA,
                         productionWorkerLaunched=False, binarySha256=core.sha(binary.read_bytes()))
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(launch, 'inputs', return_value=(plan, policy)))
                stack.enter_context(patch.object(launch, 'source_commitment', return_value='synthetic-source'))
                stack.enter_context(patch.object(launch, 'verifier_dependencies', return_value={'synthetic': 'pin'}))
                b = launch.binding(build, package, out, sensor, node)
                a = dict(launch.pins('synthetic-source'), domain=core.DOMAIN, operationCommitment=b['operationCommitment'],
                         binarySha256=b['binarySha256'], packagePath=b['packagePath'], outputPath=b['outputPath'],
                         founderApproved=True, noRetry=True, macOnPowerOpenLid=True, executionContext='require_escalated',
                         maximumInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0}, RPC=0, WSS=0,
                         notBeforeUnix=int(time.time())-1, expiresUnix=int(time.time())+300)
                paths = [root / n for n in ['binding.json', 'authority.json', 'build.json']]
                for path, value in zip(paths, [b, a, build]): path.write_bytes(core.canonical(value))
                admission = stack.enter_context(patch.object(launch, 'admission', return_value=({'status': 'PASS'}, [{}])))
                if failure == 'admission': admission.side_effect = ValueError('SYNTHETIC_LOW_RAM')
                def fake_native(raw, output, sensor, previous):
                    result = dict(exitCode=0, stop=None, workerReaped=reaped, resourcesReliable=True)
                    if failure == 'native': raise RuntimeError('SYNTHETIC_NATIVE_FAILURE')
                    if completion_payload is not None:
                        payload = completion_payload(b['operationCommitment']) if callable(completion_payload) else completion_payload
                        (output / 'runtime/NATIVE_COMPLETION.json').write_bytes(payload)
                    return result
                native = stack.enter_context(patch.object(launch, 'supervise', side_effect=fake_native))
                completion_check = stack.enter_context(patch.object(launch, 'verify_completion', return_value={}))
                if failure == 'completion': completion_check.side_effect = ValueError('SYNTHETIC_COMPLETION_REJECTED')
                verified = dict(status='RECORDED_PAIR_INTEGRITY_PASS', qualifiedClaims=0,
                                economicAssurance='UNRESOLVED', heterogeneousAgreement='NOT_EVALUATED')
                def fake_verify(command, **kwargs):
                    if failure != 'empty-verifier': kwargs['stdout'].write(core.canonical(verified))
                    return types.SimpleNamespace(returncode=1 if failure == 'verify' else 0)
                verifier = stack.enter_context(patch.object(launch.subprocess, 'run', side_effect=fake_verify))
                final = launch.execute(*paths, binary)
                if failure == 'admission':
                    self.assertEqual(final['terminal'], 'HOST_STOP'); native.assert_not_called(); verifier.assert_not_called()
                elif failure == 'native':
                    self.assertEqual(final['terminal'], 'INTERRUPTED_UNVERIFIED'); verifier.assert_not_called()
                    self.assertFalse((out / 'MANIFEST.json').exists())
                    self.assertIsNone(final['nativeInvocations'])
                elif failure == 'completion':
                    self.assertEqual(final['terminal'], expected_terminal)
                    self.assertEqual(final['nativeInvocations'], expected_counts)
                    self.assertEqual(json.loads((out / 'runtime/FINAL_RESULT.json').read_text()), final)
                    if completion_payload is not None:
                        original = (out / 'runtime/NATIVE_COMPLETION.json').read_bytes()
                        self.assertEqual(final['recordedNativeCompletion'],
                                         {'path': 'runtime/NATIVE_COMPLETION.json', 'sha256': core.sha(original)})
                    verifier.assert_not_called()
                    if not reaped:
                        self.assertFalse((out / 'MANIFEST.json').exists())
                        self.assertIs(final['resources']['workerReaped'], False)
                elif failure:
                    self.assertEqual(final['terminal'], 'INTERRUPTED_UNVERIFIED')
                else:
                    self.assertEqual(final['terminal'], 'GO_HOOKR_PLAN_PAIR_OBSERVED_UNQUALIFIED')
                    self.assertEqual(final['nativeInvocations'], {'ACTUAL': 1, 'BRANCH': 1, 'B': 0})
                    self.assertTrue((out / 'MANIFEST.json').exists())
                # A second call with the same approved identity cannot reach a sensor.
                calls = admission.call_count
                with self.assertRaises(ValueError): launch.execute(*paths, binary)
                self.assertEqual(admission.call_count, calls)

    def test_synthetic_success_and_second_entry_rejection(self): self.run_mock()
    def test_admission_failure_prevents_dispatch(self): self.run_mock('admission')
    def test_native_failure_prevents_verifier_and_completion_seal(self): self.run_mock('native')
    def test_verifier_error_cannot_become_pass(self): self.run_mock('verify')
    def test_empty_successful_verifier_cannot_become_pass(self): self.run_mock('empty-verifier')

    def test_malformed_or_truncated_completion_preserves_terminal_evidence(self):
        for payload in [b'{', b'{"result":', b'{"result":{"terminal":"HOST_STOP"']:
            with self.subTest(payload=payload): self.run_mock('completion', completion_payload=payload)

    def test_deep_completion_cannot_break_final_result_serialization(self):
        # Isolate the recursion boundary from the unittest runner's call stack.
        code = """from plan_native.test.test_workflow import Workflow
for depth in [980, 985, 989, 990, 993, 995, 999, 1001]:
    Workflow().run_mock('completion', completion_payload=b'[' * depth + b'0' + b']' * depth)
"""
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=core.HERE.parent,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TZ': 'UTC'},
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_structurally_incomplete_completion_does_not_infer_counts(self):
        for result in [None, [], {}, {'terminal': 'HOST_STOP'},
                       {'terminal': 'HOST_STOP', 'nativeInvocations': None},
                       {'terminal': 'HOST_STOP', 'nativeInvocations': {'ACTUAL': 1}},
                       {'terminal': 'HOST_STOP', 'nativeInvocations': {'ACTUAL': True, 'BRANCH': 0, 'B': 0}}]:
            with self.subTest(result=result):
                self.run_mock('completion', completion_payload=lambda op: core.canonical({'operationCommitment': op, 'result': result}))

    def test_valid_recorded_stop_is_retained_without_becoming_success(self):
        result = dict(terminal='BRANCH_HOST_STOP', nativeInvocations={'ACTUAL': 1, 'BRANCH': 1, 'B': 0},
                      canonicalActualValid=True, RPC=0, WSS=0, economicAssurance='UNRESOLVED',
                      heterogeneousAgreement='NOT_EVALUATED', externalDelivery='HOLD', cause='SYNTHETIC_MISSING_WITNESS')
        self.run_mock('completion', completion_payload=lambda op: core.canonical({'operationCommitment': op, 'result': result}),
                      expected_terminal='BRANCH_HOST_STOP', expected_counts={'ACTUAL': 1, 'BRANCH': 1, 'B': 0})

    def test_unbound_or_invalid_recorded_stop_cannot_supply_terminal_or_counts(self):
        valid = dict(terminal='HOST_STOP', nativeInvocations={'ACTUAL': 0, 'BRANCH': 0, 'B': 0},
                     canonicalActualValid=False, RPC=0, WSS=0, economicAssurance='UNRESOLVED',
                     heterogeneousAgreement='NOT_EVALUATED', externalDelivery='HOLD')
        changes = [('nativeInvocations', {'ACTUAL': True, 'BRANCH': 0, 'B': 0}),
                   ('nativeInvocations', {'ACTUAL': 0, 'BRANCH': 1, 'B': 0}),
                   ('nativeInvocations', {'ACTUAL': 1, 'BRANCH': 1, 'B': 1}),
                   ('nativeInvocations', None), ('terminal', 'SUCCESS'), ('RPC', 1),
                   ('economicAssurance', 'QUALIFIED'), ('canonicalActualValid', None)]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                result = dict(valid); result[key] = value
                self.run_mock('completion', completion_payload=lambda op: core.canonical({'operationCommitment': op, 'result': result}))
        self.run_mock('completion', completion_payload=core.canonical({'operationCommitment': 'OLD_OPERATION', 'result': valid}))
        for payload in [b'null', b'[]']:
            self.run_mock('completion', completion_payload=payload)

    def test_unconfirmed_cleanup_never_infers_counts_or_seals(self):
        self.run_mock('completion', completion_payload=b'{', reaped=False)


if __name__ == '__main__': unittest.main()
