import {createHash} from 'node:crypto';
import {parseStrictEvidenceJson} from '../vendor/strict-json.mjs';

export const MAX_BYTES = 4_000_000;
export const fail = code => {throw Object.assign(new Error(code), {code})};
export const need = (condition, code) => {if (!condition) fail(code)};
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
export const isDigest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const freeze = value => {
  if (value && typeof value === 'object') {for (const v of Object.values(value)) freeze(v);Object.freeze(value)}
  return value;
};

// Bounded ASCII codec from the published Branch Protocol 0.2 encoding.
// Call only with parsed JSON, never arbitrary application objects.
export function canonical(value) {
  let count = 0, bytes = 0;
  const charge = n => need((bytes += n) <= MAX_BYTES, 'JSON_LIMIT');
  function encode(v, depth) {
    need(++count <= 100_000 && depth <= 64, 'JSON_LIMIT');
    if (v === null || typeof v === 'boolean') {const s=JSON.stringify(v);charge(s.length);return s}
    if (typeof v === 'number') {need(Number.isSafeInteger(v) && !Object.is(v,-0), 'NUMBER_INVALID');const s=String(v);charge(s.length);return s}
    if (typeof v === 'string') {need(!/[^\x00-\x7f]/.test(v), 'NON_ASCII');const s=JSON.stringify(v);charge(s.length);return s}
    need(v && typeof v === 'object', 'JSON_INVALID');
    const keys=Object.keys(v);charge(2+Math.max(0,keys.length-1));
    if (Array.isArray(v)) return '['+v.map(x=>encode(x,depth+1)).join(',')+']';
    return '{'+keys.sort().map(k=>{
      need(!/[^\x00-\x7f]/.test(k), 'NON_ASCII');const key=JSON.stringify(k);charge(key.length+1);
      return key+':'+encode(v[k],depth+1);
    }).join(',')+'}';
  }
  return encode(value,0);
}
export const commit = (domain, body) => sha256(canonical({domain,body}));

export function parseBytes(input) {
  need(typeof input === 'string' || Buffer.isBuffer(input) || input instanceof Uint8Array, 'INPUT_TYPE');
  need((typeof input === 'string' ? Buffer.byteLength(input) : input.byteLength) <= MAX_BYTES, 'INPUT_LIMIT');
  const bytes=Buffer.from(input);
  const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  // Bound nesting before the vendored recursive strict parser allocates objects.
  let depth=0, quoted=false, escaped=false;
  for (const c of text) {
    if (quoted) {if (escaped) escaped=false;else if (c==='\\') escaped=true;else if (c==='"') quoted=false}
    else if (c==='"') quoted=true;
    else if (c==='{' || c==='[') {need(++depth<=64, 'JSON_LIMIT')}
    else if (c==='}' || c===']') depth--;
  }
  const value=parseStrictEvidenceJson(text);canonical(value);
  return {bytes,value};
}

export function closed(value, fields, code='FIELDS_INVALID') {
  need(value && typeof value==='object' && !Array.isArray(value) &&
    [Object.prototype,null].includes(Object.getPrototypeOf(value)),code);
  const descriptors=Object.getOwnPropertyDescriptors(value),keys=Reflect.ownKeys(descriptors);
  need(keys.length===fields.length && keys.every(k=>fields.includes(k) && descriptors[k].enumerable &&
    Object.hasOwn(descriptors[k],'value')),code);
  return value;
}
