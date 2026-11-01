"""Host admission v4: synthetic sensor packets and a harmless child only; nothing here allocates memory."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from developer.files import canonical, load, sha
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import api, host_v3, host_v4
from test_host_v3 import MIB, packet

V3_POLICY_SHA = '2b4c477e8382101ad44685b7ff367a8b5989bb254d4b50f638b6298f6ea48b91'
WARN, CRITICAL = 2, 4


def pair(first=None, second=None):
    a = packet(**(first or {}))
    b = copy.deepcopy(a)
    b.update(beganNs=2_100_000_000, endedNs=2_110_000_000)
    b.update(second or {})
    return [a, b]


def busy(i, **changes):
    """A WARN packet of a host that is swapping other processes' pages in and out."""
    value = packet(beganNs=2_100_000_000 + i * 300_000_000, endedNs=2_110_000_000 + i * 300_000_000,
                   pressureBefore=WARN, pressureAfter=WARN, swapInPages=10 + 50 * i, swapOutPages=20 + 7 * i,
                   swapUsedBeforeBytes=1024 * MIB + i * MIB, swapUsedBytes=1024 * MIB + (i + 1) * MIB)
    value.update(changes)
    return value


class Policy(unittest.TestCase):
    def test_v4_is_a_separate_profile_and_v3_is_unchanged(self):
        self.assertEqual(host_v4.PROFILE, 'macos-host-admission-v4')
        self.assertNotEqual(host_v4.POLICY_SHA, host_v3.POLICY_SHA)
        self.assertEqual(host_v3.POLICY_SHA, V3_POLICY_SHA)
        self.assertEqual(host_v3.PROFILE, 'macos-host-admission-v3')
        self.assertEqual(host_v4.RECORD, 'HOST_V4.json')
        # The v3 decisions stay exactly as before for the inputs v4 now accepts.
        with self.assertRaisesRegex(ValueError, 'MEMORY_PRESSURE'):
            host_v3.assess(pair(second={'pressureAfter': WARN}))
        with self.assertRaisesRegex(ValueError, 'SWAP_ACTIVITY'):
            host_v3.assess(pair(second={'swapInPages': 11}))

    def test_worker_limits_in_the_policy_are_the_reviewed_ones(self):
        for key in ('workerRssBytes', 'workerAndObserverCpuSeconds', 'nativeWallSeconds', 'nativeStageSeconds',
                    'workflowSeconds', 'maximumSampleSeconds', 'maximumSampleGapSeconds', 'runtimeSampleSpacingSeconds',
                    'admissionSpacingSeconds', 'sensorProcessWallSeconds', 'reserveModel', 'reservedMemory'):
            self.assertEqual(host_v4.POLICY[key], host_v3.POLICY[key], key)

    def test_unrecognized_policy_modes_cannot_remove_checks(self):
        for key in ('availabilityMode', 'pressureMode', 'swapMode', 'policyRevision'):
            with self.subTest(key=key), patch.dict(host_v4.POLICY, {key: 'UNRECOGNIZED'}):
                with self.assertRaisesRegex(ValueError, 'AVAILABILITY_POLICY'):
                    host_v4.assess(pair())


