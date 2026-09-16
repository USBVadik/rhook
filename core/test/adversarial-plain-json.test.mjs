import assert from 'node:assert/strict'
import test from 'node:test'

import {
  verifyBranchEvidenceTranscript,
  verifyEnvelopeEvidence,
} from '../src/index.mjs'
import {
  clone,
  findingCodes,
  frozenTranscript,
  recomputeAll,
  recomputeEnvelope,
  recomputeTranscript,
  withCompactEntry,
} from './helpers.mjs'

async function forged(mutator, { envelope = null, allEnvelopes = false } = {}) {
  const transcript = clone(await frozenTranscript())
  mutator(transcript)
  if (allEnvelopes) recomputeAll(transcript)
  else {
    if (envelope) recomputeEnvelope(envelope(transcript))
    recomputeTranscript(transcript)
  }
  return transcript
}

function assertInvalid(result, code) {
  assert.equal(result.valid, false)
  assert.ok(findingCodes(result).includes(code), JSON.stringify(result.findings))
}

test('probe 1: malformed branch digest remains invalid after transcript commitment recomputation', async () => {
  const value = await forged((transcript) => { transcript.body.branches.actual.digest = 'not-a-digest' })
  assertInvalid(verifyBranchEvidenceTranscript(value), 'INVALID_BRANCH_COMMITMENT')
})

test('probe 2: malformed semantic endpoint remains invalid after transcript commitment recomputation', async () => {
  const value = await forged((transcript) => { transcript.body.semanticEvidence[0].actual.endpoint.address = 'not-an-address' })
  assertInvalid(verifyBranchEvidenceTranscript(value), 'INVALID_SEMANTIC_ENDPOINT')
})

test('probe 3: arbitrary semanticChangeCommitments object fails both strict verifiers after all commitments are recomputed', async () => {
  const value = await forged((transcript) => { transcript.body.changedTransitions[0].actual.body.semanticChangeCommitments = [{ garbage: true }] }, { envelope: (transcript) => transcript.body.changedTransitions[0].actual })
  assertInvalid(verifyEnvelopeEvidence(value.body.changedTransitions[0].actual), 'INVALID_SEMANTIC_CHANGE_COMMITMENT_SHAPE')
  assertInvalid(verifyBranchEvidenceTranscript(value), 'INVALID_SEMANTIC_CHANGE_COMMITMENT_SHAPE')
})

test('unknown top-level, body, envelope, compact, semantic, and commitment fields fail closed', async () => {
  const mutations = [
    (t) => { t.unknown = true },
    (t) => { t.body.unknown = true },
    (t) => { t.body.changedTransitions[0].actual.body.unknown = true },
    (t) => { withCompactEntry(t).unknown = true },
    (t) => { t.body.semanticEvidence[0].actual.endpoint.unknown = true },
    (t) => { t.body.branches.actual.algorithm = 'sha256' },
  ]
  for (const mutate of mutations) {
    const value = await forged(mutate, { allEnvelopes: true })
    assert.equal(verifyBranchEvidenceTranscript(value).valid, false)
  }
})

test('invalid envelope hashes and quantities fail despite consistent receipt/transcript hashes', async () => {
  const mutations = [
    (e) => { e.body.envelope.transactionHash = '0x12' },
    (e) => { e.body.envelope.blockNumber = 100 },
    (e) => { e.body.execution.gasAndFee.gasUsed = '01' },
    (e) => { e.body.execution.logsCommitment = 'z'.repeat(64) },
    (e) => { e.body.execution.successorStateCommitment = 'f'.repeat(63) },
  ]
  for (const mutate of mutations) {
    const value = await forged((t) => mutate(t.body.changedTransitions[0].actual), { envelope: (t) => t.body.changedTransitions[0].actual })
    assert.equal(verifyBranchEvidenceTranscript(value).valid, false)
  }
})

test('semantic malformed hash, quantity, selector, source locator, and record identity fail after rehash', async () => {
  const mutations = [
    (s) => { s.actual.endpoint.selector = '0x1234' },
    (s) => { s.actual.source.slot = '0x12' },
    (s) => { s.actual.recordIdentity.digest = 'not-a-digest' },
    (s) => { s.actual.postStateCommitment = 'z'.repeat(64) },
    (s) => { s.actual.canonicalValue = '01' },
  ]
  for (const mutate of mutations) {
    const value = await forged((t) => mutate(t.body.semanticEvidence[0]))
    assert.equal(verifyBranchEvidenceTranscript(value).valid, false)
  }
})

