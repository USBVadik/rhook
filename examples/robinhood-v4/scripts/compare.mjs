import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { buildExecutedEnvelopeEvidence, buildInvalidatedEnvelopeEvidence } from '../../../runtime/src/index.mjs'
import { example, loadArtifacts, checkIntervention, checkSemantic, verifyRecords } from './artifacts.mjs'
import { read, write, sha, objectDigest, withoutLifecycle } from './common.mjs'

const { files, reference, integrity } = loadArtifacts()
const { expected } = reference
const manifest = JSON.parse(files['target-case-manifest.json'])
const headers = JSON.parse(files['inputs/canonical-headers.json'])
const headerByNumber = new Map(headers.map(h => [Number(BigInt(h.number)), h]))
const actual = read('results/actual/CONTROL/native.json')
const actualModes = ['ORIGINAL', 'CONTROL', 'RHOOK_OFF', 'RHOOK_ON']
const continuity = []
function qualifyNative(run, kind, name) {
  assert.equal(run.blocks.length, 50, name)
  assert.equal(run.summary.count, 50)
  assert.equal(run.summary.inputSha256, integrity.files['inputs/session.json'].sha256)
  assert.equal(run.summary.witnessSha256, integrity.files['inputs/witness.json'].sha256)
  assert.equal(run.summary.initialRoot, expected.initialRoot)
  assert.equal(run.summary.initialStateLoads, 1)
  assert.equal(run.summary.computedStateReopens, 49)
  assert.equal(run.summary.canonicalStateResets, 0)
  assert.equal(run.summary.finalRoot, kind === 'COUNTERFACTUAL' ? expected.counterfactualEndpointRoot : expected.actualEndpointRoot)
  for (const [i, b] of run.blocks.entries()) {
    const pin = expected.nativeBlockDigests[kind][i]
    assert.equal(b.blockNumber, pin.number)
    assert.equal(objectDigest(withoutLifecycle(b)), pin.sha256, `${name}: full frozen native block ${pin.number}`)
    const previousRoot = i ? run.blocks[i - 1].finalStateRoot : expected.initialRoot
    assert.equal(b.startStateRoot, previousRoot)
    continuity.push({ mode: name, block: b.blockNumber, previousFinalRoot: previousRoot, startingRoot: b.startStateRoot, finalRoot: b.finalStateRoot })
    if (kind !== 'COUNTERFACTUAL') {
      const h = headerByNumber.get(b.blockNumber)
      assert.equal(b.finalStateRoot, h.stateRoot)
      assert.equal(b.receiptsRoot, h.receiptsRoot)
      assert.equal(b.computedBlockHash, manifest.canonicalOrder[i].hash)
      assert.equal(BigInt(b.gasUsed), BigInt(h.gasUsed))
    } else {
      assert.equal(b.computedHeader, null)
      assert.equal(b.computedBlockHash, null)
      assert.deepEqual(b.transactionHashes, actual.blocks[i].transactionHashes)
      assert.deepEqual(b.phase4.historicalL1Context, actual.blocks[i].phase4.historicalL1Context)
    }
  }
}
function qualifyEvidence(dir, branch, totals) {
  const names = readdirSync(`${dir}/envelopes`).sort()
  assert.deepEqual(names, Object.keys(reference.envelopes[branch]).sort())
  const serialized = Object.fromEntries(names.map(n => [n, readFileSync(`${dir}/envelopes/${n}`, 'utf8')]))
  verifyRecords(serialized, totals)
  // Byte-for-byte equality preserves the original 642 strict records, not just totals.
  for (const name of names) assert.equal(serialized[name], reference.envelopes[branch][name], `${branch}: frozen envelope ${name}`)
  const verifier = spawnSync(process.execPath, [join(example, 'scripts/verify-envelopes.mjs'), `${dir}/envelopes`], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 })
  assert.equal(verifier.status, 0, verifier.stderr)
  const strict = JSON.parse(verifier.stdout)
  assert.equal(strict.count, 321)
  assert.equal(strict.valid, true)
  write(`${dir}/strict-verification.json`, strict)
}
for (const name of actualModes) qualifyNative(read(`results/actual/${name}/native.json`), name === 'ORIGINAL' ? 'ORIGINAL' : 'ACTUAL', name)
qualifyEvidence('results/actual/RHOOK_ON', 'ACTUAL', expected.actualLifecycle)
write('results/actual/comparison.json', { status: 'PASS', blocks: 50, envelopes: 321, fullNativeOutputsMatchFrozen: true, strictEvidence: 321 })
if (process.argv[2] === 'actual') { console.log('ACTUAL canonical control: PASS (50 blocks / 321 envelopes)'); process.exit(0) }

