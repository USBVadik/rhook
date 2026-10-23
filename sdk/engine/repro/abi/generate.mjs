import {readFile, readdir, mkdir, writeFile} from 'node:fs/promises'
import {resolve, join} from 'node:path'
import assert from 'node:assert/strict'
import solc from 'solc'

assert.ok(solc.version().startsWith('0.8.30+commit.73712a01.'), 'Wrong Solidity compiler')
const nitro = resolve(process.argv[2])
const dir = join(nitro, 'contracts-local/src/precompiles')
const sources = {}
for (const name of (await readdir(dir)).filter(n => n.endsWith('.sol')).sort()) {
  sources[name] = {content: await readFile(join(dir, name), 'utf8')}
}
const input = {language: 'Solidity', sources, settings: {outputSelection: {'*': {'*': ['abi']}}}}
const output = JSON.parse(solc.compile(JSON.stringify(input)))
assert.equal((output.errors ?? []).filter(e => e.severity === 'error').length, 0)
await writeFile('solc-input.json', JSON.stringify(input, null, 2) + '\n')
await writeFile('solc-output.json', JSON.stringify(output, null, 2) + '\n')
for (const [source, contracts] of Object.entries(output.contracts)) {
  const out = join(nitro, 'contracts-local/out/precompiles', source)
  await mkdir(out, {recursive: true})
  for (const [name, {abi}] of Object.entries(contracts)) {
    await writeFile(join(out, `${name}.json`), JSON.stringify({abi, bytecode: {object: ''}}, null, 2) + '\n')
  }
}
console.log(JSON.stringify({solc: solc.version(), sourceCount: Object.keys(sources).length, buildOnly: true}))
