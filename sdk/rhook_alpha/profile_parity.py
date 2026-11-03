"""Parity of the descriptor worker (nitro-hook-profile-overlay/0.1) with the accepted SDK 0.4 runs. Offline.

Two strict comparators over recorded JSON, and the pre-registered G5 matrix:

- compare_initial_worlds: the worker's offline --profile-state worlds against the overlay records of an accepted
  SDK 0.4 run (initial state only, no execution);
- matrix: the expected values of every required outcome field, taken from the accepted SDK 0.4 FINAL.json files
  before any profile-overlay run, with the I_gas expectation;
- evaluate: one completed profile-overlay run against its pre-registered row;
- evaluate_runs: all three runs from their own recorded files, with I_gas computed only from those evaluations.

Every required field must be present and non-empty on both sides. A field that is missing, null or empty is
MISSING, and any MISSING or MISMATCH fails the comparison: absent values never compare equal. New domains and
commitments (scenario/evidence commitments, overlay records, schema/profile names) may differ and are reported
as informational only. Nothing here runs a worker, EVM or network, and a PASS here is not native parity of
anything but the compared fields.
"""
import copy
import re
from developer.files import canonical, digest

MATRIX_SCHEMA = 'rhook/profile-native-parity-matrix/0.1'
RESULT_SCHEMA = 'rhook/profile-native-parity-result/0.1'
INITIAL_SCHEMA = 'rhook/profile-initial-world-comparison/0.1'
WORLDS = ('SCENARIO_BASELINE', 'SCENARIO_VARIANT')
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
SWAP = '0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f'
ACTOR = '0xd2480fd61af9bc73b8c73e8fdcabceb6f21ea8ff'
# The G5 order and its SDK 0.4 references (records/<name> of the accepted Demo 0.5 runs).
RUNS = (
    ('LP23_DF_ON', [dict(kind='LP_REWARDS_BPS', parameters=dict(lpBps=23))], 'lp23'),
    ('LP100_DF_OFF', [dict(kind='DYNAMIC_FEE', parameters=dict(dynamicFee='OFF'))], 'dynamic-fee-off'),
    ('LP23_DF_OFF', [dict(kind='DYNAMIC_FEE', parameters=dict(dynamicFee='OFF')), dict(kind='LP_REWARDS_BPS', parameters=dict(lpBps=23))], 'combined'),
)
REQUIRED = ('receiptStatus', 'gasUsed', 'logs', 'receipts', 'stateRoot', 'receiptsRoot', 'outerSwapFeePips',
            'actorTargetTokenTransferNetBaseUnits', 'actorBalanceAfterWei', 'actorNonceAfter')
INFORMATIONAL = ('scenarioCommitment', 'evidenceCommitment', 'schema', 'profile', 'overlay', 'originalWitnessCommitment')
# The input fields that define the same action and environment; they must be byte-equal to the reference input.
SAME_INPUTS = ('checkpoint', 'parent', 'chainConfig', 'inventory', 'commonSetup', 'actions', 'environment', 'limits', 'poolId',
               'releaseManifestSha256')
INITIAL_KEYS = ('commonSetupRoot', 'worldInitialRoot', 'commonSimulationSetup', 'configurationAccount', 'configurationSlot', 'originalWord',
                'initialWord')
# SHA-256 of the accepted SDK 0.4 run records (Demo 0.5 reference records, as listed in its SHA256SUMS). The
# expected values are read only from bytes with these hashes.
REFERENCES = {
    'lp23': dict(inputSha256='ef31cf66909872bfa053d52b83987fac1feda149f257b4145ed1a12f45ce385d',
                 finalSha256='12504aaa29a8c8842225fa99ae5e705f219ec066b04271c58fde026d8d1e0139'),
    'dynamic-fee-off': dict(inputSha256='90b72e52bd1a8844ec84368ae56f52e4f0272a7737f521765a5b1fe2188c5722',
                            finalSha256='c23964f002079dc218dcaeb0441a6df0650e35a2cd06aacfc9522a178e6cbca1'),
    'combined': dict(inputSha256='43b50d00bfb84211147aa11607fb36dd1179f702031fa6c50d33bf8e3a684489',
                     finalSha256='9b069bb898163fe34bee77cee334ccca4ec17651f7bbe58cffb3cca28519d4ed'),
}
# The commitment of the matrix built from exactly those records (fixed before any profile-overlay run).
EXPECTED_MATRIX_COMMITMENT = 'fe12a9d2fc7adfdd66a8358d1a8fec6bf8f7b6c9c148aedca30d8cd2f303b04f'


