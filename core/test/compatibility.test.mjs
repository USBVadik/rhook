import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'

import {
  branchEvidenceTranscriptHash,
  exportBranchEvidenceTranscript,
  exportEnvelopeEvidence,
  isBranchEvidenceTranscriptVerified,
  isEnvelopeEvidenceVerified,
  verifyBranchEvidenceTranscript,
  verifyEnvelopeEvidence,
} from '../src/index.mjs'
import { clone, frozenTranscript, recomputeEnvelope, recomputeTranscript } from './helpers.mjs'

test('the included transcript remains valid under strict verification', async () => {
  const transcript = await frozenTranscript()
  const result = verifyBranchEvidenceTranscript(transcript)
  assert.equal(isBranchEvidenceTranscriptVerified(result), true)
  assert.equal(branchEvidenceTranscriptHash(transcript), transcript.transcriptCommitment.digest)
})

test('every full changed-envelope record independently passes strict verification', async () => {
  const transcript = await frozenTranscript()
  for (const transition of transcript.body.changedTransitions) {
    for (const record of [transition.actual, transition.counterfactual]) assert.equal(isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(record)), true)
  }
})

test('strict exports are canonical, newline-terminated, and byte-stable', async () => {
  const transcript = await frozenTranscript()
  const first = exportBranchEvidenceTranscript(transcript)
  const second = exportBranchEvidenceTranscript(JSON.parse(first))
  assert.equal(first, second)
  assert.equal(first.endsWith('\n'), true)
  const envelope = transcript.body.changedTransitions[0].actual
  assert.equal(exportEnvelopeEvidence(envelope), exportEnvelopeEvidence(JSON.parse(exportEnvelopeEvidence(envelope))))
})

test('strict schema failure short-circuits before commitment and divergence stages', async () => {
  const transcript = clone(await frozenTranscript())
  transcript.body.semanticEvidence[0].actual.endpoint.address = 'not-an-address'
  transcript.transcriptCommitment.digest = '0'.repeat(64)
  transcript.body.divergence = { lifecycle: { status: 'NONE' }, stateCommitment: { status: 'NONE' }, semantic: { status: 'NONE' } }
  const result = verifyBranchEvidenceTranscript(transcript)
  assert.equal(result.valid, false)
  assert.deepEqual(result.findings.map((finding) => finding.code), ['INVALID_SEMANTIC_ENDPOINT'])
})

test('valid non-empty semantic-change commitment shape remains compatible', async () => {
  const transcript = clone(await frozenTranscript())
  const envelope = transcript.body.changedTransitions[0].actual
  envelope.body.semanticChangeCommitments = [{ domain: 'semantic-change', digest: 'a'.repeat(64) }]
  recomputeEnvelope(envelope)
  recomputeTranscript(transcript)
  assert.equal(verifyEnvelopeEvidence(envelope).valid, true)
  assert.equal(verifyBranchEvidenceTranscript(transcript).valid, true)
})

test('present explicit zero and valid absence remain a real semantic presence divergence', async () => {
  const transcript = clone(await frozenTranscript())
  const semantic = transcript.body.semanticEvidence[0]
  semantic.actual.canonicalValue = `0x${'00'.repeat(32)}`
  semantic.counterfactual.presence = 'VALID_ABSENT'
  semantic.counterfactual.presenceReason = 'VALID_ABSENCE'
  semantic.counterfactual.valueKind = null
  semantic.counterfactual.canonicalValue = null
  semantic.verdict = 'PRESENCE_CHANGED'
  transcript.body.divergence.semantic = { status: 'DIVERGED', envelopeIndex: semantic.envelopeIndex, slot: semantic.slot, verdict: 'PRESENCE_CHANGED' }
  recomputeTranscript(transcript)
  assert.equal(verifyBranchEvidenceTranscript(transcript).valid, true)
})

test('commitment mismatch is rejected after otherwise strict schema validation', async () => {
  const transcript = clone(await frozenTranscript())
  transcript.transcriptCommitment.digest = '0'.repeat(64)
  const result = verifyBranchEvidenceTranscript(transcript)
  assert.equal(result.valid, false)
  assert.deepEqual(result.findings.map((finding) => finding.code), ['TRANSCRIPT_COMMITMENT_MISMATCH'])
})

test('verification is deterministic for identical plain JSON', async () => {
  const transcript = await frozenTranscript()
  const bytes = JSON.stringify(transcript)
  const results = Array.from({ length: 3 }, () => verifyBranchEvidenceTranscript(JSON.parse(bytes)))
  assert.deepEqual(results[0], results[1])
  assert.deepEqual(results[1], results[2])
  assert.equal(createHash('sha256').update(exportBranchEvidenceTranscript(transcript)).digest('hex'), createHash('sha256').update(exportBranchEvidenceTranscript(transcript)).digest('hex'))
})

test('semantic record domains allow generic slash paths but reject malformed segments', async () => {
  const valid = clone(await frozenTranscript())
  valid.body.semanticEvidence[0].actual.recordIdentity.domain = 'rhook/token-balance/1'
  recomputeTranscript(valid)
  assert.equal(verifyBranchEvidenceTranscript(valid).valid, true)

  for (const domain of ['rhook//record/1', 'rhook/record/', 'rhook\\record']) {
    const malformed = clone(await frozenTranscript())
    malformed.body.semanticEvidence[0].actual.recordIdentity.domain = domain
    recomputeTranscript(malformed)
    assert.equal(verifyBranchEvidenceTranscript(malformed).valid, false)
  }
})
