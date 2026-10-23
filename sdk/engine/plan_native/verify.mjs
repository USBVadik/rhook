// Recorded-result verification only. This module neither launches nor emulates an EVM.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {keccak256} from '../adapters/hookr-case/primitives.mjs';
import {authenticateProof} from '../adapters/hookr-case/proof.mjs';
import {parseStrictEvidenceJson as parseStrictJson} from '../adapters/hookr-case/strict-json.mjs';
import {trieRoot, headerHash, bloom, receiptBytes} from './ethereum.mjs';

const require = createRequire(new URL('../adapters/hookr-case/package.json', import.meta.url));
const {parseTransaction, recoverTransactionAddress} = require('viem');
const sha = raw => createHash('sha256').update(raw).digest('hex');
const topic = s => keccak256('0x' + Buffer.from(s).toString('hex'));
const transfer = topic('Transfer(address,address,uint256)');
const swap = topic('Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)');
const fee = topic('HookFee(bytes32,address,uint256,uint256,uint256)');
const token = '0x3c022d43a9f826cd206c2ba60bc753d8b36185c4';
const manager = '0x8366a39cc670b4001a1121b8f6a443a643e40951';
const root = '0x89c9fb50d1f03192230ffb1c279bb6e7d3fe6acc';

export function readJson(file, maximum = 32 << 20) {
  if (file instanceof URL) file = fileURLToPath(file);
  file = path.resolve(file);
  for (let p = file; ; p = path.dirname(p)) {
    assert(!fs.lstatSync(p).isSymbolicLink(), 'SYMLINK_INPUT');
    if (p === path.dirname(p)) break;
  }
  const stat = fs.statSync(file);
  assert(stat.isFile() && stat.size <= maximum, 'INPUT_SIZE_OR_TYPE');
  const raw = fs.readFileSync(file);
  assert(raw.length <= maximum);
  return {raw, value: parseStrictJson(raw.toString('utf8'))};
}

export async function authenticatePackage(raw, plan) {
  assert.equal(sha(raw), plan.packageSha256, 'PACKAGE_SHA256');
  const p = parseStrictJson(raw.toString('utf8'));
  assert.deepEqual(p.checkpoint, plan.checkpoint);
  assert.equal(headerHash(p.parent), plan.checkpoint.blockHash);
  assert.equal(headerHash(p.block), plan.blockHash);
  assert.equal(p.parent.stateRoot, plan.checkpoint.stateRoot);
  assert.equal(p.block.parentHash, plan.checkpoint.blockHash);
  assert.equal(p.block.stateRoot, plan.stateRoot);
  assert.equal(p.block.receiptsRoot, plan.receiptsRoot);
  assert.equal(Number(BigInt(p.block.number)), plan.blockNumber);
  assert.equal(trieRoot(p.rawTransactions), p.block.transactionsRoot);
  assert.equal(p.rawTransactions.length, 7);
  assert.deepEqual(p.rawTransactions.map(keccak256), plan.arrivals);
  for (let i = 0; i < 7; i++) {
    const tx = p.block.transactions[i];
    assert.equal(tx.hash, plan.arrivals[i]);
    if (i !== 0) {
      const parsed = parseTransaction(p.rawTransactions[i]);
      assert.equal(parsed.chainId, plan.checkpoint.chainId);
      assert.equal((await recoverTransactionAddress({serializedTransaction: p.rawTransactions[i]})).toLowerCase(), tx.from.toLowerCase());
      assert.equal(parsed.to.toLowerCase(), tx.to.toLowerCase());
    }
  }
  assert.equal(plan.arrivals[3], plan.subject);
  assert.equal(p.block.transactions[3].from.toLowerCase(), plan.sender);
  assert.equal(p.block.transactions[3].to.toLowerCase(), plan.router);
  const nodes = new Map(p.state.map(raw => [keccak256(raw), raw]));
  const codes = new Map(p.codes.map(raw => [keccak256(raw), raw]));
  let rules;
  for (const item of p.proofs) {
    const verified = authenticateProof(plan.checkpoint.stateRoot, item.address, item.slots ?? [],
      {...item.proof, storageProof: item.proof.storageProof ?? []});
    for (const [hash, bytes] of verified.nodes) {
      if (nodes.has(hash)) assert.equal(nodes.get(hash), bytes);
      nodes.set(hash, bytes);
    }
    if (item.address === plan.intervention.account) rules = verified;
  }
  assert(rules, 'RULES_PROOF_REQUIRED');
  const slot = rules.resolutions.find(x => x.key === plan.intervention.slot);
  assert.equal(BigInt(slot.value), BigInt(plan.intervention.expectedOldWord));
  const rulesCode = '0x4b6d50b40981b8082f3ee5a7ebf57e48489f71c94c2a3b94032a1d1a382b515b';
  assert(codes.has(rulesCode), 'ACTUAL_RULES_CODE_BYTES_REQUIRED');
  assert.equal(keccak256(codes.get(rulesCode)), rulesCode);
  const base64 = map => Object.fromEntries([...map].sort(([a], [b]) => a.localeCompare(b))
    .map(([h, bytes]) => [h, Buffer.from(bytes.slice(2), 'hex').toString('base64')]));
  const witness = {checkpoint: p.checkpoint, nodes: base64(nodes), codes: base64(codes), attempts: null};
  assert.equal(sha('rhook/native-prestate-witness/0.1\n' + JSON.stringify(witness)), plan.witnessCommitment);
  const old = BigInt(plan.intervention.expectedOldWord), next = BigInt(plan.intervention.newWord);
  const mask = BigInt(plan.intervention.mask);
  assert.equal(mask, 65535n << 160n);
  assert.equal((old >> 160n) & 65535n, 100n);
  assert.equal((old ^ next) & ~mask, 0n);
  return p;
}

