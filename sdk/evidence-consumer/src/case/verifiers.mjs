// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {spawn} from 'node:child_process';
import {fail, need, sha256} from '../codec.mjs';
import {localRoot, parseEvidence, readPinned, readRegularBytes} from './evidence.mjs';
import {eth} from './projections.mjs';

const PYTHON = '/usr/bin/python3';
const WRAPPER = 'verify_portable_chain.py';
const TIMEOUT_MS = 20_000;
const OUTPUT_BYTES = 256 * 1024;

function run(executable, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, {
      cwd, env: {PATH: '/usr/bin:/bin', HOME: cwd, TMPDIR: cwd, LANG: 'C', GOMAXPROCS: '2',
        GOMEMLIMIT: '256MiB'}, stdio: ['ignore', 'pipe', 'pipe'], detached: true,
    });
    const output = [];
    let size = 0;
    let stopped = null;
    const stop = reason => {
      if (stopped) return;
      stopped = reason;
      if (child.pid) {
        try { process.kill(-child.pid, 'SIGKILL'); } catch (error) {
          if (error.code !== 'ESRCH') child.kill('SIGKILL');
        }
      }
    };
    const timer = setTimeout(() => stop('VERIFIER_TIMEOUT'), TIMEOUT_MS);
    for (const [stream, retain] of [[child.stdout, true], [child.stderr, false]]) {
      stream.on('data', chunk => {
        size += chunk.length;
        if (size > OUTPUT_BYTES) stop('VERIFIER_OUTPUT_LIMIT');
        else if (retain && !stopped) output.push(chunk);
      });
    }
    child.on('error', reject);
    child.on('close', (status, signal) => {
      clearTimeout(timer);
      try {
        if (stopped) fail(stopped);
        need(signal === null && output.length > 0, 'VERIFIER_NO_REPORT');
        resolve({status, report: parseEvidence(Buffer.concat(output))});
      } catch (error) {
        reject(error);
      }
    });
  });
}

function stage(root, name, bytes, mode = 0o400) {
  const file = path.join(root, name);
  fs.mkdirSync(path.dirname(file), {recursive: true, mode: 0o700});
  fs.writeFileSync(file, bytes, {mode, flag: 'wx'});
}

async function snapshot(action) {
  const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'rhook-verify-'));
  try { return await action(root); }
  finally { fs.rmSync(root, {recursive: true, force: true}); }
}

const depsPrefix = 'sdk/engine/adapters/hookr-case/node_modules';
function stageDependencies(sdk, scratch, pins) {
  const source = localRoot(path.join(sdk, depsPrefix));
  const inventory = [];
  let bytes = 0;
  let entries = 0;
  function walk(relative) {
    for (const entry of fs.readdirSync(path.join(source, relative), {withFileTypes: true})) {
      need(++entries <= pins.dependencyFiles * 2 && /^[\w.@-]+$/.test(entry.name), 'VERIFIER_DEPENDENCY_IDENTITY');
      const name = path.join(relative, entry.name);
      if (entry.isDirectory()) {
        walk(name);
        continue;
      }
      need(entry.isFile(), 'VERIFIER_DEPENDENCY_IDENTITY');
      const file = path.join(source, name);
      need(fs.realpathSync(file) === file, 'VERIFIER_DEPENDENCY_IDENTITY');
      const data = readRegularBytes(file, pins.dependencyBytes - bytes);
      bytes += data.length;
      inventory.push([name, {bytes: data.length, sha256: sha256(data)}]);
      stage(scratch, path.join(depsPrefix, name), data);
    }
  }
  walk('');
  inventory.sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0);
  need(inventory.length === pins.dependencyFiles && bytes === pins.dependencyBytes &&
    sha256(JSON.stringify(Object.fromEntries(inventory))) === pins.dependencyInventorySha256, 'VERIFIER_DEPENDENCY_IDENTITY');
}

const failureCodes = new Set(['EVIDENCE_HASH_MISMATCH', 'EVIDENCE_SIZE_MISMATCH', 'EVIDENCE_CHANGED',
  'EVIDENCE_PATH_UNSAFE', 'VERIFIER_DEPENDENCY_IDENTITY', 'VERIFIER_REPORT_MISMATCH', 'STRICT_JSON_SYNTAX']);

function toolFailure(error, kind, paths) {
  const status = failureCodes.has(error.code) ? 'FAIL' : 'UNRESOLVED';
  const reason = error.code === 'ENOENT'
    ? (paths?.missingReason ?? 'VERIFIER_OR_INPUT_NOT_INSTALLED')
    : error.code ?? kind;
  return {status, reason};
}

