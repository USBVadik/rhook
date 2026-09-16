import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const workflowUrl = new URL('../.github/workflows/ci.yml', import.meta.url)
const packageUrl = new URL('../package.json', import.meta.url)

test('CI runs the complete reviewer gate on Node 22', async () => {
  const workflow = await readFile(workflowUrl, 'utf8')
  const pkg = JSON.parse(await readFile(packageUrl, 'utf8'))

  assert.match(workflow, /node-version: 22/)
  assert.match(workflow, /actions\/checkout@[0-9a-f]{40} # v4\.2\.2/)
  assert.match(workflow, /actions\/setup-node@[0-9a-f]{40} # v4\.4\.0/)
  assert.doesNotMatch(workflow, /uses: actions\/(?:checkout|setup-node)@v[0-9]/)
  for (const command of ['npm ci', 'npm run check', 'npm test', 'npm run quickstart']) {
    assert.match(workflow, new RegExp(`- run: ${command.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`))
  }
  assert.equal(pkg.scripts.quickstart, 'npm run demo:generate && npm run demo:inspect && npm run demo:verify && npm run demo:tamper')
})
