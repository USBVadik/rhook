import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.scenario import api

class ScenarioBoundary(unittest.TestCase):
    def test_retained_plan_cannot_silently_acquire_a_larger_gas_action(self):
        from developer.files import canonical,digest,save
        from rhook_alpha.cases.scenario import closure
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home');p=sdk.configure_scenario()
            p=api.describe(sdk,p['planId']);p['assumptions']['gas']=5000000
            p.pop('planCommitment');p['planCommitment']=digest(canonical(p))
            (sdk.home/'scenarios/plans'/p['planId']/'PLAN.json').write_bytes(canonical(p)+b'\n')
            # Read-only inspection remains available for retained plans.
            self.assertEqual(api.describe(sdk,p['planId'])['assumptions']['gas'],5000000)
            with mock.patch.object(api,'runtime',side_effect=AssertionError('runtime touched before stale-plan check')):
                with self.assertRaisesRegex(ValueError,'STALE_SCENARIO_PLAN_GAS'):
                    api.acquire(sdk,p['planId'],Path(tmp).resolve()/'capture',credential_file='not-read',account_assertions='not-read',read_only=True)
                with self.assertRaisesRegex(ValueError,'STALE_SCENARIO_PLAN_GAS'):
                    closure.prepare(sdk,p['planId'],Path(tmp).resolve()/'closure')
            self.assertFalse((Path(tmp)/'capture').exists())

    def test_capture_gas_must_match_the_bound_plan(self):
        from developer.files import canonical,digest,save,sha
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home');p=sdk.configure_scenario()
            capture=Path(tmp).resolve()/'capture';capture.mkdir()
            body={'schema':'rhook/hookr-scenario/0.1','poolId':p['intent']['poolId'],'actions':[{'gas':5000000}],
                  'configurations':{'variant':['0x'+hex(50<<160)[2:].zfill(64)]}}
            body['scenarioCommitment']=digest(b'rhook/hookr-scenario/0.1\n'+canonical(body))
            save(capture/'SCENARIO.json',body)
            save(capture/'SDK_RESULT.json',{'status':'AUTHENTICATED_SCENARIO_CAPTURED','cleanupConfirmed':True,'planId':p['planId'],
                 'planCommitment':p['planCommitment'],'scenarioSha256':sha(capture/'SCENARIO.json'),'scenarioCommitment':body['scenarioCommitment']})
            with self.assertRaisesRegex(ValueError,'SCENARIO_PLAN_GAS_LINK'):api._input(sdk,capture)

    def test_configure_requires_no_runtime_or_memory_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            with mock.patch.object(api,'runtime',side_effect=AssertionError('offline planning')):
                p=sdk.configure_scenario(lp_bps=50)
            self.assertEqual(p['profile'],'nitro-hookr-scenario/0.1')
            self.assertFalse(p['executionAuthorized'])
            self.assertEqual(p['assumptions']['gas'],10000000)
            self.assertEqual(api.describe(sdk,p['planId'])['intent']['lpBps'],50)
            self.assertFalse((sdk.home/'RUNTIME.json').exists())
            self.assertFalse((sdk.home/'scenarios/consents').exists())

    def test_scenario_cannot_be_described_as_a_historical_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home');p=sdk.configure_scenario()
            with self.assertRaises((ValueError,OSError)):sdk.describe(p['planId'])

    def test_unsupported_pool_and_rule_stop_without_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            for options in [{'pool_id':'0x'+'00'*32},{'lp_bps':True},{'lp_bps':100},{'lp_bps':-1}]:
                with self.assertRaises(ValueError):sdk.configure_scenario(**options)
            self.assertFalse((sdk.home/'scenarios').exists())

    def test_capture_is_opt_in_before_runtime_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home');out=Path(tmp)/'out'
            with mock.patch.object(api,'runtime',side_effect=AssertionError('must not open runtime')):
                with self.assertRaisesRegex(ValueError,'EXPLICIT_READ_ONLY'):
                    sdk.acquire_scenario('c-'+'a'*32,out,credential_file='not-read',account_assertions='not-read')
            self.assertFalse(out.exists())

    def test_run_requires_owner_and_ready_host_before_loading_any_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home')
            with mock.patch.object(api,'_input',side_effect=AssertionError('must not read state')):
                for options in [{},{'local_owner':True},{'mac_ready':True}]:
                    with self.assertRaisesRegex(ValueError,'EXPLICIT_LOCAL_OWNER'):sdk.run_scenario('not-read',**options)

    def test_policy_reuses_original_v2_numerical_guards(self):
        inherited=json.loads((api.native.SDK_ROOT/'engine/case_sdk/policy.json').read_text());scenario=json.loads((api.HERE/'policy.json').read_text())
        for k in inherited:
            if k not in ['profile','workload','maximumInvocations']:self.assertEqual(scenario[k],inherited[k],k)
        self.assertEqual(scenario['maximumInvocations'],{'SCENARIO_BASELINE':1,'SCENARIO_VARIANT':1})
        self.assertEqual(scenario['RPC'],0)

    def test_tampered_intent_never_becomes_a_different_scenario(self):
        from developer.files import load,canonical
        with tempfile.TemporaryDirectory() as tmp:
            sdk=CaseSDK(Path(tmp).resolve()/'home');p=sdk.configure_scenario();path=sdk.home/'scenarios/plans'/p['planId']/'PLAN.json'
            v=load(path);v['intent']['lpBps']=0;path.write_bytes(canonical(v)+b'\n')
            with self.assertRaisesRegex(ValueError,'SCENARIO_PLAN_DRIFT'):api.describe(sdk,p['planId'])

if __name__=='__main__':unittest.main()