class Admission(unittest.TestCase):
    def test_warn_pressure_with_swap_in_out_and_swap_used_growth_passes_as_telemetry(self):
        samples = [busy(0), busy(4)]
        samples[1]['beganNs'] = samples[0]['endedNs'] + 1_000_000_000
        samples[1]['endedNs'] = samples[1]['beganNs'] + 10_000_000
        result = host_v4.assess(samples)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual((result['maximumPressure'], result['warningPressureReadings'], result['pressureReadings']), (WARN, 4, 4))
        self.assertEqual((result['swapInDeltaPages'], result['swapOutDeltaPages']), (200, 28))
        self.assertEqual(result['swapUsedBytes'], dict(first=1024 * MIB, last=1029 * MIB, minimum=1024 * MIB, maximum=1029 * MIB))
        self.assertEqual((result['pressureAdmissionEnforced'], result['swapActivityAdmissionEnforced']), ('CRITICAL_ONLY', False))
        self.assertFalse(result['reservedMemory'])
        # The same packets stop v3.
        with self.assertRaises(ValueError):
            host_v3.assess(samples)

    def test_normal_quiet_host_still_passes(self):
        result = host_v4.assess(pair())
        self.assertEqual((result['status'], result['maximumPressure'], result['warningPressureReadings']), ('PASS', 1, 0))
        self.assertEqual((result['swapInDeltaPages'], result['swapOutDeltaPages']), (0, 0))

    def test_critical_and_unknown_pressure_stop(self):
        for key in ('pressureBefore', 'pressureAfter'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'CRITICAL_MEMORY_PRESSURE'):
                host_v4.assess(pair(second={key: CRITICAL}))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'CRITICAL_MEMORY_PRESSURE'):
                host_v4.assess(pair(first={key: CRITICAL}), runtime=True)
        for value in (0, 3, 99, True, '2'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'MEMORY_PRESSURE_ENCODING|COUNTER_ENCODING'):
                host_v4.assess(pair(second={'pressureAfter': value}))

    def test_decreasing_counters_are_a_sensor_regression(self):
        for key in ('swapInPages', 'swapOutPages', 'compressions', 'decompressions'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'VM_COUNTER_REGRESSION'):
                host_v4.assess(pair(first={key: 50}, second={key: 49}))

    def test_corrupt_or_stale_telemetry_and_host_changes_stop(self):
        bad = [(dict(freePages=True), 'COUNTER_ENCODING'), (dict(inactivePages=-1), 'COUNTER_ENCODING'),
               (dict(pageBytes=123), 'PAGE_OR_PHYSICAL'), (dict(fileBackedPages=1 << 64), 'COUNTER_ENCODING'),
               (dict(speculativePages=1 << 50), 'IMPOSSIBLE'), (dict(source='DARWIN_HOST_VM64/1'), 'V4_SENSOR_PROFILE'),
               (dict(platform='darwin-x86_64'), 'V4_SENSOR_PROFILE'), (dict(boot=''), 'BOOT_ENCODING'),
               (dict(beganNs=2_100_000_000, endedNs=2_500_000_000), 'SENSOR_TIMING')]
        for change, code in bad:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, code):
                host_v4.assess(pair(second=change))
        samples = pair(); del samples[1]['anonymousPages']
        with self.assertRaisesRegex(ValueError, 'V4_SENSOR_FIELDS'):
            host_v4.assess(samples)
        for change, code in [(dict(boot='new'), 'HOST_IDENTITY_CHANGED'), (dict(physicalBytes=16384 * MIB), 'HOST_IDENTITY_CHANGED'),
                             (dict(beganNs=5_000_000_000, endedNs=5_010_000_000), 'RESOURCE_SAMPLE_GAP'),
                             (dict(beganNs=1_005_000_000, endedNs=1_015_000_000), 'RESOURCE_SAMPLE_GAP')]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, code):
                host_v4.assess(pair(second=change))
        # Admission samples must be at least 0.9 s apart; runtime samples need not be.
        close = pair(second=dict(beganNs=1_300_000_000, endedNs=1_310_000_000))
        with self.assertRaisesRegex(ValueError, 'RESOURCE_SAMPLE_GAP'):
            host_v4.assess(close)
        self.assertEqual(host_v4.assess(close, runtime=True)['status'], 'PASS')
        with self.assertRaisesRegex(ValueError, 'TWO_RESOURCE_SAMPLES_REQUIRED'):
            host_v4.assess([packet()])


