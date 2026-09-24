import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import solc from '../tooling/node_modules/solc/index.js'
const dir='source/nitro/contracts-local/src/precompiles'
const sources={}
for(const name of (await readdir(dir)).filter(n=>n.endsWith('.sol')).sort()) sources[name]={content:await readFile(`${dir}/${name}`,'utf8')}
const input={language:'Solidity',sources,settings:{outputSelection:{'*':{'*':['abi']}}}}
const output=JSON.parse(solc.compile(JSON.stringify(input)))
await mkdir('build-info',{recursive:true})
await writeFile('build-info/solc-input.json',JSON.stringify(input,null,2)+'\n')
await mkdir('build-info',{recursive:true})
await writeFile('build-info/solc-output.json',JSON.stringify(output,null,2)+'\n')
assert.equal((output.errors??[]).filter(e=>e.severity==='error').length,0)
for(const [source,contracts] of Object.entries(output.contracts)) {
  const out=`source/nitro/contracts-local/out/precompiles/${source}`
  await mkdir(out,{recursive:true})
  for(const [name,{abi}] of Object.entries(contracts)) await writeFile(`${out}/${name}.json`,JSON.stringify({abi,bytecode:{object:''}},null,2)+'\n')
}
console.log(JSON.stringify({solc:solc.version(),sources:Object.keys(sources).length,output:'ABI only from pinned precompile interface sources; no EVM code replacement'}))
