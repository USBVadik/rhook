import assert from 'node:assert/strict';

// The account must already have passed MPT authentication at the selected root.
export function verifyCodeBinding(account, codes, expected, hashBytes) {
  assert.equal(account.status, 'PRESENT', 'CONTRACT_ACCOUNT_REQUIRED');
  assert.equal(account.codeHash, expected, 'AUTHENTICATED_ACCOUNT_CODE_HASH');
  assert(codes.has(expected), 'CODE_PREIMAGE_REQUIRED');
  const bytes = codes.get(expected);
  assert.equal(hashBytes(bytes), expected, 'CODE_PREIMAGE_HASH');
  return bytes;
}
