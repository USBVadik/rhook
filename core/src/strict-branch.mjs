import {
  ADDRESS_RE,
  DECIMAL_RE,
  DIGEST_RE,
  HASH32_RE,
  HEX_RE,
  SELECTOR_RE,
  TOKEN_RE,
  TRANSCRIPT_DOMAIN,
  addFinding,
  arrayEqual,
  canonical,
  exactObject,
  isCanonicalAddress,
  isCanonicalDecimal,
  isCanonicalDigest,
  isCanonicalHash32,
  isCanonicalHex,
  isCanonicalSelector,
  isStableToken,
  sameEnvelopeIdentity,
  sha256Canonical,
  strictlyIncreasing,
  validCommitmentSummary,
  validDomain,
  validEnvelopeIdentity,
  validRecordDomain,
  verifyInStages,
} from './strict-common.mjs'
import { verifyEnvelopeEvidenceStrict } from './strict-envelope.mjs'

const VERDICTS = new Set(['EQUAL', 'VALUE_CHANGED', 'KIND_CHANGED', 'PRESENCE_CHANGED', 'BOTH_ABSENT', 'NOT_COMPARABLE'])
const CHANGED_VERDICTS = new Set(['VALUE_CHANGED', 'KIND_CHANGED', 'PRESENCE_CHANGED'])
const REQUIRED_LIMITATIONS = ['ENGINEERING_CONFORMANCE_ONLY', 'NO_FULL_STATE_DUMP', 'NO_HUMAN_CAUSATION_INFERENCE', 'SINGLE_TARGET_ONLY']

function shapeCommitment(value, findings, path) {
  exactObject(value, ['domain', 'digest'], findings, 'INVALID_COMMITMENT_SHAPE', path)
}

function shapeIdentity(value, findings, path) {
  exactObject(value, ['blockNumber', 'transactionHash', 'transactionIndex'], findings, 'INVALID_ENVELOPE_IDENTITY_SHAPE', path)
}

function shapeSemanticSide(side, findings, path) {
  if (!exactObject(side, ['canonicalValue', 'endpoint', 'postStateCommitment', 'presence', 'presenceReason', 'recordIdentity', 'source', 'valueKind'], findings, 'INVALID_SEMANTIC_SIDE_SHAPE', path)) return
  exactObject(side.endpoint, ['address', 'selector'], findings, 'INVALID_SEMANTIC_ENDPOINT_SHAPE', `${path}.endpoint`)
  shapeCommitment(side.recordIdentity, findings, `${path}.recordIdentity`)
  const source = side.source
  if (source?.kind === 'STORAGE_SLOT') exactObject(source, ['kind', 'slot'], findings, 'INVALID_SEMANTIC_SOURCE_SHAPE', `${path}.source`)
  else if (source?.kind === 'RETURN_WORD') exactObject(source, ['kind', 'position'], findings, 'INVALID_SEMANTIC_SOURCE_SHAPE', `${path}.source`)
  else if (source?.kind === 'ACCOUNT_FIELD') exactObject(source, ['field', 'kind'], findings, 'INVALID_SEMANTIC_SOURCE_SHAPE', `${path}.source`)
  else if (source?.kind === 'CODE') exactObject(source, ['kind'], findings, 'INVALID_SEMANTIC_SOURCE_SHAPE', `${path}.source`)
  else addFinding(findings, 'INVALID_SEMANTIC_SOURCE', `${path}.source`, 'unknown semantic source kind')
}

