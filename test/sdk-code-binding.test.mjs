import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import test from 'node:test';
import {verifyCodeBinding} from '../sdk/rhook_alpha/cases/adapters/code.mjs';

// Synthetic hash primitive: this tests binding, not Ethereum proof verification.
const hash=bytes=>'0x'+createHash('sha256').update(bytes).digest('hex');
const code='0x6000',expected=hash(code);
const account={status:'PRESENT',codeHash:expected};

test('code bytes must belong to the authenticated account',()=>{
 assert.equal(verifyCodeBinding(account,new Map([[expected,code]]),expected,hash),code);
 assert.throws(()=>verifyCodeBinding({...account,codeHash:hash('different')},new Map([[expected,code]]),expected,hash));
});
test('unbound code does not turn an absent account into a present contract',()=>{
 assert.throws(()=>verifyCodeBinding({...account,status:'ABSENT'},new Map([[expected,code]]),expected,hash));
});
test('matching metadata still requires the original code preimage',()=>{
 assert.throws(()=>verifyCodeBinding(account,new Map(),expected,hash));
 assert.throws(()=>verifyCodeBinding(account,new Map([[expected,'tampered']]),expected,hash));
});
