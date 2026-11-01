// RHOOK verify-pack/0.1: offline check of a recorded Hookr ACTUAL/BRANCH pair without the witness.
//
// Nothing is re-executed. The checks reuse the accepted recorded-world verifier (verifyWorld/verifyPair
// in rhook_alpha/cases/adapters/hookr.mjs) and replace its witness package with a small public chain
// context that must hash to the block the user trusts. README.md in this directory states what each
// level does and does not establish.
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {isDeepStrictEqual} from 'node:util';
import {keccak256} from '../engine/adapters/hookr-case/primitives.mjs';
import {parseStrictEvidenceJson} from '../engine/adapters/hookr-case/strict-json.mjs';
import {headerHash, trieRoot} from '../engine/plan_native/ethereum.mjs';
import {authenticatePackage, verifyPair, verifyWorld} from '../rhook_alpha/cases/adapters/hookr.mjs';

const require = createRequire(new URL('../engine/adapters/hookr-case/package.json', import.meta.url));
const {parseTransaction, recoverTransactionAddress} = require('viem');

export const TOOL = 'rhook-verify-pack/0.1';
export const REPORT_SCHEMA = 'rhook/verify-pack-report/0.1';
export const CONTEXT_SCHEMA = 'rhook/verify-pack-chain-context/0.1';
export const PINS_SCHEMA = 'rhook/verify-pack-pins/0.1';
export const PLAN_SCHEMA = 'rhook/hookr-runtime-plan/0.2';
export const PACK_FILES = Object.freeze(['ACTUAL.json', 'BRANCH.json', 'CHAIN_CONTEXT.json', 'RUNTIME_PLAN.json']);
const PINNED_RECORDS = ['ACTUAL.json', 'BRANCH.json', 'RUNTIME_PLAN.json'];
const MAX_FILE_BYTES = 8 << 20;
const LP_MASK = 65535n << 160n;
const HASH = /^0x[0-9a-f]{64}$/;
const SHA256 = /^[0-9a-f]{64}$/;

// Boundaries that hold for every report, whatever the checks found.
export const LIMITATIONS = Object.freeze({
  prestateAuthentication: 'NOT_PERFORMED',
  nativeReexecution: 'NOT_PERFORMED',
  heterogeneousAgreement: 'NOT_EVALUATED',
  economicAssurance: 'UNRESOLVED',
  qualifiedClaims: 0,
});

const PLAN_KEYS = ['arrivals', 'blockHash', 'blockNumber', 'checkpoint', 'externalDelivery', 'inputCommitment',
  'intervention', 'nativeOrdinal', 'observation', 'packageSha256', 'receiptsRoot', 'router', 'selection', 'sender',
  'source', 'stateRoot', 'subject', 'transactions', 'witnessCommitment'];
const RUNTIME_PLAN_KEYS = ['caseDescriptorSha256', 'newValue', 'plan', 'schema', 'semanticPlanCommitment'];
const INTERVENTION_KEYS = ['account', 'checkpoint', 'expectedOldWord', 'mask', 'newWord', 'pool', 'slot'];
const CHECKPOINT_KEYS = ['blockHash', 'blockNumber', 'chainId', 'stateRoot'];
const WORLD_RESULT_KEYS = ['blockHash', 'gasUsed', 'inputCommitment', 'matched', 'observation', 'producedHeader',
  'receipts', 'receiptsRoot', 'stateRoot', 'transactions', 'witnessCommitment', 'world'];
const CONTEXT_KEYS = ['block', 'chainId', 'origin', 'parent', 'rawTransactions', 'schema'];
// Exactly the fields headerHash() commits to, plus the hash itself. Anything else would be unbound.
const HEADER_FIELDS = ['baseFeePerGas', 'difficulty', 'extraData', 'gasLimit', 'gasUsed', 'hash', 'logsBloom', 'miner',
  'mixHash', 'nonce', 'number', 'parentHash', 'receiptsRoot', 'sha3Uncles', 'stateRoot', 'timestamp', 'transactionsRoot'];
const QUANTITY_FIELDS = ['baseFeePerGas', 'difficulty', 'gasLimit', 'gasUsed', 'number', 'timestamp'];
const DATA_FIELDS = {extraData: null, hash: 32, logsBloom: 256, miner: 20, mixHash: 32, nonce: 8, parentHash: 32,
  receiptsRoot: 32, sha3Uncles: 32, stateRoot: 32, transactionsRoot: 32};
// The Nitro internal transaction is bound only by its hash; signed transactions also by these fields.
const SYSTEM_TX_FIELDS = ['hash'];
const SIGNED_TX_FIELDS = ['from', 'hash', 'input', 'to', 'value'];
const PINS_KEYS = ['files', 'name', 'schema', 'source'];