export function verifyWorld(record, name, plan, pkg) {
  assert.equal(record.error, '');
  assert(record.missingLookupAttempts == null || record.missingLookupAttempts.length === 0);
  const r = record.result;
  assert.equal(r.world, name); assert.equal(r.transactions, 7);
  assert.equal(r.inputCommitment, plan.inputCommitment);
  assert.equal(r.witnessCommitment, plan.witnessCommitment);
  assert.equal(headerHash(r.producedHeader), r.blockHash);
  assert.equal(r.producedHeader.hash, r.blockHash);
  assert.equal(r.producedHeader.stateRoot, r.stateRoot);
  assert.equal(r.producedHeader.receiptsRoot, r.receiptsRoot);
  assert.equal(r.producedHeader.transactionsRoot, pkg.block.transactionsRoot);
  assert.equal(r.producedHeader.parentHash, plan.checkpoint.blockHash);
  assert.equal(Number(BigInt(r.producedHeader.number)), plan.blockNumber);
  for (const field of ['sha3Uncles', 'miner', 'difficulty', 'gasLimit', 'timestamp', 'extraData', 'mixHash', 'nonce', 'baseFeePerGas'])
    assert.deepEqual(r.producedHeader[field], pkg.block[field]);
  assert.equal(r.receipts.length, 7);
  let cumulative = 0n, logIndex = 0; const combined = Buffer.alloc(256);
  for (const [i, receipt] of r.receipts.entries()) {
    assert.equal(receipt.transactionHash, plan.arrivals[i]);
    assert.equal(Number(BigInt(receipt.transactionIndex)), i);
    assert.equal(receipt.blockHash, r.blockHash);
    assert.equal(Number(BigInt(receipt.blockNumber)), plan.blockNumber);
    assert([0n, 1n].includes(BigInt(receipt.status)));
    assert.equal(bloom(receipt.logs ?? []), receipt.logsBloom);
    cumulative += BigInt(receipt.gasUsed);
    assert.equal(BigInt(receipt.cumulativeGasUsed), cumulative);
    const rb = Buffer.from(receipt.logsBloom.slice(2), 'hex');
    for (let j = 0; j < 256; j++) combined[j] |= rb[j];
    for (const log of receipt.logs ?? []) {
      assert.equal(log.transactionHash, receipt.transactionHash);
      assert.equal(Number(BigInt(log.transactionIndex)), i);
      assert.equal(Number(BigInt(log.blockNumber)), plan.blockNumber);
      assert.equal(log.blockHash, r.blockHash); assert.equal(log.removed, false);
      assert.equal(Number(BigInt(log.logIndex)), logIndex++);
    }
    if (BigInt(receipt.status) === 0n) assert.equal((receipt.logs ?? []).length, 0);
  }
  assert.equal(combined.toString('hex'), r.producedHeader.logsBloom.slice(2));
  assert.equal(cumulative, BigInt(r.gasUsed));
  assert.equal(cumulative, BigInt(r.producedHeader.gasUsed));
  assert.equal(trieRoot(r.receipts.map(receiptBytes)), r.receiptsRoot);
  const obs = r.observation;
  assert.equal(obs.complete, true); assert.deepEqual(obs.plan, plan.observation);
  for (const phase of ['beforeFirstArrival', 'afterBlockFinalizationBeforeCommit']) {
    const s = obs[phase];
    assert.deepEqual(s.accounts.map(x => x.address), plan.observation.accounts);
    assert.equal(s.storage.length, 1);
    assert.deepEqual(s.storage[0].key, plan.observation.storage[0]);
    assert.equal(s.storage[0].value, name === 'ACTUAL' ? plan.intervention.expectedOldWord : plan.intervention.newWord);
  }
  assert(obs.subjectCalls.length > 0);
  const first = obs.subjectCalls[0], tx = pkg.block.transactions[3];
  assert.equal(first.from, plan.sender); assert.equal(first.to, plan.router);
  assert.equal(first.input, tx.input); assert.equal(BigInt(first.nativeCallValue), BigInt(tx.value));
  for (const [i, call] of obs.subjectCalls.entries()) {
    assert(Number.isInteger(call.depth) && call.depth >= 0);
    if (i === 0) { assert.equal(call.parent, -1); assert.equal(call.depth, 0); }
    else { assert(Number.isInteger(call.parent) && call.parent >= 0 && call.parent < i);
      assert.equal(call.depth, obs.subjectCalls[call.parent].depth + 1); }
  }
  if (name === 'ACTUAL') {
    assert.equal(r.matched, true); assert(r.patch == null);
    for (const k of ['stateRoot', 'receiptsRoot', 'blockHash']) assert.equal(r[k], plan[k]);
  } else {
    assert.deepEqual(r.patch.intervention, plan.intervention);
    assert.equal(r.patch.semanticInitialWrites, 1);
    assert.equal(r.patch.originalWitnessUnchanged, true);
    assert.equal(r.patch.originalWitnessCommitment, plan.witnessCommitment);
    assert.equal(r.patch.world, 'HYPOTHETICAL_CHECKPOINT_BRANCH');
    assert.equal(r.matched, r.stateRoot === plan.stateRoot && r.receiptsRoot === plan.receiptsRoot && r.blockHash === plan.blockHash);
  }
  return r;
}

