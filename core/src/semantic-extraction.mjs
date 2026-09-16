// State-bound semantic extraction and deterministic branch comparison.
//
// Engineering conformance only. NO scientific validation, NO historical data,
// NO network, NO protocol adapter, NO recovery policy, NO multi-target
// intervention, NO historical case identity. This module reuses the section-1
// typed boundary layer (boundary-types.mjs) and the section-2 evidence
// commitments (execution-evidence.mjs) unchanged.
//
// PURPOSE. A single SEMANTIC EXTRACTION is the atomic unit of "what a run says
// about one observable fact". Every extraction is bound, at construction, to
// SIX things and cannot exist without all six:
//
//   (1) exact endpoint            — the callable observed (address + selector),
//                                   typed via section-1 Address + HexBytes.
//   (2) exact post-state commitment — a section-2 execution-evidence receipt
//                                   digest (Digest brand). The value being
//                                   extracted MUST trace back to a stored
//                                   execution-state commitment; an extraction
//                                   with no committed post-state is rejected.
//   (3) typed record identity     — a section-1 Commitment (domain-tagged
//                                   Digest) naming the record the fact came
//                                   from. Distinct from the post-state receipt.
//   (4) canonical lookup/source descriptor — HOW the value was located
//                                   (storage-slot Hash32, return-word Hash32,
//                                   account-field, or code). Canonical + typed.
//   (5) explicit presence state   — PRESENT | VALID_ABSENT | NOT_COMPUTED from
//                                   section-1. ABSENT is a first-class state.
//   (6) canonical value           — a section-1 typed value (Quantity, Hash32,
//                                   HexBytes, Address, account/storage record),
//                                   present ONLY when presence is PRESENT.
//
// The deterministic diff compares an ACTUAL extraction to a COUNTERFACTUAL
// extraction of THE SAME semantic slot. Its central invariant:
//
//   ABSENT is NOT zero, NOT empty, NOT missing, NOT not-computed.
//
// A slot that is VALID_ABSENT on one side and PRESENT-with-zero (or
// PRESENT-with-empty-code) on the other is a REAL, TYPED difference, never a
// collapsed "both falsy -> equal". A NOT_COMPUTED side never silently reads as
// absence. Every compared value is traceable to a stored post-state commitment,
// so a diff cannot be produced from a value that was never committed.

import {
  KIND,
  PRESENCE,
  isAddress,
  isHash32,
  isDigest,
  parseDigest,
  isCommitment,
  isQuantity,
  isHexBytes,
  isPresent,
  isValidAbsent,
  isNotComputed,
} from './boundary-types.mjs'
import { fail, requireCondition, rejectUndefined } from './errors.mjs'
import {
  RESULT,
  resultValid,
  resultError,
} from './port-results.mjs'

// A selector is a 4-byte function selector (typed as HexBytes with byteLength 4)
// or the empty selector `0x` for a raw account/storage observation.
function requireSelector(sel) {
  requireCondition(isHexBytes(sel), 'INVALID_ENDPOINT', 'endpoint selector must be typed HexBytes')
  requireCondition(sel.byteLength === 4 || sel.byteLength === 0, 'INVALID_ENDPOINT',
    `endpoint selector must be 4 bytes (a call) or 0 bytes (a raw observation), got ${sel.byteLength}`)
  return sel
}

// ---------------------------------------------------------------------------
// (1) ENDPOINT — the exact callable observed. Address (section-1) + selector.
// ---------------------------------------------------------------------------

export function makeEndpoint(address, selector) {
  requireCondition(isAddress(address), 'INVALID_ENDPOINT', 'endpoint address must be a typed Address (section-1)')
  requireSelector(selector)
  return Object.freeze({
    kind: 'Endpoint',
    address: address.value,
    selector: selector.value,
    selectorBytes: selector.byteLength,
  })
}

export function isEndpoint(x) {
  return x !== null && typeof x === 'object' && x.kind === 'Endpoint'
}

function endpointKey(e) {
  return `${e.address}#${e.selector}`
}

// ---------------------------------------------------------------------------
// (4) LOOKUP / SOURCE DESCRIPTOR — canonical, typed description of HOW a value
// was located. Every variant carries a typed section-1 locator, never a raw
// string, so the descriptor itself cannot smuggle an un-parsed key.
// ---------------------------------------------------------------------------

export const SOURCE = Object.freeze({
  STORAGE_SLOT: 'STORAGE_SLOT',   // read at a storage slot (Hash32 slot key)
  RETURN_WORD: 'RETURN_WORD',     // a 32-byte return word (Hash32 position hash)
  ACCOUNT_FIELD: 'ACCOUNT_FIELD', // balance | nonce | code of an account
  CODE: 'CODE',                   // the account code bytes
})

