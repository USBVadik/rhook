"""Pinned recorded-evidence inspection; no Ethereum crypto, worker or network."""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

DESCRIPTOR_SHA256 = '426cc32fcc901494e3e625acf63ed12e1057b1261d1fe2c0af85539d6d2a256c'
DEMO_ID = 'hookr-on-demand-99236464-lp100-lp50'
RECORDS = ('DISCOVERY_FINAL.json', 'OFFLINE_FINAL.json')
MAX_BYTES = 2 << 20
FIELDS = ('stateRoot', 'receiptsRoot', 'producedSyntheticHeader', 'systemTransactionHash',
          'actionMapping', 'receipts', 'actorBalanceBefore', 'actorBalanceAfter',
          'actorNonceAfter', 'overlay')
LABELS = ('SCENARIO_BASELINE', 'SCENARIO_VARIANT')
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
SWAP = '0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f'
SCOPE = dict(consumer='PINNED_RECORDED_INTEGRITY_AND_LOG_ARITHMETIC',
             MPTProofVerification=False, receiptTrieRecomputed=False,
             headerHashRecomputed=False, transactionSignatureRecovered=False,
             EVMReexecution=False, independentRustAgreement='NOT_EVALUATED',
             independentConsensusProof=False, resourceTelemetryVerified=False,
             qualifiedClaims=0)


def require(condition, code):
    if not condition:
        raise ValueError(code)


def _read(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES, 'INPUT_NOT_BOUNDED_REGULAR_FILE')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES
                and (before.st_dev, before.st_ino) == (info.st_dev, info.st_ino), 'INPUT_CHANGED_OR_NOT_REGULAR')
        raw = stream.read(MAX_BYTES + 1)
        require(len(raw) == info.st_size and len(raw) <= MAX_BYTES, 'INPUT_SIZE_CHANGED')
        return raw


def _parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'DUPLICATE_JSON_KEY')
            value[key] = item
        return value

    def reject(_):
        raise ValueError('NON_INTEGER_OR_NONFINITE_JSON')

    def integer(text):
        value = int(text)
        require(abs(value) <= (1 << 53) - 1, 'UNSAFE_JSON_INTEGER')
        return value

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=reject,
                           parse_constant=reject, parse_int=integer)
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            require(depth <= 64, 'JSON_DEPTH_LIMIT')
            if isinstance(item, dict):
                pending.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('JSON_ENCODING_OR_DEPTH') from error


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _hex(value, digits=None):
    pattern = r'0x[0-9a-f]{' + str(digits) + '}' if digits is not None else r'0x[0-9a-f]{1,64}'
    require(isinstance(value, str) and re.fullmatch(pattern, value), 'HEX_ENCODING')
    return int(value, 16)


