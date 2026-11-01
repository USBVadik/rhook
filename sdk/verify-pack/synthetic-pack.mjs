// Deterministic SYNTHETIC verify-pack fixture. Not chain data: the block, roots and receipts are made up.
// It exercises the same checks as a real pack (signed subject transaction, receipts trie, header hashes,
// Swap/Transfer economics) without any private witness or historical result.
//
//   node sdk/verify-pack/synthetic-pack.mjs --write   # regenerate examples/synthetic-lp50
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {keccak256} from '../engine/adapters/hookr-case/primitives.mjs';
import {bloom, headerHash, receiptBytes, trieRoot} from '../engine/plan_native/ethereum.mjs';
import {CONTEXT_SCHEMA, PINS_SCHEMA, PLAN_SCHEMA, sha256Hex, stableJson} from './verify-pack.mjs';

const require = createRequire(new URL('../engine/adapters/hookr-case/package.json', import.meta.url));
const {privateKeyToAccount} = require('viem/accounts');

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SYNTHETIC_DIR = path.join(HERE, 'examples/synthetic-lp50');
export const SYNTHETIC_PINS = path.join(HERE, 'examples/synthetic-lp50.pins.json');

const label = (text) => createHash('sha256').update(`rhook verify-pack synthetic fixture 0.1: ${text}`).digest('hex');
const h32 = (text) => '0x' + label(text);
const word = (n) => (BigInt.asUintN(256, BigInt(n))).toString(16).padStart(64, '0');
const topicOf = (signature) => keccak256('0x' + Buffer.from(signature).toString('hex'));
const pad = (address) => '0x' + '0'.repeat(24) + address.slice(2);
const q = (n) => '0x' + BigInt(n).toString(16);

// The recorded-world verifier reads RHOOK Transfer events and PoolManager Swap events by these addresses.
const TOKEN = '0x3c022d43a9f826cd206c2ba60bc753d8b36185c4';
const MANAGER = '0x8366a39cc670b4001a1121b8f6a443a643e40951';
const ROUTER = '0x1111111111111111111111111111111111111111';
const RULES = '0x2222222222222222222222222222222222222222';
const POOL = h32('pool');
const SLOT = h32('rules slot');
const CHAIN_ID = 4663;
const PARENT_NUMBER = 1_000_000;
const LP_MASK = 65535n << 160n;
const BASE_WORD = (BigInt(h32('rules word')) & ~LP_MASK);
const ZERO_BLOOM = '0x' + '00'.repeat(256);
const EMPTY_CODE_HASH = '0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470';

function header(fields) {
  const h = {
    parentHash: fields.parentHash, sha3Uncles: '0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347',
    miner: '0xa4b000000000000000000073657175656e636572', stateRoot: fields.stateRoot,
    transactionsRoot: fields.transactionsRoot, receiptsRoot: fields.receiptsRoot, logsBloom: fields.logsBloom,
    difficulty: '0x1', number: q(fields.number), gasLimit: '0x4000000000000', gasUsed: q(fields.gasUsed),
    timestamp: q(1_790_000_000 + fields.number - PARENT_NUMBER), extraData: h32('extra ' + fields.number),
    mixHash: h32('mix ' + fields.number), nonce: '0x0000000000000001', baseFeePerGas: '0x1312d00',
  };
  return {...h, hash: headerHash(h)};
}

function combinedBloom(receipts) {
  const out = Buffer.alloc(256);
  for (const r of receipts) Buffer.from(r.logsBloom.slice(2), 'hex').forEach((b, i) => { out[i] |= b; });
  return '0x' + out.toString('hex');
}

