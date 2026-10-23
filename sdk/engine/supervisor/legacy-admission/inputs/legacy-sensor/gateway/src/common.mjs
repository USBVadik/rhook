export {need,fail,closed,hash,commit,canonical,parseWire,ordinary,exclusive,fsyncDir,safeCode} from '../vendor/build15/src/util.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {need,ordinary,parseWire,canonical,hash} from '../vendor/build15/src/util.mjs';
export const same=(a,b)=>canonical(a)===canonical(b);
export const json=(p,max=4000000)=>JSON.parse(ordinary(p,max).toString('utf8'));
export const strict=(p,max=128000)=>parseWire(ordinary(p,max).toString('utf8'),max);
export function within(root,relative){need(typeof relative==='string'&&relative.length<160&&relative.split('/').every(x=>/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(x)),'ALLOCATION_INVALID');const p=path.join(root,relative);need(p.startsWith(root+path.sep),'ALLOCATION_INVALID');let at=root;for(const part of relative.split('/')){at=path.join(at,part);if(fs.existsSync(at))need(!fs.lstatSync(at).isSymbolicLink(),'ALLOCATION_SYMLINK');}return p;}
export function fileHash(p,max=2300000000){
 const before=fs.lstatSync(p);need(before.isFile()&&!before.isSymbolicLink()&&before.size<=max,'EVIDENCE_FILE_INVALID');
 const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
 try{const h=createHash('sha256'),buf=Buffer.alloc(65536);let n,total=0;while((n=fs.readSync(fd,buf,0,buf.length,null))){total+=n;need(total<=max,'EVIDENCE_LIMIT');h.update(buf.subarray(0,n));}const after=fs.fstatSync(fd);need(after.ino===before.ino&&after.dev===before.dev&&after.size===before.size&&after.mtimeMs===before.mtimeMs&&total===before.size,'EVIDENCE_CHANGED');return {bytes:total,sha256:h.digest('hex')};}finally{fs.closeSync(fd);}
}
import {createHash} from 'node:crypto';
