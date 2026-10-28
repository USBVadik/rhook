"""Trusted built-in intervention adapters; capsule data never imports Python code."""
import copy
import re
from developer.files import require
from .capsule import PROFILE, hash32, seal

class HookrLP:
    identity = 'hookr-1.lp-bps/1'
    account = '0x4a71c270b1520f94064268102aebd744b0de7942'
    slot = '0x1ad7756ae873b72ee7b85d116a86b7b2c5244640095753f73687752bed4705aa'
    pool = '0x94d1a318a67449c1fd850f354b4694be69483a6e94148787659e487ecb8c6780'
    code = '0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b'

    def plan(self, d, intervention):
        require(d['execution']['profile'] == PROFILE and d['checkpoint']['chainId'] == 4663, 'UNSUPPORTED_EXECUTION_PROFILE')
        c = copy.deepcopy(d['adapter']['config'])
        require(set(c) == {'account', 'slot', 'pool', 'expectedOldWord', 'rulesRuntimeHash', 'subject', 'ordinal', 'sender', 'router', 'observation'}, 'HOOKR_ADAPTER_FIELDS')
        require(all((type(c[k]) is str and re.fullmatch('0x[0-9a-f]{40}', c[k]) for k in ('account', 'sender', 'router'))), 'HOOKR_ADDRESS')
        require(all((hash32(c[k]) for k in ('slot', 'pool', 'expectedOldWord', 'subject'))) and c['rulesRuntimeHash'] == self.code, 'HOOKR_HASH_OR_GENERATION')
        require(type(c['ordinal']) is int and 1 <= c['ordinal'] < len(d['arrivals']) and (d['arrivals'][c['ordinal']] == c['subject']), 'SUBJECT_ORDINAL')
        require(type(intervention) is dict and set(intervention) == {'rule', 'value'} and (intervention['rule'] == 'lpBps') and (type(intervention['value']) is int) and (0 <= intervention['value'] <= 99), 'LP_BPS_INTEGER_0_TO_99_REQUIRED')
        require((c['account'], c['slot'], c['pool']) == (self.account, self.slot, self.pool), 'UNSUPPORTED_HOOKR_POOL_BINDING')
        o = c['observation']
        require(type(o) is dict and set(o) == {'accounts', 'storage', 'subject', 'nativeOrdinal'} and (o['subject'] == c['subject']) and (type(o['nativeOrdinal']) is int) and (o['nativeOrdinal'] == c['ordinal']), 'OBSERVATION_IDENTITY')
        require(type(o['accounts']) is list and 0 < len(o['accounts']) <= 16 and (len(set(o['accounts'])) == len(o['accounts'])) and all((type(x) is str and re.fullmatch('0x[0-9a-f]{40}', x) for x in o['accounts'])), 'OBSERVATION_ACCOUNTS')
        require(o['storage'] == [{'account': c['account'], 'slot': c['slot']}], 'OBSERVATION_STORAGE')
        old = int(c['expectedOldWord'], 16)
        mask = 65535 << 160
        require((old & mask) >> 160 <= 10000, 'ORIGINAL_LP_RANGE')
        i = {k: c[k] for k in ('account', 'slot', 'pool', 'expectedOldWord')}
        i.update(checkpoint=d['checkpoint'], mask=f'0x{mask:064x}', newWord=f"0x{old & ~mask | intervention['value'] << 160:064x}")
        return {'packageSha256': d['assets']['BLOCK_PACKAGE.json']['sha256'], 'inputCommitment': d['execution']['inputCommitment'], 'witnessCommitment': d['execution']['witnessCommitment'], 'checkpoint': d['checkpoint'], **d['target'], 'arrivals': d['arrivals'], 'transactions': len(d['arrivals']), 'subject': c['subject'], 'sender': c['sender'], 'router': c['router'], 'observation': o, 'intervention': i, 'rulesRuntimeHash': c['rulesRuntimeHash']}

    def capsule(self, raw, *, case_id, subject_index, input_commitment, witness_commitment, original_word=None):
        from developer.files import strict, digest
        p = strict(raw)
        block = p['block']
        arrivals = block['transactions']
        require(type(subject_index) is int and 0 <= subject_index < len(arrivals), 'SUBJECT_ORDINAL')
        tx = arrivals[subject_index]
        words = [item for proof in p['proofs'] if proof['address'].lower() == self.account for item in proof['proof']['storageProof'] if item['key'].lower() == self.slot]
        declared = {int(item['value'], 16) for item in words}
        if original_word is not None:
            declared.add(int(original_word, 16))
        require(len(declared) == 1, 'DECLARED_RULES_WORD_REQUIRED_OR_CONFLICTING')
        old = declared.pop()
        require(0 <= old < 2 ** 256, 'RULES_WORD_RANGE')
        config = {'account': self.account, 'slot': self.slot, 'pool': self.pool, 'expectedOldWord': f'0x{old:064x}', 'rulesRuntimeHash': self.code, 'subject': tx['hash'], 'ordinal': subject_index, 'sender': tx['from'].lower(), 'router': tx['to'].lower(), 'observation': {'accounts': list(dict.fromkeys([tx['from'].lower(), tx['to'].lower(), self.account])), 'storage': [{'account': self.account, 'slot': self.slot}], 'subject': tx['hash'], 'nativeOrdinal': subject_index}}
        d = seal({'schema': 'rhook/case-capsule/0.1', 'caseId': case_id, 'checkpoint': p['checkpoint'], 'target': {'blockNumber': int(block['number'], 16), 'blockHash': block['hash'], 'stateRoot': block['stateRoot'], 'receiptsRoot': block['receiptsRoot']}, 'arrivals': [tx['hash'] for tx in arrivals], 'assets': {'BLOCK_PACKAGE.json': {'sha256': digest(raw), 'bytes': len(raw)}}, 'execution': {'profile': PROFILE, 'inputCommitment': input_commitment, 'witnessCommitment': witness_commitment}, 'adapter': {'id': self.identity, 'config': config}, 'provenance': {'kind': 'USER_SUPPLIED', 'description': 'Locally packaged input; chain trust and proof authentication are separate.'}, 'coverage': {'reads': 'UNKNOWN', 'writes': 'UNKNOWN'}})
        self.authentication_plan(d)
        return d

    def authentication_plan(self, d):
        return self.plan(d, {'rule': 'lpBps', 'value': 0})

    def compare(self, verified):
        from decimal import Decimal, localcontext
        a, b = (verified['worlds'][k] for k in ('ACTUAL', 'BRANCH'))
        x, y = (int(v['buyerRhookTransferNetBaseUnits']) for v in (a, b))
        with localcontext() as c:
            c.prec = 50
            percent = format(Decimal(y - x) * 100 / Decimal(x), 'f') if x > 0 else None
        return {'status': 'VERIFIED_COMPARISON',
                'subjectRhookTransferNetActualBaseUnits': str(x), 'subjectRhookTransferNetBranchBaseUnits': str(y), 'subjectRhookTransferNetDeltaBaseUnits': str(y-x),
                'transferNetMeaning': 'SIGNED_SELECTED_SENDER_ERC20_TRANSFER_EVENT_NET_NOT_PROFIT_OR_STORAGE_BALANCE',
                'buyerTransferNetActualBaseUnits': str(x), 'buyerTransferNetBranchBaseUnits': str(y), 'buyerTransferNetDeltaBaseUnits': str(y - x), 'buyerTransferNetIncreasePercent': percent,
                'legacyBuyerFields': 'Compatibility aliases for the selected sender; they do not classify the sender as a buyer.',
                'subjectGasDelta': str(int(b['subjectGasUsed']) - int(a['subjectGasUsed'])), 'outerSwapFeePips': {name: v['outerSwap']['feePips'] if v['outerSwap'] else None for name, v in [('ACTUAL', a), ('BRANCH', b)]}, 'economicAssurance': 'UNRESOLVED', 'heterogeneousAgreement': 'NOT_EVALUATED', 'qualifiedClaims': 0, 'limitation': 'Receipt Transfer-event net, not final token-storage balances. No independent EVM re-execution.'}
from .historical.adapter import HistoricalDynamicFeeOff
BUILTINS = {HookrLP.identity: HookrLP(), HistoricalDynamicFeeOff.identity: HistoricalDynamicFeeOff()}

def get_adapter(d):
    require(d['adapter']['id'] in BUILTINS, 'UNSUPPORTED_ADAPTER: ' + d['adapter']['id'])
    return BUILTINS[d['adapter']['id']]
