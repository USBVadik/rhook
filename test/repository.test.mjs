import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { readFile, readdir, stat } from 'node:fs/promises'
import { dirname, extname, join, relative, resolve } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { verifyBranchEvidenceTranscriptJson } from '../core/src/index.mjs'

const run = promisify(execFile)
const currentTestFile = fileURLToPath(import.meta.url)
const root = resolve(dirname(currentTestFile), '..')

async function walk(directory) {
  const files = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === '.git' || entry.name === '.kiro' || entry.name === '.rhook' || entry.name === 'node_modules') continue
    const path = join(directory, entry.name)
    if (entry.isDirectory()) files.push(...await walk(path))
    else files.push(path)
  }
  return files.sort()
}

test('standalone transcript and reviewer commands work without workspace dependencies', async () => {
  const transcript = await readFile(join(root, 'examples/minimal/transcript.json'), 'utf8')
  assert.equal(verifyBranchEvidenceTranscriptJson(transcript).valid, true)
  const inspect = await run(process.execPath, ['scripts/inspect-transcript.mjs'], { cwd: root })
  assert.match(inspect.stdout, /Envelope 1[\s\S]*SUCCESS -> REVERT/)
  const verify = JSON.parse((await run(process.execPath, ['scripts/verify-transcript.mjs'], { cwd: root })).stdout)
  assert.equal(verify.status, 'PASS')
  assert.equal(verify.replayPerformed, false)
  const tamper = JSON.parse((await run(process.execPath, ['scripts/tamper-transcript.mjs'], { cwd: root })).stdout)
  assert.equal(tamper.status, 'EXPECTED_REJECTION')
  assert.ok(tamper.findings.some((finding) => finding.code === 'INVALID_SEMANTIC_ENDPOINT'))
})

test('all local Markdown links resolve inside the standalone repository', async () => {
  const markdown = (await walk(root)).filter((path) => extname(path) === '.md')
  const failures = []
  for (const path of markdown) {
    const text = await readFile(path, 'utf8')
    for (const match of text.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
      const target = match[1]
      if (target.startsWith('#') || /^[a-z]+:\/\//i.test(target)) continue
      const resolved = resolve(dirname(path), target.split('#')[0])
      try { await stat(resolved) } catch { failures.push(`${relative(root, path)} -> ${target}`) }
    }
  }
  assert.deepEqual(failures, [])
})

test('repository contains no local paths, credentials, agent residue, or environment files', async () => {
  const files = await walk(root)
  const textFiles = files.filter((path) => path !== currentTestFile && !path.endsWith('package-lock.json'))
  const combined = (await Promise.all(textFiles.map((path) => readFile(path, 'utf8')))).join('\n')
  assert.doesNotMatch(combined, /\/Users\/|\/home\/|KIROCREW|Kiro Crew|agent prompt|workflow transcript/i)
  assert.doesNotMatch(combined, /AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/)
  assert.equal(files.some((path) => /(^|\/)\.env(?:\.|$)/.test(relative(root, path))), false)
})

test('repository tree is small and excludes research/archive clutter', async () => {
  const files = await walk(root)
  const forbidden = files.filter((path) => {
    const repositoryPath = relative(root, path)
    if (repositoryPath === '.github/workflows/ci.yml') return false
    return /\.(?:patch|log|tgz|svg)$/i.test(path) || /(?:workflow|authorization|qualification|closure|checkpoint)/i.test(repositoryPath)
  })
  assert.deepEqual(forbidden, [])
  const oversized = []
  for (const path of files) if ((await stat(path)).size > 100_000) oversized.push(relative(root, path))
  assert.deepEqual(oversized, [])
  assert.equal(files.filter((path) => path.endsWith('.json') && !path.endsWith('package.json') && !path.endsWith('package-lock.json')).length, 2)
})

test('README explains the primitive in its first screen without inflated claims', async () => {
  const readme = await readFile(join(root, 'README.md'), 'utf8')
  const firstScreen = readme.slice(0, 900)
  assert.match(firstScreen, /RHOOK is an explainable deterministic counterfactual execution substrate for onchain state machines\./)
  assert.match(firstScreen, /ACTUAL[\s\S]*COUNTERFACTUAL/)
  assert.match(firstScreen, /npm run quickstart/)
  assert.doesNotMatch(readme, /revolutionary|world[- ]first|production[- ]ready|guaranteed|game[- ]changing/i)
  assert.match(readme, /has not been scientifically rerun on Alchemix/i)
})

test('public host requires explicit execution injection and has no private runner import', async () => {
  const host = await readFile(join(root, 'host/src/instrumented-block.mjs'), 'utf8')
  assert.match(host, /typeof runBlock === 'function'/)
  assert.doesNotMatch(host, /alchemix|\/Users\/|run-block-forced-historical-envelope/)
  const pkg = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'))
  assert.deepEqual(pkg.dependencies, undefined)
  assert.equal(pkg.scripts.quickstart, 'npm run demo:generate && npm run demo:inspect && npm run demo:verify && npm run demo:tamper')
})

test('adapted public source hashes match the reproducibility map', async () => {
  const provenance = JSON.parse(await readFile(join(root, 'docs/reproducibility/source-hashes.json'), 'utf8'))
  assert.ok(provenance.canonicalSourceSha256ByPublicPath)
  assert.ok(provenance.publicSourceSha256)
  for (const [path, expected] of Object.entries(provenance.publicSourceSha256)) {
    const actual = createHash('sha256').update(await readFile(join(root, path))).digest('hex')
    assert.equal(actual, expected, path)
  }
})

test('git-publishable files exclude local paths and ignored agent metadata', async () => {
  const { stdout } = await run('git', ['ls-files', '--cached', '--others', '--exclude-standard'], { cwd: root })
  const paths = stdout.trim().split('\n').filter(Boolean)
  assert.ok(paths.length > 0)
  assert.equal(paths.some((path) => path === '.kiro' || path.startsWith('.kiro/')), false)
  const text = (await Promise.all(paths.filter((path) => resolve(root, path) !== currentTestFile).map((path) => readFile(join(root, path), 'utf8')))).join('\n')
  assert.doesNotMatch(text, /\/Users\/|\/home\/|KIROCREW|Kiro Crew|agent prompt|workflow transcript/i)
})
