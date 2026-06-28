import assert from 'node:assert/strict'
import { normalizeChatMessages } from '../src/store/chatPagination.js'
import {
  applyAgentManifest,
  applyAgentProcess,
  getExpertProcessGroups,
  getSupervisorProcesses,
  hasExpertProcessBlocks
} from '../src/utils/agentProcess.js'

const manifestOnlyMessage = {
  role: 'assistant',
  content: '',
  agentManifest: []
}

applyAgentManifest(manifestOnlyMessage, {
  experts: [
    {
      agent_key: 'search',
      agent_name: '搜索专家',
      description: '查询实时信息',
      tools: ['web_search']
    }
  ]
})

assert.equal(hasExpertProcessBlocks(manifestOnlyMessage), false)
assert.deepEqual(getExpertProcessGroups(manifestOnlyMessage), [])

const message = {
  role: 'assistant',
  content: '',
  thinking: '主流程',
  action: '',
  observation: ''
}

applyAgentManifest(message, {
  experts: [
    {
      agent_key: 'search',
      agent_name: '搜索专家',
      description: '查询实时信息',
      tools: ['web_search']
    }
  ]
})

applyAgentProcess(message, {
  scope: 'supervisor',
  agent_key: 'supervisor',
  agent_name: '主助手',
  phase: 'thought',
  content: '已安排 1 个专家协作处理。',
  step_index: 1
})

applyAgentProcess(message, {
  scope: 'supervisor',
  agent_key: 'supervisor',
  agent_name: '主助手',
  phase: 'action',
  content: '已交给搜索专家处理。',
  step_index: 2
})

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'action',
  content: 'web_search(北京天气)',
  step_index: 3
})

applyAgentProcess(message, {
  scope: 'supervisor',
  agent_key: 'supervisor',
  agent_name: '主助手',
  phase: 'thought',
  content: '识别到需要调用：搜索专家',
  step_index: 1
})

applyAgentProcess(message, {
  scope: 'supervisor',
  agent_key: 'supervisor',
  agent_name: '主助手',
  phase: 'call',
  content: '搜索专家\n任务：搜索专家处理：北京天气',
  step_index: 2
})

applyAgentProcess(message, {
  scope: 'supervisor',
  agent_key: 'supervisor',
  agent_name: '主助手',
  phase: 'call',
  content: '搜索专家\n任务：搜索专家处理：北京天气',
  step_index: 2
})

applyAgentProcess(message, {
  scope: 'supervisor',
  agent_key: 'supervisor',
  agent_name: '主助手',
  phase: 'observation',
  content: '搜索专家输出：北京天气晴。',
  step_index: 4
})

assert.equal(hasExpertProcessBlocks(message), true)
assert.deepEqual(
  getSupervisorProcesses(message).map((item) => `${item.phase}:${item.content}`),
  [
    'thought:识别到需要调用：搜索专家',
    'call:搜索专家\n任务：搜索专家处理：北京天气',
    'observation:搜索专家输出：北京天气晴。'
  ]
)
assert.equal(
  getSupervisorProcesses(message).some((item) => item.content.includes('已开始处理')),
  false
)

const groups = getExpertProcessGroups(message)
assert.equal(groups.length, 1)
assert.equal(groups[0].agentKey, 'search')
assert.equal(groups[0].agentName, '搜索专家')
assert.deepEqual(groups[0].processes.map((item) => item.content), ['web_search(北京天气)'])
assert.equal(message.thinking, '主流程')
assert.equal(message.action, '')

const normalized = normalizeChatMessages([
  {
    send_type: 1,
    content: '回答',
    send_at: '2026-06-24T10:00:00',
    extra_data: {
      agent_manifest: message.agentManifest,
      agent_processes: message.agentProcesses,
      thoughts: ['旧思考'],
      actions: ['旧操作'],
      observations: ['旧观察']
    }
  }
])

assert.equal(hasExpertProcessBlocks(normalized[0]), true)
assert.equal(getExpertProcessGroups(normalized[0])[0].agentName, '搜索专家')
assert.equal(normalized[0].thinking, '')
assert.equal(normalized[0].action, '')
assert.equal(normalized[0].observation, '')

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'action',
  content: 'topic=expert_tasks debug stack trace',
  step_index: 2
})

assert.deepEqual(
  getExpertProcessGroups(message)[0].processes.map((item) => item.content),
  ['web_search(北京天气)']
)

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'thought',
  content: 'Thought: 查询天气原因',
  step_index: 3
})

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'action',
  content: 'Action Input: {"city":"北京"}',
  step_index: 4
})

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'observation',
  content: 'Observation: 北京多云',
  step_index: 5
})

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'final_answer',
  content: 'Final Answer: 适合带伞',
  step_index: 6
})

