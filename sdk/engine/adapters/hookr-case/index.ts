import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {encodeAbiParameters, keccak256, type Hex} from 'viem';
import {
  HOOKR_1, releaseManifest, encodeRulesConfig, decodeRulesConfig,
  checkRulesConfig, type RulesConfig,
} from 'hookr-sdk';
import {authenticateProof} from './proof.mjs';
import {canonical, commitment} from './primitives.mjs';
import {parseStrictEvidenceJson} from './strict-json.mjs';

const read = (name: string) => parseStrictEvidenceJson(
  fs.readFileSync(new URL(name, import.meta.url), 'utf8'));
const saved = read('../../repro/portable/plan.json');
const pins = read('./pins.json');
const MASK = 65535n << 160n;
const word = (n: bigint): Hex => `0x${n.toString(16).padStart(64, '0')}`;
const digest = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const lower = (value: string) => value.toLowerCase();
export const ruleId: string = pins.caseRule;

function requireValue(ok: unknown, code: string): asserts ok {
  if (!ok) throw new Error(code);
}

function decimal(value: unknown): number {
  requireValue(typeof value === 'string' && /^(0|[1-9][0-9]{0,3})$/.test(value), 'DECIMAL_BPS_REQUIRED');
  return Number(value);
}

const identity = {
  schema: 'rhook/hookr-case/0.1', packageSha256: saved.packageSha256,
  checkpoint: saved.checkpoint, blockNumber: String(saved.blockNumber),
  blockHash: saved.blockHash, arrivals: saved.arrivals,
  poolId: saved.intervention.pool, generation: 'hookr-1', rulesModule: 'standard',
};
const caseId: string = commitment('rhook/hookr-case/0.1', identity);

