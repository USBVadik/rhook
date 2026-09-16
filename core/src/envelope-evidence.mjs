import { createHash } from 'node:crypto'

import { fail, requireCondition, rejectUndefined } from './errors.mjs'
import {
  isBlockNumber,
  isCommitment,
  isDigest,
  isHash32,
  isQuantity,
} from './boundary-types.mjs'

export const VALIDATION_STATUS = Object.freeze({ VALID: 'VALID', INVALID: 'INVALID' })
export const ENVELOPE_LIFECYCLE = Object.freeze({
  SUCCESS: 'SUCCESS',
  REVERT: 'REVERT',
  PRE_EXECUTION_INVALIDATED: 'PRE_EXECUTION_INVALIDATED',
})
export const EXCEPTION_KIND = Object.freeze({ NONE: 'NONE', REVERT: 'REVERT', VALIDATION: 'VALIDATION' })

const DOMAIN = 'rhook/gcec-02/envelope-evidence/v2'
const TOKEN_RE = /^[A-Z][A-Z0-9_]{0,95}$/
const DIGEST_RE = /^[0-9a-f]{64}$/
const HASH32_RE = /^0x[0-9a-f]{64}$/
const DECIMAL_RE = /^(?:0|[1-9][0-9]*)$/
const BRAND = Symbol('rhook/gcec-02/envelope-evidence-brand')

function branded(kind, value) {
  return Object.freeze({ [BRAND]: kind, kind, ...value })
}
function hasBrand(value, kind) {
  return value !== null && typeof value === 'object' && value[BRAND] === kind
}
function cleanToken(value, label) {
  rejectUndefined(value, 'INVALID_EVIDENCE_TOKEN', `${label} is undefined`)
  requireCondition(typeof value === 'string' && TOKEN_RE.test(value), 'INVALID_EVIDENCE_TOKEN', `${label} must be an uppercase stable token`)
  return value
}
function requireTyped(value, predicate, code, label) {
  rejectUndefined(value, code, `${label} is undefined`)
  requireCondition(predicate(value), code, `${label} is not the required typed value`)
  return value
}
function canonical(value) {
  if (value === null) return 'null'
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    requireCondition(Number.isSafeInteger(value), 'NONDETERMINISTIC_ENVELOPE_EVIDENCE', 'number must be a safe integer')
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  requireCondition(value && typeof value === 'object', 'NONDETERMINISTIC_ENVELOPE_EVIDENCE', 'unsupported evidence value')
  const keys = Object.keys(value).sort()
  return `{${keys.map((key) => {
    rejectUndefined(value[key], 'NONDETERMINISTIC_ENVELOPE_EVIDENCE', `undefined field ${key}`)
    return `${JSON.stringify(key)}:${canonical(value[key])}`
  }).join(',')}}`
}
const hash = (value) => createHash('sha256').update(value).digest('hex')

export function makeEnvelopeIdentity({ blockNumber, transactionIndex, transactionHash }) {
  const block = requireTyped(blockNumber, isBlockNumber, 'INVALID_ENVELOPE_IDENTITY', 'blockNumber')
  const index = requireTyped(transactionIndex, isQuantity, 'INVALID_ENVELOPE_IDENTITY', 'transactionIndex')
  const txHash = requireTyped(transactionHash, isHash32, 'INVALID_ENVELOPE_IDENTITY', 'transactionHash')
  return branded('EnvelopeIdentity', {
    blockNumber: block.value,
    transactionIndex: index.value,
    transactionHash: txHash.value,
  })
}
export const isEnvelopeIdentity = (value) => hasBrand(value, 'EnvelopeIdentity')

export function validationValid() {
  return branded('ValidationOutcome', { status: VALIDATION_STATUS.VALID, classification: 'VALID_ENVELOPE' })
}
export function validationInvalid(classification) {
  return branded('ValidationOutcome', { status: VALIDATION_STATUS.INVALID, classification: cleanToken(classification, 'validation classification') })
}
export const isValidationOutcome = (value) => hasBrand(value, 'ValidationOutcome')

