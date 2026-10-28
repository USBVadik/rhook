import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {parseStrictEvidenceJson} from '../../engine/adapters/hookr-case/strict-json.mjs';
import {parseRecordedJson} from '../../engine/case_sdk/json.mjs';
export function readBoundedJson(file,maximum=32<<20,fractions=false){
 file=path.resolve(file);
 for(let p=file;;p=path.dirname(p)){
  assert(!fs.lstatSync(p).isSymbolicLink(),'SYMLINK_INPUT');if(p===path.dirname(p))break;
 }
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
 let raw;
 try{
  const st=fs.fstatSync(fd);assert(st.isFile()&&st.size<=maximum,'INPUT_TYPE_OR_SIZE');
  const buffer=Buffer.alloc(maximum+1);let used=0,n;
  while(used<buffer.length&&(n=fs.readSync(fd,buffer,used,buffer.length-used,null))>0)used+=n;
  assert(used<=maximum,'INPUT_SIZE');raw=buffer.subarray(0,used);
 }finally{fs.closeSync(fd)}
 const text=new TextDecoder('utf-8',{fatal:true}).decode(raw);
 let depth=0,quoted=false,escape=false;
 for(const c of text){if(quoted){if(escape)escape=false;else if(c==='\\')escape=true;else if(c==='"')quoted=false}
 else if(c==='"')quoted=true;else if(c==='['||c==='{')assert(++depth<=64,'JSON_DEPTH');else if(c===']'||c==='}')depth--}
 return {raw,value:(fractions?parseRecordedJson:parseStrictEvidenceJson)(text)};
}
export function readRawJournal(file){
 // JSONL requires the same bounded descriptor read, using one string JSON value.
 file=path.resolve(file);for(let p=file;;p=path.dirname(p)){assert(!fs.lstatSync(p).isSymbolicLink());if(p===path.dirname(p))break}
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);let raw;
 try{const s=fs.fstatSync(fd);assert(s.isFile()&&s.size<=1048576);raw=Buffer.alloc(s.size);let n=0,k;while(n<raw.length&&(k=fs.readSync(fd,raw,n,raw.length-n,null))>0)n+=k;assert.equal(n,raw.length)}finally{fs.closeSync(fd)}
 assert(raw.length&&raw.at(-1)===10);const rows=[];let previous='';
 for(const line of raw.subarray(0,-1).toString('utf8').split('\n')){
  const row=parseRecordedJson(line);assert.equal(row.sequence,rows.length);assert.equal(row.previousSha256,previous);
  previous=createHash('sha256').update(line).digest('hex');rows.push(row);
 }
 return rows;
}