const ACCOUNT_FIELDS = Object.freeze(new Set(['balance', 'nonce', 'code']))

export function sourceStorageSlot(slotKey) {
  requireCondition(isHash32(slotKey), 'INVALID_SOURCE', 'storage-slot source key must be a typed Hash32 (section-1)')
  return Object.freeze({ kind: SOURCE.STORAGE_SLOT, slot: slotKey.value })
}

export function sourceReturnWord(positionHash) {
  requireCondition(isHash32(positionHash), 'INVALID_SOURCE', 'return-word source position must be a typed Hash32')
  return Object.freeze({ kind: SOURCE.RETURN_WORD, position: positionHash.value })
}

export function sourceAccountField(field) {
  rejectUndefined(field, 'INVALID_SOURCE', 'account-field source needs a field name')
  requireCondition(ACCOUNT_FIELDS.has(field), 'INVALID_SOURCE', `account field must be one of balance|nonce|code: ${field}`)
  return Object.freeze({ kind: SOURCE.ACCOUNT_FIELD, field })
}

export function sourceCode() {
  return Object.freeze({ kind: SOURCE.CODE })
}

function isSource(s) {
  return s !== null && typeof s === 'object'
    && (s.kind === SOURCE.STORAGE_SLOT || s.kind === SOURCE.RETURN_WORD
      || s.kind === SOURCE.ACCOUNT_FIELD || s.kind === SOURCE.CODE)
}

function sourceKey(s) {
  switch (s.kind) {
    case SOURCE.STORAGE_SLOT: return `${s.kind}:${s.slot}`
    case SOURCE.RETURN_WORD: return `${s.kind}:${s.position}`
    case SOURCE.ACCOUNT_FIELD: return `${s.kind}:${s.field}`
    case SOURCE.CODE: return `${s.kind}`
    default: return fail('INVALID_SOURCE', 'unknown source kind')
  }
}

// ---------------------------------------------------------------------------
// Post-state commitment binding (2) + typed record identity (3).
//
// The post-state commitment is a section-2 evidence RECEIPT digest — the value
// being extracted is asserted to have existed in the execution state committed
// by that receipt. It is accepted either as a bare Digest (section-1) or as a
// section-2 verified record's receipt.digest. The typed record identity is a
// section-1 Commitment naming the source record.
// ---------------------------------------------------------------------------

function requirePostStateDigest(commitment) {
  // Accept a section-1 Digest directly, or a section-2 receipt object
  // { domain, algo, digest }. Reject anything that is not traceable to a
  // stored commitment — an extraction with no committed post-state is illegal.
  rejectUndefined(commitment, 'MISSING_POST_STATE', 'extraction requires a post-state commitment (no untraceable values)')
  if (isDigest(commitment)) return commitment.value
  if (commitment !== null && typeof commitment === 'object'
    && typeof commitment.algo === 'string' && typeof commitment.digest === 'string') {
    requireCondition(commitment.algo === 'sha256', 'INVALID_POST_STATE', 'post-state receipt algo must be sha256')
    // Re-validate through the section-1 Digest parser so a malformed digest
    // string can never be accepted as a commitment.
    return parseDigest(commitment.digest).value
  }
  return fail('INVALID_POST_STATE', 'post-state commitment must be a section-1 Digest or a section-2 receipt')
}

// ---------------------------------------------------------------------------
// SEMANTIC EXTRACTION — the bound atomic unit. Construction enforces all six
// bindings; there is no way to build a partially-bound extraction.
// ---------------------------------------------------------------------------

export function makeExtraction({ endpoint, postState, recordIdentity, source, presence }) {
  requireCondition(isEndpoint(endpoint), 'INVALID_EXTRACTION', 'extraction requires a typed Endpoint (binding 1)')
  const postStateDigest = requirePostStateDigest(postState) // binding 2
  requireCondition(isCommitment(recordIdentity), 'INVALID_EXTRACTION',
    'extraction requires a typed record-identity Commitment (binding 3, section-1)')
  requireCondition(isSource(source), 'INVALID_EXTRACTION', 'extraction requires a canonical source descriptor (binding 4)')

  // binding 5 + 6: presence must be a section-1 Presence; a PRESENT presence
  // must carry a canonical typed value; a non-PRESENT presence must NOT.
  rejectUndefined(presence, 'INVALID_EXTRACTION', 'extraction requires an explicit presence state (binding 5)')
  requireCondition(isPresent(presence) || isValidAbsent(presence) || isNotComputed(presence),
    'INVALID_EXTRACTION', 'presence must be PRESENT | VALID_ABSENT | NOT_COMPUTED (section-1)')

  let value = null
  let valueKind = null
  if (isPresent(presence)) {
    value = presence.value
    valueKind = canonicalValueKind(value, source)
  }

  return Object.freeze({
    kind: 'SemanticExtraction',
    endpoint,
    postStateDigest,                 // (2) traceability anchor
    recordDomain: recordIdentity.domain,
    recordDigest: recordIdentity.value, // (3)
    source,                          // (4)
    presence: presence.presence,     // (5) 'PRESENT' | 'VALID_ABSENT' | 'NOT_COMPUTED'
    presenceReason: presence.reason ?? null,
    value,                           // (6) typed value, or null when not PRESENT
    valueKind,
  })
}