const LEVEL_TEXT = Object.freeze({
  artifactIntegrity: {
    establishes: 'The pinned files are byte-identical to hashes published outside this pack.',
    doesNotEstablish: 'Anything about their content. A hash inside the pack is not an anchor.',
  },
  chainContext: {
    establishes: 'The public parent and target headers hash to the plan checkpoint and target block, and the signed transactions match the transactions root and the plan arrivals.',
    doesNotEstablish: 'That the target block is canonical, unless a trusted block hash is supplied.',
  },
  canonicalActual: {
    covered: [
      'receipt type, status, cumulativeGasUsed, logsBloom and logs (committed by the receipts root)',
      'per-receipt gasUsed (determined by consecutive cumulativeGasUsed values)',
      'stateRoot, receiptsRoot and blockHash',
      'produced header fields compared with the target header',
    ],
    notCovered: [
      'observation.beforeFirstArrival and observation.afterBlockFinalizationBeforeCommit: storage values, balances, nonces and code hashes, including the RulesConfig value the intervention starts from',
      'observation.subjectCalls: the recorded call trace',
      'receipt fields outside the receipts trie: gasUsedForL1, multiGasUsed, effectiveGasPrice, contractAddress',
      'inputCommitment and witnessCommitment: compared with the plan, not recomputed',
    ],
    establishes: 'The recorded ACTUAL receipts recompute to the receipts root of the anchored block, and the recorded stateRoot and blockHash equal that block.',
    doesNotEstablish: 'That RHOOK computed ACTUAL itself; the recorded values equal canonical chain data and could have been copied from it. Recorded observations (the RulesConfig value before the first arrival, call traces, balances) are engine records that no receipt commits to.',
  },
  recordedBranch: {
    establishes: 'BRANCH is internally consistent: receipts trie, blooms, gas sums, header hash, the declared intervention and the shared parent observation.',
    doesNotEstablish: 'That BRANCH is the correct EVM result. A self-consistent forgery passes this level; only native re-execution or an independent engine can test it.',
  },
});

class PackError extends Error {
  constructor(code, detail) {
    super(`${code}: ${detail}`);
    this.code = code;
    this.detail = detail;
  }
}

function check(ok, code, detail) {
  if (!ok) throw new PackError(code, detail);
}

function exactKeys(value, keys, code, label) {
  check(value !== null && typeof value === 'object' && !Array.isArray(value), code, `${label} must be an object`);
  check(isDeepStrictEqual(Object.keys(value).sort(), [...keys].sort()), code,
    `${label} keys must be exactly ${keys.join(', ')}`);
}

export const sha256Hex = (bytes) => createHash('sha256').update(bytes).digest('hex');

// Sorted keys, two-space indent, trailing newline: the same input always gives the same bytes.
export function stableJson(value) {
  const sort = (v) => {
    if (Array.isArray(v)) return v.map(sort);
    if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sort(v[k])]));
    return v;
  };
  return JSON.stringify(sort(value), null, 2) + '\n';
}

function parseJson(bytes, name) {
  try {
    return parseStrictEvidenceJson(bytes.toString('utf8'));
  } catch (error) {
    throw new PackError('MALFORMED_JSON', `${name}: ${error.message}`);
  }
}

/**
 * Relative change of the buyer's Transfer-event net, truncated to 10 decimals.
 * Defined only when the ACTUAL net is positive: a zero or negative net (the buyer sent more of the
 * token than it received in the subject receipt) has no meaningful "percent more output", so null.
 */
export function percentChange(delta, base) {
  if (base <= 0n) return null;
  const sign = delta < 0n ? '-' : '+';
  const scaled = ((delta < 0n ? -delta : delta) * 10n ** 12n) / base;
  return `${sign}${scaled / 10n ** 10n}.${(scaled % 10n ** 10n).toString().padStart(10, '0')}`;
}

const lpBits = (word) => (BigInt(word) >> 160n) & 65535n;

// --- Profile: the recorded Hookr LP Rewards pair (rhook/hookr-runtime-plan/0.2) ------------------------

