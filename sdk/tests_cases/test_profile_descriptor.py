"""Profile Descriptor 0.1: G1 equivalence, G2 negative acceptance, the Dynamic Fee Tuning probe and binding.

Offline only. Optional environment:
  RHOOK_PROFILE_FIXTURE_OUT  directory: write the cross-language fixtures the Go tests read (G1 table, negatives,
                             binding specs).
  RHOOK_ACCEPTED_RECORDS     directory with records/{lp23,dynamic-fee-off,combined}/inputs/SCENARIO.json of the
                             accepted native runs (private; read-only).
"""
import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

from developer.files import canonical, digest
from rhook_alpha import config_overlay as co
from rhook_alpha import profile_descriptor as pd
from rhook_alpha.execution import _profile
from rhook_alpha.session.core import VARIANT_SCHEMA, commit as session_commit

RAW = (pd.DESCRIPTOR_DIR / 'hookr-1.json').read_bytes()
D = pd.parse(RAW)
ORIGINALS = pd.originals_from_descriptor(D)
RULES = '0x4a71c270b1520f94064268102aebd744b0de7942'
ROOT = '0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc'
ROOT_ON = '0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
ROOT_OFF = '0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
# Written out, as in the Go overlay tests: independent of both engines.
WORD_ORIGINAL = '0x0000000007d0000000000064000000020000000000000000002cec0000000000'
WORD_LP23 = '0x0000000007d0000000000017000000020000000000000000002cec0000000000'
WORD_DYN_OFF = '0x0000000007d0000000000064000000000000000000000000000bb80000000000'
WORD_MERGED = '0x0000000007d0000000000017000000000000000000000000000bb80000000000'
WORD_TUNED = '0x0000000007d0000000000064000000010000000000000000001f400000000000'
ENGINE = dict(sourceSha256='a' * 64, binarySha256='b' * 64, policySha256='c' * 64)
SYNTHETIC_CONFIG = hashlib.sha256(b'{}').hexdigest()
FIXTURES = {}


def lp(v):
    return dict(kind='LP_REWARDS_BPS', parameters=dict(lpBps=v))


DYN_OFF = dict(kind='DYNAMIC_FEE', parameters=dict(dynamicFee='OFF'))


def tuning(max_fee, sens):
    return dict(kind='DYNAMIC_FEE_TUNING', parameters=dict(maxFeePips=max_fee, dynamicFeeSens=sens))


def legacy_configs():
    rows = [[dict(kind='LP_REWARDS_BPS', lpBps=v)] for v in range(100)]
    rows.append([dict(kind='DYNAMIC_FEE', dynamicFee='OFF')])
    rows += [[dict(kind='DYNAMIC_FEE', dynamicFee='OFF'), dict(kind='LP_REWARDS_BPS', lpBps=v)] for v in range(100)]
    return rows


def code_of(fn, *args):
    try:
        fn(*args)
    except pd.DescriptorError as error:
        return error.code
    return 'ACCEPTED'


def mutate(edit):
    d = json.loads(RAW)
    edit(d)
    return canonical(d) + b'\n'


def synthetic_source():
    """A complete scenario-input body with synthetic values; no witness, no private data."""
    words = [w['value'] for w in D['originalState']['words'] if w['target'] == 'rulesConfig']
    s = dict(schema='rhook/hookr-scenario/0.1', origin=dict(kind='AUTHENTICATED_CHECKPOINT_SCENARIO', capsuleId='d' * 64),
             checkpoint=dict(chainId=4663, blockNumber=101935336, blockHash='0x' + '11' * 32, stateRoot='0x' + '22' * 32),
             parent=dict(number='0x6136ce8'), chainConfig='0x7b7d', inventory=dict(nodes=[], codes=[]),
             releaseManifestSha256=D['release']['manifestCommitment'], poolId=D['pool']['poolId'],
             configurations=dict(baseline=list(words), variant=list(words)),
             commonSetup=dict(actor='0xd2480fd61af9bc73b8c73e8fdcabceb6f21ea8ff', fundingWei='1000000000000000000', nonce=0,
                              requireOriginalAbsence=True),
             actions=[dict(id='e' * 64, nonce=0, gas=10000000, gasPriceWei='1000000000', amountInWei='1000000000000000',
                           minimumOutputBaseUnits='1', sqrtPriceLimitX96='4295128740', deadline=1793385090, signedTransaction='0x00')],
             environment=dict(l2BlockNumber=101935337, l2Timestamp=1793384790, l1BlockNumber=1, syntheticL1BaseFeeWei='1',
                              poster='0x' + '00' * 20, delayedMessagesRead=1),
             engine=dict(ENGINE), limits=dict(nativeWallSeconds=120, nativeCPUSeconds=120, workerRSSBytes=1 << 30, stageWallSeconds=140,
                                             workflowWallSeconds=180, outputBytes=64 << 20, rpc=0, worlds=2))
    s['scenarioCommitment'] = pd.commit('rhook/hookr-scenario/0.1', s)
    return s


class FakeReader(pd.StateReader):
    def __init__(self):
        self.codes = {c['address']: c.get('runtimeCodeHash') for c in D['contracts']}
        self.store = {}
        for t in D['targets']:
            address = next(c['address'] for c in D['contracts'] if c['name'] == t['contract'])
            for i in range(t['words']):
                self.store[(address, pd._word(int(t['slot'], 16) + i))] = pd._word(ORIGINALS[t['name']][i])

    def code_hash(self, address):
        return self.codes.get(address)

    def has_code(self, address):
        return True if address in self.codes else None

    def storage(self, address, slot):
        return self.store.get((address, slot))


class FakeState:
    """Storage-only world view; it records every write. It has no balance, nonce or code setter."""

    def __init__(self, reader):
        self.store = dict(reader.store)
        self.writes = 0

    def get_storage(self, address, slot):
        return self.store.get((address, slot))

    def set_storage(self, address, slot, value):
        self.writes += 1
        self.store[(address, slot)] = value


