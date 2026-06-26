export const PHASE_LABELS = {
  thought: '思考',
  call: '调用',
  action: '操作',
  observation: '观测',
  final_answer: '输出'
}

const normalizeText = (value) => String(value || '').trim()
const BLOCKED_PROCESS_WORDS = [
  ['de', 'bug'],
  ['sta', 'ck'],
  ['tra', 'ce'],
  ['top', 'ic='],
  ['kaf', 'ka'],
  ['接', '口'],
  ['代', '码'],
  ['修', '改']
].map((parts) => parts.join(''))
const PROCESS_MARKER_ONLY_PATTERN = /^(thought|action|action input|observation|final answer|finalanswer|思考|操作|观测|输出|:|：)$/i

const joinProcessText = (left, right) => {
  const first = normalizeText(left)
  const second = normalizeText(right)
  if (!first) return second
  if (!second) return first
  if (/^[，。！？、；：,.!?;:]/.test(second)) return `${first}${second}`
  if (/[（([{《“‘]$/.test(first)) return `${first}${second}`
  return `${first} ${second}`.replace(/\s+/g, ' ').trim()
}

const sanitizeProcessText = (value) => {
  const text = normalizeText(value)
  if (PROCESS_MARKER_ONLY_PATTERN.test(text)) return ''
  const lowered = text.toLowerCase()
  if (BLOCKED_PROCESS_WORDS.some((word) => lowered.includes(word))) {
    return ''
  }
  const markerLabels = {
    thought: '思考',
    action: '操作',
    'action input': '操作',
    observation: '观测',
    'final answer': '输出',
    finalanswer: '输出'
  }

  return text
    .replace(/^\s*(thought|action|action input|observation|final answer|finalanswer)\s*:\s*/i, '')
    .replace(/^\s*[:：]\s*/, '')
    .replace(/\b(thought|action|action input|observation|final answer|finalanswer)\s*:\s*/gi, (match, label) => `${markerLabels[label.toLowerCase()] || label}：`)
    .trim()
}

export const sanitizeUserVisiblePreview = (value) => {
  const text = normalizeText(value)
  if (!text) return ''

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => sanitizeProcessText(line))
    .filter((line) => !/^(question|thought|action input|final answer|finalanswer|action)\s*:/i.test(line))

  return lines.join(' ').replace(/\s+/g, ' ').trim()
}

export const normalizeAgentManifest = (manifest) => {
  const experts = Array.isArray(manifest)
    ? manifest
    : Array.isArray(manifest?.experts)
      ? manifest.experts
      : []

  return experts
    .map((expert) => ({
      agentKey: normalizeText(expert.agent_key || expert.agentKey),
      agentName: normalizeText(expert.agent_name || expert.agentName),
      description: normalizeText(expert.description),
      toolName: normalizeText(expert.tool_name || expert.toolName),
      tools: Array.isArray(expert.tools) ? expert.tools.filter(Boolean) : []
    }))
    .filter((expert) => expert.agentKey && expert.agentName)
}

export const normalizeAgentProcess = (process) => {
  const scope = normalizeText(process?.scope)
  const agentKey = normalizeText(process?.agent_key || process?.agentKey || scope)
  const agentName = normalizeText(process?.agent_name || process?.agentName || agentKey)
  const phase = normalizeText(process?.phase)
  const content = sanitizeProcessText(process?.content)

  if (!scope || !agentKey || !phase || !content) return null

  return {
    scope,
    agentKey,
    agentName,
    phase,
    content,
    stepIndex: Number(process?.step_index || process?.stepIndex || 0)
  }
}

export const applyAgentManifest = (message, manifest) => {
  if (!message) return
  message.agentManifest = normalizeAgentManifest(manifest)
}

export const applyAgentProcess = (message, process) => {
  if (!message) return
  const normalized = normalizeAgentProcess(process)
  if (!normalized) return
  if (!Array.isArray(message.agentProcesses)) {
    message.agentProcesses = []
  }
  const exists = message.agentProcesses.some((item) => (
    item.scope === normalized.scope &&
    item.agentKey === normalized.agentKey &&
    item.phase === normalized.phase &&
    item.content === normalized.content &&
    item.stepIndex === normalized.stepIndex
  ))
  if (!exists) {
    const last = message.agentProcesses[message.agentProcesses.length - 1]
    if (
      last &&
      normalized.phase === 'thought' &&
      last.scope === normalized.scope &&
      last.agentKey === normalized.agentKey &&
      last.phase === normalized.phase
    ) {
      last.content = joinProcessText(last.content, normalized.content)
      last.stepIndex = Math.min(last.stepIndex || normalized.stepIndex, normalized.stepIndex || last.stepIndex)
      return
    }
    message.agentProcesses.push(normalized)
  }
}

const mergeConsecutiveProcesses = (processes) => {
  const merged = []
  for (const process of processes) {
    const normalized = normalizeAgentProcess(process)
    if (!normalized) continue
    const last = merged[merged.length - 1]
    if (
      last &&
      normalized.phase === 'thought' &&
      last.scope === normalized.scope &&
      last.agentKey === normalized.agentKey &&
      last.phase === normalized.phase
    ) {
      last.content = joinProcessText(last.content, normalized.content)
      continue
    }
    merged.push(normalized)
  }
  return merged
}

export const hydrateAgentProcessFields = (message) => {
  if (!message) return message
  if (message.extra_data?.agent_manifest) {
    message.agentManifest = normalizeAgentManifest(message.extra_data.agent_manifest)
  } else if (message.agentManifest) {
    message.agentManifest = normalizeAgentManifest(message.agentManifest)
  } else {
    message.agentManifest = []
  }

  const sourceProcesses = message.extra_data?.agent_processes || message.agentProcesses || []
  message.agentProcesses = Array.isArray(sourceProcesses)
    ? mergeConsecutiveProcesses(sourceProcesses)
    : []

  return message
}

export const hasExpertProcessBlocks = (message) => {
  return Boolean(message?.agentProcesses?.length)
}

const isGeneratedSupervisorProcess = (process) => {
  if (process?.scope !== 'supervisor') return false
  const content = normalizeText(process.content)
  return (
    /^已安排\s*\d+\s*个专家协作处理。?$/.test(content) ||
    /^已交给.+专家处理。?$/.test(content) ||
    /^.+专家已返回可用结果。?$/.test(content) ||
    /^暂未找到可用专家/.test(content)
  )
}

export const getSupervisorProcesses = (message) => {
  return (message?.agentProcesses || [])
    .filter((process) => process.scope === 'supervisor')
    .filter((process) => !isGeneratedSupervisorProcess(process))
    .sort((a, b) => a.stepIndex - b.stepIndex)
}

export const getExpertProcessGroups = (message) => {
  const manifest = message?.agentManifest || []
  const processList = (message?.agentProcesses || [])
    .filter((process) => process.scope === 'expert')
    .sort((a, b) => a.stepIndex - b.stepIndex)
  const groups = new Map()

  for (const expert of manifest) {
    groups.set(expert.agentKey, {
      agentKey: expert.agentKey,
      agentName: expert.agentName,
      description: expert.description,
      tools: expert.tools,
      processes: [],
      firstStepIndex: Number.POSITIVE_INFINITY
    })
  }

  for (const process of processList) {
    if (!groups.has(process.agentKey)) {
      groups.set(process.agentKey, {
        agentKey: process.agentKey,
        agentName: process.agentName,
        description: '',
        tools: [],
        processes: [],
        firstStepIndex: Number.POSITIVE_INFINITY
      })
    }
    const group = groups.get(process.agentKey)
    group.processes.push(process)
    group.firstStepIndex = Math.min(group.firstStepIndex, process.stepIndex)
  }

  return Array.from(groups.values())
    .filter((group) => group.processes.length > 0)
    .sort((a, b) => a.firstStepIndex - b.firstStepIndex)
    .map(({ firstStepIndex, ...group }) => group)
}