function words(data, count) {
  assert(new RegExp('^0x[0-9a-f]{' + count * 64 + '}$').test(data), 'EVENT_LAYOUT');
  return Array.from({length: count}, (_, i) => BigInt('0x' + data.slice(2 + i * 64, 66 + i * 64)));
}
function address(word) { assert(/^0x0{24}[0-9a-f]{40}$/.test(word)); return '0x' + word.slice(-40); }
function signed(n, width) {
  const value = BigInt.asIntN(width, n);
  assert.equal(BigInt.asUintN(256, value), n, 'ABI_SIGN_EXTENSION'); return value.toString();
}

export function economics(result, plan) {
  const receipt = result.receipts[3]; const transfers = [], swaps = [], fees = [], unclassified = [];
  const nets = {};
  for (const log of receipt.logs ?? []) {
    if (log.topics[0] === transfer && log.topics.length === 3) {
      const from = address(log.topics[1]), to = address(log.topics[2]);
      const [value] = words(log.data, 1); const t = log.address;
      nets[t] ??= {}; nets[t][from] = (nets[t][from] ?? 0n) - value; nets[t][to] = (nets[t][to] ?? 0n) + value;
      transfers.push({token: t, from, to, value: value.toString(), logIndex: log.logIndex});
    } else if (log.address === manager && log.topics[0] === swap) {
      assert.equal(log.topics.length, 3); const w = words(log.data, 6);
      assert(w[2] < (1n << 160n) && w[3] < (1n << 128n) && w[5] < (1n << 24n));
      swaps.push({pool: log.topics[1], sender: address(log.topics[2]), amount0: signed(w[0], 128),
        amount1: signed(w[1], 128), feePips: w[5].toString(), tick: signed(w[4], 24), logIndex: log.logIndex});
    } else if (log.address === root && log.topics[0] === fee) {
      assert.equal(log.topics.length, 3); const w = words(log.data, 3);
      fees.push({pool: log.topics[1], currency: address(log.topics[2]), earnedWei: String(w[0]),
        refundWei: String(w[1]), burnedSubjectBaseUnits: String(w[2]), logIndex: log.logIndex});
    } else unclassified.push(log);
  }
  const outer = swaps.filter(s => s.pool === plan.intervention.pool && s.sender === plan.router);
  const success = BigInt(receipt.status) === 1n;
  const before = result.observation.beforeFirstArrival, after = result.observation.afterBlockFinalizationBeforeCommit;
  const accountDeltas = before.accounts.map((a, i) => ({address: a.address,
    nativeBalanceDeltaWei: (BigInt(after.accounts[i].balance) - BigInt(a.balance)).toString(),
    nonceDelta: after.accounts[i].nonce - a.nonce, beforeCodeHash: a.codeHash, afterCodeHash: after.accounts[i].codeHash}));
  return {subjectStatus: success ? 'SUCCESS' : 'REVERT', subjectGasUsed: BigInt(receipt.gasUsed).toString(),
    buyerRhookTransferNetBaseUnits: (nets[token]?.[plan.sender] ?? 0n).toString(),
    buyerOutputMeaning: 'ERC20_TRANSFER_EVENT_NET_NOT_TOKEN_STORAGE_BALANCE',
    outerSwap: outer.length === 1 ? outer[0] : null,
    outerSwapStatus: outer.length === 1 ? 'OBSERVED' : success ? 'UNRESOLVED_EVENT_CARDINALITY' : 'NOT_APPLICABLE',
    transfers, swaps, hookFeeEvents: fees, unclassifiedEvents: unclassified,
    transferNets: Object.fromEntries(Object.entries(nets).map(([t, a]) => [t, Object.fromEntries(Object.entries(a).map(([k, v]) => [k, String(v)]))])),
    accountDeltas, observedStorageBefore: before.storage, observedStorageAfter: after.storage,
    stateObservation: result.observation, economicAssurance: 'UNRESOLVED'};
}