class Runtime(unittest.TestCase):
    def test_runtime_guard_continues_through_warn_and_swap_then_stops_on_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve() / 'HOST_RUNTIME'
            guard = host_v4.RuntimeGuard(Path('/unused'), directory, packet())
            with patch.object(host_v4, 'capture_sensor', side_effect=[busy(i) for i in range(5)]):
                for _ in range(5):
                    guard.poll(force=True)
            self.assertEqual(guard.count, 5)
            summary = guard.summary()
            self.assertEqual((summary['runtimeTelemetry'], summary['maximumRuntimePressure'], summary['warningPressureReadings']),
                             ('MEASURED', WARN, 10))
            self.assertEqual((summary['hostGuardStopped'], summary['hostGuardStopCause']), (False, None))
            self.assertEqual((summary['swapInDeltaPages'], summary['swapOutDeltaPages']), (200, 28))
            self.assertEqual(summary['scope'], 'HOST_TELEMETRY_ONLY_NOT_RUN_OUTCOME')
            with patch.object(host_v4, 'capture_sensor', return_value=busy(5, pressureAfter=CRITICAL)):
                with self.assertRaisesRegex(ValueError, 'CRITICAL_MEMORY_PRESSURE'):
                    guard.poll(force=True)
            self.assertEqual(load(directory / 'STOP.json')['sample'], 5)
            stopped = guard.summary()
            self.assertTrue(stopped['hostGuardStopped'])
            self.assertIn('CRITICAL_MEMORY_PRESSURE', stopped['hostGuardStopCause'])
            # The stopping packet is not folded into the accepted telemetry.
            self.assertEqual((stopped['runtimeSamples'], stopped['maximumRuntimePressure']), (5, WARN))

    def test_no_runtime_samples_is_not_measured_never_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            guard = host_v4.RuntimeGuard(Path('/unused'), Path(tmp).resolve() / 'HOST_RUNTIME',
                                         packet(pressureBefore=WARN, pressureAfter=WARN))
            summary = guard.summary()
        self.assertEqual((summary['runtimeSamples'], summary['runtimeTelemetry']), (0, 'NOT_MEASURED'))
        for key in ('maximumRuntimePressure', 'warningPressureReadings', 'swapInDeltaPages', 'swapOutDeltaPages', 'swapUsedBytes'):
            self.assertIsNone(summary[key], key)
        self.assertFalse(summary['hostGuardStopped'])

    def _supervise(self, helper_body, packets, rss=1):
        from rhook_alpha.cases import native
        native.guards()
        from case_sdk.common import portable
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve(); (root / 'artifacts').mkdir(); (root / 'runtime').mkdir()
        helper = root / 'artifacts/rhook-saved-pair'
        helper.write_text('#!' + sys.executable + ' -I\nimport sys,time\nsys.stdin.buffer.read()\n' + helper_body)
        helper.chmod(0o700)
        feed = iter(packets)
        with patch.object(portable.guards, 'sample_owned', return_value={'rssBytes': rss}), \
             patch.object(host_v4, 'capture_sensor', side_effect=lambda *a: next(feed)):
            result = host_v4.supervise(b'{}', root, Path('/unused'), packet())
        return root, result, portable

    def test_worker_finishes_while_the_host_is_warn_and_swapping(self):
        root, result, _ = self._supervise('time.sleep(1.2)\n', [busy(i) for i in range(200)])
        self.assertTrue(result['workerReaped'])
        self.assertIsNone(result['stop'])
        self.assertEqual(result['exitCode'], 0)
        self.assertFalse((root / 'runtime/HOST_RUNTIME/STOP.json').exists())
        summary = load(root / 'runtime/HOST_RUNTIME/SUMMARY.json')
        self.assertGreater(summary['runtimeSamples'], 0)
        self.assertEqual((summary['runtimeTelemetry'], summary['maximumRuntimePressure'], summary['hostGuardStopped']),
                         ('MEASURED', WARN, False))
        self.assertGreater(summary['swapInDeltaPages'], 0)

    def test_critical_pressure_during_the_run_kills_and_reaps_the_worker(self):
        root, result, _ = self._supervise('time.sleep(10)\n', [busy(0), busy(1, pressureBefore=CRITICAL)] + [busy(2)] * 50)
        self.assertTrue(result['workerReaped'])
        self.assertIsNotNone(result['stop'])
        self.assertNotEqual(result['exitCode'], 0)
        self.assertIn('CRITICAL_MEMORY_PRESSURE', load(root / 'runtime/HOST_RUNTIME/STOP.json')['cause'])
        summary = load(root / 'runtime/HOST_RUNTIME/SUMMARY.json')
        self.assertTrue(summary['hostGuardStopped'])
        self.assertIn('CRITICAL_MEMORY_PRESSURE', summary['hostGuardStopCause'])

    def test_worker_rss_limit_still_stops_under_v4(self):
        root, result, portable = self._supervise('time.sleep(10)\n', [busy(i) for i in range(200)], rss=(1 << 30) + 1)
        self.assertEqual(result['stop'], 'SAMPLED_WORKER_RSS_LIMIT')
        self.assertTrue(result['workerReaped'])
        self.assertNotEqual(result['exitCode'], 0)
        # The host summary describes host telemetry only; it never reads as a successful run.
        summary = load(root / 'runtime/HOST_RUNTIME/SUMMARY.json')
        self.assertEqual((summary['scope'], summary['hostGuardStopped']), ('HOST_TELEMETRY_ONLY_NOT_RUN_OUTCOME', False))
        self.assertNotIn('status', summary)
        # CPU and wall are the unchanged reviewed limits of the native supervisor.
        self.assertEqual((portable.LIMITS['pairWallSeconds'], portable.LIMITS['workerKernelCpuSeconds'],
                          portable.LIMITS['workerSampledRssBytes']), (120, 120, 1 << 30))


