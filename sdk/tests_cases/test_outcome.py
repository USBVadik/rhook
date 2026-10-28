"""Reporting regressions; any subprocess is a harmless sleeping Python fixture."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

from developer.files import load, save, sha
from rhook_alpha.cases import native
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import closure, host_v3, outcome
from test_host_v3 import packet

OP = 'f' * 64


def measured(**changes):
    value = dict(exitCode=-9, stop='SUPERVISION_FAILURE_ValueError', workerReaped=True, resourcesReliable=True)
    value.update(changes)
    return value


def native_record(**changes):
    value = dict(operationCommitment=OP, result=dict(ownedBridgesClosed=True), producerEntries=0)
    value.update(changes)
    return value


class OutcomeRecords(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.rt = self.root / 'runtime'
        self.rt.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def host_stop(self):
        (self.rt / 'HOST_RUNTIME').mkdir()
        save(self.rt / 'HOST_RUNTIME/STOP.json', dict(cause='IMMEDIATE_FREE_RESERVE', sample=8))

    def test_missing_native_keeps_authoritative_host_cause_and_unknown_bridge_cleanup(self):
        self.host_stop()
        with self.assertRaises(outcome.NativeStageStop) as caught:
            outcome.require_stage(self.rt, OP, measured())
        report = caught.exception.report
        self.assertEqual(report['causeCode'], 'HOST_STOP: IMMEDIATE_FREE_RESERVE')
        self.assertEqual(report['nativeCompletion'], 'MISSING')
        self.assertEqual(report['workerExit'], dict(code=-9, signal='SIGKILL'))
        self.assertEqual(report['processTermination'], 'CONFIRMED')
        self.assertEqual(report['engineBridgeClosure'], 'UNKNOWN')
        self.assertTrue(report['primaryStop']['evidencePath'].endswith('HOST_RUNTIME/STOP.json'))
        self.assertNotIn('FileNotFoundError', json.dumps(report))

    def test_present_completion_is_retained_by_reference_even_when_host_stops(self):
        self.host_stop()
        save(self.rt / 'NATIVE_COMPLETION.json', native_record())
        value = outcome.inspect_stage(self.rt, OP, measured())
        self.assertEqual(value.completion, native_record())
        self.assertEqual(value.diagnostics['nativeCompletion'], 'PRESENT')
        self.assertRegex(value.diagnostics['evidencePaths']['nativeCompletion']['sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(value.primary['code'], 'IMMEDIATE_FREE_RESERVE')

    def test_first_sticky_supervisor_stop_precedes_later_generic_host_failure(self):
        self.host_stop()
        value = outcome.inspect_stage(self.rt, OP, measured(stop='PAIR_WALL_TIME_LIMIT'))
        self.assertEqual(value.primary['kind'], 'SUPERVISOR_STOP')
        self.assertEqual(value.primary['code'], 'PAIR_WALL_TIME_LIMIT')

    def test_unlinked_completion_never_confirms_engine_cleanup(self):
        save(self.rt / 'NATIVE_COMPLETION.json', native_record(operationCommitment='a' * 64))
        value = outcome.inspect_stage(self.rt, OP, measured(exitCode=0, stop=None))
        self.assertIsNone(value.completion)
        self.assertEqual(value.diagnostics['nativeCompletion'], 'MISMATCH')
        self.assertEqual(value.diagnostics['engineBridgeClosure'], 'UNKNOWN')
        self.assertEqual(value.primary['code'], 'NATIVE_COMPLETION_MISMATCH')

    def test_unreadable_and_deep_completion_cannot_mask_primary_stop(self):
        self.host_stop()
        path = self.rt / 'NATIVE_COMPLETION.json'
        for raw in [b'{', b'[' * 100 + b'0' + b']' * 100, b'[]', b'{"result": []}']:
            with self.subTest(raw=raw[:20]):
                path.write_bytes(raw)
                value = outcome.inspect_stage(self.rt, OP, measured())
                self.assertEqual(value.primary['code'], 'IMMEDIATE_FREE_RESERVE')
                self.assertIsNone(value.completion)

    def test_fifo_and_symlink_records_are_bounded_and_rejected(self):
        path = self.rt / 'NATIVE_COMPLETION.json'
        os.mkfifo(path)
        self.assertEqual(outcome.inspect_stage(self.rt, OP, measured()).diagnostics['nativeCompletion'], 'INVALID')
        path.unlink()
        path.symlink_to(self.root / 'elsewhere')
        self.assertEqual(outcome.inspect_stage(self.rt, OP, measured()).diagnostics['nativeCompletion'], 'INVALID')

    def test_invalid_stop_record_is_a_stop_even_if_completion_claims_success(self):
        (self.rt / 'HOST_RUNTIME').mkdir()
        save(self.rt / 'HOST_RUNTIME/STOP.json', {})
        save(self.rt / 'NATIVE_COMPLETION.json', native_record())
        value = outcome.inspect_stage(self.rt, OP, measured(exitCode=0, stop=None))
        self.assertEqual(value.primary['code'], 'STOP_RECORD_UNREADABLE')

    def test_missing_completion_with_zero_exit_is_explicit_and_non_successful(self):
        with self.assertRaisesRegex(outcome.NativeStageStop, 'NATIVE_COMPLETION_MISSING'):
            outcome.require_stage(self.rt, OP, measured(exitCode=0, stop=None))

    def test_failed_or_unknown_supervision_never_becomes_native_success(self):
        save(self.rt / 'NATIVE_COMPLETION.json', native_record())
        for change in [dict(workerReaped=False), dict(exitCode=None), dict(resourcesReliable=False), dict(exitCode=True)]:
            with self.subTest(change=change), self.assertRaises(outcome.NativeStageStop):
                outcome.require_stage(self.rt, OP, measured(stop=None, **change))

    def test_normal_linked_completion_still_passes_reporting_gate(self):
        save(self.rt / 'NATIVE_COMPLETION.json', native_record())
        self.assertEqual(outcome.require_stage(self.rt, OP, measured(exitCode=0, stop=None)), native_record())

    def test_discovery_cleanup_keeps_engine_uncertainty_separate(self):
        save(self.root / 'BINDING.json', dict(operationCommitment=OP))
        save(self.rt / 'PROCESS_COMPLETION.json', measured())
        clean, diagnostics = outcome.discovery_cleanup(self.root)
        self.assertFalse(clean)
        self.assertEqual(diagnostics['processTermination'], 'CONFIRMED')
        self.assertEqual(diagnostics['engineBridgeClosure'], 'UNKNOWN')
        save(self.rt / 'NATIVE_COMPLETION.json', native_record())
        self.assertTrue(outcome.discovery_cleanup(self.root)[0])

    def test_missing_discovery_is_not_started_rather_than_a_fabricated_completion(self):
        clean, diagnostics = outcome.discovery_cleanup(self.root / 'absent')
        self.assertTrue(clean)
        self.assertEqual(diagnostics['processTermination'], 'NOT_STARTED')
        self.assertEqual(diagnostics['nativeCompletion'], 'NOT_STARTED')

    def test_plain_failures_remain_plain_without_fabricating_host_stop(self):
        value = {}
        outcome.apply_failure(value, ValueError('INPUT_REJECTED'))
        self.assertEqual(value, dict(causeCode='ValueError: INPUT_REJECTED'))


class HarmlessSupervision(unittest.TestCase):
    def test_macro_uses_typed_discovery_stop_and_keeps_cleanup_false(self):
        native.guards()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); home = root / 'home'; (home / 'scenarios').mkdir(parents=True)
            (home / 'scenarios/.consent.key').write_bytes(b'x' * 32)
            assets = {}
            for name in ('worker', 'sensor'):
                path = root / name; path.write_bytes(b'nonexecutable test staging')
                assets[name] = dict(path=str(path), sha256=sha(path))
            runtime = dict(files=dict(assets, node=dict(path='/never-executed')), sourceCommitment='d' * 64, policySha256='e' * 64)
            host = dict(sensor=assets['sensor']); out = root / 'out'
            binding = dict(operationCommitment=OP, planId='c-' + 'b' * 32, runtime=runtime,
                           hostAdmission=host, sdkFilesCommitment='c' * 64, intent={})
            broker = SimpleNamespace(pid=12345, returncode=None)
            broker.poll = lambda: broker.returncode
            broker.terminate = lambda: setattr(broker, 'returncode', -15)
            broker.wait = lambda **_: broker.returncode
            def spawn(*args, **kwargs):
                capture = Path(kwargs['cwd']) / 'capture'
                save(capture / 'DISCOVERY_READY.json', {})
                save(capture / 'PROVISIONAL_SCENARIO.json', dict(scenarioCommitment='a' * 64))
                return broker
            def supervised(_raw, stage, *_args):
                rt = stage / 'runtime'; (rt / 'HOST_RUNTIME').mkdir()
                save(rt / 'HOST_RUNTIME/STOP.json', dict(cause='IMMEDIATE_FREE_RESERVE', sample=8))
                save(rt / 'PROCESS_COMPLETION.json', measured())
                return measured()
            with mock.patch.object(closure, 'active_group', return_value=123), \
                 mock.patch.object(closure, 'account'), mock.patch.object(closure, 'prepare', return_value=binding), \
                 mock.patch.object(closure.native, 'guards', return_value=(lambda _:contextlib.nullcontext(), None, None, None)), \
                 mock.patch.object(closure.power, 'observe'), \
                 mock.patch.object(host_v3, 'admission', return_value=({}, [packet()])), \
                 mock.patch.object(host_v3, 'supervise', side_effect=supervised), \
                 mock.patch.object(closure.subprocess, 'Popen', side_effect=spawn):
                result = closure.run(SimpleNamespace(home=home), binding['planId'], out,
                    credential_file=root / 'unused-token', account_assertions=root / 'unused-account',
                    expected_operation=OP, local_owner=True, mac_ready=True)
            self.assertEqual(result['causeCode'], 'HOST_STOP: IMMEDIATE_FREE_RESERVE')
            self.assertEqual(result['nativeCompletion'], 'MISSING')
            self.assertEqual(result['discoveryDiagnostics']['processTermination'], 'CONFIRMED')
            self.assertEqual(result['discoveryDiagnostics']['engineBridgeClosure'], 'UNKNOWN')
            self.assertFalse(result['cleanupConfirmed']); self.assertTrue(result['brokerReaped'])
            self.assertEqual(load(out / 'RESULT.json')['causeCode'], result['causeCode'])
            self.assertNotIn('FileNotFoundError', json.dumps(result))

    def test_resource_stop_reaps_owned_child_and_reaches_installed_cli_nonzero(self):
        from rhook_alpha.cases.__main__ import main
        native.guards()
        from case_sdk.common import portable
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'artifacts').mkdir(); (root / 'runtime').mkdir()
            helper = root / 'artifacts/rhook-saved-pair'
            helper.write_text('#!' + sys.executable + ' -I\nimport sys,time\nsys.stdin.buffer.read()\ntime.sleep(10)\n')
            helper.chmod(0o700)
            current = packet(beganNs=2_100_000_000, endedNs=2_110_000_000,
                             freePages=108 * (1 << 20) // 4096, speculativePages=0)
            # Synthetic sensor packets and RSS; actual harmless child, production
            # RuntimeGuard/monitored kill+reap and production result interpretation.
            with mock.patch.object(portable.guards, 'sample_owned', return_value={'rssBytes':1}), \
                 mock.patch.object(host_v3, 'capture_sensor', return_value=current):
                resource_result = host_v3.supervise(b'{}', root, Path('/unused'), packet())
            self.assertTrue(resource_result['workerReaped'])
            self.assertEqual(resource_result['exitCode'], -signal.SIGKILL)
            self.assertFalse((root / 'runtime/NATIVE_COMPLETION.json').exists())
            pid = load(root / 'runtime/PROCESS_STARTED.json')['pid']
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
            with self.assertRaises(outcome.NativeStageStop) as caught:
                outcome.require_stage(root / 'runtime', OP, resource_result)
            result = dict(status='SCENARIO_CLOSURE_STOP', cleanupConfirmed=False,
                          operationPermanentlyClosed=True, automaticRetry=False)
            outcome.apply_failure(result, caught.exception)
            with mock.patch.object(closure, 'run', return_value=result), \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = main(['--home', str(root / 'home'), 'scenario-close', '--plan', 'c-' + 'a' * 32,
                             '--output', str(root / 'out'), '--credential-file', '/unused',
                             '--account-assertions', '/unused', '--operation', OP, '--local-owner', '--mac-ready'])
            self.assertEqual(code, 1)
            reported = json.loads(stdout.getvalue())
            self.assertEqual(reported['causeCode'], 'HOST_STOP: IMMEDIATE_FREE_RESERVE')
            self.assertEqual(reported['processTermination'], 'CONFIRMED')
            self.assertEqual(reported['engineBridgeClosure'], 'UNKNOWN')
            self.assertFalse(reported['cleanupConfirmed'])
            self.assertFalse((root / 'home').exists())


if __name__ == '__main__': unittest.main()