for (const name of ['CONTROL', 'OFF', 'ON']) qualifyNative(read(`results/F4/${name}/native.json`), 'COUNTERFACTUAL', name)
const cf = read('results/F4/CONTROL/native.json')
const actualRecords = actual.blocks.flatMap(b => b.phase4.records)
const records = cf.blocks.flatMap(b => b.phase4.records)
assert.equal(records.length, 321)
assert.equal(cf.summary.phase4.interventionCount, 1)
const x = records[3]
assert.equal(x.preStateRoot, actualRecords[3].preStateRoot)
assert.notEqual(x.postStateRoot, actualRecords[3].postStateRoot)
assert.deepEqual(records.slice(0, 3), actualRecords.slice(0, 3))
assert.equal(records.filter(r => r.intervention).length, 1)
checkIntervention(x.intervention, manifest)
assert.deepEqual(x.intervention, expected.intervention)
const first = predicate => {
  const i = records.findIndex((r, n) => predicate(r, actualRecords[n]))
  return i < 0 ? null : { block: records[i].block, index: records[i].index, transactionHash: records[i].canonicalTransactionHash }
}
const firstStateDivergence = first((c, a) => c.postStateRoot !== a.postStateRoot)
const firstLifecycleDivergence = first((c, a) => c.lifecycle !== a.lifecycle)
const firstResultDivergence = first((c, a) => objectDigest(c.execution ?? c.invalidation) !== objectDigest(a.execution ?? a.invalidation))
assert.deepEqual(firstStateDivergence, expected.firstStateDivergence)
assert.deepEqual(firstLifecycleDivergence, expected.firstLifecycleDivergence)
assert.deepEqual(firstResultDivergence, expected.firstResultDivergence)
const boundary = cf.blocks.findIndex((b, i) => i && b.startStateRoot !== actual.blocks[i].startStateRoot)
assert.equal(boundary, 1)
const firstBoundary = { block: cf.blocks[boundary].blockNumber, branchStartRoot: cf.blocks[boundary].startStateRoot, actualStartRoot: actual.blocks[boundary].startStateRoot, previousBranchFinalRoot: cf.blocks[boundary-1].finalStateRoot }
assert.deepEqual(firstBoundary, expected.firstDivergentBlockBoundary)
const invalidations = records.filter(r => r.lifecycle === 'PRE_EXECUTION_INVALIDATED')
assert.equal(invalidations.length, 13)
for (const r of invalidations) {
  assert.equal(r.invalidation.classification, 'NATIVE_INSUFFICIENT_GAS_FUNDS')
  assert.equal(r.preStateRoot, r.postStateRoot)
  assert.equal(r.gasPoolBefore, r.gasPoolAfter)
  assert.equal(r.callEntries, 0)
  assert.equal(r.opcodeCount, 0)
  assert.equal(r.invalidation.beforeEVM, true)
}
qualifyEvidence('results/F4/ON', 'COUNTERFACTUAL', expected.counterfactualLifecycle)
const bindings = read('results/F4/ON/bindings.json')
assert.equal(bindings.length, records.length)
for (const [i, binding] of bindings.entries()) {
  const r = records[i]
  assert.deepEqual([binding.block,binding.index,binding.transactionHash,binding.preStateRoot,binding.postStateRoot], [r.block,r.index,r.canonicalTransactionHash,r.preStateRoot,r.postStateRoot])
  let rebuilt
  if (r.lifecycle === 'PRE_EXECUTION_INVALIDATED') {
    assert.equal(binding.event, 'invalidatedTx')
    assert.deepEqual(binding.nativePayload, r)
    rebuilt = buildInvalidatedEnvelopeEvidence({ blockNumber:r.block,transactionIndex:r.index,transactionHash:r.canonicalTransactionHash,gasLimit:BigInt(binding.gasLimit),stateRoot:r.preStateRoot,classification:r.invalidation.classification })
  } else {
    const { execution:e, receipt } = binding.nativePayload
    assert.deepEqual(e, r.execution)
    rebuilt = buildExecutedEnvelopeEvidence({ blockNumber:r.block,transactionIndex:r.index,transactionHash:r.canonicalTransactionHash,executedTransactionHash:r.canonicalTransactionHash,gasLimit:BigInt(e.gasLimit),gasUsed:BigInt(e.usedGas),feePaid:e.feePaid,predecessorStateRoot:r.preStateRoot,successorStateRoot:r.postStateRoot,receiptStatus:Number(BigInt(receipt.status)),exception:e.executionError,returnData:e.returnData,logs:receipt.logs ?? [] })
  }
  assert.deepEqual(read(`results/F4/ON/envelopes/${binding.envelope}`), rebuilt.evidence)
}
const mod = 1n << 256n
const y = run => run.blocks.at(-1).semanticValues.map((v,i) => ((BigInt(v)-BigInt(run.summary.initialSemanticValues[i])+mod)%mod).toString())
const semantic = { definition:expected.semantic.definition,slots:expected.semantic.slots,initial:{root:actual.summary.initialRoot,values:actual.summary.initialSemanticValues},actual:{root:actual.summary.finalRoot,values:actual.blocks.at(-1).semanticValues,YX128:y(actual)},counterfactual:{root:cf.summary.finalRoot,values:cf.blocks.at(-1).semanticValues,YX128:y(cf)} }
assert.deepEqual(cf.summary.initialSemanticValues, actual.summary.initialSemanticValues)
semantic.deltaActualMinusCounterfactualX128 = semantic.actual.YX128.map((v,i)=>(BigInt(v)-BigInt(semantic.counterfactual.YX128[i])).toString())
checkSemantic(semantic)
for (const branch of ['actual','counterfactual']) for (const key of ['root','values','YX128']) assert.deepEqual(semantic[branch][key], expected.semantic[branch][key])
assert.deepEqual(semantic.deltaActualMinusCounterfactualX128, expected.semantic.deltaActualMinusCounterfactualX128)
write('results/semantic-comparison.json', semantic)
write('results/invalidations.json', invalidations)
write('results/intervention-commitment.json', x.intervention)
write('results/branch-continuity.json', continuity)
const commitmentBody = { caseArchiveSha256:integrity.archive.sha256,interventionSha256:x.intervention.commitmentSha256,actualNativeSha256:sha(readFileSync('results/actual/CONTROL/native.json')),counterfactualNativeSha256:sha(readFileSync('results/F4/CONTROL/native.json')),actualRoot:actual.summary.finalRoot,counterfactualRoot:cf.summary.finalRoot,semanticSha256:objectDigest(semantic),continuitySha256:objectDigest(continuity) }
const domain='rhook/example/robinhood-v4/session/1\n'
write('results/session-commitment.json', { domain,body:commitmentBody,commitmentSha256:sha(domain+JSON.stringify(commitmentBody)),scope:'Case-local sidecar; not a generic public RHOOK evidence schema' })
const result = { status:'PASS',blocks:50,envelopes:321,actualLifecycle:expected.actualLifecycle,counterfactualLifecycle:expected.counterfactualLifecycle,firstStateDivergence,firstLifecycleDivergence,firstResultDivergence,firstDivergentBlockBoundary:firstBoundary,actualEndpointRoot:actual.summary.finalRoot,counterfactualEndpointRoot:cf.summary.finalRoot,evidence:{actual:321,counterfactual:321},semantic }
write('results/summary.json', result)
const lines = ['RHOOK REAL-CHAIN COUNTERFACTUAL','Chain       Robinhood Chain 4663','Pool        ETH / SHIB',`Pool ID     ${manifest.pool.poolId}`,'Range       70397227–70397276','Envelopes   321','','Lifecycle                      ACTUAL  COUNTERFACTUAL',...Object.keys(expected.actualLifecycle).map(k=>`${k.padEnd(30)} ${String(expected.actualLifecycle[k]).padStart(6)}  ${String(expected.counterfactualLifecycle[k]).padStart(14)}`),'','First state divergence: 70397227 : 3','First lifecycle divergence: 70397227 : 4 — SUCCESS -> REVERT','First divergent block boundary crossed: 70397227 -> 70397228','','Terminal roots:',`ACTUAL          ${actual.summary.finalRoot}`,`COUNTERFACTUAL  ${cf.summary.finalRoot}`,'','pool-level accrued fee growth per active liquidity unit (raw X128)',...['currency0','currency1'].flatMap((k,i)=>[`${k} ACTUAL          ${semantic.actual.YX128[i]}`,`${k} COUNTERFACTUAL  ${semantic.counterfactual.YX128[i]}`,`${k} ACTUAL - CF     ${semantic.deltaActualMinusCounterfactualX128[i]}`]),'','Intervention: native Message.Data replacement; original Message.Tx retained.',`Original calldata SHA-256:    ${x.intervention.body.originalCalldataSha256}`,`Replacement calldata SHA-256: ${x.intervention.body.replacementCalldataSha256}`,`Intervention commitment:      ${x.intervention.commitmentSha256}`,'Preserved Message fields: '+Object.keys(x.targetMessageBefore).filter(k=>k!=='Data').join(', '),'No re-signing; no claim the changed calldata was signed/broadcast under this hash.','Historical envelope identity is retained for alignment and native poster-cost accounting.','','FIXED: checkpoint; historical envelopes/order; downstream signed inputs; declared intervention; block environment; endpoint/query.','REGENERATED: validation/lifecycle; native gas/accounting; results/logs; successor and subsequent branch state; endpoint fee growth.','Conditional historical execution; no alternative consensus-valid fork, LP payout or causal attribution.','','Strict evidence: ACTUAL 321/321 PASS; COUNTERFACTUAL 321/321 PASS','Detailed machine-readable evidence: work/results/','RESULT: PASS']
console.log(lines.join('\n'))
write('results/terminal-summary.json', lines)