function checkProfile(runtimePlan, actual, branch) {
  exactKeys(runtimePlan, RUNTIME_PLAN_KEYS, 'INCOMPATIBLE_PROFILE', 'RUNTIME_PLAN.json');
  check(runtimePlan.schema === PLAN_SCHEMA, 'INCOMPATIBLE_PROFILE', `plan schema must be ${PLAN_SCHEMA}`);
  const plan = runtimePlan.plan;
  exactKeys(plan, PLAN_KEYS, 'INCOMPATIBLE_PROFILE', 'plan');
  exactKeys(plan.checkpoint, CHECKPOINT_KEYS, 'INCOMPATIBLE_PROFILE', 'plan.checkpoint');
  check(plan.checkpoint.chainId === 4663, 'INCOMPATIBLE_PROFILE', 'only Robinhood Chain (4663) is supported');
  check(plan.source === 'NIL_NO_HYDRATION', 'INCOMPATIBLE_PROFILE', 'plan must declare offline nil-Source replay');
  check(plan.blockNumber === plan.checkpoint.blockNumber + 1, 'INCOMPATIBLE_PROFILE', 'target must be the block after the checkpoint');
  check(Array.isArray(plan.arrivals) && plan.arrivals.length === plan.transactions && plan.transactions > 0,
    'INCOMPATIBLE_PROFILE', 'arrivals must list every transaction');
  check(plan.arrivals.every((h) => HASH.test(h)), 'INCOMPATIBLE_PROFILE', 'arrivals must be lowercase 32-byte hashes');
  for (const field of ['blockHash', 'stateRoot', 'receiptsRoot', 'subject']) {
    check(HASH.test(plan[field]), 'INCOMPATIBLE_PROFILE', `plan.${field} must be a lowercase 32-byte hash`);
  }
  check(Number.isSafeInteger(plan.nativeOrdinal) && plan.nativeOrdinal > 0 && plan.nativeOrdinal < plan.transactions,
    'INCOMPATIBLE_PROFILE', 'subject must be a user transaction inside the block');
  check(plan.arrivals[plan.nativeOrdinal] === plan.subject && plan.observation?.subject === plan.subject
    && plan.observation?.nativeOrdinal === plan.nativeOrdinal, 'INCOMPATIBLE_PROFILE', 'subject is not linked consistently');

  const i = plan.intervention;
  exactKeys(i, INTERVENTION_KEYS, 'UNSUPPORTED_INTERVENTION', 'plan.intervention');
  check(isDeepStrictEqual(i.checkpoint, plan.checkpoint), 'UNSUPPORTED_INTERVENTION', 'intervention checkpoint differs from plan checkpoint');
  for (const field of ['expectedOldWord', 'newWord', 'mask', 'pool', 'slot']) {
    check(HASH.test(i[field]), 'UNSUPPORTED_INTERVENTION', `intervention.${field} must be a lowercase 32-byte word`);
  }
  check(BigInt(i.mask) === LP_MASK, 'UNSUPPORTED_INTERVENTION', 'only the RulesConfig lpBps field (bits 160-175) is supported');
  check(((BigInt(i.expectedOldWord) ^ BigInt(i.newWord)) & ~LP_MASK) === 0n, 'UNSUPPORTED_INTERVENTION',
    'intervention changes bits outside lpBps');
  const lpBefore = lpBits(i.expectedOldWord), lpAfter = lpBits(i.newWord);
  check(lpBefore <= 10000n && lpAfter <= 99n, 'UNSUPPORTED_INTERVENTION', 'lpBps values are outside the supported range');
  // The accepted runtime plan format stores newValue as a decimal string.
  check(runtimePlan.newValue === lpAfter.toString(), 'UNSUPPORTED_INTERVENTION', 'newValue does not match the new lpBps bits');
  check(isDeepStrictEqual(plan.observation.storage, [{account: i.account, slot: i.slot}]), 'UNSUPPORTED_INTERVENTION',
    'observed storage must be exactly the intervened slot');

  for (const [name, record] of [['ACTUAL.json', actual], ['BRANCH.json', branch]]) {
    exactKeys(record, ['error', 'missingLookupAttempts', 'result'], 'INCOMPATIBLE_PROFILE', name);
    const keys = name === 'BRANCH.json' ? [...WORLD_RESULT_KEYS, 'patch'] : WORLD_RESULT_KEYS;
    exactKeys(record.result, keys, 'INCOMPATIBLE_PROFILE', `${name} result`);
  }
  return {plan, lpBefore, lpAfter};
}

// --- Chain context: public headers and transactions, bound to the plan ------------------------------
//
// This is the witness-free part of authenticatePackage() in hookr.mjs. The package there is trusted
// through its pinned SHA-256; this context is trusted only through the header hashes, so the signed
// transaction bytes are additionally bound to the transaction fields that verifyWorld() reads.

function canonicalHeader(header, label, extra = []) {
  exactKeys(header, [...HEADER_FIELDS, ...extra], 'CHAIN_CONTEXT_SHAPE', label);
  for (const field of QUANTITY_FIELDS) {
    check(typeof header[field] === 'string' && /^0x(?:0|[1-9a-f][0-9a-f]*)$/.test(header[field]), 'CHAIN_CONTEXT_SHAPE',
      `${label}.${field} must be a canonical lowercase quantity`);
  }
  for (const [field, size] of Object.entries(DATA_FIELDS)) {
    const value = header[field];
    check(typeof value === 'string' && /^0x(?:[0-9a-f]{2})*$/.test(value) && (size === null || value.length === 2 + 2 * size),
      'CHAIN_CONTEXT_SHAPE', `${label}.${field} must be lowercase hex${size === null ? '' : ` of ${size} bytes`}`);
  }
}