export function exceptionNone() {
  return branded('ExceptionOutcome', { kind: EXCEPTION_KIND.NONE, classification: 'NO_EXCEPTION', dataCommitment: { presence: 'VALID_ABSENT', reason: 'NOT_APPLICABLE' } })
}
export function exceptionRevert(classification, dataCommitment = null) {
  let data
  if (dataCommitment === null) data = { presence: 'VALID_ABSENT', reason: 'NO_REVERT_DATA_COMMITMENT' }
  else {
    const digest = requireTyped(dataCommitment, isDigest, 'INVALID_EXCEPTION', 'revert data commitment')
    data = { presence: 'PRESENT', digest: digest.value }
  }
  return branded('ExceptionOutcome', { kind: EXCEPTION_KIND.REVERT, classification: cleanToken(classification, 'revert classification'), dataCommitment: Object.freeze(data) })
}
export function exceptionValidation(classification) {
  return branded('ExceptionOutcome', { kind: EXCEPTION_KIND.VALIDATION, classification: cleanToken(classification, 'validation exception classification'), dataCommitment: { presence: 'VALID_ABSENT', reason: 'NOT_EXECUTED' } })
}
export const isExceptionOutcome = (value) => hasBrand(value, 'ExceptionOutcome')

export function makeGasAndFee({ gasLimit, gasUsed, feePaid }) {
  const limit = requireTyped(gasLimit, isQuantity, 'INVALID_GAS_ACCOUNTING', 'gasLimit')
  const used = requireTyped(gasUsed, isQuantity, 'INVALID_GAS_ACCOUNTING', 'gasUsed')
  const fee = requireTyped(feePaid, isQuantity, 'INVALID_GAS_ACCOUNTING', 'feePaid')
  requireCondition(used.big <= limit.big, 'INVALID_GAS_ACCOUNTING', 'gasUsed exceeds gasLimit')
  return branded('GasAndFee', { gasLimit: limit.value, gasUsed: used.value, feePaid: fee.value })
}
export const isGasAndFee = (value) => hasBrand(value, 'GasAndFee')

function commitmentSummary(value, label) {
  const commitment = requireTyped(value, isCommitment, 'INVALID_SEMANTIC_CHANGE_COMMITMENT', label)
  requireCondition(typeof commitment.domain === 'string' && commitment.domain.length > 0 && !/[\\/]|rci-\d{3}|secret|token/i.test(commitment.domain), 'INVALID_SEMANTIC_CHANGE_COMMITMENT', `${label} domain is not host-neutral`)
  return { domain: commitment.domain, digest: commitment.value }
}

