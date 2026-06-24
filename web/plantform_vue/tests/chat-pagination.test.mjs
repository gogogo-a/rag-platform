import assert from 'node:assert/strict'
import {
  getInitialMessagePage,
  getOlderMessagePage,
  normalizeChatMessages
} from '../src/store/chatPagination.js'

const makeMessage = (index, sendType = index % 2) => ({
  uuid: `msg-${index}`,
  content: `message-${index}`,
  send_type: sendType,
  send_at: `2026-06-24T10:${String(index).padStart(2, '0')}:00`
})

assert.equal(getInitialMessagePage(0, 10), 1)
assert.equal(getInitialMessagePage(1, 10), 1)
assert.equal(getInitialMessagePage(10, 10), 1)
assert.equal(getInitialMessagePage(11, 10), 2)
assert.equal(getInitialMessagePage(21, 10), 3)

assert.equal(getOlderMessagePage(3), 2)
assert.equal(getOlderMessagePage(2), 1)
assert.equal(getOlderMessagePage(1), null)

const pageMessages = [
  makeMessage(11, 0),
  makeMessage(12, 1),
  makeMessage(13, 2),
  makeMessage(14, 1)
]
const normalized = normalizeChatMessages(pageMessages)

assert.deepEqual(
  normalized.map((message) => message.uuid),
  ['msg-11', 'msg-12', 'msg-14']
)
assert.equal(normalized[0].role, 'user')
assert.equal(normalized[1].role, 'assistant')
assert.equal(normalized[0].create_at, pageMessages[0].send_at)

console.log('chat pagination tests passed')