class ParityError(ValueError):
    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def _present(value):
    return value is not None and value != '' and value != [] and value != {}


def _field_row(name, actual, expected, have_actual, have_expected):
    if not (have_actual and have_expected and _present(actual) and _present(expected)):
        return dict(field=name, result='MISSING', actualPresent=have_actual and _present(actual), expectedPresent=have_expected and _present(expected))
    return dict(field=name, result='MATCH' if actual == expected else 'MISMATCH',
                **({} if actual == expected else dict(actual=actual, expected=expected)))


def compare_fields(actual, expected, fields):
    """Rows for every field; a field absent, null or empty on either side is MISSING."""
    rows = [_field_row(k, actual.get(k) if type(actual) is dict else None, expected.get(k) if type(expected) is dict else None,
                       type(actual) is dict and k in actual, type(expected) is dict and k in expected) for k in fields]
    return dict(status='PASS' if rows and all(r['result'] == 'MATCH' for r in rows) else 'FAIL', rows=rows)


def compare_initial_worlds(state, reference_final):
    """Worker --profile-state worlds against the overlay records of a recorded SDK 0.4 run. storageWrites is
    required when the reference records it (the SDK 0.4 config-overlay worker does; the LP and Dynamic Fee
    workers do not)."""
    worlds = reference_final.get('worlds') if type(reference_final) is dict else None
    if type(state) is not dict or type(worlds) is not list or [w.get('world') if type(w) is dict else None for w in worlds] != list(WORLDS):
        return dict(schema=INITIAL_SCHEMA, status='FAIL', reason='WORLD_SHAPE', worlds=[])
    out = []
    for label, world in zip(('baseline', 'variant'), worlds):
        mine, recorded = state.get(label), world.get('overlay')
        keys = list(INITIAL_KEYS) + (['storageWrites'] if type(recorded) is dict and 'storageWrites' in recorded else [])
        row = compare_fields(mine, recorded, keys)
        out.append(dict(world=world['world'], compared=keys, **row))
    return dict(schema=INITIAL_SCHEMA, status='PASS' if all(w['status'] == 'PASS' for w in out) else 'FAIL', worlds=out)


def _int_hex(value, name):
    if type(value) is not str or re.fullmatch('0x[0-9a-f]+', value) is None:
        raise ParityError('PARITY_REQUIRED_FIELD_MISSING', name)
    return int(value, 16)


def project_world(world, *, token, pool_manager, pool_id, actor=ACTOR):
    """Required outcome fields of one recorded world. Raises PARITY_REQUIRED_FIELD_MISSING for an absent field;
    it never substitutes a default."""
    if type(world) is not dict:
        raise ParityError('PARITY_REQUIRED_FIELD_MISSING', 'world')
    for k in ('receipts', 'stateRoot', 'receiptsRoot', 'actorBalanceAfter', 'actorNonceAfter'):
        if k not in world or not _present(world[k]):
            raise ParityError('PARITY_REQUIRED_FIELD_MISSING', k)
    receipts = world['receipts']
    if type(receipts) is not list or len(receipts) != 2 or type(receipts[1]) is not dict:
        raise ParityError('PARITY_REQUIRED_FIELD_MISSING', 'receipts[1]')
    receipt = receipts[1]
    if type(receipt.get('logs')) is not list:
        raise ParityError('PARITY_REQUIRED_FIELD_MISSING', 'receipts[1].logs')
    status, gas = _int_hex(receipt.get('status'), 'receipts[1].status'), _int_hex(receipt.get('gasUsed'), 'receipts[1].gasUsed')
    topic = '0x' + actor[2:].rjust(64, '0')
    net, fees = 0, []
    for log in receipt['logs']:
        if type(log) is not dict or type(log.get('topics')) is not list or type(log.get('data')) is not str:
            raise ParityError('PARITY_REQUIRED_FIELD_MISSING', 'receipts[1].logs[]')
        if log.get('address') == token and len(log['topics']) == 3 and log['topics'][0] == TRANSFER and len(log['data']) == 66:
            amount = int(log['data'], 16)
            net += amount if log['topics'][2] == topic else 0
            net -= amount if log['topics'][1] == topic else 0
        # Uniswap v4 Swap(uint24 fee) is the sixth non-indexed ABI word.
        if log.get('address') == pool_manager and len(log['topics']) == 3 and log['topics'][0] == SWAP and log['topics'][1] == pool_id \
                and len(log['data']) == 386:
            fees.append(int(log['data'][-64:], 16))
    if not fees:
        raise ParityError('PARITY_REQUIRED_FIELD_MISSING', 'outerSwapFeePips')
    return dict(receiptStatus=status, gasUsed=gas, logs=copy.deepcopy(receipt['logs']), receipts=copy.deepcopy(receipts),
                stateRoot=world['stateRoot'], receiptsRoot=world['receiptsRoot'], outerSwapFeePips=fees,
                actorTargetTokenTransferNetBaseUnits=str(net), actorBalanceAfterWei=world['actorBalanceAfter'], actorNonceAfter=world['actorNonceAfter'])