// A PRESENT extraction's value must be a section-1 typed value, and its type
// must be consistent with the source descriptor (a storage/return word is a
// Hash32; a code source is HexBytes; an account balance/nonce is a Quantity).
function canonicalValueKind(value, source) {
  requireCondition(value !== null && typeof value === 'object' && typeof value.kind === 'string',
    'INVALID_EXTRACTION', 'a PRESENT extraction value must be a section-1 typed value (binding 6)')
  switch (source.kind) {
    case SOURCE.STORAGE_SLOT:
    case SOURCE.RETURN_WORD:
      requireCondition(isHash32(value), 'INVALID_EXTRACTION',
        `${source.kind} value must be a typed Hash32 word`)
      return KIND.HASH32
    case SOURCE.CODE:
      requireCondition(isHexBytes(value), 'INVALID_EXTRACTION', 'CODE value must be typed HexBytes')
      return KIND.HEXBYTES
    case SOURCE.ACCOUNT_FIELD:
      if (source.field === 'code') {
        requireCondition(isHexBytes(value), 'INVALID_EXTRACTION', 'account code must be typed HexBytes')
        return KIND.HEXBYTES
      }
      requireCondition(isQuantity(value), 'INVALID_EXTRACTION',
        `account ${source.field} must be a typed Quantity`)
      return KIND.QUANTITY
    default:
      return fail('INVALID_EXTRACTION', 'unknown source kind for value binding')
  }
}

export function isExtraction(x) {
  return x !== null && typeof x === 'object' && x.kind === 'SemanticExtraction'
}

/** The canonical slot identity an extraction observes: endpoint + source. */
export function extractionSlotKey(x) {
  requireCondition(isExtraction(x), 'INVALID_EXTRACTION', 'not a SemanticExtraction')
  return `${endpointKey(x.endpoint)}|${sourceKey(x.source)}`
}

// ---------------------------------------------------------------------------
// TYPED VALUE EQUALITY — explicit, per-kind, no coercion. Two PRESENT values
// are equal only if they are the same section-1 kind AND canonically equal.
// A Quantity zero and an empty HexBytes are DIFFERENT kinds -> never equal.
// ---------------------------------------------------------------------------

function typedValueEqual(a, b) {
  if (a.kind !== b.kind) return false
  switch (a.kind) {
    case KIND.HASH32:
    case KIND.HEXBYTES:
    case KIND.ADDRESS:
      return a.value === b.value
    case KIND.QUANTITY:
    case KIND.BLOCK_NUMBER:
      return a.big === b.big
    default:
      return fail('INVALID_DIFF', `no typed equality for value kind ${a.kind}`)
  }
}

// ---------------------------------------------------------------------------
// DETERMINISTIC ACTUAL-vs-COUNTERFACTUAL DIFF.
//
// The two extractions MUST observe the same semantic slot (same endpoint, same
// source). The verdict is one of a closed, total set. ABSENT is never conflated
// with zero/empty/missing/not-computed: presence disagreement is its own
// verdict distinct from value difference.
// ---------------------------------------------------------------------------

export const DIFF = Object.freeze({
  EQUAL: 'EQUAL',                             // same presence; if PRESENT, same typed value
  VALUE_CHANGED: 'VALUE_CHANGED',             // both PRESENT, values differ (same kind)
  KIND_CHANGED: 'KIND_CHANGED',               // both PRESENT, different value kinds
  PRESENCE_CHANGED: 'PRESENCE_CHANGED',       // presence states differ (e.g. ABSENT vs PRESENT-zero)
  BOTH_ABSENT: 'BOTH_ABSENT',                 // both VALID_ABSENT — an agreement, not a change
  NOT_COMPARABLE: 'NOT_COMPARABLE',           // at least one side NOT_COMPUTED — cannot diff
})

// A post-state digest is traceable only if it satisfies the SAME bare-digest
// lexical contract parseDigest enforces at construction: a lowercase 64-hex
// sha-256 digest. This is the diff-time mirror of that parser, so a forged
// extraction-shaped object cannot pass a length-only check with non-hex bytes.
const POST_STATE_DIGEST_RE = /^[0-9a-f]{64}$/

function isTraceablePostStateDigest(d) {
  return typeof d === 'string' && POST_STATE_DIGEST_RE.test(d)
}

