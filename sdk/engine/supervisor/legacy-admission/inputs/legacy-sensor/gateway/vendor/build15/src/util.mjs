import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
export {parseWire,canonical} from '../vendor/client/src/json.mjs';
import {canonical} from '../vendor/client/src/json.mjs';
export const fail=code=>{throw Object.assign(new Error(code),{code});};
export const need=(v,c)=>{if(!v)fail(c);};
export const closed=(v,keys)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
export const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
export const commit=(domain,body)=>hash(canonical({domain,body}));
export const fsyncDir=p=>{const fd=fs.openSync(p,'r');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}};
export function ordinary(p,max=16*1024*1024){const s=fs.lstatSync(p);need(s.isFile()&&!s.isSymbolicLink()&&s.size<=max,'HOST_FILE_INVALID');return fs.readFileSync(p);}
export function exclusive(p,data){const fd=fs.openSync(p,fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_WRONLY|fs.constants.O_NOFOLLOW,0o600);try{fs.writeFileSync(fd,data);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fsyncDir(path.dirname(p));}
export const safeCode=e=>typeof e?.code==='string'&&/^[A-Z][A-Z0-9_]{0,95}$/.test(e.code)?e.code:'LOCAL_GATEWAY_FAILURE';