function shapeAxis(axis, kind, findings, path) {
  if (!axis || typeof axis.status !== 'string') {
    addFinding(findings, 'INVALID_DIVERGENCE_SHAPE', path, 'axis status required')
    return
  }
  if (axis.status === 'NONE' || (kind === 'semantic' && axis.status === 'UNDETERMINED')) exactObject(axis, ['status'], findings, 'INVALID_DIVERGENCE_SHAPE', path)
  else if (axis.status === 'DIVERGED' && kind === 'lifecycle') exactObject(axis, ['actual', 'counterfactual', 'envelopeIndex', 'status'], findings, 'INVALID_DIVERGENCE_SHAPE', path)
  else if (axis.status === 'DIVERGED' && kind === 'stateCommitment') exactObject(axis, ['actualPostStateCommitment', 'counterfactualPostStateCommitment', 'envelopeIndex', 'status'], findings, 'INVALID_DIVERGENCE_SHAPE', path)
  else if (axis.status === 'DIVERGED' && kind === 'semantic') exactObject(axis, ['envelopeIndex', 'slot', 'status', 'verdict'], findings, 'INVALID_DIVERGENCE_SHAPE', path)
  else addFinding(findings, 'INVALID_DIVERGENCE_SHAPE', path, 'unsupported divergence status')
}

function shape(transcript, findings) {
  if (!exactObject(transcript, ['body', 'transcriptCommitment'], findings, 'INVALID_TRANSCRIPT_RECORD_SHAPE', '$')) return
  const body = transcript.body
  if (!exactObject(body, ['branches', 'changedTransitions', 'coverage', 'divergence', 'domain', 'intervention', 'limitations', 'provenance', 'schema', 'semanticEvidence', 'unchangedCommitments'], findings, 'INVALID_TRANSCRIPT_BODY_SHAPE', '$.body')) return
  if (exactObject(body.branches, ['actual', 'counterfactual'], findings, 'INVALID_BRANCHES_SHAPE', '$.body.branches')) {
    shapeCommitment(body.branches.actual, findings, '$.body.branches.actual')
    shapeCommitment(body.branches.counterfactual, findings, '$.body.branches.counterfactual')
  }
  if (exactObject(body.intervention, ['kind', 'singleTarget', 'target'], findings, 'INVALID_INTERVENTION_SHAPE', '$.body.intervention')) shapeIdentity(body.intervention.target, findings, '$.body.intervention.target')
  exactObject(body.coverage, ['changedEnvelopes', 'declaredEnvelopes', 'unchangedEnvelopes'], findings, 'INVALID_COVERAGE_SHAPE', '$.body.coverage')
  if (!Array.isArray(body.changedTransitions)) addFinding(findings, 'INVALID_CHANGED_TRANSITIONS', '$.body.changedTransitions', 'expected an array')
  else body.changedTransitions.forEach((item, index) => exactObject(item, ['actual', 'counterfactual', 'envelopeIndex'], findings, 'INVALID_CHANGED_TRANSITION_SHAPE', `$.body.changedTransitions[${index}]`))
  if (!Array.isArray(body.unchangedCommitments)) addFinding(findings, 'INVALID_UNCHANGED_COMMITMENTS', '$.body.unchangedCommitments', 'expected an array')
  else body.unchangedCommitments.forEach((item, index) => {
    const path = `$.body.unchangedCommitments[${index}]`
    if (exactObject(item, ['actualPostStateCommitment', 'actualReceipt', 'counterfactualPostStateCommitment', 'counterfactualReceipt', 'envelope', 'envelopeIndex'], findings, 'INVALID_UNCHANGED_COMMITMENT_SHAPE', path)) shapeIdentity(item.envelope, findings, `${path}.envelope`)
  })
  if (!Array.isArray(body.semanticEvidence)) addFinding(findings, 'INVALID_SEMANTIC_EVIDENCE', '$.body.semanticEvidence', 'expected an array')
  else body.semanticEvidence.forEach((item, index) => {
    const path = `$.body.semanticEvidence[${index}]`
    if (exactObject(item, ['actual', 'counterfactual', 'envelopeIndex', 'slot', 'verdict'], findings, 'INVALID_SEMANTIC_EVIDENCE_SHAPE', path)) {
      shapeSemanticSide(item.actual, findings, `${path}.actual`)
      shapeSemanticSide(item.counterfactual, findings, `${path}.counterfactual`)
    }
  })
  if (!Array.isArray(body.limitations)) addFinding(findings, 'INVALID_LIMITATIONS', '$.body.limitations', 'expected an array')
  if (exactObject(body.divergence, ['lifecycle', 'semantic', 'stateCommitment'], findings, 'INVALID_DIVERGENCE_SHAPE', '$.body.divergence')) {
    shapeAxis(body.divergence.lifecycle, 'lifecycle', findings, '$.body.divergence.lifecycle')
    shapeAxis(body.divergence.stateCommitment, 'stateCommitment', findings, '$.body.divergence.stateCommitment')
    shapeAxis(body.divergence.semantic, 'semantic', findings, '$.body.divergence.semantic')
  }
  exactObject(body.provenance, ['derivesFromStoredEnvelopeEvidence', 'infersHumanCausation', 'semanticValuesStateBound'], findings, 'INVALID_PROVENANCE_SHAPE', '$.body.provenance')
  exactObject(transcript.transcriptCommitment, ['algorithm', 'digest', 'domain'], findings, 'INVALID_TRANSCRIPT_COMMITMENT_SHAPE', '$.transcriptCommitment')
}

