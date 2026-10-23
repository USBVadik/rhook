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
  exportBranchEvidenceTranscript,
  isBranchEvidenceTranscriptVerified,
  isEnvelopeEvidenceVerified,
  makeEndpoint,
  makeEnvelopeIdentity,
  makeExtraction,
  makeGasAndFee,
  parseAddress,
  parseBlockNumber,
  parseDigest,
  parseHash32,
  parseHexBytes,
  parseQuantity,
  present,
  sourceReturnWord,
  sourceStorageSlot,
  validationValid,
  verifyBranchEvidenceTranscript,
  verifyBranchEvidenceTranscriptJson,
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

function mixedObservations({ callUnchanged = false, envelopeCount = 1 } = {}) {
  const actualEnvelopes = Array.from({ length: envelopeCount }, (_, index) => envelope({ index }))
  const counterfactualEnvelopes = Array.from({ length: envelopeCount }, (_, index) => envelope({ index, successor: digest('24') }))
  const address = parseAddress(`0x${'ab'.repeat(20)}`)
  const semanticPairs = actualEnvelopes.flatMap((actual, index) => [
    { selector: '0x', source: sourceStorageSlot(parseHash32(hash32('00'))) },
    { selector: '0x12345678', source: sourceReturnWord(parseHash32(hash32('00'))) },
  ].map(({ selector, source }) => {
    const endpoint = makeEndpoint(address, parseHexBytes(selector))
    const extraction = (postState, value) => makeExtraction({
      endpoint,
      postState: parseDigest(postState),
      recordIdentity: createCommitment(digest('61'), 'observed-value'),
      source,
      presence: present(parseHash32(hash32(value))),
    })
    return {
      envelopeIndex: parseQuantity(String(index)),
      actual: extraction(actual.body.execution.successorStateCommitment, '05'),
      counterfactual: extraction(counterfactualEnvelopes[index].body.execution.successorStateCommitment,
        callUnchanged && selector !== '0x' ? '05' : '06'),
    }
  }))
  return {
    branches: { actual: createCommitment(digest('aa'), 'actual-branch'), counterfactual: createCommitment(digest('bb'), 'counterfactual-branch') },
    intervention: { kind: 'REPLACE_COMMITTED_INPUT', target: identity(0) },
    actualEnvelopes,
    counterfactualEnvelopes,
    semanticPairs,
  }
}

test('mixed storage and call observations use the strict code-unit order', () => {
  const transcript = buildBranchEvidenceTranscript(mixedObservations())
  const semantic = transcript.body.semanticEvidence
  assert.deepEqual(semantic.map((item) => item.actual.source.kind), ['RETURN_WORD', 'STORAGE_SLOT'])
  assert.equal(verifyBranchEvidenceTranscript(transcript).valid, true)
  assert.deepEqual(transcript.body.divergence.semantic, {
    status: 'DIVERGED', envelopeIndex: 0, slot: semantic[0].slot, verdict: 'VALUE_CHANGED',
  })
  assert.equal(verifyBranchEvidenceTranscriptJson(exportBranchEvidenceTranscript(transcript)).valid, true)
})

test('first semantic divergence skips an equal call before a changed storage observation', () => {
  const transcript = buildBranchEvidenceTranscript(mixedObservations({ callUnchanged: true }))
  const semantic = transcript.body.semanticEvidence
  assert.deepEqual(semantic.map((item) => item.verdict), ['EQUAL', 'VALUE_CHANGED'])
  assert.deepEqual(transcript.body.divergence.semantic, {
    status: 'DIVERGED', envelopeIndex: 0, slot: semantic[1].slot, verdict: 'VALUE_CHANGED',
  })
  assert.equal(verifyBranchEvidenceTranscript(transcript).valid, true)
})

test('semantic input permutations preserve envelope priority, bytes and commitment', () => {
  const input = mixedObservations({ envelopeCount: 2 })
  const expected = buildBranchEvidenceTranscript(input)
  const bytes = exportBranchEvidenceTranscript(expected)
  assert.deepEqual(expected.body.semanticEvidence.map((item) => [item.envelopeIndex, item.actual.source.kind]), [
    [0, 'RETURN_WORD'], [0, 'STORAGE_SLOT'], [1, 'RETURN_WORD'], [1, 'STORAGE_SLOT'],
  ])
  for (const first of input.semanticPairs) {
    for (const second of input.semanticPairs.filter((item) => item !== first)) {
      const remaining = input.semanticPairs.filter((item) => item !== first && item !== second)
      for (const tail of [remaining, [...remaining].reverse()]) {
        const semanticPairs = [first, second, ...tail]
        const transcript = buildBranchEvidenceTranscript({ ...input, semanticPairs })
        assert.deepEqual(semanticPairs, [first, second, ...tail])
        assert.equal(exportBranchEvidenceTranscript(transcript), bytes)
        assert.deepEqual(transcript.transcriptCommitment, expected.transcriptCommitment)
        assert.equal(verifyBranchEvidenceTranscript(transcript).valid, true)
      }
    }
  }
})
