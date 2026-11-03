"""Parameterized Config Overlay Engine 0.1 (SDK 0.4): one profile for typed Hookr config interventions.

Python mirror of the worker's native/overlay.go. A fixed registry of typed interventions (LP Rewards
lpBps 100 -> 0..99, Dynamic Fee ON -> OFF) is composed into masked writes on the authenticated original
Rules config word and Root record. Arbitrary storage writes are not representable: targets, fields,
masks, ranges and original-state preconditions are part of this source and of the reviewed worker.

Preparation is offline. It authenticates the original Root/Rules target leaves against the checkpoint
root (read-only MPT proofs), derives the writes and binds the reviewed worker identity. It never runs
the worker, never computes results and grants no execution authority.
"""
import copy
from developer.files import canonical, digest, load, no_links, save, sha, sync
from .execution import ExecutionSDK, ExecutionError, check, commit, _input, _profile, _validate_spec, DOMAIN as LP_DOMAIN

DOMAIN = 'rhook/hookr-config-overlay/0.1'
PROFILE = 'nitro-hookr-config-overlay/0.1'
KIND = 'AUTHENTICATED_CHECKPOINT_CONFIG_OVERLAY'
PLAN_DOMAIN = DOMAIN + '/plan'
LP_REWARDS = 'LP_REWARDS_BPS'
DYNAMIC_FEE = 'DYNAMIC_FEE'
ROOT_ON = '0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
ROOT_OFF = '0x020101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'
# Engine identity of the reviewed config-overlay worker. Set only after its build and offline acceptance;
# preparation can bind it before registration, authentication and runs still require exactly this runtime.
ACCEPTED_OVERLAY_ENGINE = dict(sourceSha256='6ab16554be64da4e0f0b38c6d633d530a3a195d37ff5c151c3c819639961a1cf',
                               binarySha256='84e5c55180f220cb04ea63e3c44c09e6aa3e00431eb95a702899bbdb543ad22b',
                               policySha256='792b13a533f79d8d66ade565a5ad41cdb45bd1da4684e06dcdc1825c1a04abc6')

RULES, ROOT = 0, 1
# name: (target, shift, width), the field layout of the pinned Hookr generation.
FIELDS = dict(maxFeePips=(RULES, 40, 24), sensitivity=(RULES, 128, 16), lpBps=(RULES, 160, 16), rootMode=(ROOT, 248, 8))


def _mask(name):
    _, shift, width = FIELDS[name]
    return ((1 << width) - 1) << shift


def field(word, name):
    _, shift, width = FIELDS[name]
    return (word >> shift) & ((1 << width) - 1)


def fields(rules, root):
    """Decoded target fields of one Rules config word and one Root record (ints or 0x-hex)."""
    r = int(rules, 16) if type(rules) is str else rules
    o = int(root, 16) if type(root) is str else root
    return dict(lpBps=field(r, 'lpBps'), maxFeePips=field(r, 'maxFeePips'), sensitivity=field(r, 'sensitivity'), rootMode=field(o, 'rootMode'))


def _hex(value):
    return '0x' + format(value, '064x')


def _lp_rule(item, profile):
    v = item.get('lpBps')
    check(set(item) == {'kind', 'lpBps'} and type(v) is int and 0 <= v <= 99, 'CONFIG_OVERLAY_LP_PARAMETER',
          'LP_REWARDS_BPS takes exactly one integer lpBps 0-99; the original is LP100.')
    return [('lpBps', lambda x: x == 100, v)]


def _dynamic_rule(item, profile):
    check(set(item) == {'kind', 'dynamicFee'} and item.get('dynamicFee') == 'OFF', 'CONFIG_OVERLAY_DYNAMIC_FEE_PARAMETER',
          'DYNAMIC_FEE takes exactly dynamicFee OFF; ON is the recorded original.')
    base = profile['baseLpFeePips']
    return [('maxFeePips', lambda x: x > base, base), ('sensitivity', lambda x: x > 0, 0), ('rootMode', lambda x: x == 3, 2)]