export async function authenticateChainContext(context, plan) {
  exactKeys(context, CONTEXT_KEYS, 'CHAIN_CONTEXT_SHAPE', 'CHAIN_CONTEXT.json');
  check(context.schema === CONTEXT_SCHEMA, 'CHAIN_CONTEXT_SHAPE', `schema must be ${CONTEXT_SCHEMA}`);
  check(typeof context.origin === 'string' && context.origin.length <= 200, 'CHAIN_CONTEXT_SHAPE', 'origin must be a short label');
  check(context.chainId === plan.checkpoint.chainId, 'CHAIN_CONTEXT_MISMATCH', 'chain id differs from the plan');
  const {parent, block, rawTransactions: raw} = context;
  canonicalHeader(parent, 'parent');
  canonicalHeader(block, 'block', ['transactions']);
  check(Array.isArray(block.transactions), 'CHAIN_CONTEXT_SHAPE', 'block.transactions must be an array');
  block.transactions.forEach((tx, i) => exactKeys(tx, i === 0 ? SYSTEM_TX_FIELDS : SIGNED_TX_FIELDS, 'CHAIN_CONTEXT_SHAPE',
    `block.transactions[${i}]`));

  const parentHash = headerHash(parent);
  check(parentHash === plan.checkpoint.blockHash, 'CHAIN_CONTEXT_MISMATCH', 'parent header does not hash to the plan checkpoint');
  check(parent.hash === parentHash, 'CHAIN_CONTEXT_MISMATCH', 'parent.hash field disagrees with the header');
  check(parent.stateRoot === plan.checkpoint.stateRoot, 'CHAIN_CONTEXT_MISMATCH', 'parent stateRoot differs from the plan checkpoint');
  check(Number(BigInt(parent.number)) === plan.checkpoint.blockNumber, 'CHAIN_CONTEXT_MISMATCH', 'parent number differs');

  const blockHash = headerHash(block);
  check(blockHash === plan.blockHash, 'CHAIN_CONTEXT_MISMATCH', 'target header does not hash to the plan block hash');
  check(block.hash === blockHash, 'CHAIN_CONTEXT_MISMATCH', 'block.hash field disagrees with the header');
  check(block.parentHash === parentHash, 'CHAIN_CONTEXT_MISMATCH', 'target header does not follow the parent');
  check(block.stateRoot === plan.stateRoot && block.receiptsRoot === plan.receiptsRoot, 'CHAIN_CONTEXT_MISMATCH',
    'target roots differ from the plan');
  check(Number(BigInt(block.number)) === plan.blockNumber, 'CHAIN_CONTEXT_MISMATCH', 'target number differs');

  check(Array.isArray(raw) && raw.length === plan.transactions && Array.isArray(block.transactions)
    && block.transactions.length === plan.transactions, 'CHAIN_CONTEXT_MISMATCH', 'transaction count differs from the plan');
  check(raw.every((r) => typeof r === 'string' && /^0x(?:[0-9a-f]{2})+$/.test(r)), 'CHAIN_CONTEXT_SHAPE', 'raw transactions must be lowercase hex');
  check(trieRoot(raw) === block.transactionsRoot, 'CHAIN_CONTEXT_MISMATCH', 'raw transactions do not match the transactions root');
  check(isDeepStrictEqual(raw.map((r) => keccak256(r)), plan.arrivals), 'CHAIN_CONTEXT_MISMATCH', 'transaction hashes differ from the plan arrivals');

  for (let i = 0; i < raw.length; i++) {
    const tx = block.transactions[i];
    check(tx && tx.hash === plan.arrivals[i], 'CHAIN_CONTEXT_MISMATCH', `transaction ${i} hash differs`);
    // Arrival 0 is the Nitro internal transaction: unsigned, bound only by its hash and the trie.
    if (i === 0) continue;
    let parsed, from;
    try {
      parsed = parseTransaction(raw[i]);
      from = (await recoverTransactionAddress({serializedTransaction: raw[i]})).toLowerCase();
    } catch (error) {
      throw new PackError('CHAIN_CONTEXT_MISMATCH', `transaction ${i} does not decode: ${error.shortMessage ?? error.message}`);
    }
    check(parsed.chainId === plan.checkpoint.chainId, 'CHAIN_CONTEXT_MISMATCH', `transaction ${i} chain id differs`);
    check(from === String(tx.from).toLowerCase(), 'CHAIN_CONTEXT_MISMATCH', `transaction ${i} signer differs from its from field`);
    const lower = (v) => (v == null ? null : String(v).toLowerCase());
    check(lower(parsed.to) === lower(tx.to), 'CHAIN_CONTEXT_MISMATCH', `transaction ${i} recipient differs`);
    check(lower(parsed.data ?? '0x') === lower(tx.input), 'CHAIN_CONTEXT_MISMATCH', `transaction ${i} input differs from the signed bytes`);
    check((parsed.value ?? 0n) === BigInt(tx.value), 'CHAIN_CONTEXT_MISMATCH', `transaction ${i} value differs from the signed bytes`);
  }
  const subject = block.transactions[plan.nativeOrdinal];
  check(String(subject.from).toLowerCase() === plan.sender && String(subject.to).toLowerCase() === plan.router,
    'CHAIN_CONTEXT_MISMATCH', 'subject transaction sender or router differs from the plan');
  return {block};
}

