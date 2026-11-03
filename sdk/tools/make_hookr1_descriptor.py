#!/usr/bin/env python3
"""Write the canonical hookr-1 profile descriptor and its catalogue entry from the accepted SDK 0.4 sources.

Inputs are the accepted profile.json and constants at f6134fd plus the vendor field layout (hookr-sdk 1.1.1,
MIT). The output is data only; tests check it against the legacy Go/Python code independently.
Usage: python3 -B tools/make_hookr1_descriptor.py [--check]
"""
import json
import sys
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SDK))
from developer.files import canonical, digest  # noqa: E402
from rhook_alpha import profile_descriptor as pd  # noqa: E402

NATIVE = SDK / 'rhook_alpha/cases/scenario/native'
OUT = NATIVE / 'descriptors'
ROOT_ON = '0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
SWAP_TOPIC = '0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f'
TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
SEED = 'RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST'
CHAIN_CONFIG_SHA256 = 'dfa6de28a2dcf9fa3079d97c73401af7c7df0bc7222a6a3fe1e927d98104ffe0'
SDK_SOURCE = 'hookr-sdk@1.1.1:STRUCT_COMPONENTS.RulesConfig'
# Revision 2 (independent semantic review BLOCK on revision 1): the largest maxFeePips the pool's Root caps admit.
TUNING_MAX_FEE_UNDER_ROOT_CAPS = 11500
# SHA-256 of the independent semantic review report of revision 2 (verdict PASS), kept in the private record.
REVIEW_R2_SHA256 = 'b391d728c6a22bc0ccdaa4e9e526ced0bdf3e7aabfb3241b20dda79ba9d4d637'


def field(name, target, word, offset, width, typ, unit, source):
    return dict(name=name, target=target, word=word, offset=offset, width=width, type=typ, unit=unit, semanticsSource=source)


def cmp(left, op, right):
    return {'compare': dict(left=left, op=op, right=right)}


def F(name):
    return {'field': name}


def C(value):
    return {'const': str(value)}


def P(name):
    return {'param': name}


