import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DIFF,
  diffExtractions,
  isEnvelopeEvidenceVerified,
  verifyEnvelopeEvidence,
} from '../../core/src/index.mjs'
import {
  buildExecutedEnvelopeEvidence,
  buildInvalidatedEnvelopeEvidence,
  buildSemanticExtractionFromRuntimeObservation,
  buildStateBoundary,
  canonicalRuntimeJson,
  runtimeDigest,
  verifyStateBoundary,
} from '../src/index.mjs'

const root = (pair) => `0x${pair.repeat(32)}`
const address = (pair) => `0x${pair.repeat(20)}`
const frame = (overrides = {}) => ({
  blockNumber: '1000',
  transactionIndex: '0',
  transactionHash: root('11'),
  executedTransactionHash: root('11'),
  gasLimit: '50000',
  gasUsed: '21000',
  feePaid: '21000',
  predecessorStateRoot: root('21'),
  successorStateRoot: root('22'),
  receiptStatus: 1,
  exception: null,
  returnData: '0x',
  logs: [],
  ...overrides,
})

function storageObservation(value, presence = 'PRESENT') {
  return {
    endpointAddress: address('aa'),
    selector: '0x',
    source: { kind: 'STORAGE_SLOT', slot: root('00') },
    presence,
    ...(presence === 'PRESENT' ? { value } : { reason: 'ACCOUNT_OR_SLOT_ABSENT' }),
  }
}

test('native Ethereum state roots are deterministically bound without mislabelling the raw root as SHA-256', () => {
  const first = buildStateBoundary(root('12'))
  const second = buildStateBoundary(root('12'))
  assert.deepEqual(first, second)
  assert.equal(first.algorithm, 'ETHEREUM_STATE_ROOT_KECCAK256')
  assert.equal(first.stateRoot, root('12'))
  assert.equal(first.commitment.kind, 'Digest')
  assert.equal(verifyStateBoundary(first), true)
  assert.notEqual(first.commitment.value, first.stateRoot.slice(2))
})

test('successful execution becomes independently verified envelope evidence', () => {
  const result = buildExecutedEnvelopeEvidence(frame())
  assert.equal(result.evidence.body.execution.lifecycle, 'SUCCESS')
  assert.equal(result.evidence.body.execution.gasAndFee.gasUsed, '21000')
  assert.equal(result.evidence.body.execution.gasAndFee.feePaid, '21000')
  assert.equal(isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(result.evidence)), true)
  assert.equal(result.evidence.body.predecessorStateCommitment, result.predecessor.commitment.value)
  assert.equal(result.evidence.body.execution.successorStateCommitment, result.successor.commitment.value)
})

test('actual EVM exception and receipt status become explicit REVERT evidence', () => {
  const result = buildExecutedEnvelopeEvidence(frame({ receiptStatus: 0, exception: 'revert', gasUsed: '23117', feePaid: '23117', returnData: '0x08c379a0' }))
  assert.equal(result.evidence.body.execution.lifecycle, 'REVERT')
  assert.equal(result.evidence.body.execution.exception.kind, 'REVERT')
  assert.equal(result.evidence.body.execution.exception.classification, 'EVM_REVERT')
  assert.equal(result.evidence.body.execution.exception.dataCommitment.presence, 'PRESENT')
  assert.equal(isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(result.evidence)), true)
})

test('pre-execution validation failure emits invalidation evidence with unchanged state and zero accounting', () => {
  const result = buildInvalidatedEnvelopeEvidence({
    blockNumber: '1000', transactionIndex: '1', transactionHash: root('13'), gasLimit: '50000', stateRoot: root('21'), classification: 'nonce too high',
  })
  assert.equal(result.evidence.body.execution.lifecycle, 'PRE_EXECUTION_INVALIDATED')
  assert.equal(result.evidence.body.execution.executed, false)
  assert.equal(result.evidence.body.execution.gasAndFee.gasUsed, '0')
  assert.equal(result.evidence.body.predecessorStateCommitment, result.evidence.body.execution.successorStateCommitment)
  assert.equal(isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(result.evidence)), true)
})

test('receipt/exception contradictions and undefined raw values fail closed', () => {
  assert.throws(() => buildExecutedEnvelopeEvidence(frame({ receiptStatus: 1, exception: 'revert' })), (error) => error.code === 'CONTRADICTORY_RUNTIME_LIFECYCLE')
  assert.throws(() => buildExecutedEnvelopeEvidence(frame({ gasUsed: undefined })), /UNDEFINED_RUNTIME_VALUE/)
  assert.throws(() => buildExecutedEnvelopeEvidence(frame({ transactionHash: undefined })), /INVALID_RUNTIME_HEX|UNDEFINED_RUNTIME_VALUE/)
})

test('semantic observation is converted once and bound to exact envelope successor state', () => {
  const run = buildExecutedEnvelopeEvidence(frame())
  const extraction = buildSemanticExtractionFromRuntimeObservation({
    observation: storageObservation(root('01')),
    postStateBoundary: run.successor,
    envelopeEvidence: run.evidence,
  })
  assert.equal(extraction.postStateDigest, run.evidence.body.execution.successorStateCommitment)
  assert.equal(extraction.endpoint.address, address('aa'))
  assert.equal(extraction.source.kind, 'STORAGE_SLOT')
  assert.equal(extraction.presence, 'PRESENT')
  assert.equal(extraction.value.value, root('01'))
})

test('stale or detached semantic state binding is rejected', () => {
  const run = buildExecutedEnvelopeEvidence(frame())
  const detached = buildStateBoundary(root('99'))
  assert.throws(() => buildSemanticExtractionFromRuntimeObservation({
    observation: storageObservation(root('01')),
    postStateBoundary: detached,
    envelopeEvidence: run.evidence,
  }), (error) => error.code === 'SEMANTIC_STATE_BINDING_MISMATCH')
})

test('valid absence remains distinct from a present explicit zero storage word', () => {
  const run = buildExecutedEnvelopeEvidence(frame())
  const presentZero = buildSemanticExtractionFromRuntimeObservation({ observation: storageObservation(root('00')), postStateBoundary: run.successor, envelopeEvidence: run.evidence })
  const absent = buildSemanticExtractionFromRuntimeObservation({ observation: storageObservation(null, 'VALID_ABSENT'), postStateBoundary: run.successor, envelopeEvidence: run.evidence })
  assert.equal(diffExtractions(presentZero, absent).verdict, DIFF.PRESENCE_CHANGED)
})

test('canonical runtime commitments are insertion-order stable and reject undefined', () => {
  assert.equal(canonicalRuntimeJson({ z: 1, a: { y: true, b: 'X' } }), canonicalRuntimeJson({ a: { b: 'X', y: true }, z: 1 }))
  assert.equal(runtimeDigest('TEST', { b: 2, a: 1 }), runtimeDigest('TEST', { a: 1, b: 2 }))
  assert.throws(() => canonicalRuntimeJson({ value: undefined }), /UNDEFINED_RUNTIME_VALUE/)
})