export async function verifyPair({read, verifyPackRoot, trustedBlockHash, pins, projection}) {
  if (!verifyPackRoot || !trustedBlockHash) return {status: 'UNRESOLVED', reason: 'VERIFY_PACK_AND_EXTERNAL_BLOCK_HASH_REQUIRED'};
  if (Number(process.versions.node.split('.')[0]) < 24) return {status: 'UNSUPPORTED', reason: 'VERIFY_PACK_REQUIRES_NODE_24'};
  try {
    return await snapshot(async root => {
      const sdk = localRoot(verifyPackRoot);
      for (const [name, pin] of Object.entries(pins.files)) stage(root, name, readPinned(sdk, name, pin));
      stageDependencies(sdk, root, pins);
      const packFiles = ['ACTUAL.json', 'BRANCH.json', 'RUNTIME_PLAN.json', 'CHAIN_CONTEXT.json'];
      const inputs = Object.fromEntries(packFiles.map(name => [name, read(name)]));
      for (const [name, bytes] of Object.entries(inputs)) stage(root, 'bundle/' + name, bytes);
      const result = await run(process.execPath, ['--no-global-search-paths', '--permission', '--allow-fs-read=' + root,
        'sdk/verify-pack/cli.mjs', 'verify', '--bundle', 'bundle', '--pins', 'sdk/verify-pack/pins/hookr-pair03-lp50.json',
        '--trusted-block-hash', trustedBlockHash, '--json'], root);
      const r = result.report;
      if (r.outcome === 'CHECK_FAILED') return {status: 'FAIL', outcome: r.outcome, reason: r.failure?.code ?? 'VERIFY_PACK_FAILED'};
      need(result.status === 0 && r.schema === 'rhook/verify-pack-report/0.1' && r.tool === 'rhook-verify-pack/0.1' &&
        r.outcome === 'RECORDED_PAIR_CONSISTENT_FULLY_ANCHORED' && r.failure === null && r.reexecution === 'NONE' &&
        r.anchoring?.complete === true && r.anchoring.externalPins === 'MATCH' && r.anchoring.trustedBlock === 'MATCH' &&
        r.anchoring.trustedBlockHash === trustedBlockHash && r.case?.targetBlockHash === projection.history.blockHash &&
        r.case.targetBlock === projection.history.blockNumber && r.case.chainId === 4663 &&
        r.case.subjectOrdinal === projection.subject.ordinal && r.case.subjectTransaction === projection.subject.transactionHash &&
        packFiles.every(name => r.inputs?.[name]?.sha256 === sha256(inputs[name])) &&
        r.levels?.chainContext?.status === 'BOUND_TO_TRUSTED_BLOCK' &&
        r.levels.canonicalActual?.status === 'ACTUAL_RECEIPTS_AND_ROOTS_MATCH_TRUSTED_BLOCK' &&
        r.levels.recordedBranch?.status === 'RECORDED_BRANCH_INTERNALLY_CONSISTENT' &&
        r.limitations?.nativeReexecution === 'NOT_PERFORMED' && r.limitations.qualifiedClaims === 0,
      'VERIFIER_REPORT_MISMATCH');
      for (const role of ['actual', 'branch']) {
        for (const field of ['buyerRhookTransferNetBaseUnits', 'outerSwapFeePips', 'subjectGasUsed', 'subjectStatus']) {
          need(r.economics?.[role]?.[field] === projection.comparison[role][field], 'VERIFIER_REPORT_MISMATCH');
        }
      }
      return {status: 'PASS', outcome: r.outcome, anchoring: r.anchoring, levels: r.levels,
        case: r.case, inputs: r.inputs, economics: r.economics, limitations: r.limitations};
    });
  } catch (error) {
    return toolFailure(error, 'VERIFY_PACK_UNAVAILABLE');
  }
}

const A = 'A_consensus';
const P1 = 'P1_beacon_exec_binding';
const B = 'B_el_ancestry';
const cryptoExecutables = new Set(['consensus-verify-01/bin/rhook-eth-consensus-verify',
  'consensus-close-01/bin/rhook-eth-consensus-close', 'anchor-01/bin/rhook-eth-anchor']);
const portableInputs = [
  WRAPPER, ...cryptoExecutables, eth.capsule, eth.el, eth.ssz,
  'runs/consensus-acquire-02/bootstrap-primary.json',
  'runs/consensus-acquire-02/finality-primary.json',
  'runs/consensus-acquire-02/RESULT-primary.json',
];

function allTrue(object, keys) {
  return keys.every(key => object?.[key] === true);
}

