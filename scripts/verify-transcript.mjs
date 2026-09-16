import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import {
  parseStrictEvidenceJson,
  verifyBranchEvidenceTranscriptJson,
} from '../core/src/index.mjs'

const input = process.argv[2] ? resolve(process.cwd(), process.argv[2]) : new URL('../examples/minimal/transcript.json', import.meta.url)
const text = await readFile(input, 'utf8')
const fileSha256 = createHash('sha256').update(text).digest('hex')
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
