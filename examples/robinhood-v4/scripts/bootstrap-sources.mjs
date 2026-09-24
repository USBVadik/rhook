import { readFileSync, mkdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
const pins = JSON.parse(readFileSync('dependencies.json'))
mkdirSync('downloads', { recursive: true })
for (const source of pins.sources) {
  const archive = `downloads/${source.name}.tar.gz`
  execFileSync('curl', ['--fail', '--location', '--retry', '3', '--output', archive, source.url], { stdio: 'inherit' })
  const content = readFileSync(archive)
  if (content.length !== source.bytes || createHash('sha256').update(content).digest('hex') !== source.sha256) throw Error(`Source integrity failed: ${source.name}`)
  mkdirSync(source.directory, { recursive: true })
  execFileSync('tar', ['-xzf', archive, '--strip-components=1', '-C', source.directory], { stdio: 'inherit' })
}