function assertLifecycleCombination({ validation, lifecycle, exception, gasAndFee, predecessor, successor }) {
  requireCondition(Object.values(ENVELOPE_LIFECYCLE).includes(lifecycle), 'INVALID_ENVELOPE_LIFECYCLE', 'unknown lifecycle')
  if (lifecycle === ENVELOPE_LIFECYCLE.SUCCESS) {
    requireCondition(validation.status === VALIDATION_STATUS.VALID, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'success requires valid envelope')
    requireCondition(exception.kind === EXCEPTION_KIND.NONE, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'success cannot carry an exception')
  } else if (lifecycle === ENVELOPE_LIFECYCLE.REVERT) {
    requireCondition(validation.status === VALIDATION_STATUS.VALID, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'revert requires valid envelope')
    requireCondition(exception.kind === EXCEPTION_KIND.REVERT, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'revert requires explicit revert classification')
  } else {
    requireCondition(validation.status === VALIDATION_STATUS.INVALID, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalidation requires invalid validation outcome')
    requireCondition(exception.kind === EXCEPTION_KIND.VALIDATION, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalidation requires validation classification')
    requireCondition(gasAndFee.gasUsed === '0' && gasAndFee.feePaid === '0', 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalidated envelope cannot consume gas or fees')
    requireCondition(predecessor === successor, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalidated envelope must preserve state commitment')
  }
}

export function buildEnvelopeEvidence({
  envelope,
  predecessorStateCommitment,
  validation,
  lifecycle,
  exception,
  gasAndFee,
  logsCommitment,
  successorStateCommitment,
  executionResultCommitment,
  semanticChangeCommitments = [],
}) {
  requireCondition(isEnvelopeIdentity(envelope), 'INVALID_ENVELOPE_EVIDENCE', 'envelope identity must be typed')
  requireCondition(isValidationOutcome(validation), 'INVALID_ENVELOPE_EVIDENCE', 'validation outcome must be typed')
  requireCondition(isExceptionOutcome(exception), 'INVALID_ENVELOPE_EVIDENCE', 'exception outcome must be typed')
  requireCondition(isGasAndFee(gasAndFee), 'INVALID_ENVELOPE_EVIDENCE', 'gas/fee outcome must be typed')
  const predecessor = requireTyped(predecessorStateCommitment, isDigest, 'INVALID_ENVELOPE_EVIDENCE', 'predecessor state commitment')
  const successor = requireTyped(successorStateCommitment, isDigest, 'INVALID_ENVELOPE_EVIDENCE', 'successor state commitment')
  const logs = requireTyped(logsCommitment, isDigest, 'INVALID_ENVELOPE_EVIDENCE', 'logs commitment')
  const result = requireTyped(executionResultCommitment, isDigest, 'INVALID_ENVELOPE_EVIDENCE', 'execution result commitment')
  requireCondition(Array.isArray(semanticChangeCommitments), 'INVALID_ENVELOPE_EVIDENCE', 'semanticChangeCommitments must be an array')
  assertLifecycleCombination({ validation, lifecycle, exception, gasAndFee, predecessor: predecessor.value, successor: successor.value })
  const semanticChanges = semanticChangeCommitments.map((value, index) => commitmentSummary(value, `semantic change ${index}`)).sort((a, b) => `${a.domain}:${a.digest}`.localeCompare(`${b.domain}:${b.digest}`))
  const body = Object.freeze({
    schema: 'generic-ce-envelope-evidence/2',
    envelope: Object.freeze({ blockNumber: envelope.blockNumber, transactionIndex: envelope.transactionIndex, transactionHash: envelope.transactionHash }),
    predecessorStateCommitment: predecessor.value,
    validation: Object.freeze({ status: validation.status, classification: validation.classification }),
    execution: Object.freeze({
      lifecycle,
      executed: lifecycle !== ENVELOPE_LIFECYCLE.PRE_EXECUTION_INVALIDATED,
      exception: Object.freeze({ kind: exception.kind, classification: exception.classification, dataCommitment: Object.freeze({ ...exception.dataCommitment }) }),
      gasAndFee: Object.freeze({ gasLimit: gasAndFee.gasLimit, gasUsed: gasAndFee.gasUsed, feePaid: gasAndFee.feePaid }),
      logsCommitment: logs.value,
      successorStateCommitment: successor.value,
      executionResultCommitment: result.value,
    }),
    semanticChangeCommitments: Object.freeze(semanticChanges.map((item) => Object.freeze(item))),
  })
  const receipt = Object.freeze({ domain: DOMAIN, algorithm: 'sha256', digest: hash(canonical(body)) })
  return Object.freeze({ body, receipt })
}

function validDecimal(value) { return typeof value === 'string' && DECIMAL_RE.test(value) }
function verifyBody(body, findings) {
  const add = (code, detail) => findings.push(Object.freeze({ code, detail }))
  if (!body || typeof body !== 'object' || body.schema !== 'generic-ce-envelope-evidence/2') return add('INVALID_SCHEMA', 'invalid envelope evidence schema')
  const envelope = body.envelope
  if (!envelope || !validDecimal(envelope.blockNumber) || !validDecimal(envelope.transactionIndex) || !HASH32_RE.test(envelope.transactionHash ?? '')) add('INVALID_ENVELOPE_IDENTITY', 'malformed canonical envelope identity')
  for (const [field, value] of [['predecessorStateCommitment', body.predecessorStateCommitment], ['successorStateCommitment', body.execution?.successorStateCommitment], ['logsCommitment', body.execution?.logsCommitment], ['executionResultCommitment', body.execution?.executionResultCommitment]]) if (!DIGEST_RE.test(value ?? '')) add('INVALID_COMMITMENT', `${field} malformed`)
  if (!Object.values(VALIDATION_STATUS).includes(body.validation?.status) || !TOKEN_RE.test(body.validation?.classification ?? '')) add('INVALID_VALIDATION', 'invalid validation outcome')
  const execution = body.execution
  if (!execution || !Object.values(ENVELOPE_LIFECYCLE).includes(execution.lifecycle)) add('INVALID_LIFECYCLE', 'invalid lifecycle')
  if (!execution?.exception || !Object.values(EXCEPTION_KIND).includes(execution.exception.kind) || !TOKEN_RE.test(execution.exception.classification ?? '')) add('INVALID_EXCEPTION', 'invalid exception outcome')
  const gas = execution?.gasAndFee
  if (!gas || !validDecimal(gas.gasLimit) || !validDecimal(gas.gasUsed) || !validDecimal(gas.feePaid) || (gas && BigInt(gas.gasUsed) > BigInt(gas.gasLimit))) add('INVALID_GAS_ACCOUNTING', 'invalid gas/fee accounting')
  if (execution) {
    const expectedExecuted = execution.lifecycle !== ENVELOPE_LIFECYCLE.PRE_EXECUTION_INVALIDATED
    if (execution.executed !== expectedExecuted) add('IMPOSSIBLE_ENVELOPE_EVIDENCE', 'executed flag contradicts lifecycle')
    const valid = body.validation?.status === VALIDATION_STATUS.VALID
    if (execution.lifecycle === ENVELOPE_LIFECYCLE.SUCCESS && (!valid || execution.exception?.kind !== EXCEPTION_KIND.NONE)) add('IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalid success combination')
    if (execution.lifecycle === ENVELOPE_LIFECYCLE.REVERT && (!valid || execution.exception?.kind !== EXCEPTION_KIND.REVERT)) add('IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalid revert combination')
    if (execution.lifecycle === ENVELOPE_LIFECYCLE.PRE_EXECUTION_INVALIDATED && (valid || execution.exception?.kind !== EXCEPTION_KIND.VALIDATION || gas?.gasUsed !== '0' || gas?.feePaid !== '0' || body.predecessorStateCommitment !== execution.successorStateCommitment)) add('IMPOSSIBLE_ENVELOPE_EVIDENCE', 'invalid pre-execution invalidation combination')
  }
  if (!Array.isArray(body.semanticChangeCommitments)) add('INVALID_SEMANTIC_CHANGES', 'semantic change commitments must be an array')
}

export function verifyEnvelopeEvidence(record) {
  const findings = []
  try { verifyBody(record?.body, findings) } catch (error) { findings.push(Object.freeze({ code: 'MALFORMED_EVIDENCE', detail: String(error?.message ?? error) })) }
  if (!record?.receipt || record.receipt.domain !== DOMAIN || record.receipt.algorithm !== 'sha256' || !DIGEST_RE.test(record.receipt.digest ?? '')) findings.push(Object.freeze({ code: 'INVALID_RECEIPT', detail: 'invalid receipt shape' }))
  else {
    try { if (hash(canonical(record.body)) !== record.receipt.digest) findings.push(Object.freeze({ code: 'RECEIPT_MISMATCH', detail: 'body does not match receipt' })) } catch (error) { findings.push(Object.freeze({ code: 'NONDETERMINISTIC_EVIDENCE', detail: String(error?.message ?? error) })) }
  }
  return Object.freeze({ valid: findings.length === 0, findings: Object.freeze(findings), receipt: record?.receipt ?? null })
}
export const isEnvelopeEvidenceVerified = (result) => result?.valid === true && Array.isArray(result.findings) && result.findings.length === 0
export function exportEnvelopeEvidence(record) {
  requireCondition(isEnvelopeEvidenceVerified(verifyEnvelopeEvidence(record)), 'UNVERIFIED_ENVELOPE_EVIDENCE', 'cannot export invalid envelope evidence')
  return `${canonical(record)}\n`
}