export async function verifyEthereum({read, trustedCheckpoint, pins, projection, linuxPins, verifierRoot}) {
  if (!trustedCheckpoint) return {status: 'UNRESOLVED', reason: 'EXTERNAL_TRUSTED_CHECKPOINT_REQUIRED'};
  const linux = process.platform === 'linux' && process.arch === 'x64';
  const darwin = process.platform === 'darwin' && process.arch === 'arm64';
  if ((!linux && !darwin) || (darwin && verifierRoot !== undefined)) {
    return {status: 'UNSUPPORTED', reason: 'VERIFIER_PLATFORM_MISMATCH'};
  }
  if (linux && !verifierRoot) return {status: 'UNRESOLVED', reason: 'LINUX_AMD64_VERIFIER_ROOT_REQUIRED'};
  let missing;
  try {
    return await snapshot(async root => {
      missing = linux ? WRAPPER : undefined;
      const installed = linux ? localRoot(verifierRoot) : null;
      let el;
      for (const name of portableInputs) {
        missing = name;
        const executable = cryptoExecutables.has(name);
        const bytes = linux && executable ? readPinned(installed, name, linuxPins[name]) : read(name);
        if (name === eth.el) el = parseEvidence(bytes);
        stage(root, name, bytes, executable ? 0o500 : 0o400);
      }
      missing = undefined;
      const {history: h} = projection;
      need(el.target.number === h.blockNumber && el.target.hash === h.blockHash &&
        el.target.parentHash === h.parentHash && el.target.parentRoot === h.parentStateRoot,
      'VERIFIER_REPORT_MISMATCH');
      const {status, report: r} = await run(PYTHON, ['-I', '-B', WRAPPER, trustedCheckpoint, '--json'], root);
      need(r.schema === 'rhook/eth-portable-chain/0.1' && r.trustedCheckpointRoot_policyInput === trustedCheckpoint,
        'VERIFIER_REPORT_MISMATCH');
      if (r.terminal === 'INVALID_EVIDENCE' && status === 2) {
        return {status: 'FAIL', terminal: r.terminal, failures: r.failures};
      }
      if (r.terminal === 'UNRESOLVED' && status === 2) return {status: 'UNRESOLVED', terminal: r.terminal};
      const a = r.stageReceipts?.[A];
      const p = r.stageReceipts?.[P1];
      const b = r.stageReceipts?.[B];
      need(status === 0 && r.terminal === 'RHOOK_ETH_PORTABLE_CHAIN_VERIFIED' &&
        r.failures?.length === 0 && r.unresolved?.length === 0 && allTrue(r.stagesPassed, [A, P1, B]) &&
        a?.terminal === 'CONSENSUS_REVERIFIED_TO_FINALIZED_BEACON_HEADER' &&
        a.pinnedCheckpointRoot === trustedCheckpoint && a.fork === 'fulu' &&
        allTrue(a.selfVerifiedOffline, ['checkpointIdentity', 'committeeRootAndMerkleBranch',
          'syncCommitteeBLSSignature', 'finalityMerkleBranch']) &&
        p?.terminal === 'BEACON_EXECUTION_BINDING_VERIFIED' && p.mode === 'ssz' &&
        p.beaconRootMatches === true && p.executionBlockHashMatches === true &&
        p.inputSha256 === pins[eth.ssz].sha256 && p.inputBytes === pins[eth.ssz].bytes &&
        a.finalizedBeaconHeaderRoot === p.computedBeaconBlockRoot &&
        a.finalizedBeaconHeaderRoot === p.expectedBeaconBlockRoot &&
        a.finalizedBeaconHeaderRoot === r.finalizedBeaconHeaderRoot &&
        a.finalizedBeaconHeaderRoot === el.finalizedBeaconRoot && a.finalizedSlot === p.slot &&
        b?.classification === 'FINALIZED_ANCESTRY_VERIFIED' && allTrue(b, ['targetHashLinked', 'parentStateRootBound']) &&
        p.executionBlockHash === b.anchoredHead && p.executionBlockHash === r.finalizedExecutionBlockHash &&
        p.executionBlockHash === el.executionBlockHash && p.executionBlockHash === p.expectedExecutionBlockHash &&
        p.executionBlockNumber === el.executionBlockNumber && r.targetBlock === h.blockNumber &&
        r.capsuleSha256 === pins[eth.capsule].sha256 &&
        allTrue(r.crosslinks, ['consensusBeaconRoot_eq_blockRoot', 'derivedElHash_eq_anchoredHead', 'derivedElHash_eq_expectedHead']) &&
        allTrue(r.crosslinks?.capsuleBinding, ['targetNumber', 'targetHash', 'parentHash', 'parentStateRoot']),
      'VERIFIER_REPORT_MISMATCH');
      return {status: 'PASS', terminal: r.terminal, verifierPlatform: linux ? 'linux/amd64' : 'darwin/arm64',
        stagesPassed: r.stagesPassed, crosslinks: r.crosslinks,
        trustedCheckpoint, finalizedBeaconHeaderRoot: a.finalizedBeaconHeaderRoot, finalizedSlot: a.finalizedSlot,
        finalizedExecutionBlockHash: p.executionBlockHash, finalizedExecutionBlockNumber: p.executionBlockNumber,
        headerCount: el.headerChainHex.length, target: el.target, capsuleSha256: r.capsuleSha256,
        proofs: {consensus: a.terminal, beaconToExecution: p.terminal, elAncestry: b.classification},
        trustAssumptions: ['Externally selected weak-subjectivity checkpoint', 'Sync-committee security model',
          'FULU fork rules and pinned verifier implementations']};
    });
  } catch (error) {
    return toolFailure(error, 'PORTABLE_VERIFIER_UNAVAILABLE', {missingReason: missing ? 'MISSING_' +
      (missing === eth.ssz ? 'P1_SSZ' : cryptoExecutables.has(missing) || missing === WRAPPER ? 'VERIFIER' : 'ANCHOR_INPUT') :
      'PYTHON_OR_VERIFIER_UNAVAILABLE'});
  }
}
