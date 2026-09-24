import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
export const read = path => JSON.parse(readFileSync(path, 'utf8'))
export const write = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
export const sha = data => createHash('sha256').update(data).digest('hex')
export const bytes = value => Buffer.from(value.slice(2), 'hex')
export const hex = data => '0x' + Buffer.from(data).toString('hex')
export function ordered(value) {
  if (Array.isArray(value)) return value.map(ordered)
  if (value !== null && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, ordered(value[k])]))
  return value
}
export const objectDigest = value => sha(JSON.stringify(ordered(value)))
export const withoutLifecycle = ({ lifecycle, ...value }) => value