function appendNested(findings, prefix, verification) {
  for (const finding of verification.findings) addFinding(findings, finding.code, `${prefix}${finding.path.slice(1)}`, finding.detail)
}

function validSemanticSideTypes(side, findings, path) {
  if (!isCanonicalAddress(side.endpoint.address ?? '') || !isCanonicalSelector(side.endpoint.selector ?? '')) addFinding(findings, 'INVALID_SEMANTIC_ENDPOINT', `${path}.endpoint`, 'canonical address and empty/4-byte selector required')
  if (!validRecordDomain(side.recordIdentity.domain) || !isCanonicalDigest(side.recordIdentity.digest)) addFinding(findings, 'INVALID_SEMANTIC_RECORD_IDENTITY', `${path}.recordIdentity`, 'invalid domain or digest')
  if (!isCanonicalDigest(side.postStateCommitment ?? '')) addFinding(findings, 'INVALID_SEMANTIC_POST_STATE', `${path}.postStateCommitment`, 'canonical digest required')
  if (!['PRESENT', 'VALID_ABSENT', 'NOT_COMPUTED'].includes(side.presence)) addFinding(findings, 'INVALID_SEMANTIC_PRESENCE', `${path}.presence`, 'unknown presence state')
  const source = side.source
  if (source.kind === 'STORAGE_SLOT' && !isCanonicalHash32(source.slot ?? '')) addFinding(findings, 'INVALID_SEMANTIC_SOURCE', `${path}.source.slot`, 'canonical storage slot required')
  if (source.kind === 'RETURN_WORD' && !isCanonicalHash32(source.position ?? '')) addFinding(findings, 'INVALID_SEMANTIC_SOURCE', `${path}.source.position`, 'canonical return-word position required')
  if (source.kind === 'ACCOUNT_FIELD' && !['balance', 'nonce', 'code'].includes(source.field)) addFinding(findings, 'INVALID_SEMANTIC_SOURCE', `${path}.source.field`, 'unsupported account field')
}