test('duplicate, reordered, skipped, negative, string, and out-of-range envelope indices fail closed', async () => {
  const mutations = [
    (t) => { t.body.changedTransitions[1].envelopeIndex = t.body.changedTransitions[0].envelopeIndex },
    (t) => { t.body.changedTransitions.reverse() },
    (t) => { withCompactEntry(t).envelopeIndex = 2 },
    (t) => { t.body.changedTransitions[0].envelopeIndex = -1 },
    (t) => { t.body.changedTransitions[0].envelopeIndex = '1' },
    (t) => { t.body.changedTransitions.at(-1).envelopeIndex = 99 },
  ]
  for (const mutate of mutations) {
    const value = await forged(mutate)
    assert.equal(verifyBranchEvidenceTranscript(value).valid, false)
  }
})

test('duplicate semantic envelope/slot identity fails with a recomputed transcript commitment', async () => {
  const value = await forged((transcript) => { transcript.body.semanticEvidence.push(clone(transcript.body.semanticEvidence[0])) })
  assertInvalid(verifyBranchEvidenceTranscript(value), 'DUPLICATE_SEMANTIC_SLOT')
})

test('invalid PRESENT, VALID_ABSENT, and NOT_COMPUTED value combinations fail closed', async () => {
  const mutations = [
    (side) => { side.presence = 'VALID_ABSENT'; side.presenceReason = 'ABSENT'; },
    (side) => { side.presence = 'NOT_COMPUTED'; side.presenceReason = 'NOT_COMPUTED'; },
    (side) => { side.presenceReason = 'SHOULD_NOT_EXIST'; },
    (side) => { side.valueKind = null },
    (side) => { side.canonicalValue = null },
  ]
  for (const mutate of mutations) {
    const value = await forged((transcript) => mutate(transcript.body.semanticEvidence[0].actual))
    assert.equal(verifyBranchEvidenceTranscript(value).valid, false)
  }
})

test('malformed compact receipt, post-state, identity, and false unchanged claims fail after rehash', async () => {
  const mutations = [
    (entry) => { entry.actualReceipt = 'not-a-digest' },
    (entry) => { entry.counterfactualPostStateCommitment = 'f'.repeat(63) },
    (entry) => { entry.envelope.transactionHash = '0x12' },
    (entry) => { entry.counterfactualReceipt = 'f'.repeat(64) },
    (entry) => { entry.counterfactualPostStateCommitment = 'e'.repeat(64) },
  ]
  for (const mutate of mutations) {
    const value = await forged((transcript) => mutate(withCompactEntry(transcript)))
    assert.equal(verifyBranchEvidenceTranscript(value).valid, false)
  }
})

test('unordered and duplicate semantic-change commitments fail even with valid shapes and recomputed receipts', async () => {
  const digestA = 'a'.repeat(64)
  const digestB = 'b'.repeat(64)
  const unordered = await forged((transcript) => { transcript.body.changedTransitions[0].actual.body.semanticChangeCommitments = [{ domain: 'z-change', digest: digestB }, { domain: 'a-change', digest: digestA }] }, { envelope: (t) => t.body.changedTransitions[0].actual })
  assertInvalid(verifyEnvelopeEvidence(unordered.body.changedTransitions[0].actual), 'NONCANONICAL_SEMANTIC_CHANGE_ORDER')
  const duplicate = await forged((transcript) => { transcript.body.changedTransitions[0].actual.body.semanticChangeCommitments = [{ domain: 'a-change', digest: digestA }, { domain: 'a-change', digest: digestA }] }, { envelope: (t) => t.body.changedTransitions[0].actual })
  assertInvalid(verifyEnvelopeEvidence(duplicate.body.changedTransitions[0].actual), 'DUPLICATE_SEMANTIC_CHANGE_COMMITMENT')
})

test('impossible lifecycle combinations fail after nested and top-level commitments are recomputed', async () => {
  const mutations = [
    (e) => { e.body.execution.executed = false },
    (e) => { e.body.validation.status = 'INVALID' },
    (e) => { e.body.execution.exception.kind = 'REVERT'; e.body.execution.exception.classification = 'EVM_REVERT' },
  ]
  for (const mutate of mutations) {
    const value = await forged((t) => mutate(t.body.changedTransitions[0].actual), { envelope: (t) => t.body.changedTransitions[0].actual })
    assertInvalid(verifyBranchEvidenceTranscript(value), 'IMPOSSIBLE_ENVELOPE_EVIDENCE')
  }
})