REGISTRY = {LP_REWARDS: _lp_rule, DYNAMIC_FEE: _dynamic_rule}


def canonical_interventions(items):
    """Validate the typed shape and return the set sorted by kind. Any input order gives the same set."""
    check(type(items) in (list, tuple) and 1 <= len(items) <= len(REGISTRY), 'CONFIG_OVERLAY_INTERVENTION_COUNT',
          'Supply one or two typed interventions: LP_REWARDS_BPS and/or DYNAMIC_FEE.')
    for item in items:
        check(type(item) is dict and type(item.get('kind')) is str, 'CONFIG_OVERLAY_DESCRIPTOR', 'Each intervention is an object with a kind.')
        check(item['kind'] in REGISTRY, 'CONFIG_OVERLAY_UNKNOWN_INTERVENTION', 'Only LP_REWARDS_BPS and DYNAMIC_FEE are supported; arbitrary storage writes are not.',
              {'kind': item['kind'][:60]})
    kinds = [i['kind'] for i in items]
    check(len(set(kinds)) == len(kinds), 'CONFIG_OVERLAY_DUPLICATE_KIND', 'Each intervention kind may appear once; conflicting descriptors are refused.')
    return [copy.deepcopy(i) for i in sorted(items, key=lambda i: i['kind'])]


def compose(items, rules0, root0, profile, registry=REGISTRY):
    """Apply typed interventions to the original words; same checks as the worker's composeOverlay."""
    if registry is REGISTRY:
        canonical_interventions(items)
    check(type(items) in (list, tuple) and 1 <= len(items) <= len(registry), 'CONFIG_OVERLAY_INTERVENTION_COUNT', 'Supply one or two typed interventions.')
    check(len({i['kind'] for i in items}) == len(items), 'CONFIG_OVERLAY_DUPLICATE_KIND', 'Each intervention kind may appear once.')
    original = [int(rules0, 16), int(root0, 16)]
    words, used, applied = list(original), [0, 0], []
    for item in items:
        rule = registry.get(item['kind'])
        check(rule is not None, 'CONFIG_OVERLAY_UNKNOWN_INTERVENTION', 'Unknown intervention kind.')
        for name, precondition, value in rule(item, profile):
            target, shift, width = FIELDS[name]
            mask = _mask(name)
            check(used[target] & mask == 0, 'CONFIG_OVERLAY_MASK_CONFLICT', 'Two interventions write the same bits.', {'field': name})
            used[target] |= mask
            check(precondition(field(original[target], name)), 'CONFIG_OVERLAY_ORIGINAL_PRECONDITION',
                  'The authenticated original does not have the setting this intervention replaces.', {'field': name})
            check(0 <= value < (1 << width), 'CONFIG_OVERLAY_VALUE_WIDTH', 'Value does not fit its field.', {'field': name})
            words[target] = (words[target] & ~mask) | (value << shift)
            applied.append((name, target, value))
    for i in (RULES, ROOT):
        check((words[i] ^ original[i]) & ~used[i] == 0, 'CONFIG_OVERLAY_NON_TARGET_BITS', 'A non-target bit changed.')
    for name, target, value in applied:
        check(field(words[target], name) == value, 'CONFIG_OVERLAY_FIELD_VALUE', 'Composed field value mismatch.', {'field': name})
    p = profile
    contracts = _contracts(p)
    writes = []
    for target, (address, slot) in ((RULES, (contracts['rules']['address'], p['configSlot'])), (ROOT, (contracts['root']['address'], p['rootRecordSlot']))):
        if used[target]:
            check(words[target] != original[target], 'CONFIG_OVERLAY_NO_EFFECT', 'An intervention must change its target.')
            writes.append(dict(address=address, slot=slot, before=_hex(original[target]), after=_hex(words[target])))
    return dict(rules=_hex(words[RULES]), root=_hex(words[ROOT]), writes=writes, fields=fields(words[RULES], words[ROOT]))


