import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')

const storeSource = readFileSync(resolve(root, 'src/store/chat.js'), 'utf8')
const inputSource = readFileSync(resolve(root, 'src/components/chat/MessageInput.vue'), 'utf8')
const chatViewSource = readFileSync(resolve(root, 'src/views/chat/ChatView.vue'), 'utf8')

assert.match(storeSource, /agentMode:\s*'single'/)
assert.match(storeSource, /setAgentMode\(mode\)/)
assert.match(inputSource, /el-segmented/)
assert.match(inputSource, /agentModeOptions/)
assert.match(inputSource, /agentMode:\s*chatStore\.agentMode/)
assert.match(chatViewSource, /agentMode\s*=\s*chatStore\.agentMode/)
assert.match(chatViewSource, /formData\.append\('agent_mode',\s*agentMode\)/)

console.log('agent mode toggle wiring verified')
