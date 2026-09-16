// Discriminated port results.
//
// Reads and verification return explicit VALID, ABSENT, or ERROR branches. A
// legitimate absence cannot collapse into a value mismatch.

import { fail, requireCondition, rejectUndefined, rejectRawScalar } from './errors.mjs'
import { isPresent, isValidAbsent } from './boundary-types.mjs'

export const RESULT = Object.freeze({
  VALID: 'VALID',           // present, defined, typed value
  ABSENT: 'ABSENT',         // legitimately not present — a SUCCESS, not an error
  ERROR: 'ERROR',           // the port itself failed
})

export function resultValid(value) {
  rejectUndefined(value, 'INVALID_PORT_RESULT', 'VALID result wraps undefined')
  rejectRawScalar(value, 'INVALID_PORT_RESULT', 'VALID result must carry a typed value, not a raw string/number')
  return Object.freeze({ kind: RESULT.VALID, value })
}

export function resultAbsent(reason) {
  const r = rejectUndefined(reason, 'INVALID_PORT_RESULT', 'ABSENT result needs a reason')
  requireCondition(typeof r === 'string' && r.length > 0, 'INVALID_PORT_RESULT', 'ABSENT reason must be a non-empty string')
  return Object.freeze({ kind: RESULT.ABSENT, value: null, reason: r })
}

export function resultError(code, message) {
  requireCondition(typeof code === 'string' && code.length > 0, 'INVALID_PORT_RESULT', 'ERROR result needs a code')
  return Object.freeze({ kind: RESULT.ERROR, value: null, code, message: message ?? code })
}

export function isValid(r) {
  return r !== null && typeof r === 'object' && r.kind === RESULT.VALID
}

export function isAbsent(r) {
  return r !== null && typeof r === 'object' && r.kind === RESULT.ABSENT
}

export function isError(r) {
  return r !== null && typeof r === 'object' && r.kind === RESULT.ERROR
}

/**
 * Total inspector. Forces the caller to handle all three arms; a result whose
 * kind is not one of the three (e.g. an `undefined` that leaked from an
 * unmatched Array.find) is a fail-closed error, never a silent fall-through.
 */
export function matchResult(r, { onValid, onAbsent, onError }) {
  requireCondition(typeof onValid === 'function' && typeof onAbsent === 'function' && typeof onError === 'function',
    'INVALID_MATCH', 'matchResult requires onValid, onAbsent and onError handlers')
  if (isValid(r)) return onValid(r.value)
  if (isAbsent(r)) return onAbsent(r.reason)
  if (isError(r)) return onError(r.code, r.message)
  fail('UNTAGGED_PORT_RESULT', 'port result is not a discriminated VALID | ABSENT | ERROR')
}

/**
 * Convert a Presence (from boundary-types) into a discriminated port result.
 * This is the single adapter between the two layers — a VALID_ABSENT presence
 * becomes an ABSENT result (a success), a NOT_COMPUTED presence is an ERROR
 * (the port was asked for a value it has not produced), never a mismatch.
 */
export function presenceToResult(p) {
  if (isPresent(p)) return resultValid(p.value)
  if (isValidAbsent(p)) return resultAbsent(p.reason)
  return resultError('NOT_COMPUTED', 'presence is not yet computed')
}

/**
 * Compare a verified value against a cached value WITHOUT collapsing ABSENT and
 * WRONG-VALUE into one MISMATCH. Fixes `verified?.value === cached.value`.
 * `eq` must be an explicit typed-equality predicate.
 */
export function reconcileVerifiedAgainstCached(verified, cached, eq) {
  requireCondition(typeof eq === 'function', 'INVALID_RECONCILE', 'eq must be a typed equality predicate')
  // Fail-closed FIRST: both arms MUST already be discriminated port results. An
  // untagged/undefined arm (e.g. an optional-chain leak or an unmatched find)
  // must NOT be silently reclassified as ABSENT-vs-PRESENT — that would conflate
  // an ERROR/leak with a legitimate presence disagreement. Reject it here.
  const tagged = (r) => isValid(r) || isAbsent(r) || isError(r)
  requireCondition(tagged(verified), 'UNTAGGED_PORT_RESULT', 'verified is not a discriminated VALID | ABSENT | ERROR result')
  requireCondition(tagged(cached), 'UNTAGGED_PORT_RESULT', 'cached is not a discriminated VALID | ABSENT | ERROR result')
  // Both absent is a legitimate agreement, not a failure.
  if (isAbsent(verified) && isAbsent(cached)) return resultValid({ agreement: 'BOTH_ABSENT' })
  if (isError(verified) || isError(cached)) return resultError('RECONCILE_PORT_ERROR', 'a port errored during reconciliation')
  // One absent, one present -> a genuine presence disagreement, distinct from wrong-value.
  if (isAbsent(verified) !== isAbsent(cached)) {
    return resultError('PRESENCE_DISAGREEMENT', 'verified and cached disagree on presence (ABSENT vs PRESENT)')
  }
  // Both present: now, and only now, compare values.
  if (isValid(verified) && isValid(cached)) {
    return eq(verified.value, cached.value)
      ? resultValid({ agreement: 'VALUE_MATCH' })
      : resultError('VALUE_MISMATCH', 'verified and cached values differ')
  }
  return resultError('UNTAGGED_PORT_RESULT', 'reconcile received an untagged result')
}
