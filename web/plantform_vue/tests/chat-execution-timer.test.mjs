import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const viewSource = readFileSync(join(rootDir, 'src/views/chat/ChatView.vue'), 'utf8')
const messageSource = readFileSync(join(rootDir, 'src/components/chat/ChatMessage.vue'), 'utf8')

assert.match(viewSource, /startExecutionTimer/)
assert.match(viewSource, /finishExecutionTimer\(data\.elapsed_seconds\)/)
assert.match(viewSource, /executionElapsedSeconds/)
assert.match(viewSource, /elapsed_seconds/)
assert.doesNotMatch(viewSource, /executionTimerLabel/)
assert.doesNotMatch(viewSource, /console\./)

assert.match(messageSource, /message-execution-time/)
assert.match(messageSource, /executionLabel/)
assert.match(messageSource, /已执行/)
assert.match(messageSource, /执行/)
assert.match(messageSource, /handleCopy/)
assert.match(messageSource, /CopyDocument/)
assert.doesNotMatch(messageSource, /console\./)

console.log('chat execution timer verified')
