import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (path) => readFileSync(join(rootDir, path), 'utf8')

const apiSource = readSource('src/api/prompt.js')
const indexSource = readSource('src/api/index.js')
const routerSource = readSource('src/router/index.js')
const layoutSource = readSource('src/views/admin/AdminLayout.vue')
const pageSource = readSource('src/views/admin/PromptManagement.vue')

assert.match(apiSource, /url:\s*'\/prompts'/)
assert.match(apiSource, /url:\s*'\/prompts\/options'/)
assert.match(apiSource, /url:\s*`\/prompts\/\$\{promptUuid\}`/)
assert.match(apiSource, /url:\s*`\/prompts\/\$\{promptUuid\}\/activate`/)
assert.match(indexSource, /export \* from '\.\/prompt'/)

assert.match(routerSource, /path:\s*'prompts'/)
assert.match(routerSource, /PromptManagement\.vue/)
assert.match(layoutSource, /index="\/admin\/prompts"/)
assert.match(layoutSource, /Prompt 管理/)

assert.match(pageSource, /getPromptList/)
assert.match(pageSource, /getPromptOptions/)
assert.match(pageSource, /updatePrompt/)
assert.match(pageSource, /activatePrompt/)
assert.match(pageSource, /保存为副本/)
assert.doesNotMatch(pageSource, /console\./)

console.log('prompt management wiring verified')
