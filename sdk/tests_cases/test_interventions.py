"""Intervention planning/projection tests; these fixtures never execute EVM."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from test_execution import fixture
from rhook_alpha.execution import ExecutionSDK, ExecutionError, commit

ROOT_WORD = '0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'


class Interventions(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('rhook_alpha.interventions'), 'intervention layer missing')
        return __import__('rhook_alpha.interventions', fromlist=['plan'])

    def prepared(self, kind='hookr.dynamic-fee-off/0.1', lp=None):
        m = self.module()
        p = json.loads((Path(__file__).parents[1]/'rhook_alpha/cases/scenario/native/profile.json').read_text())
        contracts = {role: next(c for c in p['manifest']['contracts'] if c['role'] == role) for role in ('root', 'rules')}
        projection = {'schema': 'rhook/intervention-target-state/0.1', 'checkpoint': fixture()['checkpoint'], 'accounts': {}}
        for role in ('root', 'rules'):
            c = contracts[role]
            words = {p['rootRecordSlot']: ROOT_WORD} if role == 'root' else {
                '0x'+format(int(p['configSlot'],16)+i,'064x'): w for i,w in enumerate(p['baselineConfigWords'])}
            projection['accounts'][role] = dict(address=c['address'],codeHash=c['runtimeHash'],storage=words)
        return m, p, m.describe(fixture(), projection, kind=kind, lp_bps=lp, source_sha256='a'*64)

    def test_dynamic_off_is_two_writes_and_leaves_lp_and_recapture(self):
        m,p,d = self.prepared()
        self.assertEqual(d['nativeCompatibility'], 'BLOCKED_LP_ONLY_NATIVE_CONTRACT')
        self.assertEqual(len(d['writes']), 2)
        rules,root = d['writes']
        self.assertEqual((int(rules['after'],16)>>40)&0xffffff, 3000)
        self.assertEqual((int(rules['after'],16)>>128)&0xffff, 0)
        self.assertEqual((int(rules['after'],16)>>160)&0xffff, 100)
        self.assertEqual(int(root['after'],16)>>248, 2)
        for w in d['writes']:
            self.assertEqual((int(w['before'],16)^int(w['after'],16)) & ~int(w['mask'],16), 0)
        self.assertEqual(d['status'], 'INTERVENTION_PLAN_ONLY')
        self.assertFalse(d['witnessClosureEstablished'])

    def test_lp_adapter_is_same_single_write_as_existing_prepare(self):
        m,p,d = self.prepared('hookr.lp-rewards/0.1', 49)
        self.assertEqual(len(d['writes']),1)
        self.assertEqual((int(d['writes'][0]['after'],16)>>160)&0xffff,49)
        self.assertEqual(d['nativeCompatibility'], 'USE_EXISTING_LP_EXECUTION_API')
        cfg=m.execution_configuration(d,ExecutionSDK('/private/tmp/unused-intervention-home'))
        self.assertEqual(cfg,ExecutionSDK('/private/tmp/unused-intervention-home').configure(lp_bps=49,checkpoint=fixture()['checkpoint']))

    def test_dynamic_never_routes_to_existing_native_runner(self):
        m,p,d = self.prepared()
        with self.assertRaises(ExecutionError) as e:m.execution_configuration(d,ExecutionSDK('/private/tmp/unused-intervention-home'))
        self.assertEqual(e.exception.code,'UNSUPPORTED_NATIVE_INTERVENTION')

    def test_fixture_worlds_are_independent_and_preserve_unrelated_state(self):
        m,p,d = self.prepared()
        state={'checkpoint':d['checkpoint'],'accounts':copy.deepcopy(d['originalProjection']['accounts']),
               'fixedInputs':copy.deepcopy(d['fixedInputs']), 'unrelated':{'balance':'123','code':'0x1234','storage':{'7':'8'}}}
        raw=copy.deepcopy(state)
        worlds=m.fixture_worlds(d,state)
        self.assertEqual(worlds['status'],'FIXTURE_PROJECTION_ONLY_NOT_EVM')
        self.assertEqual(state,raw);self.assertEqual(worlds['baseline'],raw)
        self.assertEqual(worlds['variant']['fixedInputs'],raw['fixedInputs'])
        self.assertEqual(worlds['variant']['unrelated'],raw['unrelated'])
        worlds['variant']['unrelated']['balance']='999'
        self.assertEqual(worlds['baseline']['unrelated']['balance'],'123')
        self.assertEqual(state,raw)

    def test_serialization_is_canonical_and_rehashed_extra_write_rejected(self):
        m,p,d = self.prepared()
        self.assertEqual(m.validate(json.loads(json.dumps(d))), d)
        bad=copy.deepcopy(d);bad['writes'].append(copy.deepcopy(bad['writes'][0]))
        bad.pop('interventionCommitment');bad['interventionCommitment']=commit(m.DOMAIN,bad)
        with self.assertRaises(ExecutionError):m.validate(bad)
        bad=copy.deepcopy(d);bad['checkpoint']['blockNumber']+=1
        with self.assertRaises(ExecutionError):m.validate(bad)

    def test_missing_storage_or_code_identity_is_explicit(self):
        m,p,d = self.prepared()
        for role,field in [('rules','storage'),('root','codeHash')]:
            snap=copy.deepcopy(d['originalProjection']);snap['accounts'][role].pop(field)
            with self.assertRaises(ExecutionError) as e:m.describe(fixture(),snap,kind=d['kind'],source_sha256='a'*64)
            self.assertEqual(e.exception.code,'INTERVENTION_TARGET_STATE')

    def test_wrong_word_or_disabled_block_not_silently_repaired(self):
        m,p,d = self.prepared()
        for role,slot,word in [('rules',p['configSlot'],'0x'+'00'*32),('root',p['rootRecordSlot'],ROOT_WORD.replace('0x03','0x02'))]:
            snap=copy.deepcopy(d['originalProjection']);snap['accounts'][role]['storage'][slot]=word
            with self.assertRaises(ExecutionError):m.describe(fixture(),snap,kind=d['kind'],source_sha256='a'*64)

    def test_wrong_checkpoint_profile_kind_lp_and_source_pin_rejected(self):
        m,p,d = self.prepared()
        for changes in [dict(kind='generic-disable'),dict(kind=d['kind'],lp_bps=50),dict(kind='hookr.lp-rewards/0.1',lp_bps=100),dict(kind=d['kind'],source_sha256='z'*64)]:
            args=dict(kind=d['kind'],source_sha256='a'*64);args.update(changes)
            with self.assertRaises(ExecutionError):m.describe(fixture(),d['originalProjection'],**args)
        snap=copy.deepcopy(d['originalProjection']);snap['checkpoint']['blockNumber']+=1
        with self.assertRaises(ExecutionError):m.describe(fixture(),snap,kind=d['kind'],source_sha256='a'*64)

    def test_result_links_bind_both_hashes_without_claiming_verification(self):
        m,p,d = self.prepared()
        a=m.bind_result_hashes(d,'1'*64,'2'*64);b=m.bind_result_hashes(d,'1'*64,'3'*64)
        self.assertEqual(a['status'],'UNVERIFIED_RESULT_REFERENCES')
        self.assertEqual(a['interventionCommitment'],d['interventionCommitment'])
        self.assertNotEqual(a['evidenceCommitment'],b['evidenceCommitment'])
        with self.assertRaises(ExecutionError):m.bind_result_hashes(d,'bad','2'*64)

    def test_fixture_missing_expected_state_or_changed_action_is_rejected(self):
        m,p,d=self.prepared()
        state=dict(checkpoint=d['checkpoint'],accounts=copy.deepcopy(d['originalProjection']['accounts']),fixedInputs=copy.deepcopy(d['fixedInputs']))
        state['fixedInputs']['actions'][0]['signedTransaction']='0xab'
        with self.assertRaises(ExecutionError):m.fixture_worlds(d,state)
        state['fixedInputs']=d['fixedInputs'];state['accounts']['root']['storage'].clear()
        with self.assertRaises(ExecutionError):m.fixture_worlds(d,state)

    def test_execution_sdk_exposes_read_only_planner(self):
        sdk=ExecutionSDK('/private/tmp/unused-intervention-home')
        self.assertTrue(callable(getattr(sdk,'plan_intervention',None)))
        self.assertTrue(callable(getattr(sdk,'prepare_intervention',None)))

    def test_malformed_rehashed_descriptors_fail_with_actionable_error(self):
        m,p,d=self.prepared()
        for key,value in [('originalProjection',None),('checkpoint',None),('kind',[]),('writes',None)]:
            bad=copy.deepcopy(d);bad[key]=value;bad.pop('interventionCommitment');bad['interventionCommitment']=commit(m.DOMAIN,bad)
            with self.assertRaises(ExecutionError):m.validate(bad)
        with self.assertRaises(ExecutionError):m.describe(fixture(),None,kind=d['kind'],source_sha256='a'*64)

    def test_saved_plan_reauthentication_binds_source_and_rejects_changed_input(self):
        from unittest.mock import patch
        m,p,d=self.prepared()
        sdk=ExecutionSDK('/private/tmp/unused-intervention-home')
        with patch.object(sdk,'plan_intervention',side_effect=AssertionError('must stop before auth')):
            with self.assertRaisesRegex(ExecutionError,'INTERVENTION_SOURCE_PIN'):
                sdk.prepare_intervention(d,'missing',expected_sha256='b'*64,output='unused')
        fresh=copy.deepcopy(d);fresh['fixedInputs']['actions'][0]['signedTransaction']='0xab'
        with patch.object(sdk,'plan_intervention',return_value={'descriptor':fresh}),patch.object(sdk,'prepare',side_effect=AssertionError('never prepare altered input')):
            with self.assertRaisesRegex(ExecutionError,'INTERVENTION_PLAN_MISMATCH'):
                sdk.prepare_intervention(d,'unused',expected_sha256='a'*64,output='unused')
