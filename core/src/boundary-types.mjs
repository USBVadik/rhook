// Canonical typed boundary values.
//
// Parsing happens once at ingress. Consumers receive nominal frozen objects, so
// valid absence, not-computed, zero, and empty values cannot collapse into one
// another or into undefined.

import { fail, requireCondition, rejectUndefined, rejectRawScalar } from './errors.mjs'

// ---------------------------------------------------------------------------
// Nominal brand infrastructure.
// A branded value is a frozen object carrying a private KIND tag. Raw strings
// can never satisfy a typed boundary because the guard checks the tag, not a
// regex-at-consumer-site.
// ---------------------------------------------------------------------------

const BRAND = Symbol('rhook/core/typed-value-brand')

function brand(kind, value, extra = {}) {
  return Object.freeze({ [BRAND]: kind, kind, value, ...extra })
}

function isBranded(x, kind) {
  return x !== null && typeof x === 'object' && x[BRAND] === kind
}

// ---------------------------------------------------------------------------
// Lexical validators. Applied ONCE, at ingress. Never re-run at consumer sites.
// ---------------------------------------------------------------------------

const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/
const HASH32_RE = /^0x[0-9a-f]{64}$/           // canonical: 0x + lowercase 32-byte
const DIGEST_RE = /^[0-9a-f]{64}$/             // bare lowercase sha-256 digest
const QUANTITY_RE = /^(?:0|[1-9][0-9]*)$/       // canonical decimal, no leading zeros
const HEXBYTES_RE = /^0x(?:[0-9a-f]{2})*$/      // even-length lowercase hex, may be empty (0x)
const BLOCKNUM_RE = /^(?:0|[1-9][0-9]*)$/

function requireString(value, code, label) {
  rejectUndefined(value, code, `${label} is undefined`)
  requireCondition(typeof value === 'string', code, `${label} must be a string, not ${typeof value}`)
  return value
}

// ---------------------------------------------------------------------------
// Kind tags (exported so callers switch on a stable string, never a truthiness test).
// ---------------------------------------------------------------------------

export const KIND = Object.freeze({
  ADDRESS: 'Address',
  HASH32: 'Hash32',
  DIGEST: 'Digest',
  COMMITMENT: 'Commitment',
  QUANTITY: 'Quantity',
  BLOCK_NUMBER: 'BlockNumber',
  HEXBYTES: 'HexBytes',
})

// ---------------------------------------------------------------------------
// Address (20-byte). Stored canonically as 0x + 40 lowercase hex.
// string<->Address conversion happens here, once.
// No coercion — a non-string or malformed value is a typed error.
// ---------------------------------------------------------------------------

export function parseAddress(raw) {
  const s = requireString(raw, 'INVALID_ADDRESS', 'address')
  requireCondition(ADDRESS_RE.test(s), 'INVALID_ADDRESS', `address is not a 20-byte hex value: ${s}`)
  return brand(KIND.ADDRESS, s.toLowerCase())
}

/** The explicit ZERO address as an Address (never a bare string, never null). */
export function createZeroAddress() {
  return brand(KIND.ADDRESS, '0x0000000000000000000000000000000000000000')
}

export function isAddress(x) {
  return isBranded(x, KIND.ADDRESS)
}

export function isZeroAddress(x) {
  return isAddress(x) && x.value === '0x0000000000000000000000000000000000000000'
}

export function requireAddress(x, code = 'EXPECTED_ADDRESS') {
  requireCondition(isAddress(x), code, 'value is not a typed Address')
  return x
}

// ---------------------------------------------------------------------------
// Hash32 / Digest / Commitment. Three distinct nominal ids that MUST NOT
// be interchanged even though all are 32 bytes.
// ---------------------------------------------------------------------------

export function parseHash32(raw) {
  const s = requireString(raw, 'INVALID_HASH32', 'hash32')
  requireCondition(HASH32_RE.test(s), 'INVALID_HASH32', `not a canonical 0x-prefixed lowercase 32-byte hash: ${s}`)
  return brand(KIND.HASH32, s)
}

export function isHash32(x) {
  return isBranded(x, KIND.HASH32)
}

export function parseDigest(raw) {
  const s = requireString(raw, 'INVALID_DIGEST', 'digest')
  requireCondition(DIGEST_RE.test(s), 'INVALID_DIGEST', `not a bare lowercase sha-256 digest: ${s}`)
  return brand(KIND.DIGEST, s)
}

export function isDigest(x) {
  return isBranded(x, KIND.DIGEST)
}

/** A commitment is a Digest tagged with a domain label, kept distinct from a raw Digest. */
export function createCommitment(rawDigest, domain) {
  const d = parseDigest(rawDigest)
  const label = requireString(domain, 'INVALID_COMMITMENT', 'commitment domain')
  requireCondition(label.length > 0, 'INVALID_COMMITMENT', 'commitment domain must be non-empty')
  return brand(KIND.COMMITMENT, d.value, { domain: label })
}

export function isCommitment(x) {
  return isBranded(x, KIND.COMMITMENT)
}

// ---------------------------------------------------------------------------
// Quantity (non-negative integer, e.g. balance/nonce). Carried as canonical
// decimal string + BigInt. Consumers never call BigInt() on unvalidated input.
// Explicit ZERO quantity is a present, defined value — NOT absence.
// ---------------------------------------------------------------------------

export function parseQuantity(raw) {
  const s = requireString(raw, 'INVALID_QUANTITY', 'quantity')
  requireCondition(QUANTITY_RE.test(s), 'INVALID_QUANTITY', `not a canonical non-negative decimal: ${s}`)
  return brand(KIND.QUANTITY, s, { big: BigInt(s) })
}

