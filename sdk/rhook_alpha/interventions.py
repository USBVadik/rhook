"""Explicit checkpoint interventions. Plans/projection fixtures are not EVM runs.

Serialized commitments authenticate bytes, not their provenance. Replanning from
pinned witness is required before trusting a saved plan. Native execution always
uses the existing consent/admission path; Dynamic Fee off is deliberately blocked.
"""
import copy
from pathlib import Path
import re
import shutil
import subprocess
from developer.files import digest, strict
from .execution import ExecutionError, check, commit, _input, _profile, _validate_spec

DOMAIN = 'rhook/checkpoint-intervention/0.1'
LP = 'hookr.lp-rewards/0.1'
DYNAMIC_OFF = 'hookr.dynamic-fee-off/0.1'
AUTHENTICATOR = Path(__file__).with_name('intervention-state.mjs')
MASK_LP = 65535 << 160
MASK_DYNAMIC = (0xffffff << 40) | (65535 << 128)
MASK_MODE = 1 << 248


def _word(value):
    check(type(value) is str and re.fullmatch('0x[0-9a-f]{64}', value),
          'INTERVENTION_TARGET_STATE', 'Supply complete lowercase32-byte storage words.')
    return int(value, 16)


def _hex(value):
    return '0x' + format(value, '064x')


def _pin(value):
    check(type(value) is str and re.fullmatch('[0-9a-f]{64}', value),
          'INTERVENTION_HASH', 'Supply a lowercase SHA-256 commitment.')
    return value


def _writes(projection, kind, lp_bps):
    p = _profile()
    contracts = {role: next(c for c in p['manifest']['contracts'] if c['role'] == role) for role in ('root', 'rules')}
    try:
        check(set(projection) == {'schema','checkpoint','accounts'} and
              projection['schema'] == 'rhook/intervention-target-state/0.1' and
              set(projection['accounts']) == {'root','rules'},
              'INTERVENTION_TARGET_STATE', 'Authenticate the exact Root and Rules target projection.')
        for role in ('root','rules'):
            account = projection['accounts'][role]
            check(set(account) == {'address','codeHash','storage'} and
                  account['address'] == contracts[role]['address'] and
                  account['codeHash'] == contracts[role]['runtimeHash'],
                  'INTERVENTION_TARGET_STATE', 'Use the pinned Hookr generation and code identities.', {'role':role})
        root, rules = projection['accounts']['root'], projection['accounts']['rules']
        expected = {_hex(int(p['configSlot'],16)+i): w for i,w in enumerate(p['baselineConfigWords'])}
        check(rules['storage'] == expected and set(root['storage']) == {p['rootRecordSlot']},
              'INTERVENTION_TARGET_STATE', 'The original LP100 profile words and complete Root record are required.')
        old = _word(rules['storage'][p['configSlot']]); root_old = _word(root['storage'][p['rootRecordSlot']])
        check((root_old & ((1<<160)-1)) == int(contracts['rules']['address'],16) and
              ((root_old >> 160) & 0xffffff) == p['baseLpFeePips'] and
              ((root_old >> 232) & 255) == 1 and root_old >> 248 == 3,
              'INTERVENTION_TARGET_STATE', 'Require initialized dynamic-fee+recapture mode3, the pinned Rules and base fee.')
        def write(role, slot, before, after, mask):
            return dict(address=contracts[role]['address'],slot=slot,before=_hex(before),after=_hex(after),mask=_hex(mask))
        if kind == LP:
            check(type(lp_bps) is int and 0 <= lp_bps <= 99, 'INTERVENTION_LP_RANGE', 'Use LP0..99 from the original LP100.')
            return [write('rules',p['configSlot'],old,(old & ~MASK_LP) | (lp_bps << 160),MASK_LP)]
        check(kind == DYNAMIC_OFF and lp_bps is None, 'UNSUPPORTED_INTERVENTION',
              'Choose explicit LP modification or Dynamic Fee off; combinations/arbitrary blocks are unsupported.')
        check(((old>>40)&0xffffff) > p['baseLpFeePips'] and ((old>>128)&65535) > 0,
              'HOOK_BLOCK_NOT_ACTIVE', 'Dynamic Fee must be active in the original authenticated configuration.')
        return [write('rules',p['configSlot'],old,(old & ~MASK_DYNAMIC) | (p['baseLpFeePips']<<40),MASK_DYNAMIC),
                write('root',p['rootRecordSlot'],root_old,root_old & ~MASK_MODE,MASK_MODE)]
    except (KeyError,TypeError,ValueError) as error:
        if isinstance(error,ExecutionError): raise
        raise ExecutionError('INTERVENTION_TARGET_STATE','Supply authenticated complete target fields.') from error


