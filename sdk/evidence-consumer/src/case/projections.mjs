// SPDX-License-Identifier: Apache-2.0
import {checkLink, parseEvidence} from './evidence.mjs';

export const eth = Object.freeze({
  capsule: 'runs/p2p-actual-01/CAPSULE.json',
  discovery: 'runs/p2p-actual-01/DISCOVERY.json',
  spec: 'SPEC_tx70_x3.json',
  branch: 'runs/tx70-x3-econ/BRANCH.json',
  recorded: 'runs/closure-01/PORTABLE_CHAIN_RECEIPT.json',
  el: 'runs/elhdr-01-live/EVIDENCE.json',
  ssz: 'runs/closure-01/beacon-block-slot15734080.ssz',
});

function worldRoots(record) {
  return {stateRoot: record.stateRoot, receiptsRoot: record.receiptsRoot, blockHash: record.blockHash,
    blockGasUsed: String(record.gasUsed)};
}

export function pair03(read, pins) {
  const context = parseEvidence(read('CHAIN_CONTEXT.json'));
  const config = parseEvidence(read('RUNTIME_PLAN.json'));
  const actual = parseEvidence(read('ACTUAL.json'));
  const branch = parseEvidence(read('BRANCH.json'));
  const report = parseEvidence(read('PAIR03_VERIFIER_REPORT.json'));
  const parity = parseEvidence(read('PAIR03_CROSS_ENGINE.json'));
  const {plan} = config;
  const subject = report.case;
  checkLink(context.chainId === 4663 && config.schema === 'rhook/hookr-runtime-plan/0.2' &&
    context.block.hash === plan.blockHash && context.block.parentHash === context.parent.hash &&
    context.parent.hash === plan.checkpoint.blockHash && context.parent.stateRoot === plan.checkpoint.stateRoot &&
    plan.nativeOrdinal === subject.subjectOrdinal && plan.subject === subject.subjectTransaction &&
    context.rawTransactions.length === subject.arrivals && subject.targetBlockHash === plan.blockHash &&
    subject.intervention.to === Number(config.newValue));
  checkLink(actual.result.world === 'ACTUAL' && branch.result.world === 'BRANCH' &&
    actual.result.blockHash === plan.blockHash && branch.result.blockHash !== plan.blockHash &&
    report.inputs['ACTUAL.json'].sha256 === pins['ACTUAL.json'].sha256 &&
    report.inputs['BRANCH.json'].sha256 === pins['BRANCH.json'].sha256 &&
    report.inputs['RUNTIME_PLAN.json'].sha256 === pins['RUNTIME_PLAN.json'].sha256 &&
    parity.lp50.goActualRecordSha256 === pins['ACTUAL.json'].sha256 &&
    parity.lp50.goBranchRecordSha256 === pins['BRANCH.json'].sha256);

  const economics = report.economics;
  return {
    history: {blockNumber: plan.blockNumber, blockHash: plan.blockHash, orderedArrivals: subject.arrivals,
      parentNumber: plan.checkpoint.blockNumber, parentHash: context.parent.hash, parentStateRoot: context.parent.stateRoot},
    subject: {ordinal: plan.nativeOrdinal, transactionHash: plan.subject},
    intervention: {kind: 'hookr-1.lp-bps/1', field: subject.intervention.field, from: subject.intervention.from,
      to: subject.intervention.to, account: subject.intervention.account, slot: subject.intervention.slot,
      poolId: subject.intervention.pool, applies: 'BEFORE_FIRST_ARRIVAL', source: plan.source},
    worlds: {ACTUAL: worldRoots(actual.result), BRANCH: worldRoots(branch.result)},
    comparison: {projection: 'subject', basis: 'RECORDED_ASSERTION',
      actual: economics.actual, branch: economics.branch, gasDelta: economics.subjectGasDelta,
      buyerRhookTransferNetDeltaBaseUnits: economics.buyerRhookTransferNetDeltaBaseUnits,
      buyerRhookTransferNetDeltaPercent: economics.buyerRhookTransferNetDeltaPercent,
      units: {outerSwapFeePips: 'pips', buyerRhookTransferNetBaseUnits: 'RHOOK transfer-event base units'},
      scope: economics.measure},
    recorded: {terminal: report.outcome, heterogeneous: {terminal: parity.lp50.qualificationStatus,
      fields: parity.lp50.comparedFields, mismatches: parity.lp50.mismatches,
      unavailableMetadataEntries: parity.lp50.unavailableMetadataEntries,
      fullJsonRpcObjectParity: parity.lp50.fullJsonRpcObjectParity}},
  };
}

const SWAP = '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67';
const TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
const POOL = '0xc7bbec68d12a0d1830360f8ec58fa599ba1b0e9b';
const USDT = '0xdac17f958d2ee523a2206206994597c13d831ec7';
const WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2';