function types(transcript, findings) {
  const { body, transcriptCommitment } = transcript
  if (body.schema !== 'generic-ce-branch-evidence-transcript/2' || body.domain !== TRANSCRIPT_DOMAIN) addFinding(findings, 'INVALID_TRANSCRIPT_SCHEMA', '$.body', 'unexpected schema or domain')
  if (!validCommitmentSummary(body.branches.actual) || !validCommitmentSummary(body.branches.counterfactual)) addFinding(findings, 'INVALID_BRANCH_COMMITMENT', '$.body.branches', 'invalid branch commitment domain or digest')
  if (body.branches.actual.domain === body.branches.counterfactual.domain && body.branches.actual.digest === body.branches.counterfactual.digest) addFinding(findings, 'BRANCHES_NOT_DISTINCT', '$.body.branches', 'branch commitments must differ')
  if (!isStableToken(body.intervention.kind ?? '') || body.intervention.singleTarget !== true || !validEnvelopeIdentity(body.intervention.target)) addFinding(findings, 'INVALID_INTERVENTION', '$.body.intervention', 'invalid single-target intervention')
  for (const [name, value] of Object.entries(body.coverage)) if (!Number.isSafeInteger(value) || value < 0) addFinding(findings, 'INVALID_COVERAGE', `$.body.coverage.${name}`, 'non-negative safe integer required')
  if (body.coverage.declaredEnvelopes < 1) addFinding(findings, 'INVALID_COVERAGE', '$.body.coverage.declaredEnvelopes', 'coverage must be non-empty')
  body.changedTransitions.forEach((item, index) => {
    if (!Number.isSafeInteger(item.envelopeIndex) || item.envelopeIndex < 0) addFinding(findings, 'INVALID_ENVELOPE_INDEX', `$.body.changedTransitions[${index}].envelopeIndex`, 'non-negative safe integer required')
    appendNested(findings, `$.body.changedTransitions[${index}].actual`, verifyEnvelopeEvidenceStrict(item.actual))
    appendNested(findings, `$.body.changedTransitions[${index}].counterfactual`, verifyEnvelopeEvidenceStrict(item.counterfactual))
  })
  body.unchangedCommitments.forEach((item, index) => {
    const path = `$.body.unchangedCommitments[${index}]`
    if (!Number.isSafeInteger(item.envelopeIndex) || item.envelopeIndex < 0) addFinding(findings, 'INVALID_ENVELOPE_INDEX', `${path}.envelopeIndex`, 'non-negative safe integer required')
    if (!validEnvelopeIdentity(item.envelope)) addFinding(findings, 'INVALID_ENVELOPE_IDENTITY', `${path}.envelope`, 'canonical identity required')
    for (const field of ['actualReceipt', 'counterfactualReceipt', 'actualPostStateCommitment', 'counterfactualPostStateCommitment']) if (!isCanonicalDigest(item[field] ?? '')) addFinding(findings, 'INVALID_COMPACT_COMMITMENT', `${path}.${field}`, 'canonical schema-fixed SHA-256 digest required')
  })
  body.semanticEvidence.forEach((item, index) => {
    const path = `$.body.semanticEvidence[${index}]`
    if (!Number.isSafeInteger(item.envelopeIndex) || item.envelopeIndex < 0 || typeof item.slot !== 'string' || !VERDICTS.has(item.verdict)) addFinding(findings, 'INVALID_SEMANTIC_EVIDENCE', path, 'invalid index, slot, or verdict')
    validSemanticSideTypes(item.actual, findings, `${path}.actual`)
    validSemanticSideTypes(item.counterfactual, findings, `${path}.counterfactual`)
  })
  body.limitations.forEach((value, index) => { if (!isStableToken(value ?? '')) addFinding(findings, 'INVALID_LIMITATION', `$.body.limitations[${index}]`, 'stable token required') })
  if (body.provenance.derivesFromStoredEnvelopeEvidence !== true || body.provenance.semanticValuesStateBound !== true || body.provenance.infersHumanCausation !== false) addFinding(findings, 'INVALID_PROVENANCE', '$.body.provenance', 'invalid provenance flags')
  if (transcriptCommitment.domain !== TRANSCRIPT_DOMAIN || transcriptCommitment.algorithm !== 'sha256' || !isCanonicalDigest(transcriptCommitment.digest ?? '')) addFinding(findings, 'INVALID_TRANSCRIPT_COMMITMENT', '$.transcriptCommitment', 'invalid domain, algorithm, or digest')
}