def describe(spec, projection, *, kind, source_sha256, lp_bps=None):
    """Build a typed plan from a projection. Does NOT authenticate that projection.

    Use plan() for MPT authentication. This lower-level constructor also supports
    synthetic offline fixtures; it grants no execution capability.
    """
    _validate_spec(spec,_profile())
    check(type(projection) is dict, 'INTERVENTION_TARGET_STATE', 'Supply a complete target projection.')
    check(projection.get('checkpoint') == spec['checkpoint'], 'INTERVENTION_CHECKPOINT',
          'Use target proofs from the identical original checkpoint root.')
    writes = _writes(projection,kind,lp_bps)
    body = dict(schema=DOMAIN,status='INTERVENTION_PLAN_ONLY',kind=kind,lpBps=lp_bps,
                profile='hookr-buy/0.1',poolId=spec['poolId'],checkpoint=copy.deepcopy(spec['checkpoint']),
                sourceInputSha256=_pin(source_sha256),originalScenarioCommitment=spec['scenarioCommitment'],
                engine=copy.deepcopy(spec['engine']),originalProjection=copy.deepcopy(projection),
                fixedInputs={k:copy.deepcopy(spec[k]) for k in ('actions','commonSetup','environment','parent','chainConfig')},
                writes=writes,witnessClosureEstablished=False,
                nativeCompatibility='USE_EXISTING_LP_EXECUTION_API' if kind==LP else 'BLOCKED_LP_ONLY_NATIVE_CONTRACT',
                semantics='hypothetical-checkpoint-state; preserve original policy opening, accrued state, code and all non-target bits',
                resultBindingDomain='rhook/intervention-result-references/0.1')
    body['interventionCommitment']=commit(DOMAIN,body)
    return body


def _validate_descriptor(plan_value):
    """Validate serialization/transform semantics only; never a proof or run grant."""
    p=copy.deepcopy(plan_value)
    check(type(p) is dict, 'INTERVENTION_DESCRIPTOR', 'Supply a complete intervention descriptor.')
    pin=p.pop('interventionCommitment',None)
    check(pin == commit(DOMAIN,p), 'INTERVENTION_COMMITMENT', 'Restore the original descriptor; do not rehash edits.')
    keys={'schema','status','kind','lpBps','profile','poolId','checkpoint','sourceInputSha256','originalScenarioCommitment','engine','originalProjection','fixedInputs','writes','witnessClosureEstablished','nativeCompatibility','semantics','resultBindingDomain'}
    check(set(p)==keys and p['schema']==DOMAIN and p['status']=='INTERVENTION_PLAN_ONLY' and
          p['profile']=='hookr-buy/0.1' and p['poolId']==_profile()['poolId'] and
          type(p['originalProjection']) is dict and p['checkpoint']==p['originalProjection']['checkpoint'] and p['witnessClosureEstablished'] is False,
          'INTERVENTION_DESCRIPTOR','Use the supported original-root plan-only descriptor.')
    _pin(p['sourceInputSha256']);_pin(p['originalScenarioCommitment'])
    check(p['writes']==_writes(p['originalProjection'],p['kind'],p['lpBps']),
          'INTERVENTION_WRITES','Only the exact declared fields may change; no extra writes or masks.')
    expected='USE_EXISTING_LP_EXECUTION_API' if p['kind']==LP else 'BLOCKED_LP_ONLY_NATIVE_CONTRACT'
    check(p['nativeCompatibility']==expected and p['resultBindingDomain']=='rhook/intervention-result-references/0.1',
          'INTERVENTION_CAPABILITY','A saved descriptor cannot grant new runtime capabilities.')
    return copy.deepcopy(plan_value)


def validate(plan_value):
    """Strict plan semantics, with stable errors even for malformed JSON shapes."""
    try:
        return _validate_descriptor(plan_value)
    except ExecutionError:
        raise
    except (KeyError,TypeError,ValueError,AttributeError,RecursionError) as error:
        raise ExecutionError('INTERVENTION_DESCRIPTOR','Restore a complete supported descriptor; this is not authentication.') from error


