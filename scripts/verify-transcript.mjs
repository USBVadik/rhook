import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'

import {
  parseStrictEvidenceJson,
  verifyBranchEvidenceTranscriptJson,
} from '../core/src/index.mjs'

const text = await readFile(new URL('../examples/minimal/transcript.json', import.meta.url), 'utf8')
const fileSha256 = createHash('sha256').update(text).digest('hex')
assert.equal(fileSha256, '3c13a90e29b4b52967418784b5ff544b2e7c209676550cd56acdc7d3f13bd373')
const verification = verifyBranchEvidenceTranscriptJson(text)
assert.equal(verification.valid, true, JSON.stringify(verification.findings))
const transcript = parseStrictEvidenceJson(text)
assert.equal(transcript.body.divergence.stateCommitment.envelopeIndex, 0)
assert.equal(transcript.body.divergence.lifecycle.envelopeIndex, 1)
assert.equal(transcript.body.divergence.semantic.envelopeIndex, 2)
console.log(JSON.stringify({
  status: 'PASS',
  replayPerformed: false,
  runtimeStateLoaded: false,
  transcriptFileSha256: fileSha256,
  transcriptCommitment: transcript.transcriptCommitment.digest,
  divergence: transcript.body.divergence,
}, null, 2))