test('mismatched nested receipts fail before the recomputed transcript commitment can legitimize them', async () => {
  const value = await forged((transcript) => { transcript.body.changedTransitions[0].actual.body.execution.gasAndFee.feePaid = '1' })
  assertInvalid(verifyBranchEvidenceTranscript(value), 'ENVELOPE_RECEIPT_MISMATCH')
})

test('malformed schema and transcript commitment algorithm fail closed', async () => {
  const wrongSchema = await forged((t) => { t.body.schema = 'generic-ce-branch-evidence-transcript/999' })
  assertInvalid(verifyBranchEvidenceTranscript(wrongSchema), 'INVALID_TRANSCRIPT_SCHEMA')
  const wrongAlgorithm = await forged((t) => { t.transcriptCommitment.algorithm = 'keccak256' })
  assertInvalid(verifyBranchEvidenceTranscript(wrongAlgorithm), 'INVALID_TRANSCRIPT_COMMITMENT')
})

test('numeric JSON values cannot coerce into canonical decimal strings', async () => {
  const transcript = clone(await frozenTranscript())
  const envelope = transcript.body.changedTransitions[0].actual
  envelope.body.envelope.blockNumber = 100
  recomputeEnvelope(envelope)
  assertInvalid(verifyEnvelopeEvidence(envelope), 'INVALID_ENVELOPE_IDENTITY')

  const gasTranscript = clone(await frozenTranscript())
  const gasEnvelope = gasTranscript.body.changedTransitions[0].actual
  gasEnvelope.body.execution.gasAndFee.gasUsed = 21000
  recomputeEnvelope(gasEnvelope)
  assertInvalid(verifyEnvelopeEvidence(gasEnvelope), 'INVALID_GAS_AND_FEE')

  const semanticTranscript = clone(await frozenTranscript())
  semanticTranscript.body.semanticEvidence[0].actual.canonicalValue = 0
  recomputeTranscript(semanticTranscript)
  assertInvalid(verifyBranchEvidenceTranscript(semanticTranscript), 'INVALID_CANONICAL_SEMANTIC_VALUE')
})

test('self-consistent forged validation and exception reason states fail closed', async () => {
  const mutations = [
    (e) => { e.body.validation.classification = 'SOMETHING_ELSE' },
    (e) => { e.body.execution.exception.dataCommitment.reason = 'SOMETHING_ELSE' },
  ]
  for (const mutate of mutations) {
    const value = await forged((t) => mutate(t.body.changedTransitions[0].actual), { envelope: (t) => t.body.changedTransitions[0].actual })
    assertInvalid(verifyEnvelopeEvidence(value.body.changedTransitions[0].actual), 'IMPOSSIBLE_ENVELOPE_EVIDENCE')
  }
  const transcript = clone(await frozenTranscript())
  const invalidated = clone(transcript.body.changedTransitions[0].actual)
  invalidated.body.validation.status = 'INVALID'
  invalidated.body.validation.classification = 'NONCE_TOO_HIGH'
  invalidated.body.execution.lifecycle = 'PRE_EXECUTION_INVALIDATED'
  invalidated.body.execution.executed = false
  invalidated.body.execution.exception.kind = 'VALIDATION'
  invalidated.body.execution.exception.classification = 'NONCE_TOO_HIGH'
  invalidated.body.execution.exception.dataCommitment = { presence: 'VALID_ABSENT', reason: 'NOT_EXECUTED' }
  invalidated.body.execution.gasAndFee.gasUsed = '0'
  invalidated.body.execution.gasAndFee.feePaid = '0'
  invalidated.body.execution.successorStateCommitment = invalidated.body.predecessorStateCommitment
  recomputeEnvelope(invalidated)
  assert.equal(verifyEnvelopeEvidence(invalidated).valid, true)
  invalidated.body.execution.exception.classification = 'DIFFERENT_VALIDATION_REASON'
  recomputeEnvelope(invalidated)
  assertInvalid(verifyEnvelopeEvidence(invalidated), 'IMPOSSIBLE_ENVELOPE_EVIDENCE')
})

test('chronologically reordered envelope identities fail even when indices and commitments remain self-consistent', async () => {
  const value = await forged((transcript) => {
    const transition = transcript.body.changedTransitions.find((item) => item.envelopeIndex === 1)
    transition.actual.body.envelope.blockNumber = '99'
    transition.counterfactual.body.envelope.blockNumber = '99'
  }, { allEnvelopes: true })
  assertInvalid(verifyBranchEvidenceTranscript(value), 'NONCANONICAL_ENVELOPE_IDENTITY_ORDER')
})
