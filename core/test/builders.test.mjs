import assert from 'node:assert/strict'
import test from 'node:test'

import {
  ENVELOPE_LIFECYCLE,
  branchEvidenceTranscriptHash,
  buildBranchEvidenceTranscript,
  buildEnvelopeEvidence,
  createCommitment,
  exceptionNone,
  exceptionRevert,
  isBranchEvidenceTranscriptVerified,
  isEnvelopeEvidenceVerified,
  makeEnvelopeIdentity,
  makeGasAndFee,
  parseBlockNumber,
  parseDigest,
  parseHash32,
  parseQuantity,
  validationValid,
  verifyBranchEvidenceTranscript,
  verifyEnvelopeEvidence,
} from '../src/index.mjs'
import { recomputeEnvelope } from './helpers.mjs'

const digest = (pair) => pair.repeat(32)
const hash32 = (pair) => `0x${digest(pair)}`
const identity = (index) => makeEnvelopeIdentity({ blockNumber: parseBlockNumber('100'), transactionIndex: parseQuantity(String(index)), transactionHash: parseHash32(hash32(index === 0 ? '11' : '12')) })

function envelope({ index, lifecycle = 'SUCCESS', predecessor = digest('21'), successor = digest('22') }) {
  return buildEnvelopeEvidence({
    envelope: identity(index),
    predecessorStateCommitment: parseDigest(predecessor),
    validation: validationValid(),
    lifecycle,
    exception: lifecycle === ENVELOPE_LIFECYCLE.SUCCESS ? exceptionNone() : exceptionRevert('EVM_REVERT'),
    gasAndFee: makeGasAndFee({ gasLimit: parseQuantity('50000'), gasUsed: parseQuantity(lifecycle === ENVELOPE_LIFECYCLE.SUCCESS ? '21000' : '23000'), feePaid: parseQuantity(lifecycle === ENVELOPE_LIFECYCLE.SUCCESS ? '21000' : '23000') }),
    logsCommitment: parseDigest(digest('31')),
    successorStateCommitment: parseDigest(successor),
    executionResultCommitment: parseDigest(lifecycle === ENVELOPE_LIFECYCLE.SUCCESS ? digest('41') : digest('42')),
  })
}

test('envelope builder preserves evidence semantics with a strict postcondition', () => {
  const record = envelope({ index: 0 })
  assert.equal(record.body.schema, 'generic-ce-envelope-evidence/2')
  assert.equal(record.receipt.domain, 'rhook/gcec-02/envelope-evidence/v2')
  assert.equal(isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(record)), true)
})

test('branch builder preserves transcript semantics and strictly verifies its output', () => {
  const actual = [envelope({ index: 0, successor: digest('22') }), envelope({ index: 1, predecessor: digest('22'), successor: digest('23') })]
  const counterfactual = [envelope({ index: 0, successor: digest('24') }), envelope({ index: 1, lifecycle: 'REVERT', predecessor: digest('24'), successor: digest('25') })]
  const transcript = buildBranchEvidenceTranscript({
    branches: { actual: createCommitment(digest('aa'), 'actual-branch'), counterfactual: createCommitment(digest('bb'), 'counterfactual-branch') },
    intervention: { kind: 'REPLACE_COMMITTED_INPUT', target: identity(0) },
    actualEnvelopes: actual,
    counterfactualEnvelopes: counterfactual,
    semanticPairs: [],
  })
  assert.equal(isBranchEvidenceTranscriptVerified(verifyBranchEvidenceTranscript(transcript)), true)
  assert.equal(transcript.body.divergence.stateCommitment.envelopeIndex, 0)
  assert.equal(transcript.body.divergence.lifecycle.envelopeIndex, 1)
  assert.equal(branchEvidenceTranscriptHash(transcript), transcript.transcriptCommitment.digest)
})

test('branch builder refuses malformed input even with a recomputed receipt', () => {
  const valid = envelope({ index: 0 })
  const malformed = JSON.parse(JSON.stringify(valid))
  malformed.body.semanticChangeCommitments = [{ garbage: true }]
  recomputeEnvelope(malformed)
  assert.throws(() => buildBranchEvidenceTranscript({
    branches: { actual: createCommitment(digest('aa'), 'actual-branch'), counterfactual: createCommitment(digest('bb'), 'counterfactual-branch') },
    intervention: { kind: 'REPLACE_COMMITTED_INPUT', target: identity(0) },
    actualEnvelopes: [malformed],
    counterfactualEnvelopes: [valid],
    semanticPairs: [],
  }), (error) => error.code === 'UNVERIFIED_ENVELOPE_EVIDENCE')
})