def _worlds(final, constants):
    if type(final) is not dict or type(final.get('worlds')) is not list or [w.get('world') if type(w) is dict else None for w in final['worlds']] != list(WORLDS):
        raise ParityError('PARITY_REQUIRED_FIELD_MISSING', 'worlds')
    return {w['world']: project_world(w, **constants) for w in final['worlds']}


def constants_from_descriptor(d):
    contracts = {c['name']: c['address'] for c in d['contracts']}
    return dict(token=d['pool']['currency1'], pool_manager=contracts['poolManager'], pool_id=d['pool']['poolId'])


def i_gas(g23_off, g23_on, g100_off, g100_on):
    """Interaction of the two settings on the subject receipt's gas: G23OFF - G23ON - G100OFF + G100ON."""
    return g23_off - g23_on - g100_off + g100_on


def _reference(records, name):
    """Raw bytes of one accepted record, refused unless both SHA-256 equal the shipped pins."""
    from pathlib import Path
    from developer.files import no_links, read, strict
    pin = REFERENCES[name]
    root = no_links(Path(records)) / name
    raw_input, raw_final = read(root / 'inputs/SCENARIO.json', 8 << 20), read(root / 'runtime/scenario/FINAL.json', 8 << 20)
    if digest(raw_input) != pin['inputSha256'] or digest(raw_final) != pin['finalSha256']:
        raise ParityError('PARITY_REFERENCE_PIN', name)
    return strict(raw_input), strict(raw_final), pin


def matrix(records, d):
    """The pre-registered G5 matrix, built only from the accepted SDK 0.4 records directory (records/<name>, the
    Demo 0.5 reference records): every input and FINAL file must equal its shipped SHA-256 pin, and the result must
    equal EXPECTED_MATRIX_COMMITMENT."""
    constants = constants_from_descriptor(d)
    rows = []
    for name, items, ref in RUNS:
        spec, final, pin = _reference(records, ref)
        worlds = _worlds(final, constants)
        rows.append(dict(run=name, order=len(rows) + 1, interventions=copy.deepcopy(items), reference=ref, referenceInputSha256=pin['inputSha256'],
                         referenceFinalSha256=pin['finalSha256'], referenceScenarioCommitment=final.get('scenarioCommitment'),
                         sameInputs={k: digest(canonical(spec[k])) for k in SAME_INPUTS}, expected=worlds))
    base = [r['expected']['SCENARIO_BASELINE'] for r in rows]
    if any(b != base[0] for b in base[1:]):
        raise ParityError('PARITY_REFERENCE_BASELINES_DIFFER')
    g = {r['run']: r['expected']['SCENARIO_VARIANT']['gasUsed'] for r in rows}
    expected_i = i_gas(g['LP23_DF_OFF'], g['LP23_DF_ON'], g['LP100_DF_OFF'], base[0]['gasUsed'])
    value = dict(schema=MATRIX_SCHEMA, profile='nitro-hook-profile-overlay/0.1', requiredFields=list(REQUIRED), informationalFields=list(INFORMATIONAL),
                 sameInputFields=list(SAME_INPUTS), worlds=list(WORLDS), runs=rows, constants=constants,
                 iGas=dict(formula='G23OFF - G23ON - G100OFF + G100ON (subject receipt gasUsed; G100ON is the common baseline)',
                           expected=expected_i, referenceGas=dict(g, LP100_DF_ON=base[0]['gasUsed']),
                           note='The reference values come from three different SDK 0.4 workers; G5 measures all four with one worker.'),
                 rules=['Expected values are fixed before any profile-overlay run and are never changed after it.',
                        'A missing, null or empty required field fails; it never compares equal.',
                        'A mismatch stops the sequence for investigation; no run is repeated automatically.'])
    value['matrixCommitment'] = digest(MATRIX_SCHEMA.encode() + b'\n' + canonical(value))
    return check_matrix(value)


