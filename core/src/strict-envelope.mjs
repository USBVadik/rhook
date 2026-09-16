import {
  DECIMAL_RE,
  DIGEST_RE,
  ENVELOPE_DOMAIN,
  HASH32_RE,
  TOKEN_RE,
  addFinding,
  arrayEqual,
  exactObject,
  isCanonicalDecimal,
  isCanonicalDigest,
  isStableToken,
  sha256Canonical,
  strictlyIncreasing,
  validDomain,
  validEnvelopeIdentity,
  verifyInStages,
} from './strict-common.mjs'

const LIFECYCLES = new Set(['SUCCESS', 'REVERT', 'PRE_EXECUTION_INVALIDATED'])
const VALIDATION = new Set(['VALID', 'INVALID'])
const EXCEPTIONS = new Set(['NONE', 'REVERT', 'VALIDATION'])

function shape(record, findings) {
  if (!exactObject(record, ['body', 'receipt'], findings, 'INVALID_ENVELOPE_RECORD_SHAPE', '$')) return
  const body = record.body
  if (!exactObject(body, ['schema', 'envelope', 'predecessorStateCommitment', 'validation', 'execution', 'semanticChangeCommitments'], findings, 'INVALID_ENVELOPE_BODY_SHAPE', '$.body')) return
  exactObject(body.envelope, ['blockNumber', 'transactionIndex', 'transactionHash'], findings, 'INVALID_ENVELOPE_IDENTITY_SHAPE', '$.body.envelope')
  exactObject(body.validation, ['status', 'classification'], findings, 'INVALID_VALIDATION_SHAPE', '$.body.validation')
  if (exactObject(body.execution, ['lifecycle', 'executed', 'exception', 'gasAndFee', 'logsCommitment', 'successorStateCommitment', 'executionResultCommitment'], findings, 'INVALID_EXECUTION_SHAPE', '$.body.execution')) {
    if (exactObject(body.execution.exception, ['kind', 'classification', 'dataCommitment'], findings, 'INVALID_EXCEPTION_SHAPE', '$.body.execution.exception')) {
      const data = body.execution.exception.dataCommitment
      if (data?.presence === 'PRESENT') exactObject(data, ['presence', 'digest'], findings, 'INVALID_EXCEPTION_DATA_SHAPE', '$.body.execution.exception.dataCommitment')
      else exactObject(data, ['presence', 'reason'], findings, 'INVALID_EXCEPTION_DATA_SHAPE', '$.body.execution.exception.dataCommitment')
    }
    exactObject(body.execution.gasAndFee, ['gasLimit', 'gasUsed', 'feePaid'], findings, 'INVALID_GAS_AND_FEE_SHAPE', '$.body.execution.gasAndFee')
  }
  if (!Array.isArray(body.semanticChangeCommitments)) addFinding(findings, 'INVALID_SEMANTIC_CHANGE_COMMITMENTS', '$.body.semanticChangeCommitments', 'expected an array')
  else body.semanticChangeCommitments.forEach((entry, index) => exactObject(entry, ['domain', 'digest'], findings, 'INVALID_SEMANTIC_CHANGE_COMMITMENT_SHAPE', `$.body.semanticChangeCommitments[${index}]`))
  exactObject(record.receipt, ['domain', 'algorithm', 'digest'], findings, 'INVALID_ENVELOPE_RECEIPT_SHAPE', '$.receipt')
}

function types(record, findings) {
  const { body, receipt } = record
  if (body.schema !== 'generic-ce-envelope-evidence/2') addFinding(findings, 'INVALID_ENVELOPE_SCHEMA', '$.body.schema', 'unexpected schema')
  if (!validEnvelopeIdentity(body.envelope)) addFinding(findings, 'INVALID_ENVELOPE_IDENTITY', '$.body.envelope', 'canonical block/index/hash required')
  if (!isCanonicalDigest(body.predecessorStateCommitment ?? '')) addFinding(findings, 'INVALID_PREDECESSOR_COMMITMENT', '$.body.predecessorStateCommitment', 'expected canonical SHA-256 digest')
  if (!VALIDATION.has(body.validation.status) || !isStableToken(body.validation.classification ?? '')) addFinding(findings, 'INVALID_VALIDATION', '$.body.validation', 'invalid status or classification')
  const execution = body.execution
  if (!LIFECYCLES.has(execution.lifecycle) || typeof execution.executed !== 'boolean') addFinding(findings, 'INVALID_LIFECYCLE', '$.body.execution', 'invalid lifecycle or executed flag')
  if (!EXCEPTIONS.has(execution.exception.kind) || !isStableToken(execution.exception.classification ?? '')) addFinding(findings, 'INVALID_EXCEPTION', '$.body.execution.exception', 'invalid exception kind or classification')
  const data = execution.exception.dataCommitment
  if (data.presence === 'PRESENT') {
    if (!isCanonicalDigest(data.digest ?? '')) addFinding(findings, 'INVALID_EXCEPTION_DATA', '$.body.execution.exception.dataCommitment.digest', 'expected canonical digest')
  } else if (data.presence === 'VALID_ABSENT') {
    if (!isStableToken(data.reason ?? '')) addFinding(findings, 'INVALID_EXCEPTION_DATA', '$.body.execution.exception.dataCommitment.reason', 'expected stable reason token')
  } else addFinding(findings, 'INVALID_EXCEPTION_DATA', '$.body.execution.exception.dataCommitment.presence', 'invalid presence')
  const gas = execution.gasAndFee
  if (!isCanonicalDecimal(gas.gasLimit ?? '') || !isCanonicalDecimal(gas.gasUsed ?? '') || !isCanonicalDecimal(gas.feePaid ?? '')) addFinding(findings, 'INVALID_GAS_AND_FEE', '$.body.execution.gasAndFee', 'canonical unsigned decimal quantities required')
  else if (BigInt(gas.gasUsed) > BigInt(gas.gasLimit)) addFinding(findings, 'INVALID_GAS_AND_FEE', '$.body.execution.gasAndFee.gasUsed', 'gasUsed exceeds gasLimit')
  for (const [name, value] of [['logsCommitment', execution.logsCommitment], ['successorStateCommitment', execution.successorStateCommitment], ['executionResultCommitment', execution.executionResultCommitment]]) {
    if (!isCanonicalDigest(value ?? '')) addFinding(findings, 'INVALID_EXECUTION_COMMITMENT', `$.body.execution.${name}`, 'expected canonical SHA-256 digest')
  }
  body.semanticChangeCommitments.forEach((entry, index) => {
    if (!validDomain(entry.domain) || !isCanonicalDigest(entry.digest ?? '')) addFinding(findings, 'INVALID_SEMANTIC_CHANGE_COMMITMENT', `$.body.semanticChangeCommitments[${index}]`, 'invalid domain or digest')
  })
  if (receipt.domain !== ENVELOPE_DOMAIN || receipt.algorithm !== 'sha256' || !isCanonicalDigest(receipt.digest ?? '')) addFinding(findings, 'INVALID_ENVELOPE_RECEIPT', '$.receipt', 'invalid domain, algorithm, or digest')
}

