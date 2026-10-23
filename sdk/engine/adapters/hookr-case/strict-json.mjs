function syntax(message, index) {
  throw Object.assign(new Error(`STRICT_JSON_SYNTAX: ${message} at byte ${index}`), { code: 'STRICT_JSON_SYNTAX', index })
}

export function parseStrictEvidenceJson(text) {
  if (typeof text !== 'string') throw Object.assign(new Error('STRICT_JSON_INPUT: text must be a string'), { code: 'STRICT_JSON_INPUT' })
  let index = 0
  const whitespace = () => { while (index < text.length && /[\t\n\r ]/.test(text[index])) index += 1 }
  const consume = (character) => {
    whitespace()
    if (text[index] !== character) syntax(`expected ${JSON.stringify(character)}`, index)
    index += 1
  }
  const string = () => {
    whitespace()
    if (text[index] !== '"') syntax('expected string', index)
    const start = index
    index += 1
    while (index < text.length) {
      const character = text[index]
      if (character === '"') {
        index += 1
        try { return JSON.parse(text.slice(start, index)) } catch { syntax('invalid string escape', start) }
      }
      if (character.charCodeAt(0) < 0x20) syntax('unescaped control character', index)
      if (character === '\\') {
        index += 1
        if (index >= text.length) syntax('unterminated escape', index)
        if (text[index] === 'u') {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(index + 1, index + 5))) syntax('invalid unicode escape', index)
          index += 4
        } else if (!'"\\/bfnrt'.includes(text[index])) syntax('invalid escape', index)
      }
      index += 1
    }
    syntax('unterminated string', start)
  }
  const number = () => {
    whitespace()
    const remaining = text.slice(index)
    const match = remaining.match(/^-?(?:0|[1-9][0-9]*)/)
    if (!match) syntax('invalid integer', index)
    const token = match[0]
    if (token === '-0') syntax('negative zero is noncanonical', index)
    index += token.length
    if (/[.eE0-9]/.test(text[index] ?? '')) syntax('noncanonical or non-integer number', index)
    const value = Number(token)
    if (!Number.isSafeInteger(value)) syntax('integer exceeds safe range', index)
    return value
  }
  const value = () => {
    whitespace()
    const character = text[index]
    if (character === '"') return string()
    if (character === '{') return object()
    if (character === '[') return array()
    if (text.startsWith('true', index)) { index += 4; return true }
    if (text.startsWith('false', index)) { index += 5; return false }
    if (text.startsWith('null', index)) { index += 4; return null }
    if (character === '-' || /[0-9]/.test(character ?? '')) return number()
    syntax('unexpected token', index)
  }
  const array = () => {
    consume('[')
    const result = []
    whitespace()
    if (text[index] === ']') { index += 1; return result }
    while (true) {
      result.push(value())
      whitespace()
      if (text[index] === ']') { index += 1; return result }
      consume(',')
    }
  }
  const object = () => {
    consume('{')
    const result = {}
    const keys = new Set()
    whitespace()
    if (text[index] === '}') { index += 1; return result }
    while (true) {
      const key = string()
      if (keys.has(key)) syntax(`duplicate object key ${JSON.stringify(key)}`, index)
      keys.add(key)
      consume(':')
      Object.defineProperty(result, key, { value: value(), enumerable: true, writable: true, configurable: true })
      whitespace()
      if (text[index] === '}') { index += 1; return result }
      consume(',')
    }
  }

  const result = value()
  whitespace()
  if (index !== text.length) syntax('trailing content', index)
  return result
}