// --- Report -----------------------------------------------------------------------------------------

function cleanMessage(error) {
  return String(error.message).replace(/\s+/g, ' ').trim().slice(0, 300);
}

async function stage(report, key, fn) {
  if (report.failure) {
    report.levels[key] = {status: 'NOT_EVALUATED_AFTER_FAILURE'};
    return null;
  }
  try {
    return await fn();
  } catch (error) {
    const code = error instanceof PackError ? error.code : 'RECORD_CHECK_FAILED';
    const detail = cleanMessage(error instanceof PackError ? {message: error.detail} : error);
    report.failure = {code, detail, level: key};
    report.levels[key] = {status: 'FAIL', code};
    return null;
  }
}

function validatePins(pins) {
  exactKeys(pins, PINS_KEYS, 'PINS_SHAPE', 'pins');
  check(pins.schema === PINS_SCHEMA, 'PINS_SHAPE', `pins schema must be ${PINS_SCHEMA}`);
  check(typeof pins.name === 'string' && typeof pins.source === 'string', 'PINS_SHAPE', 'pins need a name and a source');
  check(pins.files && typeof pins.files === 'object' && !Array.isArray(pins.files), 'PINS_SHAPE', 'pins.files must be an object');
  for (const [name, value] of Object.entries(pins.files)) {
    check(PACK_FILES.includes(name), 'PINS_SHAPE', `unknown pinned file ${name}`);
    check(SHA256.test(value), 'PINS_SHAPE', `${name} pin must be lowercase SHA-256 hex`);
  }
  for (const name of PINNED_RECORDS) check(name in pins.files, 'PINS_SHAPE', `pins must cover ${name}`);
}

/**
 * Verify a pack given as in-memory file bytes.
 * @param {object} input
 * @param {Record<string, Buffer>} input.files   Pack files by name (see PACK_FILES).
 * @param {object|null} [input.pins]           Parsed pins published outside the pack, or null.
 * @param {string|null} [input.trustedBlockHash] Target block hash obtained independently, or null.
 * @returns {Promise<object>} Deterministic report (schema rhook/verify-pack-report/0.1).
 */
