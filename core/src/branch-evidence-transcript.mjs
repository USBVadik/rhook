import { createHash } from 'node:crypto'

import { fail, requireCondition, rejectUndefined } from './errors.mjs'
import { isCommitment, isQuantity } from './boundary-types.mjs'
import { DIFF, diffExtractions, extractionSlotKey, isExtraction } from './semantic-extraction.mjs'
import { isEnvelopeEvidenceVerified, isEnvelopeIdentity, verifyEnvelopeEvidence } from './envelope-evidence.mjs'

const DOMAIN = 'rhook/gcec-02/branch-evidence-transcript/v2'
const TOKEN_RE = /^[A-Z][A-Z0-9_]{0,95}$/
const DIGEST_RE = /^[0-9a-f]{64}$/
const CHANGED_DIFFS = new Set([DIFF.VALUE_CHANGED, DIFF.KIND_CHANGED, DIFF.PRESENCE_CHANGED])
const REQUIRED_LIMITATIONS = Object.freeze([
  'ENGINEERING_CONFORMANCE_ONLY',
  'SINGLE_TARGET_ONLY',
  'NO_HUMAN_CAUSATION_INFERENCE',
  'NO_FULL_STATE_DUMP',
])
const hash = (value) => createHash('sha256').update(value).digest('hex')

function canonical(value) {
  if (value === null) return 'null'
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    requireCondition(Number.isSafeInteger(value), 'NONDETERMINISTIC_BRANCH_TRANSCRIPT', 'number must be a safe integer')
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  requireCondition(value && typeof value === 'object', 'NONDETERMINISTIC_BRANCH_TRANSCRIPT', 'unsupported transcript value')
  return `{${Object.keys(value).sort().map((key) => {
    rejectUndefined(value[key], 'NONDETERMINISTIC_BRANCH_TRANSCRIPT', `undefined field ${key}`)
    return `${JSON.stringify(key)}:${canonical(value[key])}`
  }).join(',')}}`
}
function cleanToken(value, label) {
  rejectUndefined(value, 'INVALID_BRANCH_TRANSCRIPT', `${label} is undefined`)
  requireCondition(typeof value === 'string' && TOKEN_RE.test(value), 'INVALID_BRANCH_TRANSCRIPT', `${label} must be an uppercase stable token`)
  return value
}
function commitment(value, label) {
  requireCondition(isCommitment(value), 'INVALID_BRANCH_TRANSCRIPT', `${label} must be a typed Commitment`)
  requireCondition(typeof value.domain === 'string' && value.domain.length > 0 && !/[\\/]|rci-\d{3}|secret|token/i.test(value.domain), 'INVALID_BRANCH_TRANSCRIPT', `${label} domain is not host-neutral`)
  return Object.freeze({ domain: value.domain, digest: value.value })
}
function envelopeKey(body) {
  const value = body.envelope
  return `${value.blockNumber}:${value.transactionIndex}:${value.transactionHash}`
}
function plainEnvelopeIdentity(identity) {
  requireCondition(isEnvelopeIdentity(identity), 'INVALID_BRANCH_TRANSCRIPT', 'intervention target must be a typed EnvelopeIdentity')
  return Object.freeze({ blockNumber: identity.blockNumber, transactionIndex: identity.transactionIndex, transactionHash: identity.transactionHash })
}
function copyJson(value) {
  return JSON.parse(JSON.stringify(value))
}
function requireVerifiedEnvelope(record, label) {
  const verification = verifyEnvelopeEvidence(record)
  requireCondition(isEnvelopeEvidenceVerified(verification), 'UNVERIFIED_ENVELOPE_EVIDENCE', `${label} envelope evidence failed independent verification`)
  return record
}
function extractionSummary(extraction) {
  requireCondition(isExtraction(extraction), 'INVALID_BRANCH_TRANSCRIPT', 'semantic evidence must contain SemanticExtraction values')
  return Object.freeze({
    endpoint: Object.freeze({ address: extraction.endpoint.address, selector: extraction.endpoint.selector }),
    source: Object.freeze(copyJson(extraction.source)),
    recordIdentity: Object.freeze({ domain: extraction.recordDomain, digest: extraction.recordDigest }),
    postStateCommitment: extraction.postStateDigest,
    presence: extraction.presence,
    presenceReason: extraction.presenceReason,
    valueKind: extraction.valueKind,
    canonicalValue: extraction.value === null ? null : extraction.value.value,
  })
}
function envelopeChanged(actual, counterfactual) {
  return canonical(actual.body) !== canonical(counterfactual.body)
}
function firstLifecycle(changed) {
  const item = changed.find((entry) => entry.actual.body.execution.lifecycle !== entry.counterfactual.body.execution.lifecycle)
  return item ? { status: 'DIVERGED', envelopeIndex: item.envelopeIndex, actual: item.actual.body.execution.lifecycle, counterfactual: item.counterfactual.body.execution.lifecycle } : { status: 'NONE' }
}
function firstState(changed) {
  const item = changed.find((entry) => entry.actual.body.execution.successorStateCommitment !== entry.counterfactual.body.execution.successorStateCommitment)
  return item ? { status: 'DIVERGED', envelopeIndex: item.envelopeIndex, actualPostStateCommitment: item.actual.body.execution.successorStateCommitment, counterfactualPostStateCommitment: item.counterfactual.body.execution.successorStateCommitment } : { status: 'NONE' }
}
function firstSemantic(semantic) {
  const item = semantic.find((entry) => CHANGED_DIFFS.has(entry.verdict))
  return item ? { status: 'DIVERGED', envelopeIndex: item.envelopeIndex, slot: item.slot, verdict: item.verdict } : semantic.some((entry) => entry.verdict === DIFF.NOT_COMPARABLE) ? { status: 'UNDETERMINED' } : { status: 'NONE' }
}