def _observe(world, meta, index):
    s = meta['scenario']
    label = LABELS[index]
    require(world['world'] == label, 'SCENARIO_WORLD_LABEL')
    overlay = world['overlay']
    original = _hex(overlay['originalWord'], 64)
    initial = _hex(overlay['initialWord'], 64)
    mask = ((1 << 16) - 1) << 160
    lp = 100 if index == 0 else 50
    words = s['configurations']['baseline' if index == 0 else 'variant']
    require(overlay['configurationAccount'] == s['configurationAccount']
            and overlay['configurationSlot'] == s['configurationSlot']
            and original == _hex(s['configurations']['baseline'][0], 64)
            and initial == ((original & ~mask) | (lp << 160))
            and overlay['initialWord'] == words[0], 'LP_INTERVENTION')
    require(overlay['commonSimulationSetup'] == s['commonSetup']
            and world['actorBalanceBefore'] == s['commonSetup']['fundingWei']
            and type(world['actorNonceAfter']) is int and world['actorNonceAfter'] == 1,
            'COMMON_SYNTHETIC_SETUP')
    require((overlay['worldInitialRoot'] == overlay['commonSetupRoot']) == (index == 0), 'RECORDED_INITIAL_ROOT')
    require(world['actionMapping'] == [dict(actionId=s['action']['id'],
            transactionHash=s['transactionHash'], transactionOrdinal=1)], 'TRANSACTION_IDENTITY')
    receipts = world['receipts']
    require(len(receipts) == 2, 'RECORDED_RECEIPT_COUNT')
    header = world['producedSyntheticHeader']
    require(header['parentHash'] == meta['checkpoint']['blockHash']
            and _hex(header['number']) == s['environment']['l2BlockNumber']
            and _hex(header['timestamp']) == s['environment']['l2Timestamp']
            and header['stateRoot'] == world['stateRoot']
            and header['receiptsRoot'] == world['receiptsRoot'], 'RECORDED_HEADER_LINK')
    require(receipts[0]['transactionHash'] == world['systemTransactionHash'], 'SYSTEM_TRANSACTION_IDENTITY')
    receipt = receipts[1]
    require(receipt['transactionHash'] == s['transactionHash']
            and _hex(receipt['transactionIndex']) == 1 and _hex(receipt['status']) == 1,
            'TRANSACTION_IDENTITY_OR_STATUS')
    for i, r in enumerate(receipts):
        require(_hex(r['transactionIndex']) == i and r['blockHash'] == header['hash']
                and _hex(r['blockNumber']) == s['environment']['l2BlockNumber'], 'RECEIPT_IDENTITY')
    actor_topic = '0x' + s['actor'][2:].rjust(64, '0')
    net, transfers, fees = 0, 0, []
    for log in receipt['logs']:
        require(log['transactionHash'] == s['transactionHash'] and log['blockHash'] == header['hash']
                and _hex(log['transactionIndex']) == 1
                and _hex(log['blockNumber']) == s['environment']['l2BlockNumber']
                and log['removed'] is False, 'LOG_IDENTITY')
        topics = log['topics']
        if log['address'] == s['token'] and topics and topics[0] == TRANSFER:
            require(len(topics) == 3, 'TRANSFER_LAYOUT')
            amount = _hex(log['data'], 64)
            _hex(topics[1], 64); _hex(topics[2], 64)
            net += (amount if topics[2] == actor_topic else 0) - (amount if topics[1] == actor_topic else 0)
            transfers += 1
        elif log['address'] == s['poolManager'] and topics and topics[0] == SWAP:
            require(len(topics) == 3 and topics[1] == s['poolId']
                    and topics[2] == '0x' + s['router'][2:].rjust(64, '0')
                    and isinstance(log['data'], str) and re.fullmatch(r'0x[0-9a-f]{384}', log['data']), 'SWAP_LAYOUT')
            fee = int(log['data'][-64:], 16)
            require(fee < 1 << 24, 'SWAP_FEE_WIDTH')
            fees.append(fee)
    require(transfers > 0 and net > 0 and len(fees) == 1, 'OBSERVABLE_EVENT_CARDINALITY')
    return dict(world=label, receiptStatus=1, gasUsed=_hex(receipt['gasUsed']),
                tokenTransferNetBaseUnits=str(net), swapFeePips=fees,
                stateRoot=world['stateRoot'], receiptsRoot=world['receiptsRoot'],
                actorBalanceAfterWei=world['actorBalanceAfter'])