export function createZeroQuantity() {
  return brand(KIND.QUANTITY, '0', { big: 0n })
}

export function isQuantity(x) {
  return isBranded(x, KIND.QUANTITY)
}

export function isZeroQuantity(x) {
  return isQuantity(x) && x.big === 0n
}

// ---------------------------------------------------------------------------
// BlockNumber (non-negative integer). Distinct nominal type from Quantity so a
// block number can never be passed where a balance is expected and vice-versa.
// ---------------------------------------------------------------------------

export function parseBlockNumber(raw) {
  const s = requireString(raw, 'INVALID_BLOCK_NUMBER', 'blockNumber')
  requireCondition(BLOCKNUM_RE.test(s), 'INVALID_BLOCK_NUMBER', `not a canonical block number: ${s}`)
  return brand(KIND.BLOCK_NUMBER, s, { big: BigInt(s) })
}

export function isBlockNumber(x) {
  return isBranded(x, KIND.BLOCK_NUMBER)
}

// ---------------------------------------------------------------------------
// HexBytes (calldata / code). The EMPTY byte string `0x` is a present, defined,
// distinct value (empty code) — it is NOT the same as an absent account.
// ---------------------------------------------------------------------------

export function parseHexBytes(raw) {
  const s = requireString(raw, 'INVALID_HEXBYTES', 'hexBytes')
  requireCondition(HEXBYTES_RE.test(s), 'INVALID_HEXBYTES', `not even-length lowercase 0x hex: ${s}`)
  return brand(KIND.HEXBYTES, s, { byteLength: (s.length - 2) / 2 })
}

export function createEmptyCode() {
  return brand(KIND.HEXBYTES, '0x', { byteLength: 0 })
}

export function isHexBytes(x) {
  return isBranded(x, KIND.HEXBYTES)
}

export function isEmptyCode(x) {
  return isHexBytes(x) && x.byteLength === 0
}

// ---------------------------------------------------------------------------
// PRESENCE — the explicit, total, non-collapsible absence encoding.
//
//   PRESENT      : a value that exists and is defined (may itself be ZERO/EMPTY)
//   VALID_ABSENT : a lookup that legitimately found nothing (depth-0 caller,
//                  key-not-present) — a first-class SUCCESS, never an error
//   NOT_COMPUTED : a not-yet-computed result — distinct from "computed to absent"
//
// A present ZERO, an EMPTY collection, a key-not-present, and a not-computed
// result therefore each have a DISTINCT typed representation. None reduces to
// null/false/undefined/mismatch.
// ---------------------------------------------------------------------------

export const PRESENCE = Object.freeze({
  PRESENT: 'PRESENT',
  VALID_ABSENT: 'VALID_ABSENT',
  NOT_COMPUTED: 'NOT_COMPUTED',
})

export function present(value) {
  rejectUndefined(value, 'INVALID_PRESENCE', 'PRESENT wraps undefined')
  rejectRawScalar(value, 'INVALID_PRESENCE', 'PRESENT must wrap a typed value, not a raw string/number')
  return Object.freeze({ presence: PRESENCE.PRESENT, value })
}

export function validAbsent(reason) {
  const r = requireString(reason, 'INVALID_PRESENCE', 'validAbsent reason')
  return Object.freeze({ presence: PRESENCE.VALID_ABSENT, value: null, reason: r })
}

export function notComputed(reason) {
  const r = requireString(reason, 'INVALID_PRESENCE', 'notComputed reason')
  return Object.freeze({ presence: PRESENCE.NOT_COMPUTED, value: null, reason: r })
}

export function isPresent(p) {
  return p !== null && typeof p === 'object' && p.presence === PRESENCE.PRESENT
}

export function isValidAbsent(p) {
  return p !== null && typeof p === 'object' && p.presence === PRESENCE.VALID_ABSENT
}

export function isNotComputed(p) {
  return p !== null && typeof p === 'object' && p.presence === PRESENCE.NOT_COMPUTED
}

// ---------------------------------------------------------------------------
// Account presence/absence & storage presence/absence.
//
// empty-code vs absent-account is the canonical trap: an account that EXISTS
// with empty code is PRESENT with an emptyCode HexBytes; an account that does
// NOT exist is VALID_ABSENT. These can never collapse into one another.
// ---------------------------------------------------------------------------

export function presentAccount({ balance, nonce, code }) {
  requireCondition(isQuantity(balance), 'INVALID_ACCOUNT', 'account balance must be a typed Quantity')
  requireCondition(isQuantity(nonce), 'INVALID_ACCOUNT', 'account nonce must be a typed Quantity')
  requireCondition(isHexBytes(code), 'INVALID_ACCOUNT', 'account code must be typed HexBytes')
  return present(Object.freeze({ balance, nonce, code }))
}

export function absentAccount() {
  // A legitimately non-existent account is a first-class VALID_ABSENT,
  // NOT a TypeError and NOT an undefined.
  return validAbsent('ACCOUNT_DOES_NOT_EXIST')
}

/** A storage slot that holds an explicit ZERO word is PRESENT-with-zero. */
export function presentStorage(hash32Word) {
  requireCondition(isHash32(hash32Word), 'INVALID_STORAGE', 'storage word must be a typed Hash32')
  return present(Object.freeze({ word: hash32Word }))
}

/** A storage slot that was never written is VALID_ABSENT — distinct from a zero word. */
export function absentStorage() {
  return validAbsent('STORAGE_SLOT_NOT_PRESENT')
}

export const ZERO_STORAGE_WORD = '0x0000000000000000000000000000000000000000000000000000000000000000'

export function createZeroStorageWord() {
  return parseHash32(ZERO_STORAGE_WORD)
}