def intent(pool, items):
    lp, dynamic = 100, 'ON'
    for i in items:
        if i['kind'] == LP_REWARDS:
            lp = i['lpBps']
        if i['kind'] == DYNAMIC_FEE:
            dynamic = i['dynamicFee']
    return dict(schema=DOMAIN + '/intent', poolId=pool, lpBps=lp, dynamicFee=dynamic, interventions=copy.deepcopy(list(items)))


def capsule(spec):
    return commit(DOMAIN + '/checkpoint', dict(checkpoint=spec['checkpoint'], intent=intent(spec['poolId'], spec['configOverlay']['interventions'])))


def _contracts(p):
    return {r: next(c for c in p['manifest']['contracts'] if c['role'] == r) for r in ('root', 'rules')}


def original_words(projection):
    """The authenticated original Rules word and Root record from a target projection; same checks as
    interventions._writes, independent of the intervention kind."""
    p = _profile()
    contracts = _contracts(p)
    try:
        check(set(projection) == {'schema', 'checkpoint', 'accounts'} and projection['schema'] == 'rhook/intervention-target-state/0.1'
              and set(projection['accounts']) == {'root', 'rules'}, 'INTERVENTION_TARGET_STATE', 'Authenticate the exact Root and Rules target projection.')
        for role in ('root', 'rules'):
            account = projection['accounts'][role]
            check(set(account) == {'address', 'codeHash', 'storage'} and account['address'] == contracts[role]['address']
                  and account['codeHash'] == contracts[role]['runtimeHash'], 'INTERVENTION_TARGET_STATE', 'Use the pinned Hookr generation and code identities.', {'role': role})
        root, rules = projection['accounts']['root'], projection['accounts']['rules']
        expected = {_hex(int(p['configSlot'], 16) + i): w for i, w in enumerate(p['baselineConfigWords'])}
        check(rules['storage'] == expected and set(root['storage']) == {p['rootRecordSlot']}, 'INTERVENTION_TARGET_STATE',
              'The original LP100 profile words and the complete Root record are required.')
        root_old = int(root['storage'][p['rootRecordSlot']], 16)
        check((root_old & ((1 << 160) - 1)) == int(contracts['rules']['address'], 16) and ((root_old >> 160) & 0xffffff) == p['baseLpFeePips']
              and ((root_old >> 232) & 255) == 1 and _hex(root_old) == ROOT_ON, 'INTERVENTION_TARGET_STATE',
              'Require the initialized Dynamic Fee ON Root record with the pinned Rules and base fee.')
        return rules['storage'][p['configSlot']], _hex(root_old)
    except ExecutionError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ExecutionError('INTERVENTION_TARGET_STATE', 'Supply authenticated complete target fields.') from error


def describe(spec, projection, items, *, source_sha256):
    """Plan-only descriptor of one canonical intervention set over an authenticated target projection."""
    from .interventions import _pin
    _validate_spec(spec, _profile())
    check(type(projection) is dict and projection.get('checkpoint') == spec['checkpoint'], 'INTERVENTION_CHECKPOINT',
          'Use target proofs from the identical original checkpoint root.')
    canonical_set = canonical_interventions(items)
    rules0, root0 = original_words(projection)
    c = compose(canonical_set, rules0, root0, _profile())
    body = dict(schema=PLAN_DOMAIN, status='INTERVENTION_PLAN_ONLY', profile='hookr-buy/0.1', backendProfile=PROFILE, poolId=spec['poolId'],
                checkpoint=copy.deepcopy(spec['checkpoint']), sourceInputSha256=_pin(source_sha256), originalScenarioCommitment=spec['scenarioCommitment'],
                engine=copy.deepcopy(spec['engine']), originalProjection=copy.deepcopy(projection), interventions=canonical_set,
                fixedInputs={k: copy.deepcopy(spec[k]) for k in ('actions', 'commonSetup', 'environment', 'parent', 'chainConfig')},
                writes=c['writes'], fields=dict(baseline=fields(rules0, root0), variant=c['fields']), witnessClosureEstablished=False,
                semantics='hypothetical-checkpoint-state; typed masked overlay of the authenticated original; all non-target bits preserved',
                resultBindingDomain='rhook/intervention-result-references/0.1')
    return dict(body, interventionCommitment=commit(PLAN_DOMAIN, body))