export function buildBranchEvidenceTranscript({ branches, intervention, actualEnvelopes, counterfactualEnvelopes, semanticPairs, limitations = REQUIRED_LIMITATIONS }) {
  requireCondition(branches && typeof branches === 'object', 'INVALID_BRANCH_TRANSCRIPT', 'branch identities are required')
  const actualBranch = commitment(branches.actual, 'actual branch')
  const counterfactualBranch = commitment(branches.counterfactual, 'counterfactual branch')
  requireCondition(canonical(actualBranch) !== canonical(counterfactualBranch), 'BRANCHES_NOT_DISTINCT', 'actual and counterfactual branch identities must differ')
  requireCondition(intervention && typeof intervention === 'object' && !('targets' in intervention), 'MULTI_TARGET_REJECTED', 'single-target intervention required')
  const target = plainEnvelopeIdentity(intervention.target)
  const interventionKind = cleanToken(intervention.kind, 'intervention kind')
  requireCondition(Array.isArray(actualEnvelopes) && Array.isArray(counterfactualEnvelopes) && actualEnvelopes.length > 0 && actualEnvelopes.length === counterfactualEnvelopes.length, 'INVALID_BRANCH_TRANSCRIPT', 'aligned non-empty envelope arrays required')

  const changedTransitions = []
  const unchangedCommitments = []
  for (let index = 0; index < actualEnvelopes.length; index += 1) {
    const actual = requireVerifiedEnvelope(actualEnvelopes[index], `actual ${index}`)
    const counterfactual = requireVerifiedEnvelope(counterfactualEnvelopes[index], `counterfactual ${index}`)
    requireCondition(envelopeKey(actual.body) === envelopeKey(counterfactual.body), 'ENVELOPE_ORDER_MISMATCH', `canonical envelope identity mismatch at index ${index}`)
    const item = Object.freeze({ envelopeIndex: index, actual, counterfactual })
    if (envelopeChanged(actual, counterfactual)) changedTransitions.push(item)
    else unchangedCommitments.push(Object.freeze({
      envelopeIndex: index,
      envelope: Object.freeze({ ...actual.body.envelope }),
      actualReceipt: actual.receipt.digest,
      counterfactualReceipt: counterfactual.receipt.digest,
      actualPostStateCommitment: actual.body.execution.successorStateCommitment,
      counterfactualPostStateCommitment: counterfactual.body.execution.successorStateCommitment,
    }))
  }
  requireCondition(actualEnvelopes.some((record) => envelopeKey(record.body) === `${target.blockNumber}:${target.transactionIndex}:${target.transactionHash}`), 'INTERVENTION_TARGET_OUT_OF_DOMAIN', 'intervention target is not in envelope coverage')

  requireCondition(Array.isArray(semanticPairs), 'INVALID_BRANCH_TRANSCRIPT', 'semanticPairs must be an array')
  const semanticEvidence = semanticPairs.map((pair, pairIndex) => {
    requireCondition(pair && isQuantity(pair.envelopeIndex), 'INVALID_BRANCH_TRANSCRIPT', `semantic pair ${pairIndex} envelopeIndex must be typed Quantity`)
    const index = Number(pair.envelopeIndex.value)
    requireCondition(Number.isSafeInteger(index) && index >= 0 && index < actualEnvelopes.length, 'INVALID_BRANCH_TRANSCRIPT', `semantic pair ${pairIndex} envelopeIndex out of range`)
    const verdict = diffExtractions(pair.actual, pair.counterfactual)
    requireCondition(pair.actual.postStateDigest === actualEnvelopes[index].body.execution.successorStateCommitment, 'SEMANTIC_STATE_BINDING_MISMATCH', `actual semantic pair ${pairIndex} is not bound to envelope successor state`)
    requireCondition(pair.counterfactual.postStateDigest === counterfactualEnvelopes[index].body.execution.successorStateCommitment, 'SEMANTIC_STATE_BINDING_MISMATCH', `counterfactual semantic pair ${pairIndex} is not bound to envelope successor state`)
    return Object.freeze({ envelopeIndex: index, slot: extractionSlotKey(pair.actual), verdict: verdict.verdict, actual: extractionSummary(pair.actual), counterfactual: extractionSummary(pair.counterfactual) })
  }).sort((a, b) => a.envelopeIndex - b.envelopeIndex || a.slot.localeCompare(b.slot))

  requireCondition(Array.isArray(limitations), 'INVALID_BRANCH_TRANSCRIPT', 'limitations must be an array')
  const normalizedLimitations = [...new Set(limitations.map((item) => cleanToken(item, 'limitation')))].sort()
  for (const required of REQUIRED_LIMITATIONS) requireCondition(normalizedLimitations.includes(required), 'MISSING_LIMITATION', `missing mandatory limitation ${required}`)
  const divergence = Object.freeze({ lifecycle: Object.freeze(firstLifecycle(changedTransitions)), stateCommitment: Object.freeze(firstState(changedTransitions)), semantic: Object.freeze(firstSemantic(semanticEvidence)) })
  const body = Object.freeze({
    schema: 'generic-ce-branch-evidence-transcript/2',
    domain: DOMAIN,
    branches: Object.freeze({ actual: actualBranch, counterfactual: counterfactualBranch }),
    intervention: Object.freeze({ kind: interventionKind, target, singleTarget: true }),
    coverage: Object.freeze({ declaredEnvelopes: actualEnvelopes.length, changedEnvelopes: changedTransitions.length, unchangedEnvelopes: unchangedCommitments.length }),
    changedTransitions: Object.freeze(changedTransitions.map((entry) => Object.freeze({ envelopeIndex: entry.envelopeIndex, actual: Object.freeze(copyJson(entry.actual)), counterfactual: Object.freeze(copyJson(entry.counterfactual)) }))),
    unchangedCommitments: Object.freeze(unchangedCommitments),
    semanticEvidence: Object.freeze(semanticEvidence),
    divergence,
    limitations: Object.freeze(normalizedLimitations),
    provenance: Object.freeze({ derivesFromStoredEnvelopeEvidence: true, semanticValuesStateBound: true, infersHumanCausation: false }),
  })
  const transcriptCommitment = Object.freeze({ domain: DOMAIN, algorithm: 'sha256', digest: hash(canonical(body)) })
  return Object.freeze({ body, transcriptCommitment })
}

