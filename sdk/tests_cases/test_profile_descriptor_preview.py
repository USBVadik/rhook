"""The public Profile Descriptor developer preview (examples/profile_descriptor_preview.py) runs offline from a
clone and reproduces the intervention commitments of the SDK 0.6 G5 prepared inputs exactly."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SDK = Path(__file__).resolve().parents[1]
EXAMPLE = SDK / 'examples/profile_descriptor_preview.py'
DESCRIPTOR = SDK / 'rhook_alpha/cases/scenario/native/descriptors/hookr-1.json'
# interventionCommitment and capsuleId of the three G5 prepared inputs (checkpoint 101935336).
G5 = {('--lp-bps', '23'): ('373c946626acd3caf66c4a0c7adfe4f4defb6ca2614bfa899935187585550cfb',
                           'bb7e3a63cc7db41aef42adc5fe0380771f855419708b7c152b8148b85c50de09'),
      ('--dynamic-fee', 'OFF'): ('719c3dc72b943e69a5d82a04fe8fd5b91bc68d255f4609e1ea7114bf4de5145d',
                                 'bf40ea9c1666d30de489a18f215a12e9c146c9b7a1458483e2a9d23db81064ea'),
      ('--lp-bps', '23', '--dynamic-fee', 'OFF'): ('36738da0425e52980f8446fcf6d29987ae23c450bfffee211ff57bf4efa6229a',
                                                   'b7b6f2e98a9c7b04066c4d7d2a465fb23b54381e4ee4609e25efb24c7c4ccc96')}


def run(*args):
    r = subprocess.run([sys.executable, '-B', str(EXAMPLE), *args], capture_output=True, text=True, timeout=60)
    return r.returncode, json.loads(r.stdout)


class ProfileDescriptorPreview(unittest.TestCase):
    def test_catalogue_lists_the_reviewed_descriptor(self):
        code, v = run('catalogue')
        self.assertEqual(code, 0)
        self.assertEqual(v['catalogueSha256'], '93a2f234259c861e25d07b5b3257f7fea1f777c0b8526b766d55b069a7f1fe92')
        (p,) = v['profiles']
        self.assertEqual((p['profileId'], p['revision'], p['descriptorSha256']),
                         ('hookr-1', 2, '29f21a174b49a306737729da3ad48ef6e9438cd9a0c2a343504b8025ef9e9596'))
        self.assertEqual(p['kinds']['DYNAMIC_FEE_TUNING']['purposes'], ['OFFLINE_PREPARATION'])
        self.assertFalse(v['reviewedEngine']['distributed'])

    def test_inspect_shows_parameters_and_original_fields(self):
        code, v = run('inspect', '--profile', 'hookr-1')
        self.assertEqual(code, 0)
        kinds = {k['kind']: k for k in v['interventions']}
        self.assertEqual(kinds['LP_REWARDS_BPS']['parameters'], [dict(max=99, min=0, name='lpBps', type='uint')])
        self.assertEqual({f['name']: f['baseline'] for f in v['fields']}['lpBps'], 100)

    def test_plan_reproduces_the_g5_commitments_deterministically(self):
        for args, (commitment, capsule) in G5.items():
            first, again = run('plan', *args), run('plan', *args)
            self.assertEqual(first, again)
            code, v = first
            self.assertEqual((code, v['status'], v['interventionCommitment'], v['capsuleId']), (0, 'PROFILE_PLAN_ADMITTED', commitment, capsule))
            self.assertEqual((v['witnessRead'], v['nativeExecution'], v['operation']), (False, 'NOT_PERFORMED', 'NOT_BOUND'))

    def test_dynamic_fee_off_writes_the_reviewed_fields(self):
        code, v = run('plan', '--dynamic-fee', 'OFF')
        self.assertEqual(v['changedFields'], {'dynamicFeeSens': dict(baseline=2, variant=0), 'maxFeePips': dict(baseline=11500, variant=3000),
                                              'rootDynamicFeeFlag': dict(baseline=1, variant=0)})
        self.assertEqual(sorted(w['target'] for w in v['writes']), ['rootRecord', 'rulesConfig'])

    def test_refusals_carry_the_sdk_codes(self):
        cases = {('--lp-bps', '100'): 'PROFILE_PARAMETER',
                 ('--tuning-sens', '1', '--tuning-max-fee', '3000'): 'PROFILE_INVARIANT',
                 ('--tuning-sens', '1', '--tuning-max-fee', '5000', '--purpose', 'NATIVE_EXECUTION'): 'PROFILE_KIND_REVIEW_INSUFFICIENT',
                 ('--dynamic-fee', 'OFF', '--tuning-sens', '1', '--tuning-max-fee', '5000'): 'PROFILE_KIND_CONFLICT'}
        for args, expected in cases.items():
            code, v = run('plan', *args)
            self.assertEqual((code, v['status'], v['code']), (2, 'REFUSED', expected), args)

    def test_tuning_is_offline_only(self):
        code, v = run('plan', '--tuning-sens', '1', '--tuning-max-fee', '5000')
        self.assertEqual((code, v['purpose']), (0, 'OFFLINE_PREPARATION'))

    def test_a_modified_descriptor_validates_but_is_not_loaded_for_workflows(self):
        d = json.loads(DESCRIPTOR.read_bytes())
        for k in d['interventions']:
            if k['kind'] == 'LP_REWARDS_BPS':
                k['parameters'][0]['max'] = 100
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'my-descriptor.json'
            path.write_text(json.dumps(d, sort_keys=True, separators=(',', ':')) + '\n')
            code, v = run('validate', '--descriptor', str(path))
            self.assertEqual((code, v['status'], v['reviewed'], v['workflowUse']), (0, 'DESCRIPTOR_VALID', False, 'REFUSED_NOT_IN_CATALOGUE'))
            path.write_text(DESCRIPTOR.read_text().replace('"revision":2', '"revision":"2"'))
            code, v = run('validate', '--descriptor', str(path))
            self.assertEqual((code, v['code']), (2, 'DESCRIPTOR_SCHEMA'))

    def test_native_requirements_name_the_withheld_assets(self):
        code, v = run('native-requirements')
        self.assertEqual((code, v['status']), (0, 'NATIVE_EXECUTION_NOT_AVAILABLE_FROM_PUBLIC_CLONE'))
        sys.path.insert(0, str(SDK))
        from rhook_alpha import profile_descriptor as pd
        self.assertEqual(v['requiredAndNotDistributed'][0]['identity'], pd.ACCEPTED_PROFILE_ENGINE)
        self.assertEqual(v['offlineOnlyKinds'], ['DYNAMIC_FEE_TUNING'])


if __name__ == '__main__':
    unittest.main()
