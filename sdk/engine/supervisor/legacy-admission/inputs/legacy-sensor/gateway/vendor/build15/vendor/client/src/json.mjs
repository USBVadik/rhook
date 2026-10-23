// Bounded strict ASCII JSON for the private preparation wire; no duplicate keys.
export function parseWire(text,maxBytes=65536){
 const invalid=()=>{throw Error('WIRE_INVALID')}
 if(typeof text!=='string'||Buffer.byteLength(text)>maxBytes)invalid()
 let at=0,count=0;const space=()=>{while(at<text.length&&/[\t\n\r ]/.test(text[at]))at++}
 function string(){
  if(text[at++]!=='"')invalid();const start=at-1
  while(at<text.length){const c=text[at++];if(c==='\\'){if(at>=text.length)invalid();at++}else if(c==='"'){let v;try{v=JSON.parse(text.slice(start,at))}catch{invalid()}if(/[^\x20-\x7e]/.test(v))invalid();return v}}invalid()
 }
 function value(depth){
  if(depth>32||++count>4000)invalid();space()
  if(text[at]==='"')return string()
  for(const [token,result]of [['null',null],['true',true],['false',false]])if(text.startsWith(token,at)){at+=token.length;return result}
  if(text[at]==='-'||/[0-9]/.test(text[at]??'')){const start=at;while(at<text.length&&/[-0-9.eE+]/.test(text[at]))at++;const s=text.slice(start,at),n=Number(s);if(!/^-?(0|[1-9][0-9]*)$/.test(s)||!Number.isSafeInteger(n)||Object.is(n,-0))invalid();return n}
  const open=text[at++];if(open!=='{'&&open!=='[')invalid();space();const array=open==='[',out=array?[]:{},keys=new Set(),close=array?']':'}'
  if(text[at]===close){at++;return out}
  while(at<text.length){
   if(array)out.push(value(depth+1))
   else{space();const key=string();if(keys.has(key)||['__proto__','prototype','constructor'].includes(key))invalid();keys.add(key);space();if(text[at++]!==':')invalid();out[key]=value(depth+1)}
   space();const end=text[at++];if(end===close)return out;if(end!==',')invalid()
  }invalid()
 }
 const out=value(0);space();if(at!==text.length)invalid();return out
}
export function canonical(v){if(v===null||typeof v!=='object')return JSON.stringify(v);return Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}'}
export function freeze(v){if(v&&typeof v==='object'){for(const child of Object.values(v))freeze(child);Object.freeze(v)}return v}
