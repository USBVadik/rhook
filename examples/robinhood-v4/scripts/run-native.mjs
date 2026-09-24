import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
import {mkdirSync} from 'node:fs'
import {write} from './common.mjs'
const [branch,count,mode,dir,witness='inputs/witness.json']=process.argv.slice(2)
mkdirSync(dir,{recursive:true})
const run=spawnSync(process.env.RHOOK_NATIVE_RUNNER,['-branch',branch,'-count',count,'-bridge',mode,'-witness',witness],{encoding:'utf8',timeout:600000,maxBuffer:128*1024*1024})
const outputs=run.stdout.trim().split('\n').filter(Boolean).map(JSON.parse)
write(`${dir}/process.json`,{exitCode:run.status,stderr:run.stderr,error:run.error?.message??null})
if(run.status!==0){write(`${dir}/failure.json`,outputs);console.log(JSON.stringify({branch,count,status:'EXECUTION_STOP',failure:outputs.at(-1)?.failure}));process.exit(2)}
const summary=outputs.pop();assert.equal(summary.status,'SESSION_EXECUTED_UNCOMPARED')
write(`${dir}/native.json`,{blocks:outputs,summary})
console.log(JSON.stringify({branch,count,mode,status:'EXECUTED_UNCOMPARED',root:summary.finalRoot}))