def build():
    profile = json.loads((NATIVE / 'profile.json').read_bytes())
    manifest = profile['manifest']
    roles = {}
    for c in manifest['contracts']:
        roles.setdefault(c['role'], []).append(c)
    pin = lambda role, address: dict(name=role, address=address, releaseRole=role, requirement='CODE_HASH_EQUALS',
                                     runtimeCodeHash=next(c['runtimeHash'] for c in roles[role] if c['address'] == address))
    rules_address = '0x4a71c270b1520f94064268102aebd744b0de7942'
    contracts = [pin('poolManager', '0x8366a39cc670b4001a1121b8f6a443a643e40951'),
                 pin('root', profile['poolKey']['hooks']),
                 pin('router', '0xc2bc9a3fe6c4ce8c2f7eb4655b0869b01d8c93c9'),
                 pin('rules', rules_address),
                 dict(name='targetToken', address=profile['poolKey']['currency1'], requirement='CODE_PRESENT')]
    rules_fields = [('guardEndBlock', 0, 0, 40, 'uint', 'block'), ('maxFeePips', 0, 40, 24, 'uint', 'pips'),
                    ('snipeTaxPips', 0, 64, 24, 'uint', 'pips'), ('snipeFloorPips', 0, 88, 24, 'uint', 'pips'),
                    ('snipeDecaySeconds', 0, 112, 16, 'uint', 'seconds'), ('dynamicFeeSens', 0, 128, 16, 'uint', 'raw'),
                    ('burnBps', 0, 144, 16, 'uint', 'bps'), ('lpBps', 0, 160, 16, 'uint', 'bps'), ('potBps', 0, 176, 16, 'uint', 'bps'),
                    ('royaltyBps', 0, 192, 16, 'uint', 'bps'), ('protocolShareBps', 0, 208, 16, 'uint', 'bps'),
                    ('potEveryNBuys', 0, 224, 32, 'uint', 'count'), ('maxBuyQuoteAmount', 1, 0, 128, 'uint', 'baseunits'),
                    ('potMinBuyQuote', 1, 128, 128, 'uint', 'baseunits'), ('royaltyTo', 2, 0, 160, 'address', 'address'),
                    ('integrator', 3, 0, 160, 'address', 'address')]
    fields = [field(n, 'rulesConfig', w, o, wd, t, u, SDK_SOURCE) for n, w, o, wd, t, u in rules_fields]
    fields += [field('rootRulesAddress', 'rootRecord', 0, 0, 160, 'address', 'address', 'rhook:admission.go:STANDARD_POOL_BINDING@f6134fd'),
               field('rootBaseLpFeePips', 'rootRecord', 0, 160, 24, 'uint', 'pips', 'rhook:admission.go:FIRST_PROFILE_POOL_CAPS@f6134fd'),
               field('rootDynamicFeeFlag', 'rootRecord', 0, 248, 1, 'flag', 'flag', 'rhook:INTERVENTIONS.md@f6134fd'),
               field('rootRecaptureFlag', 'rootRecord', 0, 249, 1, 'flag', 'flag', 'rhook:INTERVENTIONS.md@f6134fd'),
               field('rootFlagsReserved', 'rootRecord', 0, 250, 6, 'uint', 'raw', 'rhook:dynamic.go:dynamicRootOn@f6134fd')]
    words = [dict(target='rulesConfig', word=i, value=w) for i, w in enumerate(profile['baselineConfigWords'])]
    words += [dict(target='rootRecord', word=0, value=ROOT_ON), dict(target='rootRecord', word=1, value=profile['rootCapsWord'])]
    kinds = [
        dict(kind='DYNAMIC_FEE',
             parameters=[dict(name='dynamicFee', type='enum', values=['OFF'])],
             requires=[cmp(F('maxFeePips'), 'gt', F('rootBaseLpFeePips')), cmp(F('dynamicFeeSens'), 'gt', C(0)),
                       cmp(F('rootDynamicFeeFlag'), 'eq', C(1)), cmp(F('rootRecaptureFlag'), 'eq', C(1)), cmp(F('rootFlagsReserved'), 'eq', C(0))],
             assign=[dict(field='maxFeePips', value=F('rootBaseLpFeePips')), dict(field='dynamicFeeSens', value=C(0)),
                     dict(field='rootDynamicFeeFlag', value=C(0))],
             ensures=[], conflictsWith=['DYNAMIC_FEE_TUNING']),
        dict(kind='DYNAMIC_FEE_TUNING',
             parameters=[dict(name='dynamicFeeSens', type='uint', min=1, max=10), dict(name='maxFeePips', type='uint', min=1, max=600000)],
             requires=[cmp(F('dynamicFeeSens'), 'ge', C(1)), cmp(F('maxFeePips'), 'gt', F('rootBaseLpFeePips')), cmp(F('rootDynamicFeeFlag'), 'eq', C(1))],
             assign=[dict(field='dynamicFeeSens', value=P('dynamicFeeSens')), dict(field='maxFeePips', value=P('maxFeePips'))],
             ensures=[cmp(F('maxFeePips'), 'gt', F('rootBaseLpFeePips')), cmp(F('maxFeePips'), 'le', C(600000)),
                      # Revision 2: the pool's Root caps (rulesFeeCeilings <= caps), see provenance.derivations.
                      cmp(F('maxFeePips'), 'le', C(TUNING_MAX_FEE_UNDER_ROOT_CAPS)),
                      cmp(F('dynamicFeeSens'), 'ge', C(1)), cmp(F('dynamicFeeSens'), 'le', C(10)), cmp(F('rootDynamicFeeFlag'), 'eq', C(1)),
                      {'productBound': dict(factors=[{'diff': ['maxFeePips', 'rootBaseLpFeePips']}, {'square': 'dynamicFeeSens'}],
                                            op='le', bound='7200000')},
                      {'productBound': dict(factors=[{'diff': ['maxFeePips', 'rootBaseLpFeePips']}, {'field': 'protocolShareBps'},
                                                     {'constMinusSquare': ['432', 'dynamicFeeSens']}], op='le', bound='99360000000')}],
             conflictsWith=['DYNAMIC_FEE']),
        dict(kind='LP_REWARDS_BPS',
             parameters=[dict(name='lpBps', type='uint', min=0, max=99)],
             requires=[cmp(F('lpBps'), 'eq', C(100))],
             assign=[dict(field='lpBps', value=P('lpBps'))],
             ensures=[], conflictsWith=[]),
    ]
    k = profile['poolKey']
    d = dict(
        schema=pd.SCHEMA, profileId='hookr-1', revision=2,
        chain=dict(chainId=4663, engineFamily='NITRO', arbosVersion=61, chainConfigSha256=CHAIN_CONFIG_SHA256),
        release=dict(manifest=manifest, manifestCommitment=pd.commit(pd.RELEASE_DOMAIN, manifest)),
        contracts=contracts,
        pool=dict(currency0=k['currency0'], currency1=k['currency1'], fee=k['fee'], tickSpacing=k['tickSpacing'],
                  hooksContract='root', poolId=profile['poolId']),
        targets=[dict(name='rulesConfig', contract='rules', slot=profile['configSlot'], words=4,
                      slotDerivation=dict(kind='ERC7201_MAPPING_POOL_ID', namespace='hookr.rules', fieldOffset=1)),
                 dict(name='rootRecord', contract='root', slot=profile['rootRecordSlot'], words=2,
                      slotDerivation=dict(kind='ERC7201_MAPPING_POOL_ID', namespace='hookr.root', fieldOffset=0))],
        configurationTarget='rulesConfig',
        fields=fields,
        originalState=dict(policy='EXACT_WORDS', words=words),
        interventions=kinds,
        action=dict(type='HOOKR_ROUTER_EXACT_INPUT_BUY_V1', router='router', function='swap', abi=profile['swapAbi'],
                    amountInWei='1000000000000000', gas=[5000000, 10000000], minimumOutputBaseUnits='1', sqrtPriceLimitX96='4295128740',
                    zeroForOne=True, engagement='0x' + '0' * 40, campaigns=[], transactionType='LEGACY', count=1),
        setup=dict(actor=dict(kind='PUBLIC_SIMULATION_SIGNER_V1', seed=SEED), fundingWei='1000000000000000000', nonce=0,
                   requireOriginalAbsence=True),
        measures=[dict(name='gasUsed', source='SUBJECT_RECEIPT_GAS_USED'),
                  dict(name='receiptStatus', source='SUBJECT_RECEIPT_STATUS'),
                  dict(name='outerSwapFeePips', source='EVENT_DATA_WORD', emitter='poolManager', topic0=SWAP_TOPIC, topic1='POOL_ID', word=5),
                  dict(name='actorTargetTokenTransferNetBaseUnits', source='ERC20_TRANSFER_NET', emitter='targetToken', topic0=TRANSFER_TOPIC,
                       party='ACTOR'),
                  dict(name='actorBalanceAfterWei', source='WORLD_ACTOR_BALANCE_AFTER')],
        witness=dict(readHints=[dict(path=p, sha256=digest((SDK / p).read_bytes())) for p in
                                ('rhook_alpha/cases/scenario/prefetch.json', 'rhook_alpha/cases/scenario/trace-hints.json')],
                     systemSubjects='NITRO_ARBOS61_SCENARIO_SYSTEM_V1', targetWords='ALL_DECLARED_TARGET_WORDS'),
        provenance=dict(
            sources=[dict(name='legacy-profile', kind='RHOOK_ACCEPTED_SOURCE', ref='sdk/rhook_alpha/cases/scenario/native/profile.json@f6134fd',
                          sha256=digest((NATIVE / 'profile.json').read_bytes())),
                     dict(name='hookr-sdk-generated', kind='VENDOR_SDK_MIT', ref='hookr-sdk@1.1.1/dist/core/generated.js',
                          sha256='3847b4f2c0085c2355b223db12468e14998ad2d4ac098fc1069daa1f5cbbc48f'),
                     dict(name='hookr-sdk-rules', kind='VENDOR_SDK_MIT', ref='hookr-sdk@1.1.1/dist/core/rules.js',
                          sha256='2d16671be130f9a58cd378357a9d14dcd5c2575384cf15c4869c1ca69518ae1f'),
                     dict(name='hookr-sdk-params', kind='VENDOR_SDK_MIT', ref='hookr-sdk@1.1.1/dist/core/params.js',
                          sha256='b614e5e950ecb4fa4645dfd8bd0e5c2092fec9a832b3430c57778e611b703ddb'),
                     dict(name='hookr-sdk-provenance', kind='VENDOR_SDK_MIT',
                          ref='hookr-sdk@1.1.1/provenance.json source commit 412960b37a631ce145d49fb4a1887f04a4d1fa74',
                          sha256='cfcae57bdd141dabdc7334da18590ac750684c2d9862f36fef6a53e27b868c06'),
                     dict(name='root-flag-semantics', kind='RHOOK_ACCEPTED_DOC', ref='sdk/INTERVENTIONS.md@f6134fd',
                          sha256='c0ba5fcd55ecfdf045ebb07f540df97ef18cf72e6254a9443b54b4bd618ab3bc')],
            derivations=[dict(subject='pool.poolId', method='keccak256(abi.encode(PoolKey))', result=profile['poolId']),
                         dict(subject='targets.rulesConfig.slot', method="keccak256(poolId . erc7201('hookr.rules')) + 1", result=profile['configSlot']),
                         dict(subject='targets.rootRecord.slot', method="keccak256(poolId . erc7201('hookr.root')) + 0", result=profile['rootRecordSlot']),
                         dict(subject='fields.rulesConfig', method='Solidity storage packing of STRUCT_COMPONENTS.RulesConfig in declaration order',
                              result='word0 guardEndBlock..potEveryNBuys (256 bits); word1 maxBuyQuoteAmount, potMinBuyQuote; word2 royaltyTo; word3 integrator'),
                         dict(subject='fields.rootRecord flags', method='INTERVENTIONS.md: Root mode 3 includes Dynamic Fee and recapture; mode 2 retains recapture',
                              result='bit 248 Dynamic Fee, bit 249 recapture; bits 250-255 zero in the reviewed original'),
                         dict(subject='interventions.DYNAMIC_FEE_TUNING.ensures', method='hookr-sdk checkRulesConfig and withinDynamicFeeReach (r31 bind rules)',
                              result='maxFeePips > base; sensitivity 1..10; maxFeePips <= 600000; span*sens^2 <= 7200000; span*share*(432-sens^2) <= 99360000000'),
                         dict(subject='interventions.DYNAMIC_FEE_TUNING.ensures (revision 2)',
                              method='hookr-sdk checkRulesConfig requires rulesFeeCeilings <= Root caps. Root caps are Root word 1 of the reviewed originals '
                                     '(maxLpFeePips 17800, maxQuoteTakePips 3700, maxSubjectTakeBps 0). With base 3000, protocolShareBps 2000, snipe, royalty and burn 0 '
                                     '(EXACT_WORDS) and lpBps <= 100: LP ceiling = 3000 + 80*lpBps + span - floor(span/5) <= 17800 holds for every lpBps exactly when span <= 8500',
                              result='maxFeePips <= 11500: exact at lpBps 100, conservative below. Checked exhaustively against hookr-sdk 1.1.1 on maxFeePips 2990..12010 x '
                                     'sensitivity 0..11 x lpBps 0..100: no point the descriptor accepts and the vendor refuses')],
            contractSources='hookr-sdk provenance.json states the contract sources are verified on RobinScan; they were not retrieved for this descriptor.'),
    )
    raw = canonical(d) + b'\n'
    pd.parse(raw)
    catalogue = dict(schema=pd.CATALOGUE_SCHEMA, entries=[dict(
        profileId='hookr-1', revision=2, descriptorFile='hookr-1.json', descriptorSha256=digest(raw),
        # Controlled catalogue revision after the independent semantic review of revision 2 returned PASS (report
        # SHA-256 below). Descriptor-level NATIVE_EXECUTION admits only native *candidacy*: per kind, LP Rewards and
        # Dynamic Fee OFF are legacy-equivalent candidates and Tuning stays offline-only. This text was fixed before
        # G4B and is embedded in the worker; the reviewed engine identity is recorded later in the SDK only
        # (profile_descriptor.PROFILE_ENGINE_RECORD), and a native run also needs a per-operation owner authorization.
        review=dict(status='RHOOK_REVIEWED_NATIVE_CANDIDATE', admits=['OFFLINE_PREPARATION', 'NATIVE_EXECUTION'], author='kiro',
                    independentReview='PASS_SEMANTIC_REVIEW_R2 sha256:' + REVIEW_R2_SHA256,
                    nativeExecution='NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED'),
        kinds=dict(DYNAMIC_FEE='LEGACY_EQUIVALENT_SDK04', DYNAMIC_FEE_TUNING='OFFLINE_PROBE_BIND_RULES_ONLY', LP_REWARDS_BPS='LEGACY_EQUIVALENT_SDK04'))])
    return raw, canonical(catalogue) + b'\n'


def main(argv):
    raw, cat = build()
    if '--check' in argv:
        same = (OUT / 'hookr-1.json').read_bytes() == raw and (OUT / 'CATALOGUE.json').read_bytes() == cat
        print('DESCRIPTOR_CURRENT' if same else 'DESCRIPTOR_STALE')
        return 0 if same else 1
    OUT.mkdir(exist_ok=True)
    (OUT / 'hookr-1.json').write_bytes(raw)
    (OUT / 'CATALOGUE.json').write_bytes(cat)
    print(json.dumps(dict(descriptorSha256=digest(raw), bytes=len(raw), catalogueSha256=digest(cat))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
