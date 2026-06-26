import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const source = readFileSync(resolve(root, 'src/views/chat/ChatView.vue'), 'utf8')

assert.match(source, /primaryContextUsage/)
assert.match(source, /childAgentUsages/)
assert.match(source, /子专家上下文/)
assert.match(source, /context-child-agents/)
assert.match(source, /sectionPercent\(section\.tokens,\s*primaryContextUsage\.context_window\)/)
assert.match(source, /sectionPercent\(section\.tokens,\s*agent\.context_window\)/)
assert.match(source, /上下文/)
assert.doesNotMatch(source, /总上下文/)

const childSectionIndex = source.indexOf('context-child-agents')
const mainSectionIndex = source.indexOf('context-section-list')
assert.ok(childSectionIndex > mainSectionIndex)

console.log('context usage drawer verified')