applyAgentProcess(message, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'thought',
  content: '我已完成查询。FinalAnswer:北京多云，适合室内外结合游玩。',
  step_index: 7
})

assert.deepEqual(
  getExpertProcessGroups(message)[0].processes.map((item) => item.content),
  [
    'web_search(北京天气)',
    '查询天气原因',
    '{"city":"北京"}',
    '北京多云',
    '适合带伞',
    '我已完成查询。输出：北京多云，适合室内外结合游玩。'
  ]
)

const orderedMessage = {
  role: 'assistant',
  content: ''
}

applyAgentManifest(orderedMessage, {
  experts: [
    { agent_key: 'search', agent_name: '搜索专家', tools: ['web_search'] },
    { agent_key: 'location', agent_name: '位置专家', tools: ['weather_query'] }
  ]
})

applyAgentProcess(orderedMessage, {
  scope: 'expert',
  agent_key: 'location',
  agent_name: '位置专家',
  phase: 'thought',
  content: '先查天气',
  step_index: 2
})

applyAgentProcess(orderedMessage, {
  scope: 'expert',
  agent_key: 'search',
  agent_name: '搜索专家',
  phase: 'thought',
  content: '再查景点',
  step_index: 5
})

assert.deepEqual(
  getExpertProcessGroups(orderedMessage).map((group) => group.agentName),
  ['位置专家', '搜索专家']
)

const tokenizedThoughtMessage = {
  role: 'assistant',
  content: '',
  agentManifest: [
    { agentKey: 'location', agentName: '位置专家', tools: ['weather_query'] }
  ]
}

for (const [index, content] of [
  'Thought',
  ':',
  '搜索一下北京',
  '明天天气，并说明适合',
  '去哪里玩'
].entries()) {
  applyAgentProcess(tokenizedThoughtMessage, {
    scope: 'expert',
    agent_key: 'location',
    agent_name: '位置专家',
    phase: 'thought',
    content,
    step_index: index + 1
  })
}

assert.deepEqual(
  getExpertProcessGroups(tokenizedThoughtMessage)[0].processes.map((item) => `${item.phase}:${item.content}`),
  ['thought:搜索一下北京 明天天气，并说明适合 去哪里玩']
)

const duplicatedHistoryMessage = normalizeChatMessages([
  {
    send_type: 1,
    content: '回答',
    extra_data: {
      agent_manifest: [
        { agent_key: 'search', agent_name: '搜索专家', tools: ['web_search'] }
      ],
      agent_processes: [
        {
          scope: 'expert',
          agent_key: 'search',
          agent_name: '搜索专家',
          phase: 'thought',
          content: '用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。',
          step_index: 1
        },
        {
          scope: 'expert',
          agent_key: 'search',
          agent_name: '搜索专家',
          phase: 'thought',
          content: '用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。',
          step_index: 2
        },
        {
          scope: 'expert',
          agent_key: 'search',
          agent_name: '搜索专家',
          phase: 'observation',
          content: '未找到相关搜索结果',
          step_index: 3
        },
        {
          scope: 'expert',
          agent_key: 'search',
          agent_name: '搜索专家',
          phase: 'observation',
          content: '未找到相关搜索结果',
          step_index: 4
        }
      ]
    }
  }
])[0]

assert.deepEqual(
  getExpertProcessGroups(duplicatedHistoryMessage)[0].processes.map((item) => `${item.phase}:${item.content}`),
  [
    'thought:用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。',
    'observation:未找到相关搜索结果'
  ]
)

const singleAgentMessage = {
  role: 'assistant',
  content: ''
}

applyAgentProcess(singleAgentMessage, {
  scope: 'single',
  agent_key: 'langgraph',
  agent_name: 'AI 助手',
  phase: 'action',
  content: 'knowledge_search(我如何自制一个深度学习框架呢)',
  step_index: 1
})

applyAgentProcess(singleAgentMessage, {
  scope: 'single',
  agent_key: 'langgraph',
  agent_name: 'AI 助手',
  phase: 'observation',
  content: 'DeZero 通过 60 个步骤和少量代码自制深度学习框架。',
  step_index: 2
})

assert.equal(hasExpertProcessBlocks(singleAgentMessage), true)
assert.deepEqual(
  getSupervisorProcesses(singleAgentMessage).map((item) => `${item.phase}:${item.content}`),
  [
    'action:knowledge_search(我如何自制一个深度学习框架呢)',
    'observation:DeZero 通过 60 个步骤和少量代码自制深度学习框架。'
  ]
)

console.log('agent process grouping verified')