class Registration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve(); self.sdk = CaseSDK(self.root / 'home')
        self.sensor = self.root / 'sensor'; self.sensor.write_bytes(b'sensor')

    def test_v4_has_its_own_record_and_a_v3_registration_does_not_select_v4(self):
        self.sdk.register_scenario_host(self.sensor)  # default stays v3
        self.assertTrue((self.sdk.home / 'scenarios/HOST_V3.json').is_file())
        with self.assertRaises((OSError, ValueError)):
            api.select_host(self.sdk, host_v4.PROFILE)
        value = self.sdk.register_scenario_host(self.sensor, profile=host_v4.PROFILE)
        self.assertEqual((value['profile'], value['policySha256']), (host_v4.PROFILE, host_v4.POLICY_SHA))
        selected = api.select_host(self.sdk, host_v4.PROFILE)
        self.assertEqual(selected['sensor']['sha256'], sha(self.sensor))
        self.assertEqual(api.select_host(self.sdk, host_v3.PROFILE)['policySha256'], host_v3.POLICY_SHA)
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_HOST_PROFILE'):
            api.select_host(self.sdk, 'macos-host-admission-v5')
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_HOST_PROFILE'):
            self.sdk.register_scenario_host(self.sensor, profile='auto')
        self.assertFalse((self.sdk.home / 'scenarios/consents').exists())

    def test_v4_record_drift_is_rejected(self):
        self.sdk.register_scenario_host(self.sensor, profile=host_v4.PROFILE)
        path = self.sdk.home / 'scenarios/HOST_V4.json'
        for change in ({'policySha256': host_v3.POLICY_SHA}, {'profile': host_v3.PROFILE}, {'sdkFilesCommitment': '0' * 64}):
            record = load(path); record.update(change); path.chmod(0o600); path.write_bytes(canonical(record))
            with self.subTest(change=list(change)), self.assertRaisesRegex(ValueError, 'HOST_RUNTIME_DRIFT'):
                api.select_host(self.sdk, host_v4.PROFILE)
            path.unlink(); self.sdk.register_scenario_host(self.sensor, profile=host_v4.PROFILE)
        self.sensor.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'HOST_RUNTIME_DRIFT'):
            api.select_host(self.sdk, host_v4.PROFILE)

    def test_v4_binding_is_a_new_operation_bound_to_the_v4_policy(self):
        self.sdk.register_scenario_host(self.sensor)
        self.sdk.register_scenario_host(self.sensor, profile=host_v4.PROFILE)
        capture = self.root / 'capture'; plan = {'planId': 'c-' + 'a' * 32, 'profile': api.PROFILE}
        value = {'scenarioCommitment': 'a' * 64, 'scenarioSha256': 'b' * 64}
        runtime = {'profile': api.PROFILE, 'sourceCommitment': 'c' * 64, 'files': {'worker': {'sha256': 'd' * 64}}}
        with patch.object(api, '_input', return_value=(capture, value, plan, {})), patch.object(api, 'runtime', return_value=runtime):
            v3 = api.prepare(self.sdk, capture, host_profile=host_v3.PROFILE)
            v4 = api.prepare(self.sdk, capture, host_profile=host_v4.PROFILE)
        self.assertNotEqual(v3['operationCommitment'], v4['operationCommitment'])
        self.assertEqual(v4['hostAdmission']['policySha256'], host_v4.POLICY_SHA)
        self.assertEqual(v4['hostAdmission']['profile'], host_v4.PROFILE)
        self.assertEqual({k: v for k, v in v3.items() if k not in ('hostAdmission', 'sdkFilesCommitment', 'operationCommitment')},
                         {k: v for k, v in v4.items() if k not in ('hostAdmission', 'sdkFilesCommitment', 'operationCommitment')})
        self.assertFalse((self.sdk.home / 'scenarios/consents').exists())

    def test_run_dispatches_admission_and_supervision_to_the_selected_profile(self):
        self.assertIs(api.host_profile_module(host_v4.PROFILE)[0], host_v4)
        self.assertIs(api.host_profile_module(host_v3.PROFILE)[0], host_v3)
        source = Path(api.__file__).read_text()
        self.assertIn('host=host_profile_module(host_profile)[0]', source)
        self.assertNotIn('admission,supervise=host_v3.admission,host_v3.supervise', source)

    def test_cli_and_facade_accept_v4_and_report_it_separately(self):
        from rhook_alpha.cases.__main__ import main
        from rhook_alpha.execution import ExecutionSDK, HOST_PROFILES
        self.assertEqual(HOST_PROFILES, ('v2', 'macos-host-admission-v3', 'macos-host-admission-v4'))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(['--home', str(self.sdk.home), 'scenario-register-host', str(self.sensor), '--profile', host_v4.PROFILE])
        self.assertEqual((code, json.loads(out.getvalue())['profile']), (0, host_v4.PROFILE))
        cap = ExecutionSDK(self.sdk.home).capabilities()
        profiles = cap['host']['admissionProfiles']
        self.assertTrue(profiles['macos-host-admission-v4']['registered'])
        self.assertFalse(profiles['macos-host-admission-v3']['registered'])
        self.assertFalse(cap['nativeExecutionReady'])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--home', str(self.sdk.home), 'execution-operation', '--prepared', '/x', '--host-admission', 'auto'])


if __name__ == '__main__':
    unittest.main()