def plan(prepared_input, *, expected_sha256, kind, lp_bps=None, node=None):
    """Read-only original-target MPT authentication + descriptor; no EVM/authority."""
    raw,spec=_input(prepared_input,_pin(expected_sha256));_validate_spec(spec,_profile())
    program=node or shutil.which('node')
    check(program is not None, 'INTERVENTION_AUTHENTICATOR_UNAVAILABLE', 'Install the pinned Node runtime and SDK proof dependencies.')
    try:
        r=subprocess.run([str(program),str(AUTHENTICATOR)],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
        check(len(r.stdout)<=1<<20 and len(r.stderr)<=1<<20,'INTERVENTION_AUTHENTICATOR_OUTPUT','Restore the reviewed offline authenticator.')
        if r.returncode:
            try: failure=strict(r.stdout)
            except (ValueError,UnicodeError): failure={}
            raise ExecutionError(failure.get('causeCode','INTERVENTION_AUTHENTICATOR_UNAVAILABLE'),
                                 'Supply the missing original-root dependency or install the pinned proof runtime; do not hydrate automatically.',failure.get('details',{}))
        projection=strict(r.stdout)
    except (OSError,subprocess.TimeoutExpired) as error:
        raise ExecutionError('INTERVENTION_AUTHENTICATOR_UNAVAILABLE','Use the complete pinned Node/proof runtime; no native worker is needed.') from error
    d=describe(spec,projection,kind=kind,source_sha256=digest(raw),lp_bps=lp_bps)
    return dict(status='TARGET_FIELDS_MPT_AUTHENTICATED_PLAN_ONLY',descriptor=d,
                authenticationScope='Original Root/Rules account paths, runtime code preimages and five target storage leaves only. Checkpoint trust is supplied, not consensus-verified.',
                witnessClosure='UNKNOWN_FOR_NEW_INTERVENTION',nativeExecutions=0)


def fixture_worlds(descriptor, state):
    """Two independent Python projections, not StateDB/trie roots or EVM worlds."""
    d=validate(descriptor)
    check(state.get('checkpoint')==d['checkpoint'] and state.get('fixedInputs')==d['fixedInputs'],
          'INTERVENTION_FIXED_INPUTS','Keep checkpoint, signed transaction and environment identical.')
    try:
        for role,account in d['originalProjection']['accounts'].items():
            actual=state['accounts'][role]
            check(actual['address']==account['address'] and actual['codeHash']==account['codeHash'] and
                  all(actual['storage'][key]==v for key,v in account['storage'].items()),
                  'INTERVENTION_ORIGINAL_STATE','Restore all original target fields before applying an overlay.')
    except (KeyError,TypeError) as error:
        raise ExecutionError('INTERVENTION_ORIGINAL_STATE','Supply the complete original target projection.') from error
    baseline,variant=copy.deepcopy(state),copy.deepcopy(state)
    roles={v['address']:k for k,v in d['originalProjection']['accounts'].items()}
    for w in d['writes']:variant['accounts'][roles[w['address']]]['storage'][w['slot']]=w['after']
    return dict(status='FIXTURE_PROJECTION_ONLY_NOT_EVM',baseline=baseline,variant=variant)


def execution_configuration(descriptor, sdk):
    d=validate(descriptor)
    check(d['kind']==LP,'UNSUPPORTED_NATIVE_INTERVENTION',
          'A separate versioned admission, two-write overlay and evidence verifier are required; the accepted worker is LP-only.',
          {'writes':d['writes'],'missingClosure':'Mutation paths and all newly reached reads must be authenticated; current coverage is unproven.'})
    return sdk.configure(lp_bps=d['lpBps'],checkpoint=d['checkpoint'])


def bind_result_hashes(descriptor, baseline_sha256, variant_sha256):
    """Commit references; this neither executes nor verifies supplied result files."""
    d=validate(descriptor)
    body=dict(schema=d['resultBindingDomain'],status='UNVERIFIED_RESULT_REFERENCES',
              interventionCommitment=d['interventionCommitment'],baselineSha256=_pin(baseline_sha256),variantSha256=_pin(variant_sha256))
    return dict(body,evidenceCommitment=commit(body['schema'],body))