export async function verifyPack({files, pins = null, trustedBlockHash = null}) {
  const report = {
    // Both anchors are needed before a result counts as tied to the published RHOOK result and the chain.
    anchoring: {complete: false, externalPins: 'NOT_SUPPLIED', trustedBlock: 'NOT_SUPPLIED', trustedBlockHash: null},
    case: null,
    economics: null,
    failure: null,
    inputs: {},
    levels: {},
    limitations: {...LIMITATIONS},
    outcome: 'CHECK_FAILED',
    pins: pins && typeof pins === 'object' ? {name: pins.name ?? null, source: pins.source ?? null} : null,
    reexecution: 'NONE',
    schema: REPORT_SCHEMA,
    tool: TOOL,
  };
  let records;

  await stage(report, 'artifactIntegrity', async () => {
    const missing = PACK_FILES.filter((name) => !(files && Buffer.isBuffer(files[name])));
    check(missing.length === 0, 'INCOMPLETE_PACK', `missing ${missing.join(', ')}`);
    for (const name of PACK_FILES) {
      check(files[name].length <= MAX_FILE_BYTES, 'FILE_TOO_LARGE', `${name} exceeds ${MAX_FILE_BYTES} bytes`);
      report.inputs[name] = {bytes: files[name].length, pinnedSha256: null, sha256: sha256Hex(files[name]), status: 'NOT_PINNED'};
    }
    if (pins !== null) {
      validatePins(pins);
      for (const [name, expected] of Object.entries(pins.files)) {
        report.inputs[name].pinnedSha256 = expected;
        report.inputs[name].status = report.inputs[name].sha256 === expected ? 'MATCH' : 'MISMATCH';
      }
      const bad = Object.keys(pins.files).filter((name) => report.inputs[name].status === 'MISMATCH');
      report.anchoring.externalPins = bad.length === 0 ? 'MATCH' : 'MISMATCH';
      check(bad.length === 0, 'PINNED_HASH_MISMATCH', `differs from external pins: ${bad.join(', ')}`);
    }
    records = Object.fromEntries(PACK_FILES.map((name) => [name, parseJson(files[name], name)]));
    report.levels.artifactIntegrity = {
      ...LEVEL_TEXT.artifactIntegrity,
      status: pins === null ? 'NOT_ANCHORED_NO_EXTERNAL_PINS' : 'MATCH_EXTERNAL_PINS',
    };
  });

  let profile;
  await stage(report, 'profile', async () => {
    profile = checkProfile(records['RUNTIME_PLAN.json'], records['ACTUAL.json'], records['BRANCH.json']);
    const {plan, lpBefore, lpAfter} = profile;
    report.case = {
      arrivals: plan.transactions,
      chainId: plan.checkpoint.chainId,
      checkpointBlock: plan.checkpoint.blockNumber,
      intervention: {account: plan.intervention.account, field: 'RulesConfig.lpBps', from: Number(lpBefore),
        // Without the witness, the starting value is what the plan and the recorded observation say.
        fromBasis: 'DECLARED_BY_PLAN_NOT_AUTHENTICATED_WITHOUT_WITNESS',
        pool: plan.intervention.pool, slot: plan.intervention.slot, to: Number(lpAfter)},
      subjectOrdinal: plan.nativeOrdinal,
      subjectTransaction: plan.subject,
      targetBlock: plan.blockNumber,
      targetBlockHash: plan.blockHash,
    };
    report.levels.profile = {status: 'SUPPORTED', profile: PLAN_SCHEMA};
  });

  let context;
  await stage(report, 'chainContext', async () => {
    context = await authenticateChainContext(records['CHAIN_CONTEXT.json'], profile.plan);
    if (trustedBlockHash !== null) {
      const trusted = String(trustedBlockHash).toLowerCase();
      check(HASH.test(trusted), 'TRUSTED_BLOCK_HASH_FORMAT', 'trusted block hash must be 0x followed by 64 hex digits');
      report.anchoring.trustedBlockHash = trusted;
      report.anchoring.trustedBlock = trusted === profile.plan.blockHash ? 'MATCH' : 'MISMATCH';
      check(trusted === profile.plan.blockHash, 'TRUSTED_BLOCK_HASH_MISMATCH',
        `pack describes block ${profile.plan.blockHash}, trusted hash is ${trusted}`);
    }
    const anchored = report.anchoring.trustedBlock === 'MATCH';
    if (report.inputs['CHAIN_CONTEXT.json'].status === 'NOT_PINNED' && anchored) {
      report.inputs['CHAIN_CONTEXT.json'].status = 'NOT_PINNED_BOUND_BY_TRUSTED_BLOCK_HASH';
    }
    report.levels.chainContext = {
      ...LEVEL_TEXT.chainContext,
      declaredOrigin: records['CHAIN_CONTEXT.json'].origin,
      status: anchored ? 'BOUND_TO_TRUSTED_BLOCK' : 'BOUND_TO_PLAN_UNANCHORED',
    };
  });

  await stage(report, 'canonicalActual', async () => {
    verifyWorld(records['ACTUAL.json'], 'ACTUAL', profile.plan, context);
    report.levels.canonicalActual = {
      ...LEVEL_TEXT.canonicalActual,
      receiptsRecomputed: records['ACTUAL.json'].result.receipts.length,
      status: report.anchoring.trustedBlock === 'MATCH'
        ? 'ACTUAL_RECEIPTS_AND_ROOTS_MATCH_TRUSTED_BLOCK'
        : 'ACTUAL_RECEIPTS_AND_ROOTS_CONSISTENT_UNANCHORED',
    };
  });

  let pair;
  await stage(report, 'recordedBranch', async () => {
    verifyWorld(records['BRANCH.json'], 'BRANCH', profile.plan, context);
    pair = verifyPair(records['ACTUAL.json'], records['BRANCH.json'], profile.plan, context);
    report.levels.recordedBranch = {
      ...LEVEL_TEXT.recordedBranch,
      claim: 'RHOOK_ENGINE_CLAIM_NOT_REEXECUTED',
      matchesCanonicalBlock: records['BRANCH.json'].result.matched,
      status: 'RECORDED_BRANCH_INTERNALLY_CONSISTENT',
    };
  });

  if (!report.failure) {
    const world = (e, basis) => ({
      basis,
      buyerRhookTransferNetBaseUnits: e.buyerRhookTransferNetBaseUnits,
      outerSwapFeePips: e.outerSwap?.feePips ?? null,
      subjectGasUsed: e.subjectGasUsed,
      subjectStatus: e.subjectStatus,
    });
    const a = BigInt(pair.worlds.ACTUAL.buyerRhookTransferNetBaseUnits);
    const delta = BigInt(pair.buyerRhookTransferNetDeltaBaseUnits);
    report.economics = {
      actual: world(pair.worlds.ACTUAL, report.anchoring.trustedBlock === 'MATCH' ? 'CANONICAL_RECEIPTS_OF_TRUSTED_BLOCK' : 'RECORDED_RECEIPTS_UNANCHORED'),
      branch: world(pair.worlds.BRANCH, 'RHOOK_ENGINE_RECORD_NOT_REEXECUTED'),
      buyerRhookTransferNetDeltaBaseUnits: pair.buyerRhookTransferNetDeltaBaseUnits,
      buyerRhookTransferNetDeltaPercent: percentChange(delta, a),
      measure: 'ERC20_TRANSFER_EVENT_NET_IN_SUBJECT_RECEIPT_NOT_TOKEN_STORAGE_BALANCE',
      percentRounding: 'TRUNCATED_TO_10_DECIMALS',
      subjectGasDelta: pair.subjectGasDelta,
    };
    report.anchoring.complete = report.anchoring.externalPins === 'MATCH' && report.anchoring.trustedBlock === 'MATCH';
    // Even fully anchored, BRANCH is a recorded engine claim; the outcome names only what was checked.
    report.outcome = report.anchoring.complete
      ? 'RECORDED_PAIR_CONSISTENT_FULLY_ANCHORED'
      : 'RECORDED_PAIR_CONSISTENT_NOT_FULLY_ANCHORED';
  }
  return report;
}

