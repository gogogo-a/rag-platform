import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')

const inputSource = readFileSync(resolve(root, 'src/components/chat/MessageInput.vue'), 'utf8')
const chatViewSource = readFileSync(resolve(root, 'src/views/chat/ChatView.vue'), 'utf8')
const apiSource = readFileSync(resolve(root, 'src/api/message.js'), 'utf8')

assert.match(inputSource, /defineEmits\(\['send',\s*'pause'\]\)/)
assert.match(inputSource, /defineProps/)
assert.match(inputSource, /isStreaming/)
assert.match(inputSource, /isPreparing/)
assert.match(inputSource, /computed\(\(\)\s*=>\s*isPreparing\.value\s*\|\|\s*props\.isStreaming\)/)
assert.match(inputSource, /handlePause/)
assert.match(inputSource, /{{ isSending \? '暂停' : '发送' }}/)
assert.doesNotMatch(inputSource, /发送中/)
assert.doesNotMatch(inputSource, /console\./)

assert.match(chatViewSource, /@pause="handlePauseStreaming"/)
assert.match(chatViewSource, /:is-streaming="isStreaming"/)
assert.match(chatViewSource, /streamPausedByUser/)
assert.match(chatViewSource, /if \(streamPausedByUser\.value\) return/)
assert.match(chatViewSource, /if \(streamPausedByUser\.value\) break/)
assert.match(chatViewSource, /streamAbortController/)
assert.match(chatViewSource, /new AbortController\(\)/)
assert.match(chatViewSource, /streamAbortController\.value\.abort\(\)/)
assert.match(chatViewSource, /signal:\s*streamAbortController\.value\.signal/)
assert.match(chatViewSource, /error\.name\s*===\s*'AbortError'/)
assert.doesNotMatch(chatViewSource, /console\./)

assert.match(apiSource, /options\.signal/)
assert.match(apiSource, /signal:\s*options\.signal/)
assert.doesNotMatch(apiSource, /console\./)