export function diffExtractions(actual, counterfactual) {
  requireCondition(isExtraction(actual), 'INVALID_DIFF', 'actual is not a SemanticExtraction')
  requireCondition(isExtraction(counterfactual), 'INVALID_DIFF', 'counterfactual is not a SemanticExtraction')

  // Same-slot guard: comparing two different observable slots is a category
  // error, not a diff. Fail closed rather than emit a meaningless verdict.
  requireCondition(extractionSlotKey(actual) === extractionSlotKey(counterfactual),
    'SLOT_MISMATCH', 'actual and counterfactual observe different slots (endpoint/source differ)')

  // Traceability: BOTH sides must trace to a stored post-state commitment. This
  // is guaranteed by construction (makeExtraction rejects an untraceable one),
  // re-asserted here so a hand-built object cannot bypass it. The re-assertion
  // must match the SAME lexical contract parseDigest enforces at construction
  // (a bare lowercase 64-hex sha-256 digest) — a length-only check would admit
  // 64 characters of non-hex garbage that traces to no stored commitment.
  requireCondition(isTraceablePostStateDigest(actual.postStateDigest),
    'UNTRACEABLE_VALUE', 'actual value does not trace to a stored post-state commitment')
  requireCondition(isTraceablePostStateDigest(counterfactual.postStateDigest),
    'UNTRACEABLE_VALUE', 'counterfactual value does not trace to a stored post-state commitment')

  const pa = actual.presence
  const pc = counterfactual.presence

  // NOT_COMPUTED on either side is never silently read as absence.
  if (pa === PRESENCE.NOT_COMPUTED || pc === PRESENCE.NOT_COMPUTED) {
    return buildVerdict(DIFF.NOT_COMPARABLE, actual, counterfactual,
      'at least one side is NOT_COMPUTED; a not-yet-computed side is never treated as ABSENT/zero/empty')
  }

  // Both absent — an agreement. Distinct from EQUAL-with-a-present-zero.
  if (pa === PRESENCE.VALID_ABSENT && pc === PRESENCE.VALID_ABSENT) {
    return buildVerdict(DIFF.BOTH_ABSENT, actual, counterfactual, 'both sides VALID_ABSENT')
  }

  // Presence disagreement — the core hardening: ABSENT vs PRESENT (even
  // PRESENT-with-zero or PRESENT-with-empty-code) is a real, typed difference.
  if (pa !== pc) {
    return buildVerdict(DIFF.PRESENCE_CHANGED, actual, counterfactual,
      `presence changed: ${pa} -> ${pc} (ABSENT is not zero/empty/missing)`)
  }

  // Both PRESENT: compare typed values without coercion.
  const av = actual.value
  const cv = counterfactual.value
  if (av.kind !== cv.kind) {
    return buildVerdict(DIFF.KIND_CHANGED, actual, counterfactual,
      `present value kind changed: ${av.kind} -> ${cv.kind}`)
  }
  if (typedValueEqual(av, cv)) {
    return buildVerdict(DIFF.EQUAL, actual, counterfactual, 'same presence and same typed value')
  }
  return buildVerdict(DIFF.VALUE_CHANGED, actual, counterfactual,
    `present ${av.kind} value changed`)
}

function buildVerdict(verdict, actual, counterfactual, note) {
  return Object.freeze({
    kind: 'CounterfactualDiff',
    verdict,
    slot: extractionSlotKey(actual),
    actual: summarizeSide(actual),
    counterfactual: summarizeSide(counterfactual),
    note,
  })
}

function summarizeSide(x) {
  return Object.freeze({
    presence: x.presence,
    valueKind: x.valueKind,
    value: x.presence === PRESENCE.PRESENT ? canonicalValueString(x.value) : null,
    postStateDigest: x.postStateDigest,
    recordDigest: x.recordDigest,
  })
}

function canonicalValueString(v) {
  switch (v.kind) {
    case KIND.QUANTITY:
    case KIND.BLOCK_NUMBER:
      return v.value // canonical decimal string
    default:
      return v.value // canonical 0x-hex string
  }
}

export function isDiffVerdict(x) {
  return x !== null && typeof x === 'object' && x.kind === 'CounterfactualDiff'
}

// ---------------------------------------------------------------------------
// DIFF as a discriminated port result — a diff that changed is a VALID result
// carrying the verdict; a NOT_COMPARABLE diff is an ERROR (the comparison could
// not be made), never a silent EQUAL. This keeps section-3 consistent with the
// section-2 / port-results contract.
// ---------------------------------------------------------------------------

export function diffAsResult(actual, counterfactual) {
  const v = diffExtractions(actual, counterfactual)
  if (v.verdict === DIFF.NOT_COMPARABLE) {
    return resultError('NOT_COMPARABLE', v.note)
  }
  return resultValid(v)
}
