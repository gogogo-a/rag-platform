import assert from 'node:assert/strict'
import { formatChatMessage } from '../src/utils/markdown.js'

const html = formatChatMessage(`### 北京推荐

1. **故宫**
   - 皇家建筑
   - 文化地标

| 项目 | 内容 |
| --- | --- |
| 日期 | 2026年3月19日 |
| 天气 | 晴 |
`)

assert.match(html, /<h3>北京推荐<\/h3>/)
assert.match(html, /<ol>/)
assert.match(html, /<strong>故宫<\/strong>/)
assert.match(html, /<ul>/)
assert.match(html, /<table>/)
assert.match(html, /<th>项目<\/th>/)
assert.match(html, /<td>晴<\/td>/)

const escaped = formatChatMessage('<script>alert(1)</script>')
assert.doesNotMatch(escaped, /<script>/)

console.log('markdown rendering verified')
