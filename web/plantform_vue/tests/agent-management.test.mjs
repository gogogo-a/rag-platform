import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (path) => readFileSync(join(rootDir, path), 'utf8')

const apiSource = readSource('src/api/agent.js')
const indexSource = readSource('src/api/index.js')
const routerSource = readSource('src/router/index.js')
const layoutSource = readSource('src/views/admin/AdminLayout.vue')
const pageSource = readSource('src/views/admin/AgentManagement.vue')

assert.match(apiSource, /url:\s*'\/agents'/)
assert.match(apiSource, /url:\s*'\/agents\/options'/)
assert.match(apiSource, /url:\s*`\/agents\/\$\{agentUuid\}`/)
assert.match(apiSource, /url:\s*`\/agents\/\$\{agentUuid\}\/enable`/)
assert.match(indexSource, /export \* from '\.\/agent'/)

assert.match(routerSource, /path:\s*'agents'/)
assert.match(routerSource, /AgentManagement\.vue/)
assert.match(layoutSource, /index="\/admin\/agents"/)
assert.match(layoutSource, /Agent 管理/)

assert.match(pageSource, /getAgentList/)
assert.match(pageSource, /createAgent/)
assert.match(pageSource, /updateAgent/)
assert.match(pageSource, /setAgentEnabled/)
assert.match(pageSource, /handleEdit/)
assert.match(pageSource, /agent-edit-dialog/)
assert.match(pageSource, /agent-filter/)
assert.match(pageSource, /agent-action-button/)
assert.match(pageSource, /MCP 工具/)
assert.match(pageSource, /Prompt/)
assert.match(pageSource, /启用/)
assert.match(pageSource, /禁用/)
assert.doesNotMatch(pageSource, /console\./)

console.log('agent management wiring verified')