def validate_descriptor(value):
    try:
        d = copy.deepcopy(value)
        check(type(d) is dict, 'CONFIG_OVERLAY_DESCRIPTOR', 'Supply a complete overlay descriptor.')
        pin = d.pop('interventionCommitment', None)
        check(pin == commit(PLAN_DOMAIN, d), 'INTERVENTION_COMMITMENT', 'Restore the original descriptor; do not rehash edits.')
        keys = {'schema', 'status', 'profile', 'backendProfile', 'poolId', 'checkpoint', 'sourceInputSha256', 'originalScenarioCommitment', 'engine', 'originalProjection',
                'interventions', 'fixedInputs', 'writes', 'fields', 'witnessClosureEstablished', 'semantics', 'resultBindingDomain'}
        check(set(d) == keys and d['schema'] == PLAN_DOMAIN and d['status'] == 'INTERVENTION_PLAN_ONLY' and d['profile'] == 'hookr-buy/0.1'
              and d['backendProfile'] == PROFILE and d['poolId'] == _profile()['poolId'] and d['checkpoint'] == d['originalProjection']['checkpoint']
              and d['witnessClosureEstablished'] is False, 'CONFIG_OVERLAY_DESCRIPTOR', 'Use the supported original-root plan-only descriptor.')
        check(d['interventions'] == canonical_interventions(d['interventions']), 'CONFIG_OVERLAY_CANONICAL_ORDER', 'Keep the canonical intervention order.')
        rules0, root0 = original_words(d['originalProjection'])
        c = compose(d['interventions'], rules0, root0, _profile())
        check(d['writes'] == c['writes'] and d['fields'] == dict(baseline=fields(rules0, root0), variant=c['fields']), 'INTERVENTION_WRITES',
              'Only the derived masked writes are allowed; no extra writes, fields or masks.')
        return copy.deepcopy(value)
    except ExecutionError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
        raise ExecutionError('CONFIG_OVERLAY_DESCRIPTOR', 'Restore a complete supported descriptor; this is not authentication.') from error


def plan(prepared_input, *, expected_sha256, interventions, node=None):
    """Read-only MPT authentication of the original Root/Rules targets plus a descriptor; no EVM or authority."""
    from .interventions import authenticated_projection
    canonical_interventions(interventions)
    raw, spec, projection = authenticated_projection(prepared_input, expected_sha256, node)
    d = describe(spec, projection, interventions, source_sha256=digest(raw))
    return dict(status='TARGET_FIELDS_MPT_AUTHENTICATED_PLAN_ONLY', descriptor=d,
                authenticationScope='Original Root/Rules account paths, runtime code preimages and five target storage leaves only. Checkpoint trust is supplied, not consensus-verified.',
                witnessClosure='UNKNOWN_FOR_NEW_INTERVENTION', nativeExecutions=0)


def transform(spec, plan_pin, items):
    from .interventions import _pin
    _pin(plan_pin)
    p = _profile()
    contracts = _contracts(p)
    canonical_set = canonical_interventions(items)
    c = compose(canonical_set, p['baselineConfigWords'][0], ROOT_ON, p)
    body = dict(schema=DOMAIN + '/transform', originalStateRoot=spec['checkpoint']['stateRoot'], poolId=p['poolId'], rootCodeHash=contracts['root']['runtimeHash'],
                rulesCodeHash=contracts['rules']['runtimeHash'], planCommitment=plan_pin, interventions=canonical_set, writes=c['writes'])
    return dict(body, interventionCommitment=commit(DOMAIN + '/transform', body)), c


