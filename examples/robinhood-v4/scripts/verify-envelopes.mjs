import { readdirSync,readFileSync } from 'node:fs'
import { verifyEnvelopeEvidenceJson,isEnvelopeEvidenceVerified } from '../../../core/src/index.mjs'
const directory=process.argv[2],results=[]
for(const file of readdirSync(directory).filter(f=>f.endsWith('.json')).sort()){
 const result=verifyEnvelopeEvidenceJson(readFileSync(`${directory}/${file}`,'utf8'))
 results.push({file,valid:isEnvelopeEvidenceVerified(result),findings:result.findings,receipt:result.receipt})
}
console.log(JSON.stringify({valid:results.length>0&&results.every(r=>r.valid),count:results.length,results}))
if(!results.length||results.some(r=>!r.valid))process.exitCode=1