class Keccak(unittest.TestCase):
    def test_vectors(self):
        self.assertEqual(pd.keccak256(b'').hex(), 'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        self.assertEqual(pd.keccak256(b'abc').hex(), '4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45')
        # Rate-boundary lengths cross-checked against viem's keccak256 when this test was written.
        self.assertEqual(pd.keccak256(b'x' * 135).hex()[:16], '16570bdb055e663e')
        self.assertEqual(pd.keccak256(b'x' * 136).hex()[:16], '50da8ef3747b7a7f')
        self.assertEqual(pd._word(pd.erc7201('hookr.rules')), '0x762913e4bc0f59f7b08c82f07586fa48932548ab5fab99e6db0b09765b4ff900')


class Descriptor(unittest.TestCase):
    def test_canonical_identity_and_catalogue(self):
        cat = json.loads((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes())
        self.assertEqual(cat['entries'][0]['descriptorSha256'], digest(RAW))
        d, raw, entry = pd.load_accepted('hookr-1', 'OFFLINE_PREPARATION')
        self.assertEqual((raw, d), (RAW, D))
        # After the PASS review of revision 2: a native *candidate*, kind by kind; no engine is accepted.
        self.assertEqual((entry['revision'], entry['review']['status'], entry['review']['nativeExecution'], entry['review']['admits']),
                         (2, 'RHOOK_REVIEWED_NATIVE_CANDIDATE', 'NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED', ['OFFLINE_PREPARATION', 'NATIVE_EXECUTION']))
        self.assertTrue(entry['review']['independentReview'].startswith('PASS_SEMANTIC_REVIEW_R2 sha256:'))
        _, _, native = pd.load_accepted('hookr-1', 'NATIVE_EXECUTION')
        pd.require_kind_review(native, [DYN_OFF, lp(23)], 'NATIVE_EXECUTION')
        self.assertEqual(code_of(pd.require_kind_review, native, [tuning(8000, 1)], 'NATIVE_EXECUTION'), 'PROFILE_KIND_REVIEW_INSUFFICIENT')
        self.assertEqual(code_of(pd.require_kind_review, native, [dict(kind='UNREVIEWED_KIND', parameters={})], 'NATIVE_EXECUTION'),
                         'PROFILE_KIND_REVIEW_INSUFFICIENT')
        self.assertEqual(code_of(pd.load_accepted, 'hookr-2', 'OFFLINE_PREPARATION'), 'PROFILE_NOT_IN_CATALOGUE')
        # G5 preflight: the reviewed G4B identity is recorded in the SDK (not in the embedded catalogue, which is part
        # of the worker source commitment). It is an identity, not an execution authorization.
        self.assertEqual(pd.require_engine_for_native(), dict(sourceSha256='4db4269aad9e28970eb3b13508366771c12827aa8fc5687399e28ff418251546',
                                                              binarySha256='a56db9e53a13331e21c8e45fbb20632a7bc13ef12c864afedf4169a90b35ae04',
                                                              policySha256='792b13a533f79d8d66ade565a5ad41cdb45bd1da4684e06dcdc1825c1a04abc6'))
        self.assertEqual(pd.require_engine_record(RAW)['status'], 'REVIEWED_ENGINE_IDENTITY_NOT_EXECUTION_AUTHORIZATION')
        with unittest.mock.patch.object(pd, 'ACCEPTED_PROFILE_ENGINE', None):
            self.assertEqual(code_of(pd.require_engine_for_native), 'PROFILE_ENGINE_NOT_ACCEPTED')

    def test_generator_output_is_current(self):
        sdk = Path(__file__).resolve().parents[1]
        r = subprocess.run([sys.executable, '-B', str(sdk / 'tools/make_hookr1_descriptor.py'), '--check'], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'DESCRIPTOR_CURRENT'))

    def test_reproduces_the_legacy_profile_exactly(self):
        self.assertEqual(pd.legacy_profile(D), _profile())
        self.assertEqual(D['release']['manifestCommitment'], 'c0b6aed0f8891983c39e22ab4ebe9a7e7b5fe56875301f70467c0895ba34e448')

    def test_derivations_recompute(self):
        self.assertEqual(pd.pool_id(D['pool'], ROOT), D['pool']['poolId'])
        for t in D['targets']:
            self.assertEqual(pd.derive_slot(t['slotDerivation'], D['pool']['poolId']), t['slot'])

    def test_declared_read_hints_are_the_pinned_files(self):
        sdk = Path(__file__).resolve().parents[1]
        for h in D['witness']['readHints']:
            self.assertEqual(digest((sdk / h['path']).read_bytes()), h['sha256'])

    def test_original_words_decode_to_the_reviewed_configuration(self):
        f = pd.decode_fields(D, ORIGINALS)
        expect = dict(maxFeePips=11500, dynamicFeeSens=2, lpBps=100, protocolShareBps=2000, rootBaseLpFeePips=3000,
                      rootDynamicFeeFlag=1, rootRecaptureFlag=1, rootFlagsReserved=0, guardEndBlock=0, royaltyBps=0, burnBps=0)
        self.assertEqual({k: f[k] for k in expect}, expect)
        self.assertEqual(pd._word(f['rootRulesAddress'])[-40:], RULES[2:])


class G1Equivalence(unittest.TestCase):
    def test_all_201_configurations_match_the_sdk04_engine(self):
        p = _profile()
        table = []
        for legacy in legacy_configs():
            old = co.compose(co.canonical_interventions(legacy), p['baselineConfigWords'][0], co.ROOT_ON, p)
            new = pd.compose(D, pd.legacy_items(legacy), ORIGINALS)
            strip = [dict(address=w['address'], slot=w['slot'], before=w['before'], after=w['after']) for w in new['writes']]
            self.assertEqual(strip, old['writes'], legacy)
            self.assertEqual(new['words']['rulesConfig'][0], old['rules'], legacy)
            self.assertEqual(new['words']['rootRecord'][0], old['root'], legacy)
            v = new['fields']['variant']
            mode = v['rootDynamicFeeFlag'] | (v['rootRecaptureFlag'] << 1) | (v['rootFlagsReserved'] << 2)
            self.assertEqual(dict(lpBps=v['lpBps'], maxFeePips=v['maxFeePips'], sensitivity=v['dynamicFeeSens'], rootMode=mode), old['fields'], legacy)
            # Unrelated bits: every declared field the set does not assign equals its original.
            assigned = {a['field'] for i in new['interventions'] for a in next(k for k in D['interventions'] if k['kind'] == i['kind'])['assign']}
            for name, value in v.items():
                if name not in assigned:
                    self.assertEqual(value, new['fields']['baseline'][name], (legacy, name))
            self.assertEqual(new['words']['rulesConfig'][1:], [pd._word(x) for x in ORIGINALS['rulesConfig'][1:]])
            self.assertEqual(new['words']['rootRecord'][1], pd._word(ORIGINALS['rootRecord'][1]))
            table.append(dict(items=new['interventions'], writes=new['writes'], words=new['words']))
        self.assertEqual(len(table), 201)
        FIXTURES['g1'] = table
        FIXTURES['g1Sha256'] = digest(canonical(table))

    def test_accepted_variant_words_written_out(self):
        for items, rules, root in [([lp(23)], WORD_LP23, ROOT_ON), ([DYN_OFF], WORD_DYN_OFF, ROOT_OFF), ([lp(23), DYN_OFF], WORD_MERGED, ROOT_OFF)]:
            c = pd.compose(D, items, ORIGINALS)
            self.assertEqual((c['words']['rulesConfig'][0], c['words']['rootRecord'][0]), (rules, root))

    def test_order_independence_and_canonical_form(self):
        a = pd.compose(D, [lp(23), DYN_OFF], ORIGINALS)
        b = pd.compose(D, [DYN_OFF, lp(23)], ORIGINALS)
        self.assertEqual(a, b)
        self.assertEqual([i['kind'] for i in a['interventions']], ['DYNAMIC_FEE', 'LP_REWARDS_BPS'])

    @unittest.skipUnless(os.environ.get('RHOOK_ACCEPTED_RECORDS'), 'accepted run inputs not supplied')
    def test_accepted_native_inputs(self):
        root = Path(os.environ['RHOOK_ACCEPTED_RECORDS'])
        load = lambda name: json.loads((root / name / 'inputs/SCENARIO.json').read_bytes())
        lp23, dyn, comb = load('lp23'), load('dynamic-fee-off'), load('combined')
        self.assertEqual(pd.compose(D, [lp(23)], ORIGINALS)['words']['rulesConfig'], lp23['configurations']['variant'])
        for spec, items, writes in [(dyn, [DYN_OFF], dyn['intervention']['writes']), (comb, [lp(23), DYN_OFF], comb['configOverlay']['writes'])]:
            got = [dict(address=w['address'], slot=w['slot'], before=w['before'], after=w['after']) for w in pd.compose(D, items, ORIGINALS)['writes']]
            self.assertEqual(got, writes)
        for spec in (lp23, dyn, comb):
            self.assertEqual(spec['releaseManifestSha256'], D['release']['manifestCommitment'])
            self.assertEqual(digest(bytes.fromhex(spec['chainConfig'][2:])), D['chain']['chainConfigSha256'])
            self.assertEqual(spec['configurations']['baseline'], [w['value'] for w in D['originalState']['words'] if w['target'] == 'rulesConfig'])


DESCRIPTOR_NEGATIVES = [
    ('non-canonical encoding', RAW.replace(b'{"action":', b'{ "action":', 1), 'DESCRIPTOR_ENCODING'),
    ('missing trailing newline', RAW[:-1], 'DESCRIPTOR_ENCODING'),
    ('non-ASCII byte', RAW.replace(b'"hookr-1"', b'"hookr-\xc3\xa9"', 1), 'DESCRIPTOR_ENCODING'),
    ('unknown top-level field', mutate(lambda d: d.update(balanceWrites=[])), 'DESCRIPTOR_SCHEMA'),
    ('missing field', mutate(lambda d: d.pop('witness')), 'DESCRIPTOR_SCHEMA'),
    ('unsupported descriptor version', mutate(lambda d: d.update(schema='rhook/hook-profile-descriptor/0.2')), 'DESCRIPTOR_VERSION'),
    ('incompatible engine family', mutate(lambda d: d['chain'].update(engineFamily='GETH')), 'DESCRIPTOR_CHAIN'),
    ('tampered release manifest', mutate(lambda d: d['release']['manifest']['contracts'][0].update(runtimeHash='0x' + '00' * 31 + '01')), 'DESCRIPTOR_RELEASE'),
    ('code hash not the manifest entry', mutate(lambda d: d['contracts'][3].update(runtimeCodeHash='0x' + '00' * 31 + '01')), 'DESCRIPTOR_CONTRACT'),
    ('contract outside the release', mutate(lambda d: d['contracts'][3].update(address='0x' + '12' * 20)), 'DESCRIPTOR_CONTRACT'),
    ('target on an unpinned contract', mutate(lambda d: d['targets'][0].update(contract='targetToken')), 'DESCRIPTOR_TARGET'),
    ('slot that does not recompute', mutate(lambda d: d['targets'][0].update(slot='0x' + '00' * 31 + '05')), 'DESCRIPTOR_SLOT_DERIVATION'),
    ('unknown slot derivation', mutate(lambda d: d['targets'][1].update(slotDerivation=dict(kind='RAW_PATCH'))), 'DESCRIPTOR_SLOT_DERIVATION'),
    ('pool id that does not recompute', mutate(lambda d: d['pool'].update(tickSpacing=61)), 'DESCRIPTOR_POOL_ID'),
    ('unknown field type', mutate(lambda d: d['fields'][0].update(type='int')), 'DESCRIPTOR_FIELD_LAYOUT'),
    ('bit range beyond 256', mutate(lambda d: d['fields'][11].update(width=40)), 'DESCRIPTOR_FIELD_LAYOUT'),
    ('overlapping fields', mutate(lambda d: d['fields'][1].update(offset=36)), 'DESCRIPTOR_FIELD_LAYOUT'),
    ('zero width', mutate(lambda d: d['fields'][1].update(width=0)), 'DESCRIPTOR_FIELD_LAYOUT'),
    ('width as a string', mutate(lambda d: d['fields'][1].update(width='24')), 'DESCRIPTOR_SCHEMA'),
    ('integer above 2^53', mutate(lambda d: d['fields'][1].update(width=1 << 60)), 'DESCRIPTOR_SCHEMA'),
    ('negative integer', mutate(lambda d: d['fields'][1].update(offset=-1)), 'DESCRIPTOR_SCHEMA'),
    ('unknown predicate op', mutate(lambda d: d['interventions'][2]['requires'][0]['compare'].update(op='matches')), 'DESCRIPTOR_PREDICATE'),
    ('expression smuggled into a predicate', mutate(lambda d: d['interventions'][2]['requires'].append({'expr': 'lpBps == 100'})), 'DESCRIPTOR_SCHEMA'),
    ('two predicate forms in one object', mutate(lambda d: d['interventions'][2]['requires'][0].update(
        productBound=dict(factors=[{'field': 'lpBps'}], op='le', bound='1'))), 'DESCRIPTOR_PREDICATE'),
    ('unknown factor form', mutate(lambda d: d['interventions'][1]['ensures'][6]['productBound']['factors'].append({'log': 'lpBps'})), 'DESCRIPTOR_SCHEMA'),
    ('too many factors', mutate(lambda d: d['interventions'][1]['ensures'][7]['productBound']['factors'].extend([{'field': 'lpBps'}, {'field': 'lpBps'}])), 'DESCRIPTOR_PREDICATE'),
    ('predicate on an unknown field', mutate(lambda d: d['interventions'][2]['requires'][0]['compare'].update(left={'field': 'lpBpsX'})), 'DESCRIPTOR_PREDICATE'),
    ('assignment to an unknown field', mutate(lambda d: d['interventions'][2]['assign'][0].update(field='balance')), 'DESCRIPTOR_KIND'),
    ('assignment of an address field', mutate(lambda d: d['interventions'][2]['assign'].append(dict(field='royaltyTo', value={'const': '1'}))), 'DESCRIPTOR_KIND'),
    ('code write smuggled into a kind', mutate(lambda d: d['interventions'][2].update(code='0x6000')), 'DESCRIPTOR_SCHEMA'),
    ('duplicate kinds', mutate(lambda d: d['interventions'].append(copy.deepcopy(d['interventions'][2]))), 'DESCRIPTOR_KIND'),
    ('kinds out of canonical order', mutate(lambda d: d['interventions'].reverse()), 'DESCRIPTOR_KIND'),
    ('one-sided conflict', mutate(lambda d: d['interventions'][0].update(conflictsWith=['DYNAMIC_FEE_TUNING', 'LP_REWARDS_BPS'])), 'DESCRIPTOR_KIND'),
    ('enum parameter with a range', mutate(lambda d: d['interventions'][0]['parameters'][0].update(min=0)), 'DESCRIPTOR_SCHEMA'),
    ('original state not complete', mutate(lambda d: d['originalState']['words'].pop()), 'DESCRIPTOR_ORIGINAL_STATE'),
    ('unsupported original policy', mutate(lambda d: d['originalState'].update(policy='ANY')), 'DESCRIPTOR_ORIGINAL_STATE'),
    ('unsupported action', mutate(lambda d: d['action'].update(type='ARBITRARY_CALL')), 'DESCRIPTOR_ACTION'),
    ('measure from an unknown source', mutate(lambda d: d['measures'][0].update(source='PROFIT')), 'DESCRIPTOR_MEASURE'),
]


class G2DescriptorNegatives(unittest.TestCase):
    def test_each_malformed_descriptor_stops_with_its_code(self):
        rows = []
        for name, raw, expect in DESCRIPTOR_NEGATIVES:
            self.assertEqual(code_of(pd.parse, raw), expect, name)
            rows.append(dict(name=name, rawBase64=base64.b64encode(raw).decode(), expect=expect))
        FIXTURES['descriptorNegatives'] = rows

    def test_tampered_descriptor_bytes_are_not_loaded(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(pd.DESCRIPTOR_DIR / 'CATALOGUE.json', tmp)
            (Path(tmp) / 'hookr-1.json').write_bytes(mutate(lambda d: d['fields'][1].update(semanticsSource='edited')))
            self.assertEqual(code_of(lambda: pd.load_accepted('hookr-1', 'OFFLINE_PREPARATION', directory=tmp)), 'PROFILE_DESCRIPTOR_HASH')


def with_original(target, word, value):
    o = copy.deepcopy(ORIGINALS)
    o[target][word] = value
    return o


COMPOSITION_NEGATIVES = [
    ('no interventions', [], ORIGINALS, 'PROFILE_INTERVENTION_COUNT'),
    ('unknown kind', [dict(kind='STORAGE_PATCH', parameters={})], ORIGINALS, 'PROFILE_UNKNOWN_INTERVENTION'),
    ('legacy shape without parameters', [dict(kind='LP_REWARDS_BPS', lpBps=23)], ORIGINALS, 'PROFILE_INTERVENTION_SHAPE'),
    ('duplicate interventions', [lp(23), lp(24)], ORIGINALS, 'PROFILE_DUPLICATE_KIND'),
    ('declared conflict', [DYN_OFF, tuning(8000, 1)], ORIGINALS, 'PROFILE_KIND_CONFLICT'),
    ('parameter above range', [lp(100)], ORIGINALS, 'PROFILE_PARAMETER'),
    ('parameter as boolean', [lp(True)], ORIGINALS, 'PROFILE_PARAMETER'),
    ('parameter as string', [lp('23')], ORIGINALS, 'PROFILE_PARAMETER'),
    ('enum value not admitted', [dict(kind='DYNAMIC_FEE', parameters=dict(dynamicFee='ON'))], ORIGINALS, 'PROFILE_PARAMETER'),
    ('extra parameter', [dict(kind='LP_REWARDS_BPS', parameters=dict(lpBps=23, slot='0x00'))], ORIGINALS, 'PROFILE_PARAMETER'),
    ('substituted original word', [lp(23)], with_original('rulesConfig', 0, int(WORD_LP23, 16)), 'PROFILE_ORIGINAL_WORD'),
    ('substituted unrelated original word', [lp(23)], with_original('rootRecord', 1, 0), 'PROFILE_ORIGINAL_WORD'),
    ('missing witness word', [lp(23)], {'rulesConfig': ORIGINALS['rulesConfig']}, 'PROFILE_ORIGINAL_STATE_UNAVAILABLE'),
    ('tuning equal to the original', [tuning(11500, 2)], ORIGINALS, 'PROFILE_NO_EFFECT'),
    ('tuning down to the base fee', [tuning(3000, 1)], ORIGINALS, 'PROFILE_INVARIANT'),
    ('tuning past the reach bound', [tuning(75001, 10)], ORIGINALS, 'PROFILE_INVARIANT'),
    ('tuning past the Root caps (revision 2)', [tuning(11501, 1)], ORIGINALS, 'PROFILE_INVARIANT'),
    ('tuning past the reserve bound', [tuning(118267, 1)], ORIGINALS, 'PROFILE_INVARIANT'),
    ('tuning sensitivity zero', [tuning(8000, 0)], ORIGINALS, 'PROFILE_PARAMETER'),
]


class G2CompositionNegatives(unittest.TestCase):
    def test_each_rejected_intervention_set_stops_with_its_code(self):
        rows = []
        for name, items, originals, expect in COMPOSITION_NEGATIVES:
            self.assertEqual(code_of(pd.compose, D, items, originals), expect, name)
            rows.append(dict(name=name, items=items, originals={k: [pd._word(x) for x in v] for k, v in originals.items()}, expect=expect))
        FIXTURES['compositionNegatives'] = rows

    def test_descriptor_mask_overlap_and_width(self):
        two = mutate(lambda d: d['interventions'][2]['assign'].append(dict(field='maxFeePips', value={'const': '1'})))
        mixed = pd.parse(two)
        self.assertEqual(code_of(pd.compose, mixed, [DYN_OFF, lp(23)], ORIGINALS), 'PROFILE_MASK_CONFLICT')
        wide = pd.parse(mutate(lambda d: d['interventions'][2]['parameters'][0].update(max=70000)))
        self.assertEqual(code_of(pd.compose, wide, [lp(65536)], ORIGINALS), 'PROFILE_VALUE_WIDTH')
        self.assertEqual(pd.compose(wide, [lp(65535)], ORIGINALS)['fields']['variant']['lpBps'], 65535)
        FIXTURES['maskAndWidth'] = [dict(name='mask overlap', rawBase64=base64.b64encode(two).decode(), items=[DYN_OFF, lp(23)], expect='PROFILE_MASK_CONFLICT'),
                                    dict(name='value width', rawBase64=base64.b64encode(canonical(wide) + b'\n').decode(), items=[lp(65536)], expect='PROFILE_VALUE_WIDTH')]

    def test_original_precondition(self):
        no_dynamic = with_original('rootRecord', 0, int(ROOT_OFF, 16))
        relaxed = pd.parse(mutate(lambda d: d['originalState']['words'][4].update(value=ROOT_OFF)))
        self.assertEqual(code_of(pd.compose, relaxed, [DYN_OFF], no_dynamic), 'PROFILE_ORIGINAL_PRECONDITION')
        self.assertEqual(code_of(pd.compose, relaxed, [tuning(8000, 1)], no_dynamic), 'PROFILE_ORIGINAL_PRECONDITION')


class G2StateAndApply(unittest.TestCase):
    def test_authentication_reads_every_target_word(self):
        self.assertEqual(pd.authenticate(D, FakeReader()), ORIGINALS)

    def test_wrong_code_hash(self):
        r = FakeReader()
        r.codes[RULES] = '0x' + '00' * 31 + '01'
        self.assertEqual(code_of(pd.authenticate, D, r), 'PROFILE_CODE_IDENTITY')

    def test_missing_witness_is_never_zero(self):
        r = FakeReader()
        del r.store[(RULES, pd._word(int(D['targets'][0]['slot'], 16) + 2))]
        self.assertEqual(code_of(pd.authenticate, D, r), 'PROFILE_ORIGINAL_STATE_UNAVAILABLE')
        r = FakeReader()
        r.codes[ROOT] = None
        self.assertEqual(code_of(pd.authenticate, D, r), 'PROFILE_ORIGINAL_STATE_UNAVAILABLE')

    def test_token_code_required(self):
        r = FakeReader()
        r.has_code = lambda address: False if address == D['pool']['currency1'] else True
        self.assertEqual(code_of(pd.authenticate, D, r), 'PROFILE_TOKEN_CODE_REQUIRED')

    def test_baseline_unchanged_and_all_originals_checked_before_any_write(self):
        c = pd.compose(D, [lp(23), DYN_OFF], ORIGINALS)
        base = FakeState(FakeReader())
        rows = pd.apply_writes(D, base, c['writes'], 'SCENARIO_BASELINE')
        self.assertEqual((base.writes, [r['after'] for r in rows]), (0, [r['before'] for r in rows]))
        variant = FakeState(FakeReader())
        pd.apply_writes(D, variant, c['writes'], 'SCENARIO_VARIANT')
        self.assertEqual(variant.writes, 2)
        bad = FakeState(FakeReader())
        bad.store[(ROOT, D['targets'][1]['slot'])] = ROOT_OFF
        self.assertEqual(code_of(pd.apply_writes, D, bad, c['writes'], 'SCENARIO_VARIANT'), 'PROFILE_ORIGINAL_WORD_CHANGED')
        self.assertEqual(bad.writes, 0)
        self.assertEqual(code_of(pd.apply_writes, D, base, c['writes'], 'OTHER'), 'PROFILE_WORLD')

    def test_writes_outside_declared_targets_and_non_storage_changes(self):
        c = pd.compose(D, [lp(23)], ORIGINALS)
        for edit in (lambda w: w.update(slot='0x' + '00' * 32), lambda w: w.update(address=D['pool']['currency1']),
                     lambda w: w.update(kind='BALANCE'), lambda w: w.update(target='rootRecord')):
            writes = copy.deepcopy(c['writes'])
            edit(writes[0])
            self.assertEqual(code_of(pd.check_writes, D, writes), 'PROFILE_WRITE_TARGET')
        self.assertFalse(any(hasattr(FakeState, n) for n in ('set_balance', 'set_nonce', 'set_code')))


class Probe(unittest.TestCase):
    """Dynamic Fee Tuning, keeping Dynamic Fee ON: maxFeePips 11500 -> 8000, sensitivity 2 -> 1."""

    def test_candidate_is_admitted_by_data_alone(self):
        c = pd.compose(D, [tuning(8000, 1)], ORIGINALS)
        v, b = c['fields']['variant'], c['fields']['baseline']
        self.assertEqual((v['maxFeePips'], v['dynamicFeeSens'], v['lpBps'], v['rootDynamicFeeFlag'], v['rootRecaptureFlag']), (8000, 1, 100, 1, 1))
        self.assertEqual([k for k in v if v[k] != b[k]], ['maxFeePips', 'dynamicFeeSens'])
        self.assertEqual([(w['target'], w['word'], w['after']) for w in c['writes']], [('rulesConfig', 0, WORD_TUNED)])
        span = v['maxFeePips'] - v['rootBaseLpFeePips']
        self.assertEqual((span * v['dynamicFeeSens'] ** 2, span * v['protocolShareBps'] * (432 - v['dynamicFeeSens'] ** 2)), (5000, 4310000000))
        both = pd.compose(D, [lp(23), tuning(8000, 1)], ORIGINALS)
        self.assertEqual(both['words']['rulesConfig'][0], '0x0000000007d0000000000017000000010000000000000000001f400000000000')
        FIXTURES['probe'] = dict(items=[tuning(8000, 1)], writes=c['writes'], combined=both['writes'])

    def test_bounds_follow_the_vendor_bind_rules_and_the_root_caps(self):
        # Revision 2: the pool's Root caps (17800 / 3700) bound maxFeePips at 11500 (independent review BLOCK on
        # revision 1; an exhaustive vendor check is kept with the private semantic review record).
        for items, want in [([tuning(8000, 1)], 'ACCEPTED'), ([tuning(11500, 1)], 'ACCEPTED'), ([tuning(11500, 10)], 'ACCEPTED'),
                            ([tuning(3001, 1)], 'ACCEPTED'), ([tuning(8000, 10)], 'ACCEPTED'), ([tuning(11501, 1)], 'PROFILE_INVARIANT'),
                            ([tuning(11501, 10)], 'PROFILE_INVARIANT'), ([tuning(75000, 10)], 'PROFILE_INVARIANT'),
                            ([tuning(118266, 1)], 'PROFILE_INVARIANT'), ([tuning(3000, 1)], 'PROFILE_INVARIANT'), ([tuning(8000, 0)], 'PROFILE_PARAMETER'),
                            ([tuning(8000, 11)], 'PROFILE_PARAMETER'), ([tuning(600001, 1)], 'PROFILE_PARAMETER'),
                            ([tuning(11500, 2)], 'PROFILE_NO_EFFECT'), ([lp(23), tuning(8000, 1)], 'ACCEPTED'),
                            ([lp(0), tuning(11500, 10)], 'ACCEPTED'), ([lp(23), tuning(11501, 1)], 'PROFILE_INVARIANT'),
                            ([DYN_OFF, tuning(8000, 1)], 'PROFILE_KIND_CONFLICT')]:
            self.assertEqual(code_of(lambda: pd.compose(D, pd.canonical_interventions(D, items), ORIGINALS)), want, items)

    def test_tuning_grid_table_for_go(self):
        """Codes on maxFeePips 2990..12010 x sensitivity 0..11, alone and with LP 23; Go recomputes the same table."""
        rows = []
        for with_lp in (False, True):
            for m in range(2990, 12011):
                for s in range(0, 12):
                    items = [tuning(m, s)] + ([lp(23)] if with_lp else [])
                    try:
                        items = pd.canonical_interventions(D, items)
                        pd.compose(D, items, ORIGINALS)
                        rows.append('ACCEPTED')
                    except pd.DescriptorError as error:
                        rows.append(error.code)
        table = '\n'.join(rows).encode()
        self.assertEqual(rows.count('ACCEPTED'), 2 * 8500 * 10 - 1)
        FIXTURES['tuningGrid'] = dict(maxFeePips=[2990, 12010], dynamicFeeSens=[0, 11], withLp=[None, 23], points=len(rows), sha256=digest(table))

    def test_no_go_registry_entry_exists_for_the_kind(self):
        go = (pd.DESCRIPTOR_DIR.parent / 'overlay.go').read_text()
        self.assertNotIn('DYNAMIC_FEE_TUNING', go)
        self.assertNotIn('DYNAMIC_FEE_TUNING', (pd.DESCRIPTOR_DIR.parent / 'descriptor.go').read_text())


class Binding(unittest.TestCase):
    def test_prepared_input_binds_the_descriptor(self):
        source = synthetic_source()
        rows = []
        for name, items in [('lp23', [lp(23)]), ('dynamic-fee-off', [DYN_OFF]), ('combined', [DYN_OFF, lp(23)]), ('tuning', [tuning(8000, 1)])]:
            s = pd.build_spec(source, RAW, items, ENGINE)
            self.assertEqual(s['profileOverlay']['descriptor']['sha256'], digest(RAW))
            self.assertEqual(pd.validate_spec(s, RAW), s)
            rows.append(dict(name=name, spec=s, expect='ACCEPTED'))
        s = rows[2]['spec']
        tampered = []
        t = copy.deepcopy(s)
        t['profileOverlay']['descriptor']['sha256'] = 'f' * 64
        tampered.append(('descriptor hash swapped', t, 'PROFILE_SPEC_COMMITMENT'))
        t = copy.deepcopy(t)
        t.pop('scenarioCommitment')
        t['scenarioCommitment'] = pd.commit(pd.SPEC_DOMAIN, t)
        tampered.append(('descriptor hash swapped and rehashed', t, 'PROFILE_SPEC_BINDING'))
        t = copy.deepcopy(s)
        t['profileOverlay']['writes'][0]['after'] = WORD_LP23
        t.pop('scenarioCommitment')
        t['scenarioCommitment'] = pd.commit(pd.SPEC_DOMAIN, t)
        tampered.append(('derived write edited and rehashed', t, 'PROFILE_SPEC_DERIVED_WRITES'))
        t = copy.deepcopy(s)
        t['configurations']['variant'][0] = WORD_LP23
        t.pop('scenarioCommitment')
        t['scenarioCommitment'] = pd.commit(pd.SPEC_DOMAIN, t)
        tampered.append(('variant word edited and rehashed', t, 'PROFILE_SPEC_VARIANT_WORD'))
        t = copy.deepcopy(s)
        t['profileOverlay']['interventions'].reverse()
        t.pop('scenarioCommitment')
        t['scenarioCommitment'] = pd.commit(pd.SPEC_DOMAIN, t)
        tampered.append(('non-canonical intervention order', t, 'PROFILE_CANONICAL_ORDER'))
        for name, spec, expect in tampered:
            self.assertEqual(code_of(pd.validate_spec, spec, RAW), expect, name)
            rows.append(dict(name=name, spec=spec, expect=expect))
        FIXTURES['binding'] = rows
        FIXTURES['descriptorSha256'] = digest(RAW)

    def test_variant_identity_commits_to_the_descriptor(self):
        session_id = 'a' * 64
        v1 = pd.variant_descriptor(RAW, [DYN_OFF, lp(23)])
        other = mutate(lambda d: d['provenance'].update(contractSources='edited provenance'))
        v2 = pd.variant_descriptor(other, [DYN_OFF, lp(23)])
        self.assertEqual(v1['interventions'], v2['interventions'])
        ids = {session_commit(VARIANT_SCHEMA, dict(sessionId=session_id, descriptor=v)) for v in (v1, v2)}
        self.assertEqual(len(ids), 2)

    @unittest.skipUnless(os.environ.get('RHOOK_ACCEPTED_RECORDS'), 'accepted run inputs not supplied')
    def test_binding_from_the_accepted_lp23_input(self):
        src = json.loads((Path(os.environ['RHOOK_ACCEPTED_RECORDS']) / 'lp23/inputs/SCENARIO.json').read_bytes())
        s = pd.build_spec(src, RAW, [DYN_OFF, lp(23)], ENGINE)
        self.assertEqual(s['inventory'], src['inventory'])
        self.assertEqual(s['configurations']['variant'][0], WORD_MERGED)


class _FakeSDK:
    def __init__(self, home):
        self.home = Path(home)
        self.registry = type('Registry', (), {'_prepare': staticmethod(lambda: None)})()


def _shipped_kinds():
    return json.loads((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes())['entries'][0]['kinds']


def _test_catalogue(tmp, raw, admits, kinds=None):
    """A test-only catalogue directory over the given descriptor bytes (never the shipped catalogue). Per-kind
    statuses default to the shipped ones, so an offline-only kind stays offline-only."""
    d = pd.parse(raw)
    Path(tmp).mkdir(mode=0o700)
    entry = dict(descriptorFile='test-1.json', descriptorSha256=digest(raw), kinds=dict(kinds or _shipped_kinds()),
                 profileId=d['profileId'], revision=d['revision'],
                 review=dict(admits=list(admits), author='test', independentReview='TEST_ONLY', nativeExecution='TEST_ONLY', status='TEST_ONLY'))
    Path(tmp, 'test-1.json').write_bytes(raw)
    Path(tmp, 'CATALOGUE.json').write_bytes(canonical(dict(entries=[entry], schema=pd.CATALOGUE_SCHEMA)) + b'\n')
    return Path(tmp)


def _accepting(engine, raw, directory):
    """Test-only: accept `engine` for the descriptor bytes and catalogue directory of a synthetic flow (the
    identity and its record are patched together, as the SDK requires them to agree)."""
    record = dict(pd.PROFILE_ENGINE_RECORD, engine=engine, descriptor=pd.descriptor_ref(raw),
                  catalogueSha256=digest((Path(directory) / 'CATALOGUE.json').read_bytes()))
    return unittest.mock.patch.multiple(pd, ACCEPTED_PROFILE_ENGINE=engine, PROFILE_ENGINE_RECORD=record)


def _capture(sdk, plan, spec, name='capture'):
    """A prepared-input capture as the offline preparation writes it (no acquisition, no worker)."""
    out = sdk.home / name
    out.mkdir(mode=0o700)
    raw = canonical(spec) + b'\n'
    (out / 'SCENARIO.json').write_bytes(raw)
    v = dict(status='PREPARED_SCENARIO_INPUT', authentication='PENDING_NATIVE_ADMISSION', nativeExecutions=0, cleanupConfirmed=True,
             planId=plan['planId'], planCommitment=plan['planCommitment'], scenarioSha256=hashlib.sha256(raw).hexdigest(),
             scenarioCommitment=spec['scenarioCommitment'])
    (out / 'SDK_RESULT.json').write_bytes(canonical(v) + b'\n')
    return out, v


class G4ABackend(unittest.TestCase):
    """G4A: the descriptor-driven backend profile nitro-hook-profile-overlay/0.1 in the scenario API. Offline only:
    plans, prepared-input checks and the operation proposal identity; no worker, witness or authority."""

    def setUp(self):
        import tempfile
        from rhook_alpha.cases.scenario import api
        self.api = api
        self.tmp = tempfile.TemporaryDirectory(prefix='rhook-g4a-')
        self.sdk = _FakeSDK(Path(self.tmp.name).resolve())

    def tearDown(self):
        self.tmp.cleanup()

    def test_worker_bounds_mirror_the_go_worker(self):
        self.assertIs(pd.validate_worker_bounds(D), D)
        for name, edit in [('chain id', lambda d: d['chain'].update(chainId=4664)), ('ArbOS', lambda d: d['chain'].update(arbosVersion=60)),
                           ('amount', lambda d: d['action'].update(amountInWei='2000000000000000')),
                           ('gas options', lambda d: d['action'].update(gas=[10000000])),
                           ('price limit', lambda d: d['action'].update(sqrtPriceLimitX96='4295128741')),
                           ('ABI', lambda d: d['action']['abi'][0].update(name='swapExact')),
                           ('actor seed', lambda d: d['setup']['actor'].update(seed='OTHER')),
                           ('funding', lambda d: d['setup'].update(fundingWei='2000000000000000000')),
                           ('Root flags swapped', lambda d: [f.update(offset={'rootDynamicFeeFlag': 249, 'rootRecaptureFlag': 248}[f['name']])
                                                            for f in d['fields'] if f['name'] in ('rootDynamicFeeFlag', 'rootRecaptureFlag')]),
                           ('reviewed Root caps word', lambda d: [w.update(value='0x' + '00' * 31 + '01') for w in d['originalState']['words']
                                                                 if (w['target'], w['word']) == ('rootRecord', 1)]),
                           ('reviewed Rules word 2', lambda d: [w.update(value='0x' + '00' * 31 + '01') for w in d['originalState']['words']
                                                               if (w['target'], w['word']) == ('rulesConfig', 2)]),
                           ('reviewed original Root word', lambda d: [w.update(value=ROOT_OFF) for w in d['originalState']['words']
                                                                     if (w['target'], w['word']) == ('rootRecord', 0)]),
                           ('chain config hash', lambda d: d['chain'].update(chainConfigSha256='e' * 64))]:
            alt = pd.parse(mutate(edit))
            self.assertEqual(code_of(pd.validate_worker_bounds, alt), 'PROFILE_WORKER_BOUNDS', name)

    def test_backend_profile_and_domain_are_registered_separately(self):
        api = self.api
        self.assertEqual(api.PROFILE_OVERLAY_PROFILE, pd.BACKEND_PROFILE)
        self.assertEqual(api.DOMAINS[api.PROFILE_OVERLAY_PROFILE], pd.SPEC_DOMAIN)
        self.assertEqual(len(set(api.DOMAINS.values())), len(api.PROFILES))
        self.assertIn('nitro-hook-profile-overlay/0.1', (pd.SDK_ROOT / 'tools/build_scenario_worker.py').read_text())

    def test_plan_names_the_descriptor_and_refuses_lp_outside_it(self):
        api = self.api
        plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[DYN_OFF, lp(23)])
        self.assertEqual((plan['profile'], plan['executionAuthorized'], plan['intent']['profile']['sha256']),
                         (api.PROFILE_OVERLAY_PROFILE, False, digest(RAW)))
        self.assertEqual(api.describe(self.sdk, plan['planId']), {k: v for k, v in plan.items() if k not in ('status', 'executionAuthorized', 'results')})
        for kwargs, code in [(dict(lp_bps=23, descriptor='hookr-1', interventions=[lp(23)]), 'PROFILE_OVERLAY_DESCRIPTOR_AND_INTERVENTIONS_REQUIRED'),
                             (dict(descriptor='hookr-1'), 'PROFILE_OVERLAY_DESCRIPTOR_AND_INTERVENTIONS_REQUIRED'),
                             (dict(descriptor='hookr-2', interventions=[lp(23)]), 'PROFILE_NOT_IN_CATALOGUE'),
                             (dict(descriptor='hookr-1', interventions=[lp(23), DYN_OFF]), 'PROFILE_CANONICAL_SET_REQUIRED')]:
            with self.assertRaises(ValueError) as caught:
                api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, **kwargs)
            self.assertIn(code, str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            api.configure(self.sdk, profile=api.OVERLAY_PROFILE, descriptor='hookr-1', interventions=[dict(kind='LP_REWARDS_BPS', lpBps=23)])
        self.assertIn('DESCRIPTOR_ONLY_FOR_PROFILE_OVERLAY', str(caught.exception))
        legacy = api.configure(self.sdk)
        self.assertEqual((legacy['profile'], legacy['intent']['lpBps']), (api.PROFILE, 50))

    def test_prepared_input_link_and_operation_binding(self):
        api = self.api
        # A test catalogue over a descriptor whose reviewed chain configuration is the synthetic one ('{}'); the
        # compiled chain-config bound is patched to it for this synthetic flow only (the real one is in the
        # accepted-records test below).
        raw = mutate(lambda d: d['chain'].update(chainConfigSha256=SYNTHETIC_CONFIG))
        with unittest.mock.patch.dict(pd.WORKER_BOUNDS, chainConfigSha256=SYNTHETIC_CONFIG), \
                unittest.mock.patch.object(pd, 'DESCRIPTOR_DIR', _test_catalogue(self.sdk.home / 'cat-offline', raw, ['OFFLINE_PREPARATION'])):
            plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[DYN_OFF, lp(23)])
            spec = pd.build_spec(synthetic_source(), raw, [DYN_OFF, lp(23)], ENGINE)
            capture, v = _capture(self.sdk, plan, spec)
            self.assertEqual(api._input(self.sdk, capture)[3], spec)
            other = pd.build_spec(synthetic_source(), raw, [lp(23)], ENGINE)
            capture2, _ = _capture(self.sdk, plan, other, 'capture-other')
            with self.assertRaises(ValueError) as caught:
                api._input(self.sdk, capture2)
            self.assertIn('SCENARIO_PLAN_LINK', str(caught.exception))
            r = dict(profile=api.PROFILE_OVERLAY_PROFILE, sourceCommitment='1' * 64, files=dict(worker=dict(sha256='2' * 64)))
            with self.assertRaises(pd.DescriptorError) as caught:
                api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
            self.assertEqual(caught.exception.code, 'PROFILE_REVIEW_INSUFFICIENT')
        accepted = dict(sourceSha256='1' * 64, binarySha256='2' * 64, policySha256=api.POLICY_SHA)
        native_dir = _test_catalogue(self.sdk.home / 'cat-native', raw, ['OFFLINE_PREPARATION', 'NATIVE_EXECUTION'])
        with unittest.mock.patch.dict(pd.WORKER_BOUNDS, chainConfigSha256=SYNTHETIC_CONFIG), \
                unittest.mock.patch.object(pd, 'DESCRIPTOR_DIR', native_dir):
            with self.assertRaises(pd.DescriptorError) as caught:
                api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
            self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_NOT_ACCEPTED')
            # Another worker identity than the accepted one is refused, whichever field differs.
            for field in accepted:
                with unittest.mock.patch.object(pd, 'ACCEPTED_PROFILE_ENGINE', dict(accepted, **{field: 'f' * 64})):
                    with self.assertRaises(pd.DescriptorError) as caught:
                        api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
                    self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_NOT_ACCEPTED', field)
            # The identity alone is not enough: its record must name these descriptor and catalogue bytes.
            with unittest.mock.patch.object(pd, 'ACCEPTED_PROFILE_ENGINE', accepted):
                with self.assertRaises(pd.DescriptorError) as caught:
                    api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
                self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_RECORD')
            with _accepting(accepted, raw, native_dir):
                b = api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
        self.assertEqual(b['profileDescriptor'], dict(profileId='hookr-1', revision=D['revision'], sha256=digest(raw)))
        self.assertEqual(b['profileDescriptor'], spec['profileOverlay']['descriptor'])
        body = dict(b)
        self.assertEqual(body.pop('operationCommitment'), digest(b'rhook/scenario-operation/0.1\n' + canonical(body)))

    def test_offline_only_kind_stays_offline_under_a_native_review(self):
        api = self.api
        r = dict(profile=api.PROFILE_OVERLAY_PROFILE, sourceCommitment='1' * 64, files=dict(worker=dict(sha256='2' * 64)))
        v = dict(scenarioCommitment='3' * 64, scenarioSha256='4' * 64)
        accepted = dict(sourceSha256='1' * 64, binarySha256='2' * 64, policySha256=api.POLICY_SHA)
        raw = RAW
        cat = _test_catalogue(self.sdk.home / 'cat', raw, ['OFFLINE_PREPARATION', 'NATIVE_EXECUTION'])
        with unittest.mock.patch.object(pd, 'DESCRIPTOR_DIR', cat), _accepting(accepted, raw, cat):
            plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[tuning(8000, 1)])
            with self.assertRaises(pd.DescriptorError) as caught:
                api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
            self.assertEqual(caught.exception.code, 'PROFILE_KIND_REVIEW_INSUFFICIENT')
            both = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[DYN_OFF, lp(23)])
            self.assertEqual(api.operation_binding(self.sdk, both, v, r, {'profile': 'v2'})['profileDescriptor']['sha256'], digest(raw))
        kinds = dict(_shipped_kinds(), LP_REWARDS_BPS='TEST_ONLY_UNKNOWN_STATUS')
        directory = _test_catalogue(self.sdk.home / 'cat-unknown', RAW, ['OFFLINE_PREPARATION'], kinds)
        self.assertEqual(code_of(lambda: pd.load_accepted('hookr-1', 'OFFLINE_PREPARATION', directory=directory)), 'PROFILE_CATALOGUE')

    def test_shipped_catalogue_refuses_native_operations_and_chain_config_drift(self):
        api = self.api
        plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[DYN_OFF])
        spec = pd.build_spec(synthetic_source(), RAW, [DYN_OFF], ENGINE)
        capture, v = _capture(self.sdk, plan, spec)
        with self.assertRaises(pd.DescriptorError) as caught:
            api._input(self.sdk, capture)
        self.assertEqual(caught.exception.code, 'PROFILE_CHAIN_CONFIG')
        r = dict(profile=api.PROFILE_OVERLAY_PROFILE, sourceCommitment='1' * 64, files=dict(worker=dict(sha256='2' * 64)))
        # The reviewed catalogue admits Dynamic Fee OFF as a native candidate; this runtime is not the reviewed identity.
        with self.assertRaises(pd.DescriptorError) as caught:
            api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
        self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_NOT_ACCEPTED')
        with self.assertRaises(ValueError) as caught:
            api.acquire(self.sdk, plan['planId'], self.sdk.home / 'out', credential_file='x', account_assertions='y', read_only=True)
        self.assertIn('DYNAMIC_OFFLINE_ONLY', str(caught.exception))

    def test_profiles_do_not_accept_each_others_inputs(self):
        api = self.api
        spec = pd.build_spec(synthetic_source(), RAW, [DYN_OFF, lp(23)], ENGINE)
        overlay_plan = api.configure(self.sdk, profile=api.OVERLAY_PROFILE, interventions=co.canonical_interventions(
            [dict(kind='DYNAMIC_FEE', dynamicFee='OFF'), dict(kind='LP_REWARDS_BPS', lpBps=23)]))
        capture, _ = _capture(self.sdk, overlay_plan, spec)
        with self.assertRaises(ValueError) as caught:
            api._input(self.sdk, capture)
        self.assertIn('SCENARIO_SPEC_COMMITMENT', str(caught.exception))
        self.assertEqual(code_of(pd.validate_input, synthetic_source(), RAW), 'PROFILE_SPEC_COMMITMENT')
        with self.assertRaises(ValueError):
            co.validate_spec(spec)
        r = dict(profile=api.OVERLAY_PROFILE, sourceCommitment='1' * 64, files=dict(worker=dict(sha256='2' * 64)))
        b = api.operation_binding(self.sdk, overlay_plan, dict(scenarioCommitment='3' * 64, scenarioSha256='4' * 64), r, {'profile': 'v2'})
        self.assertNotIn('profileDescriptor', b)

    @unittest.skipUnless(os.environ.get('RHOOK_ACCEPTED_RECORDS'), 'accepted run inputs not supplied')
    def test_accepted_input_passes_the_data_checks_and_stays_offline(self):
        api = self.api
        src = json.loads((Path(os.environ['RHOOK_ACCEPTED_RECORDS']) / 'lp23/inputs/SCENARIO.json').read_bytes())
        plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[DYN_OFF, lp(23)])
        spec = pd.build_spec(src, RAW, [DYN_OFF, lp(23)], src['engine'])
        capture, v = _capture(self.sdk, plan, spec)
        self.assertEqual(api._input(self.sdk, capture)[3], spec)
        r = dict(profile=api.PROFILE_OVERLAY_PROFILE, sourceCommitment='1' * 64, files=dict(worker=dict(sha256='2' * 64)))
        with self.assertRaises(pd.DescriptorError) as caught:
            api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
        self.assertEqual(caught.exception.code, 'PROFILE_ENGINE_NOT_ACCEPTED')

    def test_shipped_catalogue_native_matrix(self):
        """Shipped catalogue: a native operation for an offline-only or unreviewed kind is refused on the
        operation path (Python API and CLI run/prepare), the session layer offers no such backend, and
        legacy-equivalent kinds stop at a runtime that is not the reviewed engine identity. No authority is issued."""
        api = self.api
        r = dict(profile=api.PROFILE_OVERLAY_PROFILE, sourceCommitment='1' * 64, files=dict(worker=dict(sha256='2' * 64)))
        v = dict(scenarioCommitment='3' * 64, scenarioSha256='4' * 64)
        expect = [([tuning(8000, 1)], 'PROFILE_KIND_REVIEW_INSUFFICIENT'), ([lp(23), tuning(8000, 1)], 'PROFILE_KIND_REVIEW_INSUFFICIENT'),
                  ([DYN_OFF, lp(23)], 'PROFILE_ENGINE_NOT_ACCEPTED'), ([lp(23)], 'PROFILE_ENGINE_NOT_ACCEPTED'), ([DYN_OFF], 'PROFILE_ENGINE_NOT_ACCEPTED')]
        for items, code in expect:
            plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=pd.canonical_interventions(D, items))
            with self.assertRaises(pd.DescriptorError) as caught:
                api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
            self.assertEqual(caught.exception.code, code, items)
            # Even with an accepted engine identity, an offline-only kind stays refused.
            with unittest.mock.patch.object(pd, 'ACCEPTED_PROFILE_ENGINE', dict(sourceSha256='1' * 64, binarySha256='2' * 64, policySha256=api.POLICY_SHA)):
                if code == 'PROFILE_KIND_REVIEW_INSUFFICIENT':
                    with self.assertRaises(pd.DescriptorError) as caught:
                        api.operation_binding(self.sdk, plan, v, r, {'profile': 'v2'})
                    self.assertEqual(caught.exception.code, code)
        # An intent naming a kind outside the catalogue cannot be planned.
        with self.assertRaises(pd.DescriptorError) as caught:
            api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=[dict(kind='UNREVIEWED_KIND', parameters={})])
        self.assertEqual(caught.exception.code, 'PROFILE_UNKNOWN_INTERVENTION')
        # The session layer exposes no descriptor backend.
        from rhook_alpha.session.hookr import HookrScenarioAdapter
        adapter = HookrScenarioAdapter.__new__(HookrScenarioAdapter)
        with self.assertRaises(Exception) as caught:
            adapter.variant_descriptor({'lpBps': 23, 'backend': api.PROFILE_OVERLAY_PROFILE}, {})
        self.assertIn('UNSUPPORTED_BACKEND', str(caught.exception))

    @unittest.skipUnless(os.environ.get('RHOOK_ACCEPTED_RECORDS'), 'accepted run inputs not supplied')
    def test_run_and_prepare_refuse_before_any_authority(self):
        """api.run (the CLI scenario-run path) and api.prepare on a real prepared input: refused at the operation
        binding, before a consent key is read or an authority issued."""
        api = self.api
        src = json.loads((Path(os.environ['RHOOK_ACCEPTED_RECORDS']) / 'lp23/inputs/SCENARIO.json').read_bytes())
        r = dict(schema='rhook/scenario-runtime/0.1', profile=api.PROFILE_OVERLAY_PROFILE, sourceCommitment='1' * 64, policySha256=api.POLICY_SHA,
                 files=dict(worker=dict(path='/nonexistent', sha256='2' * 64), node=dict(path='/nonexistent', sha256='5' * 64), sensor=dict(path='/nonexistent', sha256='6' * 64)))
        for items, code in [([tuning(8000, 1)], 'PROFILE_KIND_REVIEW_INSUFFICIENT'), ([DYN_OFF, lp(23)], 'PROFILE_ENGINE_NOT_ACCEPTED')]:
            items = pd.canonical_interventions(D, items)
            plan = api.configure(self.sdk, profile=api.PROFILE_OVERLAY_PROFILE, descriptor='hookr-1', interventions=items)
            capture, _ = _capture(self.sdk, plan, pd.build_spec(src, RAW, items, dict(sourceSha256='1' * 64, binarySha256='2' * 64, policySha256=api.POLICY_SHA)),
                                  'capture-' + code.lower())
            with unittest.mock.patch.object(api, 'runtime', return_value=r):
                for call in (lambda: api.prepare(self.sdk, capture), lambda: api.run(self.sdk, capture, local_owner=True, mac_ready=True)):
                    with self.assertRaises(pd.DescriptorError) as caught:
                        call()
                    self.assertEqual(caught.exception.code, code)
            self.assertFalse((self.sdk.home / 'scenarios/consents').exists())


def tearDownModule():
    out = os.environ.get('RHOOK_PROFILE_FIXTURE_OUT')
    if out and {'g1', 'descriptorNegatives', 'compositionNegatives', 'binding', 'probe', 'maskAndWidth', 'tuningGrid'} <= set(FIXTURES):
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / 'profile-fixtures.json').write_bytes(canonical(FIXTURES) + b'\n')


if __name__ == '__main__':
    unittest.main()
