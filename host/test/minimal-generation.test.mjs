import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  parseStrictEvidenceJson,
  verifyBranchEvidenceTranscriptJson,
} from '../../core/src/index.mjs'
import { generateMinimalTranscript } from '../../examples/minimal/generate.mjs'

test('public generator executes both branches and reproduces the pinned transcript byte-for-byte', async () => {
  const generated = await generateMinimalTranscript()
  const pinned = await readFile(new URL('../../examples/minimal/transcript.json', import.meta.url), 'utf8')
  assert.equal(generated.text, pinned)
  assert.equal(verifyBranchEvidenceTranscriptJson(generated.text).valid, true)

  const transcript = parseStrictEvidenceJson(generated.text)
  assert.deepEqual(
    transcript.body.changedTransitions.map(({ actual, counterfactual }) => [actual.body.execution.lifecycle, counterfactual.body.execution.lifecycle]),
    [['SUCCESS', 'SUCCESS'], ['SUCCESS', 'REVERT'], ['SUCCESS', 'SUCCESS']],
  )
  assert.equal(transcript.body.divergence.stateCommitment.envelopeIndex, 0)
  assert.equal(transcript.body.divergence.lifecycle.envelopeIndex, 1)
  assert.equal(transcript.body.divergence.semantic.envelopeIndex, 2)
})
