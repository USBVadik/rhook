"""Synthetic physical-host packets; these tests allocate no memory workload."""
import copy
import contextlib
import io
import importlib
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import api
from developer.files import sha

MIB = 1 << 20


def packet(**changes):
    value = dict(source='DARWIN_HOST_VM64/3', platform='darwin-arm64', boot='abc-123',
                 beganNs=1_000_000_000, endedNs=1_010_000_000, physicalBytes=24576*MIB,
                 pageBytes=4096, freePages=384*MIB//4096, speculativePages=256*MIB//4096,
                 inactivePages=4096*MIB//4096, activePages=4096*MIB//4096,
                 fileBackedPages=6144*MIB//4096, anonymousPages=4096*MIB//4096,
                 purgeablePages=512*MIB//4096, wiredPages=4096*MIB//4096,
                 compressorPages=2048*MIB//4096, compressedLogicalPages=8192*MIB//4096,
                 compressions=100, decompressions=100, pressureBefore=1, pressureAfter=1,
                 swapInPages=10, swapOutPages=20, swapUsedBeforeBytes=1024*MIB,
                 swapUsedBytes=1024*MIB)
    value.update(changes)
    return value


class HostV3(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('rhook_alpha.cases.scenario.host_v3'),
                             'versioned v3 host policy is not implemented')
        self.host = importlib.import_module('rhook_alpha.cases.scenario.host_v3')

    def pair(self, first=None, second=None):
        a = packet(**(first or {}))
        b = copy.deepcopy(a)
        b.update(beganNs=2_100_000_000, endedNs=2_110_000_000)
        b.update(second or {})
        return [a, b]

    def test_cache_rich_low_free_host_has_estimate_without_reservation_claim(self):
        result = self.host.assess(self.pair())
        self.assertEqual(result['minimumEstimatedAvailableBytes'], 4480*MIB)
        self.assertFalse(result['reservedMemory'])
        self.assertTrue(result['experimental'])

    def test_no_speculative_or_purgeable_double_credit(self):
        samples = self.pair(dict(inactivePages=2048*MIB//4096,
                                 fileBackedPages=1024*MIB//4096,
                                 speculativePages=256*MIB//4096,
                                 freePages=1024*MIB//4096))
        self.assertEqual(self.host.assess(samples)['minimumEstimatedAvailableBytes'],1792*MIB)

    def test_anonymous_inactive_without_file_credit_is_telemetry(self):
        result=self.host.assess(self.pair(dict(fileBackedPages=256*MIB//4096)))
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['minimumEstimatedAvailableBytes'],384*MIB)

    def test_normal_pressure_with_low_capacity_estimate_passes_without_reservation_claim(self):
        result=self.host.assess(self.pair(dict(inactivePages=0)))
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['requiredEstimatedBytes'],0)
        self.assertFalse(result['availabilityAdmissionEnforced'])
        self.assertFalse(result['reservedMemory'])

    def test_low_immediate_free_is_recorded_and_does_not_block_admission(self):
        result=self.host.assess(self.pair(dict(freePages=1,speculativePages=0)))
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['minimumImmediateFreeBytes'],4096)
        self.assertEqual(result['requiredImmediateFreeBytes'],0)
        self.assertEqual(result['availabilityMode'],'TELEMETRY_ONLY')

    def test_wired_and_compressor_cap_is_recorded_without_blocking(self):
        result=self.host.assess(self.pair(dict(wiredPages=22016*MIB//4096)))
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['minimumEstimatedAvailableBytes'],512*MIB)

    def test_pressure_warning_critical_and_unknown_all_stop(self):
        for pressure in [0,2,4,99]:
            with self.subTest(pressure=pressure), self.assertRaisesRegex(ValueError,'MEMORY_PRESSURE'):
                self.host.assess(self.pair(second={'pressureAfter':pressure}))

    def test_swap_in_out_growth_and_regression_stop(self):
        for field,value in [('swapInPages',11),('swapInPages',9),('swapOutPages',21),('swapOutPages',19)]:
            with self.subTest(field=field,value=value), self.assertRaisesRegex(ValueError,'SWAP_ACTIVITY'):
                self.host.assess(self.pair(second={field:value}))

    def test_swap_usage_growth_inside_packet_and_between_packets_stop(self):
        for change in [dict(swapUsedBytes=1024*MIB+1),
                       dict(swapUsedBeforeBytes=1024*MIB+1,swapUsedBytes=1024*MIB+1)]:
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'ACTIVE_SWAP_USAGE'):
                self.host.assess(self.pair(second=change))

    def test_compression_activity_without_pressure_or_swap_is_recorded_not_rejected(self):
        self.assertEqual(self.host.assess(self.pair(second={'compressions':200}))['status'],'PASS')

    def test_malformed_counters_and_missing_sensor_fields_fail_closed(self):
        for changes in [dict(freePages=True),dict(inactivePages=-1),dict(pageBytes=123),
                        dict(fileBackedPages=1<<64),dict(speculativePages=1<<50)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.host.assess(self.pair(changes))
        samples=self.pair();del samples[1]['anonymousPages']
        with self.assertRaises(ValueError):self.host.assess(samples)

    def test_wrong_schema_boot_change_counter_regression_and_stale_gap_stop(self):
        for change in [dict(source='DARWIN_HOST_VM64/1'),dict(boot='new'),dict(compressions=99),
                       dict(beganNs=5_000_000_000,endedNs=5_010_000_000)]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.host.assess(self.pair(second=change))

    def test_runtime_low_or_zero_free_remains_telemetry_with_no_allocation_guarantee(self):
        self.assertEqual(self.host.assess(self.pair(dict(freePages=128*MIB//4096,
                                                        speculativePages=0)),runtime=True)['status'],'PASS')
        for runtime in (False,True):
            with self.subTest(runtime=runtime):
                result=self.host.assess(self.pair(dict(freePages=0,speculativePages=0,
                                                       inactivePages=0)),runtime=runtime)
                self.assertEqual(result['status'],'PASS')
                self.assertEqual(result['minimumImmediateFreeBytes'],0)
                self.assertEqual(result['minimumEstimatedAvailableBytes'],0)
                self.assertFalse(result['availabilityAdmissionEnforced'])
                self.assertFalse(result['reservedMemory'])

    def test_previously_stopped_free_byte_values_do_not_block(self):
        samples=self.pair(dict(freePages=201015296//4096,speculativePages=0),
                          dict(freePages=275300352//4096))
        result=self.host.assess(samples)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['minimumImmediateFreeBytes'],201015296)
        self.assertEqual(result['policyRevision'],'free-telemetry/0.1')

    def test_unknown_availability_policy_cannot_silently_remove_checks(self):
        with patch.dict(self.host.POLICY,availabilityMode='UNRECOGNIZED'):
            with self.assertRaisesRegex(ValueError,'AVAILABILITY_POLICY'):
                self.host.assess(self.pair())

    def test_runtime_guard_propagates_sensor_stop_and_records_failure(self):
        previous=packet();current=packet(beganNs=2_100_000_000,endedNs=2_110_000_000,pressureAfter=2)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp).resolve()/'HOST_RUNTIME'
            guard=self.host.RuntimeGuard(Path('/unused'),directory,previous)
            with patch.object(self.host,'capture_sensor',return_value=current):
                with self.assertRaisesRegex(ValueError,'MEMORY_PRESSURE'):guard.poll(force=True)
            self.assertTrue((directory/'STOP.json').is_file())

    def test_supervisor_reaps_benign_owned_child_on_host_pressure_stop(self):
        from rhook_alpha.cases import native
        native.guards()
        from case_sdk.common import portable
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'artifacts').mkdir();(root/'runtime').mkdir()
            helper=root/'artifacts/rhook-saved-pair'
            helper.write_text('#!'+sys.executable+' -I\nimport sys,time\nsys.stdin.buffer.read()\ntime.sleep(10)\n')
            helper.chmod(0o700)
            current=packet(beganNs=2_100_000_000,endedNs=2_110_000_000,pressureAfter=2)
            with patch.object(portable.guards,'sample_owned',return_value={'rssBytes':1}),\
                 patch.object(self.host,'capture_sensor',return_value=current):
                result=self.host.supervise(b'{}',root,Path('/unused'),packet())
            self.assertTrue(result['workerReaped'])
            self.assertIsNotNone(result['stop'])
            self.assertNotEqual(result['exitCode'],0)
            self.assertTrue((root/'runtime/HOST_RUNTIME/STOP.json').is_file())


class PowerReading(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('rhook_alpha.cases.scenario.power'),
                             'bounded power parser is not implemented')
        self.power=importlib.import_module('rhook_alpha.cases.scenario.power')

    def test_ac_source_with_discharging_battery_is_still_ac(self):
        value=self.power.parse(b"Now drawing from 'AC Power'\n -InternalBattery-0 discharging; 99%\n",
                               b'  "AppleClamshellState" = No\n')
        self.assertTrue(value['onACPower']);self.assertTrue(value['lidOpen'])

    def test_ioreg_tree_prefix_preserves_unambiguous_open_lid(self):
        value=self.power.parse(b"Now drawing from 'AC Power'\n",
                               b'  |   "AppleClamshellState" = No\n')
        self.assertTrue(value['lidOpen'])

    def test_battery_source_and_closed_lid_are_explicit_not_ready(self):
        for power,lid in [(b"Now drawing from 'Battery Power'\n",b'"AppleClamshellState" = No'),
                          (b"Now drawing from 'AC Power'\n",b'"AppleClamshellState" = Yes')]:
            with self.assertRaisesRegex(ValueError,'HOST_POWER_LID_NOT_READY'):self.power.parse(power,lid)

    def test_unsupported_contradictory_and_missing_readings_are_ambiguous(self):
        for power,lid in [(b'unknown',b'"AppleClamshellState" = No'),
                          (b"Now drawing from 'AC Power'\n",b'no key'),
                          (b"Now drawing from 'AC Power'\nNow drawing from 'Battery Power'\n",
                           b'"AppleClamshellState" = No'),
                          (b"Now drawing from 'AC Power'\n",
                           b'"AppleClamshellState" = No\n"AppleClamshellState" = Yes'),
                          (b"Now drawing from 'AC Power'\nNow drawing from 'UPS Power'\n",
                           b'"AppleClamshellState" = No'),
                          (b"Now drawing from 'AC Power'\n",
                           b'"AppleClamshellState" = No\n"AppleClamshellState" = Unknown'),
                          (b"Now drawing from 'AC Power'\n",b'"AppleClamshellState" = No-invalid')]:
            with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):self.power.parse(power,lid)


class HostSelection(unittest.TestCase):
    def setUp(self):
        self.host=importlib.import_module('rhook_alpha.cases.scenario.host_v3')

    def test_v3_is_explicit_and_unregistered_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            self.assertTrue(hasattr(api,'select_host'),'host selection is not implemented')
            self.assertEqual(api.select_host(sdk,'v2'),{'profile':'v2'})
            with self.assertRaises((OSError,ValueError)):api.select_host(sdk,self.host.PROFILE)
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_HOST_PROFILE'):api.select_host(sdk,'auto')
            self.assertFalse((sdk.home/'scenarios/consents').exists())

    def test_registered_host_sensor_substitution_and_policy_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home');sensor=root/'sensor';sensor.write_bytes(b'sensor')
            self.assertTrue(hasattr(sdk,'register_scenario_host'),'host registration is not implemented')
            value=sdk.register_scenario_host(sensor)
            self.assertEqual(value['profile'],self.host.PROFILE)
            self.assertEqual(api.select_host(sdk,self.host.PROFILE)['sensor']['sha256'],sha(sensor))
            sensor.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'HOST_RUNTIME_DRIFT'):api.select_host(sdk,self.host.PROFILE)
            sensor.write_bytes(b'sensor')
            from developer.files import load,canonical
            path=sdk.home/'scenarios/HOST_V3.json';record=load(path);record['policySha256']='0'*64
            path.write_bytes(canonical(record))
            with self.assertRaisesRegex(ValueError,'HOST_RUNTIME_DRIFT'):api.select_host(sdk,self.host.PROFILE)

    def test_new_binding_binds_host_sensor_policy_and_installed_code_without_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home');sensor=root/'sensor';sensor.write_bytes(b'sensor')
            self.assertTrue(hasattr(api,'prepare'),'exact offline operation preparation is not implemented')
            sdk.register_scenario_host(sensor)
            capture=root/'capture';plan={'planId':'c-'+'a'*32,'profile':api.PROFILE}
            value={'scenarioCommitment':'a'*64,'scenarioSha256':'b'*64}
            runtime={'profile':api.PROFILE,'sourceCommitment':'c'*64,'files':{'worker':{'sha256':'d'*64}}}
            with patch.object(api,'_input',return_value=(capture,value,plan,{})),patch.object(api,'runtime',return_value=runtime):
                v2=api.prepare(sdk,capture)
                v3=api.prepare(sdk,capture,host_profile=self.host.PROFILE)
            self.assertNotEqual(v2['operationCommitment'],v3['operationCommitment'])
            self.assertEqual(v3['hostAdmission']['policySha256'],self.host.POLICY_SHA)
            self.assertEqual(v3['hostAdmission']['sensor']['sha256'],sha(sensor))
            self.assertRegex(v3['sdkFilesCommitment'],r'^[0-9a-f]{64}$')
            self.assertFalse((sdk.home/'scenarios/consents').exists())

    def test_developer_support_change_invalidates_prepared_operation_before_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sdk=CaseSDK(root/'home');sensor=root/'sensor';sensor.write_bytes(b'sensor')
            library=root/'lib';(library/'developer').mkdir(parents=True)
            support=library/'developer/files.py';support.write_bytes(b'original support')
            with patch.object(api.native,'SDK_ROOT',library):
                self.assertTrue(hasattr(self.host,'sdk_files'),'executable support inventory is missing')
                self.assertIn('developer/files.py',self.host.sdk_files())
                sdk.register_scenario_host(sensor)
                capture=root/'capture';plan={'planId':'c-'+'a'*32,'profile':api.PROFILE}
                value={'scenarioCommitment':'a'*64,'scenarioSha256':'b'*64}
                runtime={'profile':api.PROFILE,'sourceCommitment':'c'*64,'files':{'worker':{'sha256':'d'*64}}}
                with patch.object(api,'_input',return_value=(capture,value,plan,{})),patch.object(api,'runtime',return_value=runtime):
                    old=api.prepare(sdk,capture,host_profile=self.host.PROFILE)
                    self.assertRegex(old['operationCommitment'],r'^[0-9a-f]{64}$')
                    support.write_bytes(b'changed support')
                    with self.assertRaisesRegex(ValueError,'HOST_RUNTIME_DRIFT'):
                        api.prepare(sdk,capture,host_profile=self.host.PROFILE)
                self.assertFalse((sdk.home/'scenarios/consents').exists())


class HostCli(unittest.TestCase):
    def test_host_registration_cli_returns_success_without_authority(self):
        from rhook_alpha.cases.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();sensor=root/'sensor';sensor.write_bytes(b'sensor')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code=main(['--home',str(root/'home'),'scenario-register-host',str(sensor)])
            self.assertEqual(code,0)
            self.assertEqual(__import__('json').loads(output.getvalue())['status'],'HOST_PROFILE_REGISTERED')
            self.assertFalse((root/'home/scenarios/consents').exists())

    def test_prepare_cli_returns_success_for_binding_but_failure_for_stop(self):
        from rhook_alpha.cases.__main__ import main
        binding={'schema':'rhook/scenario-operation/0.1','operationCommitment':'a'*64}
        with patch.object(CaseSDK,'prepare_scenario',return_value=binding),\
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['scenario-prepare','/not-read']),0)
        with patch.object(CaseSDK,'prepare_scenario',side_effect=ValueError('STOP')),\
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['scenario-prepare','/not-read']),1)


if __name__=='__main__':unittest.main()
