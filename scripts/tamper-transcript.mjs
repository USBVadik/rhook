import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import {
  parseStrictEvidenceJson,
  verifyBranchEvidenceTranscript,
  verifyBranchEvidenceTranscriptJson,
} from '../core/src/index.mjs'
import { canonicalRuntimeJson } from '../runtime/src/index.mjs'

const input = process.argv[2] ? resolve(process.cwd(), process.argv[2]) : new URL('../examples/minimal/transcript.json', import.meta.url)
const text = await readFile(input, 'utf8')
assert.equal(verifyBranchEvidenceTranscriptJson(text).valid, true)
const transcript = parseStrictEvidenceJson(text)
const originalCommitment = transcript.transcriptCommitment.digest
transcript.body.semanticEvidence[0].actual.endpoint.address = 'not-an-address'
transcript.transcriptCommitment.digest = createHash('sha256').update(canonicalRuntimeJson(transcript.body)).digest('hex')
const result = verifyBranchEvidenceTranscript(transcript)
assert.equal(result.valid, false)
assert.ok(result.findings.some((finding) => finding.code === 'INVALID_SEMANTIC_ENDPOINT'))
assert.ok(!result.findings.some((finding) => finding.code === 'TRANSCRIPT_COMMITMENT_MISMATCH'))
console.log(JSON.stringify({
  status: 'EXPECTED_REJECTION',
  attack: 'malformed semantic endpoint with recomputed commitment',
  originalCommitment,
  attackerCommitment: transcript.transcriptCommitment.digest,
  findings: result.findings,
}, null, 2))