function sourceKey(source) {
  if (source.kind === 'STORAGE_SLOT') return `STORAGE_SLOT:${source.slot}`
  if (source.kind === 'RETURN_WORD') return `RETURN_WORD:${source.position}`
  if (source.kind === 'ACCOUNT_FIELD') return `ACCOUNT_FIELD:${source.field}`
  return 'CODE'
}
const sideSlot = (side) => `${side.endpoint.address}#${side.endpoint.selector}|${sourceKey(side.source)}`

function ordering(transcript, findings) {
  const { body } = transcript
  const changed = body.changedTransitions.map((item) => item.envelopeIndex)
  const unchanged = body.unchangedCommitments.map((item) => item.envelopeIndex)
  if (!strictlyIncreasing(changed)) addFinding(findings, 'NONCANONICAL_CHANGED_ORDER', '$.body.changedTransitions', 'indices must be strictly increasing')
  if (!strictlyIncreasing(unchanged)) addFinding(findings, 'NONCANONICAL_UNCHANGED_ORDER', '$.body.unchangedCommitments', 'indices must be strictly increasing')
  const all = [...changed, ...unchanged].sort((left, right) => left - right)
  const expected = Array.from({ length: body.coverage.declaredEnvelopes }, (_, index) => index)
  if (!arrayEqual(all, expected)) addFinding(findings, 'NONCONTIGUOUS_ENVELOPE_COVERAGE', '$.body', 'indices must be unique, in-range, and cover 0..declared-1')
  const semantic = body.semanticEvidence.map((item) => `${String(item.envelopeIndex).padStart(16, '0')}:${item.slot}`)
  const sortedSemantic = [...semantic].sort()
  if (!arrayEqual(semantic, sortedSemantic)) addFinding(findings, 'NONCANONICAL_SEMANTIC_ORDER', '$.body.semanticEvidence', 'semantic records must be ordered by index and slot')
  if (new Set(semantic).size !== semantic.length) addFinding(findings, 'DUPLICATE_SEMANTIC_SLOT', '$.body.semanticEvidence', 'duplicate envelopeIndex/slot identity')
  const sortedLimitations = [...body.limitations].sort()
  if (!arrayEqual(body.limitations, sortedLimitations) || new Set(body.limitations).size !== body.limitations.length) addFinding(findings, 'NONCANONICAL_LIMITATIONS', '$.body.limitations', 'limitations must be sorted and unique')
  const identities = [...body.changedTransitions.map((item) => item.actual.body.envelope), ...body.unchangedCommitments.map((item) => item.envelope)].map((item) => `${item.blockNumber}:${item.transactionIndex}:${item.transactionHash}`)
  if (new Set(identities).size !== identities.length) addFinding(findings, 'DUPLICATE_ENVELOPE_IDENTITY', '$.body', 'canonical envelope identities must be unique')
  const orderedCoverage = [
    ...body.changedTransitions.map((item) => ({ index: item.envelopeIndex, envelope: item.actual.body.envelope })),
    ...body.unchangedCommitments.map((item) => ({ index: item.envelopeIndex, envelope: item.envelope })),
  ].sort((left, right) => left.index - right.index)
  for (let index = 1; index < orderedCoverage.length; index += 1) {
    const previous = orderedCoverage[index - 1].envelope
    const current = orderedCoverage[index].envelope
    const ordered = BigInt(current.blockNumber) > BigInt(previous.blockNumber)
      || (current.blockNumber === previous.blockNumber && BigInt(current.transactionIndex) > BigInt(previous.transactionIndex))
    if (!ordered) {
      addFinding(findings, 'NONCANONICAL_ENVELOPE_IDENTITY_ORDER', '$.body', 'envelope identities must increase by blockNumber/transactionIndex')
      break
    }
  }
}

function envelopeCoverage(body, index) {
  const changed = body.changedTransitions.find((item) => item.envelopeIndex === index)
  if (changed) return { kind: 'changed', actual: changed.actual.body, counterfactual: changed.counterfactual.body }
  const unchanged = body.unchangedCommitments.find((item) => item.envelopeIndex === index)
  return unchanged ? { kind: 'unchanged', entry: unchanged } : null
}