def _checked(bundle):
    root = Path(bundle).absolute()
    require(not root.is_symlink() and root.is_dir(), 'EVIDENCE_DIRECTORY_REQUIRED')
    require({p.name for p in root.iterdir()} == {'DEMO.json', *RECORDS}, 'EVIDENCE_FILE_SET')
    raw = _read(root / 'DEMO.json')
    require(hashlib.sha256(raw).hexdigest() == DESCRIPTOR_SHA256, 'DESCRIPTOR_PIN_MISMATCH')
    meta = _parse(raw)
    require(meta['schema'] == 'rhook/recorded-scenario-demo/0.1' and meta['demoId'] == DEMO_ID
            and meta['executionMode'] == 'HYPOTHETICAL_SCENARIO', 'SUPPORTED_RECORDED_DEMO_REQUIRED')
    require(meta['scope'] == SCOPE and set(meta['files']) == set(RECORDS), 'VERIFICATION_SCOPE_OR_FILES')
    s = meta['scenario']
    require(s['lpFieldShift'] == 160 and s['lpFieldWidth'] == 16
            and s['baselineLpBps'] == 100 and s['variantLpBps'] == 50
            and s['configurations']['baseline'][1:] == s['configurations']['variant'][1:]
            and len(s['configurations']['baseline']) == len(s['configurations']['variant']) == 4,
            'DECLARED_LP_INTERVENTION')
    require(s['environment']['l2BlockNumber'] == meta['checkpoint']['blockNumber'] + 1
            and s['environment']['l2Timestamp'] == meta['checkpointTimestamp'] + 1
            and s['action']['deadline'] == s['environment']['l2Timestamp'] + 300,
            'DECLARED_SYNTHETIC_ENVIRONMENT')
    documents, observations = [], []
    for index, name in enumerate(RECORDS):
        data = _read(root / name)
        require(hashlib.sha256(data).hexdigest() == meta['files'][name], 'FILE_HASH_MISMATCH')
        value = _parse(data)
        require(value['schema'] == 'rhook/hookr-scenario/0.1/evidence'
                and value['status'] == ('SCENARIO_DISCOVERY_COMPLETED' if index == 0 else 'SCENARIO_EXECUTED_UNQUALIFIED')
                and value['producerInvocations'] == 2 and value['ownedBridgesClosed'] is True
                and value['qualifiedClaims'] == 0 and len(value['worlds']) == 2,
                'RECORDED_STAGE_STATUS')
        body = dict(value)
        pin = body.pop('evidenceCommitment')
        require(hashlib.sha256(b'rhook/hookr-scenario/0.1/evidence\n' + _canonical(body)).hexdigest() == pin,
                'EVIDENCE_COMMITMENT')
        require(value['scenarioCommitment'] == meta['recordedScenarios']['discovery' if index == 0 else 'offline']
                and all(w['scenarioCommitment'] == value['scenarioCommitment'] for w in value['worlds']), 'SCENARIO_COMMITMENT_LINK')
        rows = [_observe(w, meta, i) for i, w in enumerate(value['worlds'])]
        left, right = value['worlds']
        require(left['overlay']['commonSetupRoot'] == right['overlay']['commonSetupRoot']
                and left['originalWitnessCommitment'] == right['originalWitnessCommitment']
                and left['systemTransactionHash'] == right['systemTransactionHash'], 'RECORDED_COMMON_INITIALIZATION')
        common_header = ('parentHash', 'number', 'timestamp', 'baseFeePerGas', 'gasLimit', 'miner',
                         'mixHash', 'nonce', 'extraData', 'transactionsRoot')
        require(all(left['producedSyntheticHeader'][k] == right['producedSyntheticHeader'][k]
                    for k in common_header), 'COMMON_BLOCK_ENVIRONMENT')
        documents.append(value)
        observations.append(rows)
    for a, b in zip(documents[0]['worlds'], documents[1]['worlds']):
        require(a['world'] == b['world'] and all(a[k] == b[k] for k in FIELDS), 'DISCOVERY_OFFLINE_MISMATCH')
    require(observations[0] == observations[1], 'RECORDED_OBSERVATION_MISMATCH')
    return meta, observations[1]


def verify_recorded(bundle):
    meta, _ = _checked(bundle)
    return dict(status='SCENARIO_EVIDENCE_INTEGRITY_PASS', demoId=meta['demoId'], checkpoint=meta['checkpoint'],
                checks=dict(pinnedFiles=True, evidenceCommitments=True, recordedTransactionIdentity=True,
                            lpOverlay=True, commonInitialization=True, discoveryOfflineMatch=True, receiptLogArithmetic=True),
                scope=dict(SCOPE), qualifiedClaims=0, RPC=0, nativeExecutions=0)


def inspect_recorded(bundle):
    meta, _ = _checked(bundle)
    return dict(status='SCENARIO_EVIDENCE_INSPECTED', demoId=meta['demoId'], executionMode=meta['executionMode'],
                checkpoint=meta['checkpoint'], scenario=meta['scenario'], disclosures=meta['disclosures'],
                scope=dict(SCOPE), RPC=0, nativeExecutions=0)


def compare_recorded(bundle):
    meta, worlds = _checked(bundle)
    baseline = int(worlds[0]['tokenTransferNetBaseUnits'])
    delta = int(worlds[1]['tokenTransferNetBaseUnits']) - baseline
    with localcontext() as context:
        context.prec = 50
        percent = str(Decimal(delta) * 100 / Decimal(baseline))
    return dict(status='SCENARIO_EVIDENCE_COMPARISON_PASS', demoId=meta['demoId'], worlds=worlds,
                tokenOutputDeltaBaseUnits=str(delta), tokenOutputGainPercent=percent,
                gasDelta=worlds[1]['gasUsed'] - worlds[0]['gasUsed'], scope=dict(SCOPE),
                qualifiedClaims=0, RPC=0, nativeExecutions=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'verify', 'compare'))
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent / 'evidence')
    args = parser.parse_args(argv)
    try:
        require(sys.version_info >= (3, 12), 'PYTHON_3_12_REQUIRED')
        value = {'inspect': inspect_recorded, 'verify': verify_recorded, 'compare': compare_recorded}[args.command](args.bundle)
    except (ValueError, OSError, KeyError, TypeError, IndexError, RecursionError, ArithmeticError) as error:
        print(json.dumps(dict(status='SCENARIO_EVIDENCE_FAIL', causeCode=str(error))), file=sys.stderr)
        return 1
    print(json.dumps(value, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
