import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync, readdirSync, statSync, cpSync } from 'node:fs'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { example, loadArtifacts, writeInputs, checkFrozenArtifacts } from './artifacts.mjs'
import { sha, write } from './common.mjs'

const output = process.env.RHOOK_OUTPUT ?? '/out'
const work = join(output, 'work')
mkdirSync(output, { recursive: true })
// A fresh output prevents stale generated evidence from satisfying a failed run.
assert(!readdirSync(output).includes('work'), 'Output already has work/. Use a fresh output directory.')
mkdirSync(work)
cpSync(join(example, 'build-info'), join(output, 'build-info'), { recursive: true })
const started = performance.now()
const artifacts = loadArtifacts()
checkFrozenArtifacts(artifacts)
writeInputs(work, artifacts.files)
process.env.RHOOK_NATIVE_RUNNER = join(example, 'native-runner')
process.chdir(work)
function run(script, args = []) {
  const result = spawnSync(process.execPath, [join(example, 'scripts', script), ...args], { stdio: 'inherit', timeout: 900000 })
  assert.equal(result.status, 0, `${script} failed: ${result.error?.message ?? result.signal ?? result.status}`)
}
try {
  console.log('RHOOK REAL-CHAIN COUNTERFACTUAL — replaying frozen inputs offline')
  console.log('Analytical Message.Data intervention, not a re-signed transaction. Historical envelope identity and Message.Tx are retained for alignment and Nitro poster-cost accounting. Replacement calldata is separately committed; the historical sender did not sign or broadcast it under this hash.')
  run('run-native.mjs', ['ACTUAL', '50', 'original', 'results/actual/ORIGINAL'])
  run('run-native.mjs', ['ACTUAL', '50', 'control', 'results/actual/CONTROL'])
  run('run-host.mjs', ['off', '50'])
  run('run-host.mjs', ['on', '50'])
  // Require preserved ACTUAL before beginning the counterfactual.
  run('compare.mjs', ['actual'])
  run('run-native.mjs', ['COUNTERFACTUAL', '50', 'control', 'results/F4/CONTROL'])
  run('run-counterfactual-evidence.mjs', ['50', 'off'])
  run('run-counterfactual-evidence.mjs', ['50', 'on'])
  run('compare.mjs')
  const elapsedSeconds = (performance.now() - started) / 1000
  write(join(output, 'replay-metrics.json'), { elapsedSeconds, platform: process.platform, architecture: process.arch, node: process.version, nativeRunnerSha256: sha(readFileSync(process.env.RHOOK_NATIVE_RUNNER)), offlinePolicy: 'docker --network none' })
  const files = []
  function walk(dir) { for (const name of readdirSync(dir).sort()) { const p = join(dir, name); if (statSync(p).isDirectory()) walk(p); else files.push(p) } }
  walk(output)
  const records = files.map(p => `${sha(readFileSync(p))}  ${p.slice(output.length + 1)}`)
  writeFileSync(join(output, 'SHA256SUMS'), records.join('\n') + '\n')
  console.log(`Generated output: ${output}; all ${files.length} output hashes: SHA256SUMS`)
} catch (error) {
  console.error('RESULT: FAIL\n' + error.stack)
  process.exitCode = 1
}
