import { buildBranchEvidenceTranscript as buildBranchEvidenceTranscriptV2 } from './branch-evidence-transcript.mjs'
import { buildEnvelopeEvidence as buildEnvelopeEvidenceV2 } from './envelope-evidence.mjs'
import { canonical } from './strict-common.mjs'
import { parseStrictEvidenceJson } from './strict-json.mjs'
import {
  isEnvelopeEvidenceStrictlyVerified,
  verifyEnvelopeEvidenceStrict,
} from './strict-envelope.mjs'
import {
  isBranchEvidenceTranscriptStrictlyVerified,
  verifyBranchEvidenceTranscriptStrict,
} from './strict-branch.mjs'

function requireVerified(condition, code, findings) {
  if (!condition) throw Object.assign(new Error(`${code}: ${JSON.stringify(findings)}`), { code, findings })
}

export function buildEnvelopeEvidence(input) {
  const record = buildEnvelopeEvidenceV2(input)
  const verification = verifyEnvelopeEvidenceStrict(record)
  requireVerified(isEnvelopeEvidenceStrictlyVerified(verification), 'BUILDER_POSTCONDITION_FAILED', verification.findings)
  return record
}

export function verifyEnvelopeEvidence(record) {
  return verifyEnvelopeEvidenceStrict(record)
}

export function isEnvelopeEvidenceVerified(result) {
  return isEnvelopeEvidenceStrictlyVerified(result)
}

export function exportEnvelopeEvidence(record) {
  const verification = verifyEnvelopeEvidenceStrict(record)
  requireVerified(isEnvelopeEvidenceStrictlyVerified(verification), 'UNVERIFIED_ENVELOPE_EVIDENCE', verification.findings)
  return `${canonical(record)}\n`
}

export function buildBranchEvidenceTranscript(input) {
  for (const [branch, records] of [['actual', input?.actualEnvelopes], ['counterfactual', input?.counterfactualEnvelopes]]) {
    if (!Array.isArray(records)) throw Object.assign(new Error(`INVALID_BRANCH_TRANSCRIPT: ${branch} envelopes must be an array`), { code: 'INVALID_BRANCH_TRANSCRIPT' })
    records.forEach((record, index) => {
      const verification = verifyEnvelopeEvidenceStrict(record)
      requireVerified(isEnvelopeEvidenceStrictlyVerified(verification), 'UNVERIFIED_ENVELOPE_EVIDENCE', [{ branch, index, findings: verification.findings }])
    })
  }
  const transcript = buildBranchEvidenceTranscriptV2(input)
  const verification = verifyBranchEvidenceTranscriptStrict(transcript)
  requireVerified(isBranchEvidenceTranscriptStrictlyVerified(verification), 'BUILDER_POSTCONDITION_FAILED', verification.findings)
  return transcript
}

export function verifyBranchEvidenceTranscript(transcript) {
  return verifyBranchEvidenceTranscriptStrict(transcript)
}

export function isBranchEvidenceTranscriptVerified(result) {
  return isBranchEvidenceTranscriptStrictlyVerified(result)
}

export function exportBranchEvidenceTranscript(transcript) {
  const verification = verifyBranchEvidenceTranscriptStrict(transcript)
  requireVerified(isBranchEvidenceTranscriptStrictlyVerified(verification), 'UNVERIFIED_BRANCH_TRANSCRIPT', verification.findings)
  return `${canonical(transcript)}\n`
}

export function branchEvidenceTranscriptHash(transcript) {
  const verification = verifyBranchEvidenceTranscriptStrict(transcript)
  requireVerified(isBranchEvidenceTranscriptStrictlyVerified(verification), 'UNVERIFIED_BRANCH_TRANSCRIPT', verification.findings)
  return transcript.transcriptCommitment.digest
}

function verifyJson(text, verifier, resultField) {
  try {
    return verifier(parseStrictEvidenceJson(text))
  } catch (error) {
    return Object.freeze({
      valid: false,
      findings: Object.freeze([Object.freeze({ code: error?.code ?? 'STRICT_JSON_SYNTAX', path: '$', detail: String(error?.message ?? error) })]),
      [resultField]: null,
    })
  }
}

export function verifyEnvelopeEvidenceJson(text) {
  return verifyJson(text, verifyEnvelopeEvidenceStrict, 'receipt')
}

export function verifyBranchEvidenceTranscriptJson(text) {
  return verifyJson(text, verifyBranchEvidenceTranscriptStrict, 'commitment')
}

export { verifyEnvelopeEvidenceStrict, verifyBranchEvidenceTranscriptStrict }
