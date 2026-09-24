import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync, readFileSync, appendFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { loadArtifacts, checkFrozenArtifacts } from './artifacts.mjs'

const root = fileURLToPath(new URL('../../../', import.meta.url))
checkFrozenArtifacts(loadArtifacts())
const stamp = new Date().toISOString().replaceAll(':', '-').replaceAll('.', '-')
const output = join(root, '.rhook', `robinhood-${stamp}`)
mkdirSync(output, { recursive: true })
const image = 'rhook-robinhood-v4:local'
function docker(args) {
  const r = spawnSync('docker', args, { cwd: root, stdio: 'inherit' })
  assert.equal(r.status, 0, `Docker failed: ${r.error?.message ?? r.signal ?? r.status}`)
}
try {
  const start = performance.now()
  docker(['buildx', 'build', '--load', '--platform', 'linux/arm64', '--progress=plain', '-f', 'examples/robinhood-v4/Dockerfile', '-t', image, '.'])
  const buildSeconds = (performance.now() - start) / 1000
  const runStart = performance.now()
  docker(['run', '--platform', 'linux/arm64', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,nosuid,nodev', '--mount', `type=bind,source=${output},target=/out`, image])
  writeFileSync(join(output, 'workflow-metrics.json'), JSON.stringify({ buildSeconds, runSeconds: (performance.now() - runStart) / 1000, image, source: 'clean-checkout build context; no external workspace mounts', executionNetwork: 'none' }, null, 2) + '\n')
  const metricsHash = createHash('sha256').update(readFileSync(join(output, 'workflow-metrics.json'))).digest('hex')
  appendFileSync(join(output, 'SHA256SUMS'), `${metricsHash}  workflow-metrics.json\n`)
  console.log(`Results: ${output}`)
} catch (error) {
  console.error('RESULT: FAIL\n' + error.message)
  process.exitCode = 1
}