export async function buildSyntheticPack() {
  const account = privateKeyToAccount(h32('subject signing key, test only'));
  const sender = account.address.toLowerCase();
  const input = '0x3593564c' + label('router calldata').repeat(2);
  const value = 10n ** 16n;
  const subjectRaw = await account.signTransaction({
    chainId: CHAIN_ID, type: 'eip1559', nonce: 0, to: ROUTER, value, data: input,
    gas: 2_000_000n, maxFeePerGas: 40_000_000n, maxPriorityFeePerGas: 0n,
  });
  const systemRaw = '0x6af84a' + label('system transaction') + label('system payload').slice(0, 42);
  const raw = [systemRaw, subjectRaw];
  const arrivals = raw.map((r) => keccak256(r));

  const parent = header({parentHash: h32('grandparent'), stateRoot: h32('parent state'), transactionsRoot: trieRoot([h32('parent tx')]),
    receiptsRoot: h32('parent receipts'), logsBloom: ZERO_BLOOM, number: PARENT_NUMBER, gasUsed: 21000});
  const checkpoint = {blockHash: parent.hash, blockNumber: PARENT_NUMBER, chainId: CHAIN_ID, stateRoot: parent.stateRoot};
  const oldWord = '0x' + word(BASE_WORD | (100n << 160n));
  const newWord = '0x' + word(BASE_WORD | (50n << 160n));
  const intervention = {account: RULES, checkpoint, expectedOldWord: oldWord, mask: '0x' + word(LP_MASK), newWord, pool: POOL, slot: SLOT};
  const observationPlan = {accounts: [sender, ROUTER, RULES, MANAGER, TOKEN], nativeOrdinal: 1,
    storage: [{account: RULES, slot: SLOT}], subject: arrivals[1]};
  const transactionsRoot = trieRoot(raw);
  const gasUsed = 1_234_567;

  // One world: same block template, its own buyer output, fee and state root.
  const world = (name, output, feePips, stateRoot) => {
    const logs = [
      {address: MANAGER, topics: [topicOf('Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)'), POOL, pad(ROUTER)],
        data: '0x' + [-value, output, 2n ** 96n / 1000n, 10n ** 20n, -46_000n, BigInt(feePips)].map(word).join('')},
      {address: TOKEN, topics: [topicOf('Transfer(address,address,uint256)'), pad(MANAGER), pad(sender)], data: '0x' + word(output)},
    ];
    const receipts = [
      {type: '0x6a', root: '0x', status: '0x1', cumulativeGasUsed: '0x0', logsBloom: ZERO_BLOOM, logs: [],
        transactionHash: arrivals[0], transactionIndex: '0x0', gasUsed: '0x0'},
      {type: '0x2', root: '0x', status: '0x1', cumulativeGasUsed: q(gasUsed), logsBloom: bloom(logs), logs,
        transactionHash: arrivals[1], transactionIndex: '0x1', gasUsed: q(gasUsed)},
    ];
    const receiptsRoot = trieRoot(receipts.map(receiptBytes));
    const produced = header({parentHash: parent.hash, stateRoot, transactionsRoot, receiptsRoot,
      logsBloom: combinedBloom(receipts), number: PARENT_NUMBER + 1, gasUsed});
    let logIndex = 0;
    for (const r of receipts) {
      Object.assign(r, {blockHash: produced.hash, blockNumber: produced.number});
      for (const log of r.logs) Object.assign(log, {blockHash: produced.hash, blockNumber: produced.number,
        logIndex: q(logIndex++), removed: false, transactionHash: r.transactionHash, transactionIndex: r.transactionIndex});
    }
    const accounts = (spent) => [
      {address: sender, balance: (10n ** 18n - spent).toString(), codeHash: EMPTY_CODE_HASH, nonce: spent ? 1 : 0},
      ...[ROUTER, RULES, MANAGER, TOKEN].map((a) => ({address: a, balance: '0', codeHash: h32('code ' + a), nonce: 1})),
    ];
    const slotValue = name === 'ACTUAL' ? oldWord : newWord;
    const result = {
      blockHash: produced.hash, gasUsed, inputCommitment: label('input commitment'), matched: name === 'ACTUAL',
      observation: {
        afterBlockFinalizationBeforeCommit: {accounts: accounts(value), storage: [{key: {account: RULES, slot: SLOT}, value: slotValue}]},
        beforeFirstArrival: {accounts: accounts(0n), storage: [{key: {account: RULES, slot: SLOT}, value: slotValue}]},
        callBytes: (input.length - 2) / 2, complete: true, plan: observationPlan,
        subjectCalls: [{ancestorReverted: false, depth: 0, from: sender, gasUsed, input, kind: 241,
          nativeCallValue: value.toString(), output: '0x', parent: -1, reverted: false, to: ROUTER}],
      },
      producedHeader: {...produced, blobGasUsed: null, blockAccessListHash: null, excessBlobGas: null,
        parentBeaconBlockRoot: null, requestsHash: null, slotNumber: null, withdrawalsRoot: null},
      receipts, receiptsRoot, stateRoot, transactions: 2, witnessCommitment: label('witness commitment'), world: name,
    };
    if (name === 'BRANCH') {
      result.patch = {intervention, originalWitnessCommitment: result.witnessCommitment, originalWitnessUnchanged: true,
        semanticInitialWrites: 1, world: 'HYPOTHETICAL_CHECKPOINT_BRANCH'};
    }
    return {error: '', missingLookupAttempts: null, result};
  };

  const actual = world('ACTUAL', 10n ** 24n, 11000, h32('actual state'));
  const branch = world('BRANCH', 1_005_000n * 10n ** 18n, 7000, h32('branch state'));
  const target = actual.result.producedHeader;
  const plan = {
    arrivals, blockHash: target.hash, blockNumber: PARENT_NUMBER + 1, checkpoint,
    externalDelivery: 'SYNTHETIC_FIXTURE', inputCommitment: actual.result.inputCommitment, intervention,
    nativeOrdinal: 1, observation: observationPlan, packageSha256: label('package placeholder'),
    receiptsRoot: target.receiptsRoot, router: ROUTER, selection: 'SYNTHETIC_TEST_FIXTURE_NOT_CHAIN_DATA', sender,
    source: 'NIL_NO_HYDRATION', stateRoot: target.stateRoot, subject: arrivals[1], transactions: 2,
    witnessCommitment: actual.result.witnessCommitment,
  };
  const runtimePlan = {caseDescriptorSha256: label('case descriptor'), newValue: '50', plan, schema: PLAN_SCHEMA,
    semanticPlanCommitment: label('semantic plan')};
  const block = {...target, transactions: [
    {hash: arrivals[0]},
    {from: sender, hash: arrivals[1], input, to: ROUTER, value: q(value)},
  ]};
  for (const field of ['blobGasUsed', 'blockAccessListHash', 'excessBlobGas', 'parentBeaconBlockRoot', 'requestsHash', 'slotNumber', 'withdrawalsRoot']) delete block[field];
  const context = {block, chainId: CHAIN_ID, origin: 'SYNTHETIC_TEST_FIXTURE_NOT_CHAIN_DATA', parent, rawTransactions: raw, schema: CONTEXT_SCHEMA};

  const files = Object.fromEntries([['ACTUAL.json', actual], ['BRANCH.json', branch], ['CHAIN_CONTEXT.json', context],
    ['RUNTIME_PLAN.json', runtimePlan]].map(([name, value]) => [name, Buffer.from(stableJson(value))]));
  const pins = {
    files: Object.fromEntries(['ACTUAL.json', 'BRANCH.json', 'RUNTIME_PLAN.json'].map((n) => [n, sha256Hex(files[n])])),
    name: 'synthetic-lp50', schema: PINS_SCHEMA,
    source: 'Generated by sdk/verify-pack/synthetic-pack.mjs; synthetic test data, not a RHOOK result',
  };
  return {files, pins: Buffer.from(stableJson(pins)), trustedBlockHash: target.hash};
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv[2] !== '--write') {
    process.stderr.write('Usage: node sdk/verify-pack/synthetic-pack.mjs --write\n');
    process.exit(2);
  }
  const {files, pins, trustedBlockHash} = await buildSyntheticPack();
  fs.mkdirSync(SYNTHETIC_DIR, {recursive: true});
  for (const [name, bytes] of Object.entries(files)) fs.writeFileSync(path.join(SYNTHETIC_DIR, name), bytes);
  fs.writeFileSync(SYNTHETIC_PINS, pins);
  process.stdout.write(`Wrote ${SYNTHETIC_DIR} and pins. Synthetic trusted block hash: ${trustedBlockHash}\n`);
}
