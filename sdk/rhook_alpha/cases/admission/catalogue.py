"""Closed trusted catalogue around existing typed executors; no runtime calls."""
import copy
from pathlib import Path
from developer.files import canonical, digest, load, require
from ..capsule import PROFILE as LP_PROFILE, SCHEMA as CAPSULE_SCHEMA, seal
from ..historical import PROFILE as OFF_PROFILE
from . import CLASS, SCHEMA, LP, OFF

ENTRIES = {
    LP: dict(executorProfile=LP_PROFILE, rule='lpBps', values=dict(type='INTEGER', minimum=0, maximum=99)),
    OFF: dict(executorProfile=OFF_PROFILE, rule='dynamicFee', values=dict(type='ENUM', values=['OFF'])),
}
LP_MASK = 65535 << 160
DYNAMIC_MASK = (0xffffff << 40) | (65535 << 128)
MODE_MASK = 1 << 248


def entries():
    return dict(schema='rhook/historical-intervention-catalogue/0.1', semanticClass=CLASS,
                qualification='PROPOSED_EXTENSION_NOT_QUALIFIED',
                entries=[dict(adapter=key, **copy.deepcopy(value)) for key, value in ENTRIES.items()],
                arbitraryStorageWrites=False, qualifiedClaims=0)


def resolve_plan(capsule, value):
    """Structural resolution only. Registry validates package bytes separately."""
    from ..adapters import get_adapter
    require(type(capsule) is dict and capsule.get('schema') == CAPSULE_SCHEMA
            and capsule.get('capsuleId') == seal(capsule)['capsuleId'], 'CATALOGUE_CAPSULE_IDENTITY')
    adapter = capsule['adapter']['id']
    require(type(adapter) is str and adapter in ENTRIES, 'UNSUPPORTED_ADAPTER: ' + str(adapter))
    require(capsule['execution']['profile'] == ENTRIES[adapter]['executorProfile'], 'TYPED_EXECUTOR_PROFILE_MISMATCH')
    arrivals = capsule['arrivals']
    require(type(arrivals) is list and arrivals and len(arrivals) == len(set(arrivals)), 'AMBIGUOUS_HISTORICAL_ARRIVALS')
    plan = get_adapter(capsule).plan(capsule, value)
    # Existing typed adapters own value validation and its stable diagnostics.
    require(type(value) is dict and set(value) == {'rule', 'value'}
            and value['rule'] == ENTRIES[adapter]['rule'], 'TYPED_INTERVENTION_FIELDS')
    ordinal = plan['observation']['nativeOrdinal']
    require(type(ordinal) is int and 0 < ordinal < len(arrivals)
            and arrivals.count(plan['subject']) == 1 and arrivals[ordinal] == plan['subject'], 'AMBIGUOUS_HISTORICAL_SUBJECT')
    return copy.deepcopy(plan)


def describe(capsule, value):
    plan = resolve_plan(capsule, value)
    adapter = capsule['adapter']['id']
    transform = plan['intervention']
    if adapter == LP:
        writes = [dict(address=transform['account'], slot=transform['slot'],
                       before=transform['expectedOldWord'], after=transform['newWord'],
                       mask=f'0x{LP_MASK:064x}')]
        contracts = [dict(address=transform['account'], runtimeCodeHash=plan['rulesRuntimeHash'])]
    else:
        writes = [dict(write, mask=f'0x{mask:064x}') for write, mask in zip(transform['writes'], [DYNAMIC_MASK, MODE_MASK])]
        contracts = [dict(address=write['address'], runtimeCodeHash=code)
                     for write, code in zip(writes, [transform['rulesCodeHash'], transform['rootCodeHash']])]
    keys = [(w['address'], w['slot']) for w in writes]
    require(len(keys) == len(set(keys)), 'AMBIGUOUS_STORAGE_TARGET')
    for w in writes:
        require((int(w['before'], 16) ^ int(w['after'], 16)) & ~int(w['mask'], 16) == 0, 'UNAUTHORIZED_INITIAL_BITS')
    body = dict(schema=SCHEMA, semanticClass=CLASS, qualification='PROPOSED_EXTENSION_NOT_QUALIFIED',
        resolution='DESCRIPTOR_RESOLVED_AUTHENTICATION_PENDING',
        meaning=dict(adapter=adapter, selection=copy.deepcopy(value), anchor=plan['checkpoint'],
            historicalTarget=copy.deepcopy(capsule['target']),
            boundary='AUTHENTICATED_PARENT_BEFORE_FIRST_ARRIVAL', applicationCount=1,
            storageWriteCount=len(writes), targetPool=transform['pool'], contracts=contracts, writes=writes,
            initialRoots=dict(anchor=plan['checkpoint']['stateRoot'], actual=plan['checkpoint']['stateRoot'],
                              branch='COMMIT_OF_ADMITTED_TRANSFORM_NOT_ASSERTED_BY_THIS_DESCRIPTOR'),
            preservedInitialState='ALL_STATE_OUTSIDE_EXACT_ALLOWLIST_INCLUDING_CODE_BALANCES_NONCES',
            continuation=dict(arrivals=plan['arrivals'], signedBytes='UNCHANGED',
                environment='ORIGINAL_DECLARED_HISTORICAL_CONTEXT', systemEffects='REGENERATE_PER_WORLD'),
            evolution='INDEPENDENT_OWN_PREDECESSOR_COMMON_REFERENCE_SEMANTICS_NO_CANONICAL_RESETS',
            subject=dict(transactionHash=plan['subject'], ordinal=plan['observation']['nativeOrdinal'],
                         sender=plan['sender'], router=plan['router']),
            projection=dict(subjectReceipt='AFTER_SUBJECT_EXECUTION', stateObservations=plan['observation'],
                stateBoundary='BEFORE_FIRST_ARRIVAL_AND_AFTER_BLOCK_FINALIZATION_BEFORE_COMMIT',
                quantities=['SIGNED_ERC20_TRANSFER_EVENT_NET_BASE_UNITS', 'OUTER_SWAP_FEE_PIPS', 'SUBJECT_GAS'],
                arithmetic='EXACT_INTEGER_BRANCH_MINUS_ACTUAL', tokenNetIsNotProfit=True)),
        artifactBindings=dict(capsuleId=capsule['capsuleId'], executorProfile=ENTRIES[adapter]['executorProfile'],
            legacyRuntimePlanSha256=digest(canonical(plan)), packageSha256=plan['packageSha256'],
            inputCommitment=plan['inputCommitment'], witnessCommitment=plan['witnessCommitment']),
        definitionPins=load(Path(__file__).with_name('definitions.json')),
        identityKind='CATALOGUE_ARTIFACT_NOT_BRANCH_PROTOCOL_QUERY',
        originalStateAuthenticated=False, witnessClosure='NOT_EVALUATED',
        lawfulEstablished=False, qualifiedClaims=0, executionAuthorized=False)
    body['admissionArtifactCommitment'] = digest(SCHEMA.encode() + b'\n' + canonical(body))
    return body
