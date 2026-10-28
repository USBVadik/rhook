import copy
import contextlib
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from developer.files import save
from rhook_alpha.cases.scenario import closure


class ClosureBoundary(unittest.TestCase):
    def test_acquisition_counts_come_from_verified_completion_not_a_legacy_zero(self):
        original={'nativeExecutions':0,'status':'AUTHENTICATED_SCENARIO_CAPTURED'}
        done={'discoveryOnly':True,'producerInvocations':2,'worlds':[{},{}],'status':'SCENARIO_DISCOVERY_COMPLETED'}
        self.assertEqual(closure.confirmed_acquisition(original,done)['nativeExecutions'],2)
        self.assertEqual(original['nativeExecutions'],0)
        for change in [{'discoveryOnly':False},{'producerInvocations':0},{'worlds':[]},{'status':'HOST_STOP'}]:
            with self.assertRaisesRegex(ValueError,'COUNT_UNCONFIRMED'):
                closure.confirmed_acquisition(original,dict(done,**change))

    def test_node_telemetry_checks_its_own_executable_and_group(self):
        proc=SimpleNamespace(pid=12345,args=['/usr/local/bin/node'],poll=lambda:None)
        observed=SimpleNamespace(returncode=0,stdout=f'12345 {closure.os.getpid()} 4567 1024 /usr/local/bin/node\n')
        with mock.patch.object(closure,'active_group',return_value=4567), \
             mock.patch.object(closure.subprocess,'run',return_value=observed):
            self.assertEqual(closure.sample_broker(proc)['rssBytes'],1<<20)
            observed.stdout=observed.stdout.replace('/usr/local/bin/node','/usr/bin/other')
            with self.assertRaisesRegex(ValueError,'BROKER_PROCESS_IDENTITY'):closure.sample_broker(proc)

    def test_failed_power_gate_closes_consent_without_starting_broker_or_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();home=root/'home';(home/'scenarios').mkdir(parents=True)
            (home/'scenarios/.consent.key').write_bytes(b'x'*32)
            out=root/'run';sdk=SimpleNamespace(home=home)
            binding=dict(operationCommitment='a'*64,planId='c-'+'b'*32,runtime={},hostAdmission={})
            with mock.patch.object(closure,'active_group',return_value=123), \
                 mock.patch.object(closure,'account'), \
                 mock.patch.object(closure,'prepare',return_value=binding), \
                 mock.patch.object(closure.native,'guards',return_value=(lambda _:contextlib.nullcontext(),None,None,None)), \
                 mock.patch.object(closure.power,'observe',side_effect=ValueError('POWER_NOT_READY')), \
                 mock.patch.object(closure.subprocess,'Popen') as spawn:
                result=closure.run(sdk,binding['planId'],out,credential_file=None,account_assertions=None,
                    expected_operation='a'*64,local_owner=True,mac_ready=True)
            self.assertIn('POWER_NOT_READY',result['causeCode'])
            self.assertTrue(result['operationPermanentlyClosed']);self.assertFalse(result['automaticRetry'])
            self.assertTrue((home/'scenarios/closure-consents'/binding['planId']/'CONSUMED.json').exists())
            spawn.assert_not_called()

    def test_approval_and_workflow_context_precede_account_or_state_access(self):
        with mock.patch.object(closure, 'account', side_effect=AssertionError('no read')):
            for options in ({}, {'local_owner': True}, {'mac_ready': True}):
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_CLOSURE'):
                    closure.run(None, None, None, credential_file=None, account_assertions=None, expected_operation=None, **options)
            with mock.patch.object(closure, 'active_group', return_value=None):
                with self.assertRaisesRegex(ValueError, 'WORKFLOW_CONTEXT'):
                    closure.run(None, None, None, credential_file=None, account_assertions=None,
                                expected_operation=None, local_owner=True, mac_ready=True)

    def test_fresh_free_quota_is_required_for_the_shared_bounded_capture(self):
        valid = dict(schema='rhook/scenario-account-assertions/0.1', freePlan=True,
                     paidUsageDisabled=True, chainId=4663, remainingCU=2000,
                     throughputCUPerSecond=200, observedUnixMs=int(time.time()*1000))
        with tempfile.TemporaryDirectory() as tmp:
            for index, change in enumerate(({}, {'remainingCU': 1999}, {'throughputCUPerSecond': 199},
                       {'paidUsageDisabled': False}, {'observedUnixMs': 1})):
                path=Path(tmp).resolve()/str(index);save(path,dict(valid,**change))
                if change:
                    with self.assertRaises(ValueError):closure.account(path)
                else:self.assertEqual(closure.account(path),valid)
        self.assertEqual(closure.BUDGET['requests'],64)
        self.assertEqual(closure.BUDGET['wallMs'],30000)

    def test_discovery_and_offline_commitments_must_match_beyond_economics(self):
        fields=('stateRoot','receiptsRoot','producedSyntheticHeader','systemTransactionHash',
                'actionMapping','receipts','actorBalanceBefore','actorBalanceAfter','actorNonceAfter','overlay')
        value={'worlds':[dict(world=label,**{k:k for k in fields}) for label in ('SCENARIO_BASELINE','SCENARIO_VARIANT')]}
        self.assertEqual(closure.compare_worlds(value,value)['finalSource'],'NIL')
        for field in fields:
            bad=copy.deepcopy(value);bad['worlds'][1][field]='different'
            with self.assertRaisesRegex(ValueError,'DIVERGENCE'):closure.compare_worlds(value,bad)
        with self.assertRaisesRegex(ValueError,'TWO_COMPLETED'):closure.compare_worlds({'worlds':[]},value)


if __name__ == '__main__':unittest.main()
