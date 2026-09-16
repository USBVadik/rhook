import { readFile } from 'node:fs/promises'

import {
  parseStrictEvidenceJson,
  verifyBranchEvidenceTranscriptJson,
} from '../core/src/index.mjs'

const text = await readFile(new URL('../examples/minimal/transcript.json', import.meta.url), 'utf8')
const verification = verifyBranchEvidenceTranscriptJson(text)
if (!verification.valid) throw new Error(`TRANSCRIPT_INVALID: ${JSON.stringify(verification.findings)}`)
const transcript = parseStrictEvidenceJson(text)
const transitions = new Map(transcript.body.changedTransitions.map((item) => [item.envelopeIndex, item]))
const semantics = new Map(transcript.body.semanticEvidence.map((item) => [item.envelopeIndex, item]))
const short = (digest) => `${digest.slice(0, 12)}…${digest.slice(-8)}`

console.log('RHOOK minimal branch transcript')
for (let index = 0; index < transcript.body.coverage.declaredEnvelopes; index += 1) {
  const transition = transitions.get(index)
  if (!transition) continue
  const actual = transition.actual.body
  const counterfactual = transition.counterfactual.body
  const stateChanged = actual.execution.successorStateCommitment !== counterfactual.execution.successorStateCommitment
  console.log(`\nEnvelope ${index} (${actual.envelope.blockNumber}:${actual.envelope.transactionIndex})`)
  console.log(`  lifecycle  ${actual.execution.lifecycle} -> ${counterfactual.execution.lifecycle}`)
  console.log(`  gas        ${actual.execution.gasAndFee.gasUsed} -> ${counterfactual.execution.gasAndFee.gasUsed}`)
  console.log(`  state      ${short(actual.execution.successorStateCommitment)} -> ${short(counterfactual.execution.successorStateCommitment)}${stateChanged ? '  [diverged]' : ''}`)
  const semantic = semantics.get(index)
  if (semantic) console.log(`  semantic   ${semantic.actual.canonicalValue} -> ${semantic.counterfactual.canonicalValue}  [${semantic.verdict}]`)
}
console.log('\nFirst divergence')
console.log(`  state      envelope ${transcript.body.divergence.stateCommitment.envelopeIndex}`)
console.log(`  lifecycle  envelope ${transcript.body.divergence.lifecycle.envelopeIndex}`)
console.log(`  semantic   envelope ${transcript.body.divergence.semantic.envelopeIndex}`)