function inputPackage(input: Uint8Array) {
  requireValue(input instanceof Uint8Array && input.byteLength <= 2 * 1024 * 1024, 'PACKAGE_INPUT_LIMIT');
  const bytes = Buffer.from(input); // Isolate caller-owned buffers before hashing/parsing.
  requireValue(digest(bytes) === saved.packageSha256, 'PACKAGE_SHA256');
  const p = parseStrictEvidenceJson(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  requireValue(canonical(p.checkpoint) === canonical(saved.checkpoint), 'CHECKPOINT');
  requireValue(p.parent.hash === saved.checkpoint.blockHash &&
    p.parent.stateRoot === saved.checkpoint.stateRoot &&
    BigInt(p.parent.number) === BigInt(saved.checkpoint.blockNumber), 'PARENT');
  requireValue(p.block.hash === saved.blockHash && p.block.parentHash === p.parent.hash &&
    p.block.stateRoot === saved.stateRoot && p.block.receiptsRoot === saved.receiptsRoot &&
    BigInt(p.block.number) === BigInt(saved.blockNumber), 'TARGET');
  requireValue(p.block.transactions.length === 7 && p.rawTransactions.length === 7 &&
    canonical(p.block.transactions.map((t: {hash: string}) => t.hash)) === canonical(saved.arrivals), 'ARRIVALS');
  return p;
}

function decodeStorage(words: bigint[]): RulesConfig {
  const names = ['guardEndBlock', 'maxFeePips', 'snipeTaxPips', 'snipeFloorPips',
    'snipeDecaySeconds', 'dynamicFeeSens', 'burnBps', 'lpBps', 'potBps',
    'royaltyBps', 'protocolShareBps', 'potEveryNBuys'];
  const widths = [40, 24, 24, 24, 16, 16, 16, 16, 16, 16, 16, 32];
  const fields: Record<string, number | bigint | string> = {};
  let shift = 0n;
  for (let i = 0; i < names.length; i++) {
    fields[names[i]] = Number((words[0] >> shift) & ((1n << BigInt(widths[i])) - 1n));
    shift += BigInt(widths[i]);
  }
  fields.maxBuyQuoteAmount = words[1] & ((1n << 128n) - 1n);
  fields.potMinBuyQuote = words[1] >> 128n;
  requireValue(words[2] >> 160n === 0n && words[3] >> 160n === 0n, 'UNSUPPORTED_STORAGE_PADDING');
  fields.royaltyTo = `0x${words[2].toString(16).padStart(40, '0')}`;
  fields.integrator = `0x${words[3].toString(16).padStart(40, '0')}`;
  // Packed Solidity storage is not ABI data. Cross the ABI boundary only after unpacking.
  return decodeRulesConfig(encodeRulesConfig(fields as unknown as RulesConfig));
}

function authenticate(input: Uint8Array) {
  const p = inputPackage(input);
  const manifest = releaseManifest(HOOKR_1);
  const rootPin = manifest.contracts.find(c => c.role === 'root');
  const rulesPin = manifest.contracts.find(c => c.role === 'rules');
  requireValue(rootPin && rulesPin && lower(rootPin.address) === pins.poolKey.hooks &&
    lower(rulesPin.address) === saved.intervention.account &&
    rootPin.runtimeHash === pins.rootRuntimeHash, 'RELEASE_PINS');
  const poolId = keccak256(encodeAbiParameters([
    {type: 'address'}, {type: 'address'}, {type: 'uint24'}, {type: 'int24'}, {type: 'address'},
  ], [pins.poolKey.currency0, pins.poolKey.currency1, pins.poolKey.fee,
    pins.poolKey.tickSpacing, pins.poolKey.hooks]));
  requireValue(poolId === saved.intervention.pool, 'POOL_ID');
  const configSlot = BigInt(keccak256(encodeAbiParameters(
    [{type: 'bytes32'}, {type: 'bytes32'}], [poolId, word(BigInt(pins.rulesNamespace))]))) + 1n;
  requireValue(word(configSlot) === saved.intervention.slot, 'STORAGE_LAYOUT');
  const accounts: Record<string, ReturnType<typeof authenticateProof>> = {};
  for (const pin of [rootPin, rulesPin]) {
    const proofs = p.proofs.filter((r: {address: string}) => lower(r.address) === lower(pin.address));
    requireValue(proofs.length > 0, 'ACCOUNT_PROOF_REQUIRED');
    const resolutions = new Map();
    for (const row of proofs) {
      const proof = row.proof;
      const verified = authenticateProof(saved.checkpoint.stateRoot, lower(pin.address),
        proof.storageProof.map((s: {key: string}) => word(BigInt(s.key))), proof);
      requireValue(verified.account.status === 'PRESENT' && verified.account.codeHash === pin.runtimeHash &&
        p.codes.some((code: Hex) => keccak256(code) === verified.account.codeHash), 'RUNTIME_CODE');
      for (const resolution of verified.resolutions) {
        const previous = resolutions.get(resolution.key);
        requireValue(!previous || previous.value === resolution.value, 'CONFLICTING_STORAGE_PROOF');
        resolutions.set(resolution.key, resolution);
      }
      accounts[lower(pin.address)] = verified;
    }
    accounts[lower(pin.address)].resolutions = [...resolutions.values()];
  }
  const storage = (address: string, key: bigint): bigint => {
    const rows = accounts[address].resolutions.filter((r: {key: string}) => r.key === word(key));
    requireValue(rows.length === 1, 'AUTHENTICATED_STORAGE_REQUIRED');
    return BigInt(rows[0].value);
  };
  const words = Array.from({length: 4}, (_, i) => storage(saved.intervention.account, configSlot + BigInt(i)));
  requireValue(word(words[0]) === saved.intervention.expectedOldWord &&
    word(MASK) === saved.intervention.mask, 'ORIGINAL_RULES_WORD');
  const config = decodeStorage(words);
  const root0 = storage(pins.poolKey.hooks, BigInt(pins.rootRecordSlot));
  const root1 = storage(pins.poolKey.hooks, BigInt(pins.rootRecordSlot) + 1n);
  requireValue(`0x${(root0 & ((1n << 160n) - 1n)).toString(16).padStart(40, '0')}` ===
    saved.intervention.account && ((root0 >> 232n) & 255n) === 1n, 'ROOT_RULES_BINDING');
  const baseLpFeePips = Number((root0 >> 160n) & 0xffffffn);
  const caps = {maxLpFeePips: Number(root1 & 0xffffffn),
    maxQuoteTakePips: Number((root1 >> 24n) & 0xffffffn),
    maxSubjectTakeBps: Number((root1 >> 48n) & 65535n)};
  return {config, words, baseLpFeePips, caps};
}

export function inspect(input: Uint8Array) {
  const {config, baseLpFeePips, caps} = authenticate(input);
  const configJson = Object.fromEntries(Object.entries(config).map(([k, v]) =>
    [k, typeof v === 'string' ? v : v.toString()]));
  return {
    ...structuredClone(identity), caseId, status: 'INSPECTED',
    contracts: {root: pins.poolKey.hooks, rules: saved.intervention.account, router: saved.router},
    hookrSdkVersion: '1.1.1', stateAuthenticity: 'ORIGINAL_ROOT_PROOFS_AND_CODE_MATCH',
    config: configJson, baseLpFeePips: String(baseLpFeePips),
    caps: Object.fromEntries(Object.entries(caps).map(([k, v]) => [k, String(v)])),
    supportedRule: {ruleId, minimum: pins.minimumNewValue, maximum: pins.maximumNewValue, noOpAllowed: false},
    historicalSwapBuilderCompatibility: 'NOT_ESTABLISHED',
    nativeExecution: 'NOT_RUN', witnessClosureForNewBranch: 'NOT_EVALUATED',
  };
}

export interface PlanRequest {
  caseId: string;
  ruleId: string;
  expectedOld: string;
  newValue: string;
}

export function plan(input: Uint8Array, request: PlanRequest) {
  requireValue(request && Object.getPrototypeOf(request) === Object.prototype, 'REQUEST_OBJECT');
  const descriptors = Object.getOwnPropertyDescriptors(request);
  requireValue(Object.values(descriptors).every(d => 'value' in d) &&
    canonical(Object.keys(request).sort()) === canonical(['caseId', 'expectedOld', 'newValue', 'ruleId']), 'REQUEST_FIELDS');
  requireValue(request.caseId === caseId && request.ruleId === ruleId, 'UNSUPPORTED_CASE_OR_RULE');
  const oldValue = decimal(request.expectedOld), newValue = decimal(request.newValue);
  const state = authenticate(input); // Never accept a caller-supplied inspection as trusted state.
  requireValue(oldValue === state.config.lpBps, 'EXPECTED_OLD');
  requireValue(newValue >= Number(pins.minimumNewValue) && newValue <= Number(pins.maximumNewValue), 'CASE_LP_RANGE');
  requireValue(newValue !== oldValue, 'NO_CHANGE');
  const config = {...state.config, lpBps: newValue};
  // Check the known static rule constraints and frozen pool caps. This is not a bind/governance simulation.
  checkRulesConfig(config, {baseLpFeePips: state.baseLpFeePips,
    minProtocolShareBps: state.config.protocolShareBps, caps: state.caps});
  const newWord = (state.words[0] & ~MASK) | (BigInt(newValue) << 160n);
  requireValue(((newWord ^ state.words[0]) & ~MASK) === 0n, 'UNRELATED_BITS_CHANGED');
  const intervention = {...structuredClone(saved.intervention), newWord: word(newWord)};
  const body = {
    schema: 'rhook/hookr-plan/0.1', caseId, packageSha256: saved.packageSha256,
    ruleId, expectedOld: request.expectedOld, newValue: request.newValue,
    intervention, status: 'PLANNED_NOT_EXECUTED', branchResult: null,
    savedInterventionMatch: canonical(intervention) === canonical(saved.intervention),
    executionSupport: newValue === 0 ? 'MATCHES_SAVED_INTERVENTION' : 'NEW_NATIVE_PLAN_REQUIRED',
    witnessClosure: 'NOT_EVALUATED', executionAuthorized: false,
  };
  return {...body, planCommitment: commitment('rhook/hookr-plan/0.1', body)};
}