function crossReferences(transcript, findings) {
  const { body } = transcript
  if (body.coverage.changedEnvelopes !== body.changedTransitions.length || body.coverage.unchangedEnvelopes !== body.unchangedCommitments.length || body.coverage.declaredEnvelopes !== body.changedTransitions.length + body.unchangedCommitments.length) addFinding(findings, 'COVERAGE_MISMATCH', '$.body.coverage', 'declared counts do not match records')
  body.changedTransitions.forEach((item, index) => {
    if (!sameEnvelopeIdentity(item.actual.body.envelope, item.counterfactual.body.envelope)) addFinding(findings, 'ENVELOPE_IDENTITY_MISMATCH', `$.body.changedTransitions[${index}]`, 'actual and counterfactual identities differ')
    if (canonical(item.actual.body) === canonical(item.counterfactual.body)) addFinding(findings, 'FALSE_CHANGED_TRANSITION', `$.body.changedTransitions[${index}]`, 'changed transition bodies are identical')
  })
  body.unchangedCommitments.forEach((item, index) => {
    if (item.actualReceipt !== item.counterfactualReceipt || item.actualPostStateCommitment !== item.counterfactualPostStateCommitment) addFinding(findings, 'FALSE_UNCHANGED_TRANSITION', `$.body.unchangedCommitments[${index}]`, 'compact unchanged branch commitments differ')
  })
  const targetKey = `${body.intervention.target.blockNumber}:${body.intervention.target.transactionIndex}:${body.intervention.target.transactionHash}`
  const identities = [...body.changedTransitions.map((item) => item.actual.body.envelope), ...body.unchangedCommitments.map((item) => item.envelope)]
  if (identities.filter((item) => `${item.blockNumber}:${item.transactionIndex}:${item.transactionHash}` === targetKey).length !== 1) addFinding(findings, 'INTERVENTION_TARGET_OUT_OF_DOMAIN', '$.body.intervention.target', 'target must match exactly one covered envelope')
  body.semanticEvidence.forEach((item, index) => {
    const path = `$.body.semanticEvidence[${index}]`
    const coverage = envelopeCoverage(body, item.envelopeIndex)
    if (!coverage) return addFinding(findings, 'SEMANTIC_ENVELOPE_MISSING', `${path}.envelopeIndex`, 'semantic record has no covered envelope')
    if (item.slot !== sideSlot(item.actual) || item.slot !== sideSlot(item.counterfactual)) addFinding(findings, 'SEMANTIC_SLOT_MISMATCH', `${path}.slot`, 'slot is not derived from both endpoint/source identities')
    const actualPost = coverage.kind === 'changed' ? coverage.actual.execution.successorStateCommitment : coverage.entry.actualPostStateCommitment
    const counterfactualPost = coverage.kind === 'changed' ? coverage.counterfactual.execution.successorStateCommitment : coverage.entry.counterfactualPostStateCommitment
    if (item.actual.postStateCommitment !== actualPost || item.counterfactual.postStateCommitment !== counterfactualPost) addFinding(findings, 'SEMANTIC_STATE_BINDING_MISMATCH', path, 'semantic value is detached from exact envelope successor state')
  })
  for (const required of REQUIRED_LIMITATIONS) if (!body.limitations.includes(required)) addFinding(findings, 'MISSING_LIMITATION', '$.body.limitations', `missing ${required}`)
}

function commitment(transcript, findings) {
  if (sha256Canonical(transcript.body) !== transcript.transcriptCommitment.digest) addFinding(findings, 'TRANSCRIPT_COMMITMENT_MISMATCH', '$.transcriptCommitment.digest', 'body does not match commitment')
}

function expectedValueKind(source) {
  if (source.kind === 'STORAGE_SLOT' || source.kind === 'RETURN_WORD') return 'Hash32'
  if (source.kind === 'CODE' || (source.kind === 'ACCOUNT_FIELD' && source.field === 'code')) return 'HexBytes'
  return 'Quantity'
}

