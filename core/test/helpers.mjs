import { readFile } from 'node:fs/promises'

import { sha256Canonical } from '../src/strict-common.mjs'

const fixtureUrl = new URL('../../examples/minimal/transcript.json', import.meta.url)

export async function frozenTranscript() {
  return JSON.parse(await readFile(fixtureUrl, 'utf8'))
}

export const clone = (value) => JSON.parse(JSON.stringify(value))

export function recomputeEnvelope(record) {
  record.receipt.digest = sha256Canonical(record.body)
  return record
}

export function recomputeTranscript(transcript) {
  transcript.transcriptCommitment.digest = sha256Canonical(transcript.body)
  return transcript
}

export function recomputeAll(transcript) {
  for (const transition of transcript.body.changedTransitions) {
    recomputeEnvelope(transition.actual)
    recomputeEnvelope(transition.counterfactual)
  }
  return recomputeTranscript(transcript)
}

export function findingCodes(result) {
  return result.findings.map((finding) => finding.code)
}

export function withCompactEntry(transcript, envelopeIndex = 0) {
  const position = transcript.body.changedTransitions.findIndex((item) => item.envelopeIndex === envelopeIndex)
  if (position < 0) throw new Error(`missing changed transition ${envelopeIndex}`)
  const [transition] = transcript.body.changedTransitions.splice(position, 1)
  const evidence = transition.actual
  transcript.body.unchangedCommitments.push({
    envelopeIndex,
    envelope: clone(evidence.body.envelope),
    actualReceipt: evidence.receipt.digest,
    counterfactualReceipt: evidence.receipt.digest,
    actualPostStateCommitment: evidence.body.execution.successorStateCommitment,
    counterfactualPostStateCommitment: evidence.body.execution.successorStateCommitment,
  })
  transcript.body.unchangedCommitments.sort((left, right) => left.envelopeIndex - right.envelopeIndex)
  transcript.body.coverage.changedEnvelopes -= 1
  transcript.body.coverage.unchangedEnvelopes += 1
  return transcript.body.unchangedCommitments.find((item) => item.envelopeIndex === envelopeIndex)
}