/** CLI exit code: 0 only when both anchors matched; 3 when the checks passed without them; 1 on failure. */
export function exitCodeFor(report) {
  if (report.failure) return 1;
  return report.anchoring.complete ? 0 : 3;
}

// A pins file shipped inside the pack is the pack vouching for itself. Reject it by real path (so a
// symlinked parent directory does not hide it) and by file identity (so a hard link outside does not).
// This cannot prove that a file elsewhere is independent; the user still compares it with the source.
function checkPinsOutsideBundle(pinsFile, pinsStat, directory) {
  const bundle = fs.realpathSync(directory);
  const real = fs.realpathSync(pinsFile);
  check(real !== bundle && !real.startsWith(bundle + path.sep), 'PINS_INSIDE_BUNDLE',
    'the pins file must come from outside the bundle being verified');
  const pending = [bundle];
  let seen = 0;
  while (pending.length) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, {withFileTypes: true})) {
      check(++seen <= 10000, 'PACK_DIRECTORY', 'bundle directory has too many entries');
      const file = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(file);
      else if (entry.isFile()) {
        const s = fs.statSync(file);
        check(!(s.dev === pinsStat.dev && s.ino === pinsStat.ino), 'PINS_INSIDE_BUNDLE',
          `the pins file is the same file as ${path.relative(bundle, file)} inside the bundle`);
      }
    }
  }
}

/** Read a pack directory and an optional pins file, then call verifyPack. */
export async function verifyPackDirectory(directory, {pinsFile = null, trustedBlockHash = null} = {}) {
  const files = {};
  check(fs.lstatSync(directory).isDirectory(), 'PACK_DIRECTORY', 'bundle must be a directory');
  const ignoredFiles = fs.readdirSync(directory).filter((name) => !PACK_FILES.includes(name)).sort();
  for (const name of PACK_FILES) {
    const file = path.join(directory, name);
    if (fs.existsSync(file)) {
      const stat = fs.lstatSync(file);
      check(stat.isFile() && !stat.isSymbolicLink(), 'PACK_FILE_TYPE', `${name} must be a regular file`);
      check(stat.size <= MAX_FILE_BYTES, 'FILE_TOO_LARGE', `${name} exceeds ${MAX_FILE_BYTES} bytes`);
      files[name] = fs.readFileSync(file);
    }
  }
  let pins = null;
  if (pinsFile !== null) {
    const stat = fs.lstatSync(pinsFile);
    check(stat.isFile() && stat.size <= 1 << 16, 'PINS_SHAPE', 'pins must be a small regular file');
    checkPinsOutsideBundle(pinsFile, stat, directory);
    pins = parseJson(fs.readFileSync(pinsFile), path.basename(pinsFile));
  }
  const report = await verifyPack({files, pins, trustedBlockHash});
  // Anything else in the directory, such as a hash list shipped with the pack, is not an input.
  report.ignoredFiles = ignoredFiles;
  return report;
}

/**
 * Build CHAIN_CONTEXT.json from a locally held witness package. The package is fully authenticated
 * first; only its public headers and raw transactions are copied out. State, code and proofs stay behind.
 */
