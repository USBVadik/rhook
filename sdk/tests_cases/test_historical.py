import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from rhook_alpha.cases.api import CaseSDK
from rhook_alpha.cases.adapters import get_adapter
from rhook_alpha.cases.historical import PROFILE, ADAPTER, DOMAIN
from rhook_alpha.cases.historical.adapter import HistoricalDynamicFeeOff,intervention,profile
from rhook_alpha.cases import native
from developer.files import canonical, digest


class HistoricalProfileTests(unittest.TestCase):
    def test_distinct_profile_and_exact_transform(self):
        i=intervention();p=profile()
        self.assertEqual(i['checkpoint']['blockNumber'],93251802)
        self.assertEqual(i['schema'],DOMAIN+'/transform')
        self.assertEqual(len(i['writes']),2)
        self.assertEqual((int(i['writes'][0]['after'],16)>>160)&65535,100)
        self.assertEqual((int(i['writes'][1]['after'],16)>>248)&255,2)
        self.assertIsInstance(get_adapter({'adapter':{'id':ADAPTER}}),HistoricalDynamicFeeOff)
    def test_policy_keeps_every_numerical_guard(self):
        sdk=Path(native.__file__).parents[2]
        a=json.loads((sdk/'engine/plan_native/policy.json').read_text());b=json.loads((Path(native.__file__).parent/'historical/policy.json').read_text())
        for k in a:
            if k not in ('profile','workload'):self.assertEqual(a[k],b[k],k)
    def test_other_runtime_cannot_be_routed_as_historical(self):
        from rhook_alpha.cases.historical.backend import _ScopedSDK
        with tempfile.TemporaryDirectory() as t:
            sdk=CaseSDK(Path(t).resolve())
            self.assertEqual(native._settings(sdk)[0],'nitro-hookr-lp/0.1')
            self.assertEqual(native._settings(_ScopedSDK(sdk))[0],PROFILE)
            self.assertNotEqual(native._settings(_ScopedSDK(sdk))[1],native.POLICY_SHA)
    def test_historical_completion_needs_its_domain_and_cleanup(self):
        value=dict(operationCommitment='op',schema=DOMAIN+'/completion',profile=PROFILE,ownedBridgesClosed=True,
           result=dict(nativeInvocations={'ACTUAL':1,'BRANCH':1,'B':0},canonicalActualValid=True,RPC=0,WSS=0,terminal='GO_HOOKR_PAIR_OBSERVED_UNQUALIFIED'))
        native.validate_completion(value,'op',PROFILE)
        for key,bad in [('schema','rhook/hookr-scenario/0.1'),('profile','nitro-hookr-lp/0.1'),('ownedBridgesClosed',False)]:
            v=copy.deepcopy(value);v[key]=bad
            with self.assertRaisesRegex(ValueError,'HISTORICAL_COMPLETION'):native.validate_completion(v,'op',PROFILE)
    def test_bytes_mismatch_rejected_before_any_runtime(self):
        with self.assertRaisesRegex(ValueError,'EXACT_HISTORICAL_PACKAGE'):HistoricalDynamicFeeOff().capsule(b'{}',case_id='history',subject_index=3,input_commitment='',witness_commitment='')

    @unittest.skipUnless(os.environ.get('RHOOK_HISTORICAL_TEST_PACKAGE'),'explicit retained fixture required')
    def test_actual_sdk_package_import_plan_cli_without_authority(self):
        p=profile();package=Path(os.environ['RHOOK_HISTORICAL_TEST_PACKAGE'])
        with tempfile.TemporaryDirectory() as t:
            t=Path(t).resolve();sdk=CaseSDK(t/'home');bundle=t/'bundle'
            with patch('rhook_alpha.cases.native.capture',side_effect=AssertionError('planning must not start a helper or producer')):
                sdk.package_case(package,bundle,case_id='historical-off',adapter=ADAPTER,subject_index=3,input_commitment=p['inputCommitment'],witness_commitment=p['witnessCommitment'])
                sdk.import_case(bundle)
                planned=sdk.plan('historical-off',{'rule':'dynamicFee','value':'OFF'})
                d=sdk.describe(planned['planId'])
                self.assertEqual(d['runtimePlan']['intervention'],intervention())
                self.assertEqual(d['runtimePlan']['arrivals'],p['arrivals'])
                self.assertEqual(d['runtimePlan']['schema'],DOMAIN+'/plan')
                self.assertEqual(list((sdk.home/'consents').rglob('GRANT.json')),[])
                self.assertFalse((sdk.home/'RUNTIME.json').exists())
                self.assertFalse((sdk.home/'.case-consent.key').exists())
                with self.assertRaisesRegex(ValueError,'EXACT_DYNAMIC_FEE_OFF'):sdk.plan('historical-off',{'rule':'lpBps','value':49})
                from rhook_alpha.cases.__main__ import main
                buf=io.StringIO()
                with redirect_stdout(buf):code=main(['--home',str(sdk.home),'plan','--case','historical-off','--set','dynamicFee=OFF'])
                self.assertEqual(code,0,buf.getvalue())
                self.assertEqual(json.loads(buf.getvalue())['status'],'PLANNED')


if __name__=='__main__':unittest.main()