function sideSemantics(side, findings, path) {
  if (side.presence === 'PRESENT') {
    if (side.presenceReason !== null) addFinding(findings, 'INVALID_PRESENCE_VALUE_COMBINATION', `${path}.presenceReason`, 'present value requires null reason')
    const expected = expectedValueKind(side.source)
    if (side.valueKind !== expected) addFinding(findings, 'INVALID_SEMANTIC_VALUE_KIND', `${path}.valueKind`, `expected ${expected}`)
    const validValue = expected === 'Quantity' ? isCanonicalDecimal(side.canonicalValue ?? '') : expected === 'Hash32' ? isCanonicalHash32(side.canonicalValue ?? '') : isCanonicalHex(side.canonicalValue ?? '')
    if (!validValue) addFinding(findings, 'INVALID_CANONICAL_SEMANTIC_VALUE', `${path}.canonicalValue`, `invalid ${expected} representation`)
  } else {
    if (side.valueKind !== null || side.canonicalValue !== null || !isStableToken(side.presenceReason ?? '')) addFinding(findings, 'INVALID_PRESENCE_VALUE_COMBINATION', path, 'absent/not-computed requires null value/kind and stable reason')
  }
}

function expectedVerdict(actual, counterfactual) {
  if (actual.presence === 'NOT_COMPUTED' || counterfactual.presence === 'NOT_COMPUTED') return 'NOT_COMPARABLE'
  if (actual.presence === 'VALID_ABSENT' && counterfactual.presence === 'VALID_ABSENT') return 'BOTH_ABSENT'
  if (actual.presence !== counterfactual.presence) return 'PRESENCE_CHANGED'
  if (actual.valueKind !== counterfactual.valueKind) return 'KIND_CHANGED'
  return actual.canonicalValue === counterfactual.canonicalValue ? 'EQUAL' : 'VALUE_CHANGED'
}

function semantics(transcript, findings) {
  transcript.body.semanticEvidence.forEach((item, index) => {
    const path = `$.body.semanticEvidence[${index}]`
    sideSemantics(item.actual, findings, `${path}.actual`)
    sideSemantics(item.counterfactual, findings, `${path}.counterfactual`)
    if (item.verdict !== expectedVerdict(item.actual, item.counterfactual)) addFinding(findings, 'SEMANTIC_VERDICT_MISMATCH', `${path}.verdict`, 'verdict is not re-derived')
  })
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
  const item = semantic.find((entry) => CHANGED_VERDICTS.has(entry.verdict))
  return item ? { status: 'DIVERGED', envelopeIndex: item.envelopeIndex, slot: item.slot, verdict: item.verdict } : semantic.some((entry) => entry.verdict === 'NOT_COMPARABLE') ? { status: 'UNDETERMINED' } : { status: 'NONE' }
}

function divergence(transcript, findings) {
  const expected = { lifecycle: firstLifecycle(transcript.body.changedTransitions), stateCommitment: firstState(transcript.body.changedTransitions), semantic: firstSemantic(transcript.body.semanticEvidence) }
  if (canonical(expected) !== canonical(transcript.body.divergence)) addFinding(findings, 'DIVERGENCE_MISMATCH', '$.body.divergence', 'divergence is not derived from strictly verified evidence')
}

export function verifyBranchEvidenceTranscriptStrict(transcript) {
  return verifyInStages([
    (findings) => shape(transcript, findings),
    (findings) => types(transcript, findings),
    (findings) => ordering(transcript, findings),
    (findings) => crossReferences(transcript, findings),
    (findings) => commitment(transcript, findings),
    (findings) => semantics(transcript, findings),
    (findings) => divergence(transcript, findings),
  ], { commitment: transcript?.transcriptCommitment ?? null })
}

export const isBranchEvidenceTranscriptStrictlyVerified = (result) => result?.valid === true && Array.isArray(result.findings) && result.findings.length === 0