export async function chainContextFromPackage(packageBytes, runtimePlanBytes) {
  const runtimePlan = parseJson(runtimePlanBytes, 'RUNTIME_PLAN.json');
  check(runtimePlan.schema === PLAN_SCHEMA, 'INCOMPATIBLE_PROFILE', `plan schema must be ${PLAN_SCHEMA}`);
  const pkg = await authenticatePackage(packageBytes, runtimePlan.plan);
  const pick = (value, keys) => Object.fromEntries(keys.map((k) => [k, value[k]]));
  const lower = (v) => (v == null ? null : String(v).toLowerCase());
  const context = {
    block: {...pick(pkg.block, HEADER_FIELDS), transactions: pkg.block.transactions.map((tx, i) => {
      const fields = pick(tx, i === 0 ? SYSTEM_TX_FIELDS : SIGNED_TX_FIELDS);
      return i === 0 ? fields : {...fields, from: lower(fields.from), to: lower(fields.to), input: lower(fields.input)};
    })},
    chainId: runtimePlan.plan.checkpoint.chainId,
    origin: 'PUBLIC_BLOCK_DATA_FROM_AUTHENTICATED_RHOOK_PACKAGE',
    parent: pick(pkg.parent, HEADER_FIELDS),
    rawTransactions: pkg.rawTransactions,
    schema: CONTEXT_SCHEMA,
  };
  await authenticateChainContext(context, runtimePlan.plan);
  return Buffer.from(stableJson(context));
}

const short = (h) => (h ? `${h.slice(0, 10)}…${h.slice(-6)}` : 'none');

/** Plain-text summary of a report for a terminal. */
export function renderText(report) {
  const lines = [`RHOOK verify-pack 0.1: recorded evidence check, no EVM re-execution`];
  if (report.case) {
    const c = report.case;
    lines.push(`Case: chain ${c.chainId}, block ${c.targetBlock} (${short(c.targetBlockHash)}), ${c.arrivals} arrivals, `
      + `${c.intervention.field} ${c.intervention.from} -> ${c.intervention.to}`);
  }
  const l = report.levels;
  const row = (tag, name, status) => lines.push(`  ${tag}  ${name.padEnd(22)} ${status ?? 'NOT_EVALUATED'}`);
  lines.push('Checks:');
  row('A', 'Artifact integrity', l.artifactIntegrity?.status);
  row('-', 'Chain context', l.chainContext?.status);
  row('B', 'Canonical ACTUAL', l.canonicalActual?.status);
  row('C', 'Recorded BRANCH', l.recordedBranch?.status);
  if (report.pins) lines.push(`Pins: ${report.pins.name} (${report.pins.source})`);
  if (l.chainContext?.declaredOrigin) lines.push(`Chain context origin, as declared by the pack: ${l.chainContext.declaredOrigin}`);
  if (report.ignoredFiles?.length) lines.push(`Ignored files in the pack (not inputs): ${report.ignoredFiles.join(', ')}`);
  const a = report.anchoring;
  lines.push(`Anchors: external pins ${a.externalPins}; trusted block ${a.trustedBlock}`
    + (a.trustedBlockHash ? ` (${short(a.trustedBlockHash)})` : ''));
  if (!report.failure && a.trustedBlock !== 'MATCH') lines.push('Warning: without --trusted-block-hash nothing here is tied to the real chain.');
  if (!report.failure && a.externalPins !== 'MATCH') lines.push('Warning: without --pins the files are not tied to any published RHOOK result.');
  lines.push('ACTUAL observations (storage, balances, call trace) are engine records, not checked against the chain.');
  lines.push('Not performed: prestate authentication, native re-execution, independent-engine agreement.');
  if (report.economics) {
    const e = report.economics;
    lines.push('Subject transaction, buyer RHOOK Transfer-event net (base units):');
    lines.push(`  ACTUAL  ${e.actual.buyerRhookTransferNetBaseUnits.padStart(28)}  ${e.actual.basis}`);
    lines.push(`  BRANCH  ${e.branch.buyerRhookTransferNetBaseUnits.padStart(28)}  ${e.branch.basis}`);
    const pct = e.buyerRhookTransferNetDeltaPercent;
    lines.push(`  Delta   ${e.buyerRhookTransferNetDeltaBaseUnits.padStart(28)}  `
      + (pct === null ? '(percent N/A: ACTUAL net is not positive)' : `(${pct}%)`));
    lines.push(`  Outer swap fee pips: ${e.actual.outerSwapFeePips} -> ${e.branch.outerSwapFeePips}; subject gas delta ${e.subjectGasDelta}`);
  }
  lines.push(report.failure
    ? `Outcome: CHECK_FAILED at ${report.failure.level}: ${report.failure.code}: ${report.failure.detail}`
    : `Outcome: ${report.outcome} (exit code ${exitCodeFor(report)})`);
  return lines.join('\n') + '\n';
}