function economicObservation(receipt, logs) {
  const swaps = logs.filter(log => log.address.toLowerCase() === POOL && log.topics[0] === SWAP);
  const usdtTransfers = logs.filter(log => log.address.toLowerCase() === USDT &&
    log.topics[0] === TRANSFER && log.topics[2]?.slice(-40).toLowerCase() === POOL.slice(2));
  checkLink(swaps.length === 1 && usdtTransfers.length === 1 && /^0x[0-9a-fA-F]{320}$/.test(swaps[0].data));
  const data = swaps[0].data;
  const wethDelta = BigInt.asIntN(256, BigInt('0x' + data.slice(2, 66)));
  const usdtDelta = BigInt.asIntN(256, BigInt('0x' + data.slice(66, 130)));
  checkLink(wethDelta < 0n && usdtDelta > 0n && usdtDelta === BigInt(usdtTransfers[0].data) &&
    receipt.status === 1);
  return {status: 'SUCCESS', gasUsed: String(receipt.gasUsed), usdtConsumedBaseUnits: String(usdtDelta),
    wethOutBaseUnits: String(-wethDelta)};
}

export function tx70(read) {
  const cap = parseEvidence(read(eth.capsule));
  const spec = parseEvidence(read(eth.spec));
  // Discovery is a pinned Go timing/provenance report with fractional seconds.
  const discovery = JSON.parse(read(eth.discovery));
  checkLink(discovery.terminal === 'CAPSULE_WRITTEN' && discovery.acquisition.root === cap.parentRoot);
  const run = parseEvidence(read(eth.branch));
  let portableChainTerminal = null;
  try { portableChainTerminal = parseEvidence(read(eth.recorded)).terminal; }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const {intervention: edit, actualControl: {comparison: control}} = run;
  const actual = run.actualReceipts[spec.txIndex];
  const branch = run.branchReceipts[spec.txIndex];
  checkLink(Number(cap.chainId) === 1 && cap.targetNumber === 26486739 &&
    cap.schema === 'rhook/ethereum-actual-capsule/0.1' && run.schema === 'rhook/ethereum-branch/0.1' &&
    spec.schema === 'rhook/eth-branch-spec/0.1' && spec.capsuleTargetHash === cap.targetHash &&
    spec.txIndex === 70 && [actual.index, branch.index, edit.txIndex].every(index => index === spec.txIndex) &&
    actual.hash === edit.txHash && branch.hash === edit.txHash && edit.originalSignedTxPreserved === true &&
    edit.modifiedMessageIsSignedTx === false && run.branchBlockIsCanonical === false &&
    run.actualReceipts.length === control.transactions && run.branchReceipts.length === control.transactions &&
    cap.receipts.length === control.transactions && run.branchContinuedFullBlock === true &&
    run.branchFeasible === true && run.actualControl.pass === true);
  const a = economicObservation(actual, run.interventionLogsActual);
  const b = economicObservation(branch, run.interventionLogsBranch);
  checkLink(a.usdtConsumedBaseUnits === '30000000' && b.usdtConsumedBaseUnits === '90000000');

  return {
    history: {blockNumber: cap.targetNumber, blockHash: cap.targetHash, orderedArrivals: control.transactions,
      parentNumber: cap.targetNumber - 1, parentHash: cap.parentHash, parentStateRoot: cap.parentRoot},
    subject: {transactionIndex: spec.txIndex, transactionHash: edit.txHash},
    intervention: {kind: spec.schema, field: 'UniversalRouter.V3_SWAP_EXACT_IN.amountIn',
      fromBaseUnits: '30000000', toBaseUnits: '90000000', asset: USDT, decimals: 6,
      applies: 'DERIVED_MESSAGE_DATA_AFTER_SENDER_RECOVERY', originalSignedTransactionPreserved: true},
    worlds: {ACTUAL: run.actualWorld, BRANCH: run.branchWorld},
    comparison: {projection: 'subject', basis: 'RECORDED_ASSERTION', actual: a, branch: b,
      gasDelta: String(BigInt(b.gasUsed) - BigInt(a.gasUsed)), pool: POOL,
      units: {usdtConsumedBaseUnits: {asset: USDT, decimals: 6}, wethOutBaseUnits: {asset: WETH, decimals: 18}},
      scope: 'RECORDED_SUBJECT_RECEIPT_AND_POOL_SWAP_EVENTS'},
    recorded: {terminal: run.terminal, actualControl: {receipts: control.L1_receipts,
      receiptsRoot: control.L2_receiptsRoot, stateRootAndRequestsHash: control.L3_stateRoot_requestsHash},
      branchDependencyClosure: run.branchDependencyClosure, acquisitionTerminal: discovery.terminal,
      portableChainTerminal},
  };
}