function ordering(record, findings) {
  const identities = record.body.semanticChangeCommitments.map((entry) => `${entry.domain}:${entry.digest}`)
  const sorted = [...identities].sort((left, right) => left.localeCompare(right))
  if (!arrayEqual(identities, sorted)) addFinding(findings, 'NONCANONICAL_SEMANTIC_CHANGE_ORDER', '$.body.semanticChangeCommitments', 'entries must be canonically ordered')
  if (new Set(identities).size !== identities.length) addFinding(findings, 'DUPLICATE_SEMANTIC_CHANGE_COMMITMENT', '$.body.semanticChangeCommitments', 'entries must be unique')
}

function commitment(record, findings) {
  if (sha256Canonical(record.body) !== record.receipt.digest) addFinding(findings, 'ENVELOPE_RECEIPT_MISMATCH', '$.receipt.digest', 'body does not match receipt')
}

function semantics(record, findings) {
  const { body } = record
  const { execution } = body
  const valid = body.validation.status === 'VALID'
  const data = execution.exception.dataCommitment
  const expectedExecuted = execution.lifecycle !== 'PRE_EXECUTION_INVALIDATED'
  if (execution.executed !== expectedExecuted) addFinding(findings, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', '$.body.execution.executed', 'executed contradicts lifecycle')
  if (valid && body.validation.classification !== 'VALID_ENVELOPE') addFinding(findings, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', '$.body.validation.classification', 'valid envelope requires VALID_ENVELOPE classification')
  if (!valid && body.validation.classification === 'VALID_ENVELOPE') addFinding(findings, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', '$.body.validation.classification', 'invalid envelope cannot use VALID_ENVELOPE classification')
  if (execution.lifecycle === 'SUCCESS') {
    if (!valid || execution.exception.kind !== 'NONE' || execution.exception.classification !== 'NO_EXCEPTION' || data.presence !== 'VALID_ABSENT' || data.reason !== 'NOT_APPLICABLE') addFinding(findings, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', '$.body.execution', 'invalid success combination')
  }
  if (execution.lifecycle === 'REVERT') {
    const validData = data.presence === 'PRESENT' || (data.presence === 'VALID_ABSENT' && data.reason === 'NO_REVERT_DATA_COMMITMENT')
    if (!valid || execution.exception.kind !== 'REVERT' || execution.exception.classification === 'NO_EXCEPTION' || !validData) addFinding(findings, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', '$.body.execution', 'invalid revert combination')
  }
  if (execution.lifecycle === 'PRE_EXECUTION_INVALIDATED') {
    if (valid || execution.exception.kind !== 'VALIDATION' || execution.exception.classification !== body.validation.classification || data.presence !== 'VALID_ABSENT' || data.reason !== 'NOT_EXECUTED' || execution.gasAndFee.gasUsed !== '0' || execution.gasAndFee.feePaid !== '0' || body.predecessorStateCommitment !== execution.successorStateCommitment) addFinding(findings, 'IMPOSSIBLE_ENVELOPE_EVIDENCE', '$.body.execution', 'invalid pre-execution invalidation combination')
  }
}

export function verifyEnvelopeEvidenceStrict(record) {
  return verifyInStages([
    (findings) => shape(record, findings),
    (findings) => types(record, findings),
    (findings) => ordering(record, findings),
    () => {},
    (findings) => commitment(record, findings),
    (findings) => semantics(record, findings),
  ], { receipt: record?.receipt ?? null })
}

export const isEnvelopeEvidenceStrictlyVerified = (result) => result?.valid === true && Array.isArray(result.findings) && result.findings.length === 0