export function verifyPair(actual, branch, plan, pkg) {
  const a = verifyWorld(actual, 'ACTUAL', plan, pkg), b = verifyWorld(branch, 'BRANCH', plan, pkg);
  assert.deepEqual(a.observation.beforeFirstArrival.accounts, b.observation.beforeFirstArrival.accounts);
  const ea = economics(a, plan), eb = economics(b, plan);
  return {status: 'RECORDED_PAIR_INTEGRITY_PASS', worlds: {ACTUAL: ea, BRANCH: eb},
    buyerRhookTransferNetDeltaBaseUnits: (BigInt(eb.buyerRhookTransferNetBaseUnits) - BigInt(ea.buyerRhookTransferNetBaseUnits)).toString(),
    subjectGasDelta: (BigInt(eb.subjectGasUsed) - BigInt(ea.subjectGasUsed)).toString(),
    economicAssurance: 'UNRESOLVED', heterogeneousAgreement: 'NOT_EVALUATED', qualifiedClaims: 0,
    limitation: 'Hashes, receipts and recorded observations are checked. Final state roots and call/state traces are not independently re-executed or proven by this verifier.'};
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  assert.equal(process.argv.length, 4, 'USAGE: verify.mjs PACKAGE RUNTIME');
  const planFile = readJson(new URL('./plan.json', import.meta.url));
  assert.equal(sha(planFile.raw), '61a37caca6dad2282d2488fe8e64cf3e1d5157697592362464d00b34a0d5078e');
  const pkg = await authenticatePackage(readJson(process.argv[2]).raw, planFile.value);
  const rt = path.resolve(process.argv[3]);
  const result = verifyPair(readJson(path.join(rt, 'ACTUAL.json')).value,
    readJson(path.join(rt, 'BRANCH.json')).value, planFile.value, pkg);
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}