def build_spec(original, descriptor, engine):
    d = validate_descriptor(descriptor)
    s = copy.deepcopy(original)
    s.pop('scenarioCommitment')
    s.update(schema=DOMAIN, engine=copy.deepcopy(engine))
    s['configOverlay'], c = transform(s, d['interventionCommitment'], d['interventions'])
    s['origin'] = dict(kind=KIND, capsuleId=capsule(s))
    s['configurations']['variant'] = copy.deepcopy(s['configurations']['baseline'])
    s['configurations']['variant'][0] = c['rules']
    s['scenarioCommitment'] = commit(DOMAIN, s)
    validate_spec(s)
    return s


def validate_spec(spec):
    """Mirror of the worker's validateOverlay plus the common input checks of the LP profile."""
    try:
        s = copy.deepcopy(spec)
        pin = s.pop('scenarioCommitment')
        check(s.get('schema') == DOMAIN and pin == commit(DOMAIN, s), 'CONFIG_OVERLAY_SPEC_COMMITMENT', 'Restore the versioned config-overlay input.')
        o = s.pop('configOverlay')
        check('intervention' not in s, 'CONFIG_OVERLAY_BINDING', 'A config-overlay input carries no other intervention.')
        expected, c = transform(s, o['planCommitment'], o['interventions'])
        check(o['interventions'] == canonical_interventions(o['interventions']), 'CONFIG_OVERLAY_CANONICAL_ORDER', 'Keep the canonical intervention order.')
        check(o == expected, 'CONFIG_OVERLAY_DERIVED_WRITES', 'The overlay must be exactly the derived masked writes, identities and original root.')
        p = _profile()
        variant = copy.deepcopy(p['baselineConfigWords'])
        variant[0] = c['rules']
        check(s['configurations'] == dict(baseline=p['baselineConfigWords'], variant=variant), 'CONFIG_OVERLAY_VARIANT_WORD',
              'The baseline is the pinned LP100 configuration; only the composed word 0 differs in the variant.')
        check(s['origin'] == dict(kind=KIND, capsuleId=commit(DOMAIN + '/checkpoint', dict(checkpoint=s['checkpoint'], intent=intent(s['poolId'], o['interventions'])))),
              'CONFIG_OVERLAY_ORIGIN', 'Keep the exact intervention-set/checkpoint binding.')
        # Common input checks through an explicit validation-only LP view: never written or executed.
        s['schema'] = LP_DOMAIN
        s['configurations']['variant'] = copy.deepcopy(p['baselineConfigWords'])
        old = int(s['configurations']['baseline'][0], 16)
        s['configurations']['variant'][0] = _hex((old & ~_mask('lpBps')) | (50 << 160))
        lp_intent = dict(schema='rhook/on-demand-hookr-intent/0.1', poolId=s['poolId'], lpBps=50)
        s['origin'] = dict(kind='AUTHENTICATED_CHECKPOINT_SCENARIO', capsuleId=commit('rhook/scenario-checkpoint/0.1', dict(checkpoint=s['checkpoint'], intent=lp_intent)))
        s['scenarioCommitment'] = commit(LP_DOMAIN, s)
        _validate_spec(s, p)
        check(set(spec) == set(s) | {'configOverlay'}, 'CONFIG_OVERLAY_SPEC_FIELDS', 'Unknown config-overlay input fields are unsupported.')
        return spec
    except ExecutionError:
        raise
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise ExecutionError('CONFIG_OVERLAY_SPEC_FIELDS', 'Supply the complete supported versioned input.') from error


