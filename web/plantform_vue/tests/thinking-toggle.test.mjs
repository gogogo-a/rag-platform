import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')

const storeSource = readFileSync(resolve(root, 'src/store/chat.js'), 'utf8')
const inputSource = readFileSync(resolve(root, 'src/components/chat/MessageInput.vue'), 'utf8')

assert.match(storeSource, /showThinking:\s*true/)
assert.match(inputSource, /\{\{\s*showThinking\s*\?\s*'隐藏过程'\s*:\s*'显示过程'\s*\}\}/)

console.log('thinking toggle defaults verified')
