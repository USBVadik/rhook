import { createHash } from 'node:crypto'

export const ENVELOPE_DOMAIN = 'rhook/gcec-02/envelope-evidence/v2'
export const TRANSCRIPT_DOMAIN = 'rhook/gcec-02/branch-evidence-transcript/v2'
export const DIGEST_RE = /^[0-9a-f]{64}$/
export const HASH32_RE = /^0x[0-9a-f]{64}$/
export const ADDRESS_RE = /^0x[0-9a-f]{40}$/
export const HEX_RE = /^0x(?:[0-9a-f]{2})*$/
export const SELECTOR_RE = /^0x(?:[0-9a-f]{8})?$/
export const DECIMAL_RE = /^(?:0|[1-9][0-9]*)$/
export const TOKEN_RE = /^[A-Z][A-Z0-9_]{0,95}$/
export const DOMAIN_RE = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
export const RECORD_DOMAIN_RE = /^[A-Za-z](?:[A-Za-z0-9_.:/-]{0,126}[A-Za-z0-9_.:-])?$/

export const isCanonicalDigest = (value) => typeof value === 'string' && DIGEST_RE.test(value)
export const isCanonicalHash32 = (value) => typeof value === 'string' && HASH32_RE.test(value)
export const isCanonicalAddress = (value) => typeof value === 'string' && ADDRESS_RE.test(value)
export const isCanonicalHex = (value) => typeof value === 'string' && HEX_RE.test(value)
export const isCanonicalSelector = (value) => typeof value === 'string' && SELECTOR_RE.test(value)
export const isCanonicalDecimal = (value) => typeof value === 'string' && DECIMAL_RE.test(value)
export const isStableToken = (value) => typeof value === 'string' && TOKEN_RE.test(value)

export function canonical(value) {
  if (value === null) return 'null'
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('number must be a safe integer')
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (!isPlainObject(value)) throw new Error('unsupported canonical value')
  const keys = Object.keys(value).sort()
  return `{${keys.map((key) => {
    if (value[key] === undefined) throw new Error(`undefined field ${key}`)
    return `${JSON.stringify(key)}:${canonical(value[key])}`
  }).join(',')}}`
}

export const sha256Canonical = (value) => createHash('sha256').update(canonical(value)).digest('hex')
export const isPlainObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)

export function addFinding(findings, code, path, detail) {
  findings.push(Object.freeze({ code, path, detail }))
}

export function exactObject(value, expectedKeys, findings, code, path) {
  if (!isPlainObject(value)) {
    addFinding(findings, code, path, 'expected a plain object')
    return false
  }
  const actual = Object.keys(value).sort()
  const expected = [...expectedKeys].sort()
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    const unknown = actual.filter((key) => !expected.includes(key))
    const missing = expected.filter((key) => !actual.includes(key))
    addFinding(findings, code, path, `exact keys required; unknown=[${unknown.join(',')}], missing=[${missing.join(',')}]`)
    return false
  }
  return true
}

export function validDomain(value) {
  return typeof value === 'string' && DOMAIN_RE.test(value) && !/[\\/]|rci-\d{3}|secret|token/i.test(value)
}

export function validRecordDomain(value) {
  return typeof value === 'string' && RECORD_DOMAIN_RE.test(value) && !value.includes('//') && !value.includes('\\')
}

export function validCommitmentSummary(value) {
  return isPlainObject(value) && Object.keys(value).length === 2 && Object.hasOwn(value, 'domain') && Object.hasOwn(value, 'digest') && validDomain(value.domain) && isCanonicalDigest(value.digest)
}

export function validEnvelopeIdentity(value) {
  return isPlainObject(value)
    && Object.keys(value).length === 3
    && Object.hasOwn(value, 'blockNumber')
    && Object.hasOwn(value, 'transactionIndex')
    && Object.hasOwn(value, 'transactionHash')
    && isCanonicalDecimal(value.blockNumber)
    && isCanonicalDecimal(value.transactionIndex)
    && isCanonicalHash32(value.transactionHash)
}

export function sameEnvelopeIdentity(left, right) {
  return validEnvelopeIdentity(left) && validEnvelopeIdentity(right)
    && left.blockNumber === right.blockNumber
    && left.transactionIndex === right.transactionIndex
    && left.transactionHash === right.transactionHash
}

export function verifyInStages(stages, receiptField = null) {
  const findings = []
  for (const stage of stages) {
    try { stage(findings) } catch (error) { addFinding(findings, 'MALFORMED_EVIDENCE', '$', String(error?.message ?? error)) }
    if (findings.length > 0) break
  }
  return Object.freeze({
    valid: findings.length === 0,
    findings: Object.freeze(findings),
    ...(receiptField === null ? {} : receiptField),
  })
}

export function strictlyIncreasing(values) {
  return values.every((value, index) => index === 0 || values[index - 1] < value)
}

export function arrayEqual(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index])
}