def check_matrix(value):
    """The matrix is the shipped one: its self-hash holds and equals the independently shipped commitment."""
    body = dict(value) if type(value) is dict else {}
    pin = body.pop('matrixCommitment', None)
    if (value.get('schema') if type(value) is dict else None) != MATRIX_SCHEMA or pin != digest(MATRIX_SCHEMA.encode() + b'\n' + canonical(body)) \
            or pin != EXPECTED_MATRIX_COMMITMENT:
        raise ParityError('PARITY_MATRIX_DRIFT')
    return value


def evaluate(value, run, spec, final):
    """One completed profile-overlay run (its input SCENARIO.json and verified FINAL.json) against its row."""
    check_matrix(value)
    rows = [r for r in value['runs'] if r['run'] == run]
    if len(rows) != 1:
        raise ParityError('PARITY_UNKNOWN_RUN', run)
    row = rows[0]
    inputs = [dict(field=k, result='MATCH' if type(spec) is dict and k in spec and digest(canonical(spec[k])) == row['sameInputs'][k] else 'MISMATCH')
              for k in SAME_INPUTS]
    interventions = type(spec) is dict and spec.get('profileOverlay', {}).get('interventions') == row['interventions']
    linked = type(final) is dict and type(spec) is dict and final.get('scenarioCommitment') == spec.get('scenarioCommitment')
    try:
        worlds = _worlds(final, value['constants'])
        missing = None
    except ParityError as error:
        worlds, missing = {}, str(error)
    out = {}
    for w in WORLDS:
        out[w] = compare_fields(worlds.get(w), row['expected'][w], REQUIRED)
    informational = {}
    if type(final) is dict:
        informational = dict(scenarioCommitment=final.get('scenarioCommitment'), referenceScenarioCommitment=row['referenceScenarioCommitment'],
                             evidenceCommitment=final.get('evidenceCommitment'), schema=final.get('schema'), profile=final.get('profile'))
    ok = (missing is None and linked and interventions and all(i['result'] == 'MATCH' for i in inputs)
          and all(out[w]['status'] == 'PASS' for w in WORLDS))
    return dict(schema=RESULT_SCHEMA, run=run, matrixCommitment=value['matrixCommitment'], status='PARITY_FIELDS_MATCH' if ok else 'PARITY_FAIL',
                inputLinked=linked, interventionsMatch=interventions, sameInputs=inputs, projectionError=missing, worlds=out,
                informational=informational, gasUsed={w: worlds.get(w, {}).get('gasUsed') for w in WORLDS})


def evaluate_runs(value, runs):
    """All three runs from their own recorded input and FINAL: {run name: (input spec, FINAL)}. Each is evaluated
    here against its row, and I_gas is computed only from these fresh evaluations."""
    check_matrix(value)
    names = [r['run'] for r in value['runs']]
    if type(runs) is not dict or sorted(runs) != sorted(names):
        raise ParityError('PARITY_RUN_SET', ','.join(sorted(runs) if type(runs) is dict else []))
    results = {name: evaluate(value, name, *runs[name]) for name in names}
    return dict(schema=RESULT_SCHEMA + '/sequence', matrixCommitment=value['matrixCommitment'], runs=results, iGas=_i_gas(value, results))


def _i_gas(value, results):
    """I_gas from fresh evaluate() results only. It is measured whenever all three are valid runs of their planned
    inputs (linked, interventions and same inputs equal, every world projected), whether or not the other fields
    match; parity of the whole sequence is reported beside it."""
    valid = all(r['inputLinked'] and r['interventionsMatch'] and r['projectionError'] is None and all(i['result'] == 'MATCH' for i in r['sameInputs'])
                for r in results.values())
    parity = all(r['status'] == 'PARITY_FIELDS_MATCH' for r in results.values())
    if not valid:
        return dict(status='NOT_EVALUATED', reason='EVERY_RUN_MUST_BE_A_VALID_RUN_OF_ITS_PLANNED_INPUT', allRunsParity=parity)
    g = {k: results[k]['gasUsed']['SCENARIO_VARIANT'] for k in results}
    bases = {results[k]['gasUsed']['SCENARIO_BASELINE'] for k in results}
    if len(bases) != 1:
        return dict(status='I_GAS_FAIL', reason='BASELINES_DIFFER', baselines=sorted(bases), allRunsParity=parity)
    measured = i_gas(g['LP23_DF_OFF'], g['LP23_DF_ON'], g['LP100_DF_OFF'], bases.pop())
    return dict(status='I_GAS_MATCH' if measured == value['iGas']['expected'] else 'I_GAS_MISMATCH', measured=measured, expected=value['iGas']['expected'],
                allRunsParity=parity)
