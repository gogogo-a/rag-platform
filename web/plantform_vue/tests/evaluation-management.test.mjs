import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (path) => readFileSync(join(rootDir, path), 'utf8')

const apiSource = readSource('src/api/evaluation.js')
const routerSource = readSource('src/router/index.js')
const layoutSource = readSource('src/views/admin/AdminLayout.vue')
const pageSource = readSource('src/views/admin/RAGEvaluationManagement.vue')

assert.match(layoutSource, /评估管理/)
assert.doesNotMatch(layoutSource, /RAG 评估/)
assert.match(layoutSource, /index="\/admin\/evaluations"/)

assert.match(routerSource, /path:\s*'evaluations'/)
assert.match(routerSource, /path:\s*'rag-evaluations'/)
assert.match(routerSource, /redirect:\s*'\/admin\/evaluations'/)
assert.match(routerSource, /AdminEvaluations/)

assert.match(apiSource, /getEvaluationList/)
assert.match(apiSource, /url:\s*'\/evaluations'/)

assert.match(pageSource, /评估管理/)
assert.match(pageSource, /综合评分/)
assert.match(pageSource, /评分原因/)
assert.match(pageSource, /评估类型/)
assert.match(pageSource, /RAG 评估/)
assert.match(pageSource, /正常回复评估/)
assert.match(pageSource, /长上下文评估/)
assert.match(pageSource, /工具调用评估/)
assert.match(pageSource, /多 Agent 评估/)
assert.match(pageSource, /evaluation_type:\s*activeType\.value/)
assert.match(pageSource, /llm_score/)
assert.match(pageSource, /rule_score/)
assert.match(pageSource, /score_reason/)
assert.match(pageSource, /getEvaluationList/)

assert.doesNotMatch(pageSource, /console\./)
assert.doesNotMatch(pageSource, /debugger/)
assert.doesNotMatch(pageSource, /这里用了/)
assert.doesNotMatch(pageSource, /新修改/)
assert.doesNotMatch(pageSource, /\/evaluations/)

console.log('evaluation management verified')