function expectedSemanticVerdict(actual, counterfactual) {
  if (actual.presence === 'NOT_COMPUTED' || counterfactual.presence === 'NOT_COMPUTED') return DIFF.NOT_COMPARABLE
  if (actual.presence === 'VALID_ABSENT' && counterfactual.presence === 'VALID_ABSENT') return DIFF.BOTH_ABSENT
  if (actual.presence !== counterfactual.presence) return DIFF.PRESENCE_CHANGED
  if (actual.valueKind !== counterfactual.valueKind) return DIFF.KIND_CHANGED
  return actual.canonicalValue === counterfactual.canonicalValue ? DIFF.EQUAL : DIFF.VALUE_CHANGED
}

export function verifyBranchEvidenceTranscript(transcript) {
  const findings = []
  const add = (code, detail) => findings.push(Object.freeze({ code, detail }))
  const body = transcript?.body
  if (!body || body.schema !== 'generic-ce-branch-evidence-transcript/2' || body.domain !== DOMAIN) add('INVALID_SCHEMA', 'invalid branch transcript schema/domain')
  if (!transcript?.transcriptCommitment || transcript.transcriptCommitment.domain !== DOMAIN || transcript.transcriptCommitment.algorithm !== 'sha256' || !DIGEST_RE.test(transcript.transcriptCommitment.digest ?? '')) add('INVALID_COMMITMENT', 'invalid transcript commitment')
  else {
    try { if (hash(canonical(body)) !== transcript.transcriptCommitment.digest) add('COMMITMENT_MISMATCH', 'transcript body was modified') } catch (error) { add('NONDETERMINISTIC_TRANSCRIPT', String(error?.message ?? error)) }
  }
  if (body) {
    if (body.intervention?.singleTarget !== true || body.intervention?.targets !== undefined) add('MULTI_TARGET_REJECTED', 'transcript is not single-target')
    const changed = Array.isArray(body.changedTransitions) ? body.changedTransitions : []
    const unchanged = Array.isArray(body.unchangedCommitments) ? body.unchangedCommitments : []
    if (body.coverage?.declaredEnvelopes !== changed.length + unchanged.length) add('COVERAGE_MISMATCH', 'changed+unchanged coverage does not equal declared envelopes')
    for (const [index, item] of changed.entries()) {
      if (item.envelopeIndex < 0 || !isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(item.actual)) || !isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(item.counterfactual))) add('UNVERIFIED_CHANGED_TRANSITION', `changed transition ${index} is not valid envelope evidence`)
      else if (envelopeKey(item.actual.body) !== envelopeKey(item.counterfactual.body)) add('ENVELOPE_ORDER_MISMATCH', `changed transition ${index} envelope identity mismatch`)
    }
    const semantic = Array.isArray(body.semanticEvidence) ? body.semanticEvidence : []
    for (const [index, item] of semantic.entries()) {
      if (item.verdict !== expectedSemanticVerdict(item.actual, item.counterfactual)) add('SEMANTIC_VERDICT_MISMATCH', `semantic evidence ${index} verdict is not re-derived`)
      const transition = changed.find((entry) => entry.envelopeIndex === item.envelopeIndex)
      const unchangedEntry = unchanged.find((entry) => entry.envelopeIndex === item.envelopeIndex)
      if (transition) {
        if (item.actual.postStateCommitment !== transition.actual.body.execution.successorStateCommitment || item.counterfactual.postStateCommitment !== transition.counterfactual.body.execution.successorStateCommitment) add('SEMANTIC_STATE_BINDING_MISMATCH', `semantic evidence ${index} post-state does not match stored envelope`)
      } else if (unchangedEntry) {
        if (item.actual.postStateCommitment !== unchangedEntry.actualPostStateCommitment || item.counterfactual.postStateCommitment !== unchangedEntry.counterfactualPostStateCommitment) add('SEMANTIC_STATE_BINDING_MISMATCH', `semantic evidence ${index} post-state does not match compact unchanged envelope`)
      } else add('SEMANTIC_ENVELOPE_MISSING', `semantic evidence ${index} has no envelope coverage`)
    }
    const expectedDivergence = { lifecycle: firstLifecycle(changed), stateCommitment: firstState(changed), semantic: firstSemantic(semantic) }
    if (canonical(body.divergence) !== canonical(expectedDivergence)) add('DIVERGENCE_MISMATCH', 'divergence points do not match stored evidence')
    for (const required of REQUIRED_LIMITATIONS) if (!body.limitations?.includes(required)) add('MISSING_LIMITATION', `missing ${required}`)
    if (body.provenance?.derivesFromStoredEnvelopeEvidence !== true || body.provenance?.semanticValuesStateBound !== true || body.provenance?.infersHumanCausation !== false) add('BAD_PROVENANCE', 'provenance flags are invalid')
  }
  return Object.freeze({ valid: findings.length === 0, findings: Object.freeze(findings), commitment: transcript?.transcriptCommitment ?? null })
}
export const isBranchEvidenceTranscriptVerified = (result) => result?.valid === true && result.findings?.length === 0
export function exportBranchEvidenceTranscript(transcript) {
  requireCondition(isBranchEvidenceTranscriptVerified(verifyBranchEvidenceTranscript(transcript)), 'UNVERIFIED_BRANCH_TRANSCRIPT', 'cannot export invalid branch transcript')
  return `${canonical(transcript)}\n`
}
export const branchEvidenceTranscriptHash = (transcript) => {
  requireCondition(isBranchEvidenceTranscriptVerified(verifyBranchEvidenceTranscript(transcript)), 'UNVERIFIED_BRANCH_TRANSCRIPT', 'cannot hash invalid branch transcript')
  return transcript.transcriptCommitment.digest
}