class ConfigOverlayExecutionSDK(ExecutionSDK):
    """Prepared config-overlay workflow on the separately registered overlay worker.

    Inherits the existing exact operation/run/verify/compare and host supervision unchanged.
    """
    def profiles(self):
        p = _profile()
        return [dict(id=PROFILE, backend=PROFILE, chainId=4663, poolId=p['poolId'], baseline=dict(lpBps=100, dynamicFee='ON'),
                     interventions={LP_REWARDS: dict(lpBps=dict(minimum=0, maximum=99)), DYNAMIC_FEE: dict(dynamicFee=['OFF'])},
                     composition='DISJOINT_MASKED_OVERLAY_OF_AUTHENTICATED_ORIGINAL', arbitraryStorageWrites='UNSUPPORTED', nativeHost='darwin-arm64',
                     livePreparation='UNSUPPORTED', witnessCoverage='ONLY_ESTABLISHED_BY_COMPLETED_NATIVE_EXECUTION')]

    def configure(self, **kwargs):
        raise ExecutionError('CONFIG_OVERLAY_USE_OVERLAY_API', 'Use plan_overlay and prepare_overlay with the separately registered overlay worker.')

    def prepare(self, *args, **kwargs):
        raise ExecutionError('CONFIG_OVERLAY_USE_OVERLAY_API', 'Prepare the exact committed intervention set through prepare_overlay.')

    def capabilities(self, *, witness=None):
        value = super().capabilities()
        runtime = self.home / 'scenarios/RUNTIME.json'
        if runtime.exists():
            try:
                check(load(runtime, 2 << 20)['runtime']['profile'] == PROFILE, 'CONFIG_OVERLAY_RUNTIME_REQUIRED', 'Register the overlay worker in a fresh SDK home.')
            except (ExecutionError, OSError, ValueError, KeyError, TypeError):
                value['missing'].append(dict(code='CONFIG_OVERLAY_RUNTIME_REQUIRED', nextStep='Register the separately pinned overlay worker in a fresh home.'))
        if witness is not None:
            try:
                path = no_links(witness)
                spec = load(path / 'SCENARIO.json' if path.is_dir() else path, 8 << 20)
                validate_spec(spec)
                value['preparedWitness'] = dict(available=True, checkpoint=spec['checkpoint'], authentication='PENDING_NATIVE_ADMISSION', witnessClosure='NOT_EVALUATED')
                value['missing'] = [x for x in value['missing'] if x['code'] != 'PREPARED_WITNESS_MISSING']
            except (ExecutionError, OSError, ValueError):
                value['missing'].append(dict(code='CONFIG_OVERLAY_PREPARED_WITNESS_MISSING_OR_INVALID', nextStep='Use the prepared config-overlay input.'))
        value['staticDependenciesPresent'] = not value['missing']
        return value

    def plan_overlay(self, witness, *, expected_sha256, interventions, node=None):
        return plan(witness, expected_sha256=expected_sha256, interventions=interventions, node=node)

    def prepare_overlay(self, descriptor, witness, *, expected_sha256, output, node=None, candidate_runtime=None, engine=None):
        """engine=ACCEPTED_OVERLAY_ENGINE prepares offline for that pinned worker without running it."""
        from .cases.scenario import api
        d = validate_descriptor(descriptor)
        check(d['sourceInputSha256'] == expected_sha256, 'INTERVENTION_SOURCE_PIN', 'Use the original pinned witness that produced this descriptor.')
        pinned = engine is not None
        check(not pinned or (candidate_runtime is None and ACCEPTED_OVERLAY_ENGINE is not None and engine == ACCEPTED_OVERLAY_ENGINE), 'CONFIG_OVERLAY_ENGINE_PIN',
              'Offline preparation binds only the reviewed overlay worker identity; register any other runtime first.')
        fresh = self.plan_overlay(witness, expected_sha256=expected_sha256, interventions=d['interventions'], node=node)
        check(fresh['descriptor'] == d, 'INTERVENTION_PLAN_MISMATCH', 'Reauthenticate and preserve the complete saved plan.')
        raw, original = _input(witness, expected_sha256)
        sdk = self._sdk()
        if engine is None:
            r = api.runtime(sdk) if candidate_runtime is None else api._identity(load(no_links(candidate_runtime), 65536))
            check(r['profile'] == PROFILE, 'CONFIG_OVERLAY_RUNTIME_REQUIRED', 'Register the separately pinned overlay worker in a fresh SDK home; the LP and Dynamic Fee workers are incompatible.')
            engine = dict(sourceSha256=r['sourceCommitment'], binarySha256=r['files']['worker']['sha256'], policySha256=r['policySha256'])
        else:
            engine = dict(engine)
        out = no_links(output)
        check(not out.exists(), 'FRESH_PREPARED_OUTPUT_REQUIRED', 'Choose a fresh prepared directory.')
        spec = build_spec(original, d, engine)
        plan_value = api.configure(sdk, pool_id=spec['poolId'], profile=PROFILE, interventions=d['interventions'])
        out.mkdir(mode=0o700, parents=True)
        sync(out.parent)
        save(out / 'SCENARIO.json', spec)
        save(out / 'INTERVENTION.json', d)
        save(out / 'SDK_RESULT.json', dict(status='PREPARED_SCENARIO_INPUT', authentication='PENDING_NATIVE_ADMISSION', nativeExecutions=0, cleanupConfirmed=True,
                                           planId=plan_value['planId'], planCommitment=plan_value['planCommitment'], scenarioSha256=sha(out / 'SCENARIO.json'),
                                           scenarioCommitment=spec['scenarioCommitment']))
        registered = candidate_runtime is None and not pinned
        result = dict(status='EXECUTION_PREPARED' if registered else 'EXECUTION_CANDIDATE_PREPARED', runtimeRegistration='REGISTERED' if registered else 'PENDING',
                      schema=DOMAIN + '/prepared', profile=PROFILE, prepared=str(out), planId=plan_value['planId'], checkpoint=spec['checkpoint'],
                      scenarioSha256=sha(out / 'SCENARIO.json'), scenarioCommitment=spec['scenarioCommitment'],
                      interventionCommitment=spec['configOverlay']['interventionCommitment'], descriptorCommitment=d['interventionCommitment'],
                      interventions=d['interventions'], fields=d['fields'], sourceWitnessSha256=digest(raw),
                      nativeRunDirectory=str(sdk.home / 'scenarios/runs' / plan_value['planId']), authentication='PENDING_NATIVE_ADMISSION',
                      witnessClosure='NOT_EVALUATED', nativeExecutions=0, executionAuthorized=False)
        save(out / 'PREPARATION.json', result)
        return result

    def _prepared(self, prepared):
        from .cases.scenario import api
        path = no_links(prepared)
        try:
            meta = load(path / 'PREPARATION.json', 65536)
            d = validate_descriptor(load(path / 'INTERVENTION.json', 1 << 20))
            _, capture, plan_value, spec = api._input(self._sdk(), path)
            validate_spec(spec)
            check(meta['schema'] == DOMAIN + '/prepared' and meta['profile'] == PROFILE and plan_value['profile'] == PROFILE
                  and meta['scenarioSha256'] == capture['scenarioSha256'] and meta['scenarioCommitment'] == spec['scenarioCommitment'] and meta['planId'] == plan_value['planId']
                  and meta['checkpoint'] == spec['checkpoint'] and meta['interventionCommitment'] == spec['configOverlay']['interventionCommitment']
                  and meta['descriptorCommitment'] == d['interventionCommitment'] == spec['configOverlay']['planCommitment'] and meta['sourceWitnessSha256'] == d['sourceInputSha256']
                  and meta['interventions'] == d['interventions'] == spec['configOverlay']['interventions'] == plan_value['intent']['interventions'],
                  'CONFIG_OVERLAY_PREPARATION_DRIFT', 'Use the exact prepared input, descriptor, overlay home and worker.')
            check(d['checkpoint'] == spec['checkpoint'] and d['fixedInputs'] == {k: spec[k] for k in d['fixedInputs']}, 'CONFIG_OVERLAY_FIXED_INPUTS',
                  'Preserve the original signed action, common setup and environment.')
            return path, meta
        except ExecutionError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ExecutionError('CONFIG_OVERLAY_PREPARATION_DRIFT', 'Restore the exact prepared input and descriptor.') from error
