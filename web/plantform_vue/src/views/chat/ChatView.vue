<template>
  <div class="chat-view">
    <!-- 左侧：会话列表 -->
    <aside class="chat-sidebar">
      <SessionList />
    </aside>

    <!-- 右侧：聊天区域 -->
    <main class="chat-main">
      <div class="chat-header">
        <h2 class="chat-title">
          {{ chatStore.currentSession?.name || chatStore.currentSession?.session_name || '新会话' }}
        </h2>
        <div class="chat-info">
          <button
            v-if="canViewContextUsage && chatStore.currentSessionId"
            class="context-usage-button"
            :class="contextUsageLevel"
            type="button"
            :title="contextUsageTitle"
            @click="openContextUsage"
          >
            {{ contextUsageLabel }}
          </button>
          <span class="message-count">
            {{ chatStore.messageCount }} 条消息
          </span>
        </div>
      </div>

      <el-drawer
        v-model="contextDialogVisible"
        title="上下文占用"
        direction="rtl"
        size="560px"
        class="context-usage-drawer"
      >
        <div v-if="primaryContextUsage" class="context-panel">
          <div class="context-summary">
            <div class="context-summary-item">
              <span class="summary-label">模型</span>
              <span class="summary-value">{{ primaryContextUsage.model_name }}</span>
            </div>
            <div class="context-summary-item">
              <span class="summary-label">已用</span>
              <span class="summary-value">{{ formatToken(primaryContextUsage.used_tokens) }}</span>
            </div>
            <div class="context-summary-item">
              <span class="summary-label">上下文</span>
              <span class="summary-value">{{ formatToken(primaryContextUsage.context_window) }}</span>
            </div>
            <div class="context-summary-item">
              <span class="summary-label">剩余</span>
              <span class="summary-value">{{ formatToken(primaryContextUsage.remaining_tokens) }}</span>
            </div>
          </div>

          <div class="context-meter">
            <div class="context-meter-header">
              <span>{{ contextUsageLabel }}</span>
              <span>{{ contextSourceLabel }}</span>
            </div>
            <div class="context-meter-track">
              <div class="context-meter-fill" :style="{ width: contextMeterWidth }"></div>
            </div>
          </div>

          <div v-if="contextUsageSections.length" class="context-section-list">
            <el-collapse>
              <el-collapse-item
                v-for="section in contextUsageSections"
                :key="section.type"
                :name="section.type"
              >
                <template #title>
                  <div class="context-section-title">
                    <span>{{ section.title }}</span>
                    <span>{{ formatToken(section.tokens) }} · {{ sectionPercent(section.tokens, primaryContextUsage.context_window) }}</span>
                  </div>
                </template>
                <pre class="context-section-content">{{ section.content }}</pre>
              </el-collapse-item>
            </el-collapse>
          </div>

          <div v-if="childAgentUsages.length" class="context-child-agents">
            <div class="context-child-title">子专家上下文</div>
            <el-collapse>
              <el-collapse-item
                v-for="agent in childAgentUsages"
                :key="agent.agent_key"
                :name="`child-${agent.agent_key}`"
              >
                <template #title>
                  <div class="context-section-title">
                    <span>调用：{{ agent.agent_name }}</span>
                    <span>{{ formatToken(agent.used_tokens) }} · {{ usagePercent(agent.percent) }}</span>
                  </div>
                </template>
                <div class="context-agent-summary">
                  <span>已用 {{ formatToken(agent.used_tokens) }}</span>
                  <span>剩余 {{ formatToken(agent.remaining_tokens) }}</span>
                </div>
                <div
                  v-for="section in agent.sections || []"
                  :key="`${agent.agent_key}-${section.type}`"
                  class="context-child-section"
                >
                  <div class="context-section-title">
                    <span>{{ section.title }}</span>
                    <span>{{ formatToken(section.tokens) }} · {{ sectionPercent(section.tokens, agent.context_window) }}</span>
                  </div>
                  <pre class="context-section-content">{{ section.content }}</pre>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
        <EmptyState
          v-else-if="!contextLoading"
          text="暂无上下文内容"
          subtext=""
        />
      </el-drawer>

      <div class="chat-messages" ref="messagesContainer" @scroll="handleScroll">
        <LoadingSpinner
          v-if="chatStore.messagesLoading"
          text="正在加载会话..."
          class="messages-loading"
        />

        <EmptyState
          v-else-if="!chatStore.loading && chatStore.currentMessages.length === 0"
          :icon="ChatDotRound"
          text="开始新的对话"
          subtext="向 AI 助手提问，获取智能答案"
        />

        <div v-else class="messages-list">
          <ChatMessage
            v-for="(message, index) in chatStore.currentMessages"
            :key="message.id || index"
            :message="message"
            :is-streaming="isLastMessage(index) && isStreaming"
            @regenerate="handleRegenerate"
          />
        </div>

        <!-- 加载中提示 -->
        <div v-if="isStreaming" class="streaming-indicator">
          <div class="indicator-dot"></div>
          <div class="indicator-dot"></div>
          <div class="indicator-dot"></div>
        </div>
      </div>

      <div class="chat-input-wrapper">
        <MessageInput
          ref="messageInputRef"
          :is-streaming="isStreaming"
          @send="handleSendMessage"
          @pause="handlePauseStreaming"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onActivated, onDeactivated, onBeforeUnmount, watch, defineOptions } from 'vue'
import { useUserStore, useChatStore } from '@/store'
import { sendMessageStreamWithOptions, getContextUsage } from '@/api'
import { applyAgentManifest, applyAgentProcess } from '@/utils/agentProcess'
import { ElMessage } from 'element-plus'
import { ChatDotRound } from '@element-plus/icons-vue'

import SessionList from '@/components/chat/SessionList.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import MessageInput from '@/components/chat/MessageInput.vue'
import EmptyState from '@/components/public/EmptyState.vue'
import LoadingSpinner from '@/components/public/LoadingSpinner.vue'

// 定义组件名，用于 keep-alive
defineOptions({
  name: 'ChatView'
})

const userStore = useUserStore()
const chatStore = useChatStore()

const messagesContainer = ref(null)
const messageInputRef = ref(null)
const isStreaming = ref(false)
const savedScrollPosition = ref(0) // 保存滚动位置
const contextDialogVisible = ref(false)
const contextLoading = ref(false)
const contextUsage = ref(null)
const executionStartedAt = ref(0)
const executionElapsedSeconds = ref(0)
const executionTimerId = ref(null)
const streamAbortController = ref(null)
const streamPausedByUser = ref(false)

const userScrollAttempts = ref(0) // 用户尝试滚动的次数
const allowFreeScroll = ref(false) // 是否允许自由滚动
const preserveScrollAfterPrepend = ref(null)
const shouldScrollAfterSessionLoad = ref(false)

const canViewContextUsage = computed(() => userStore.userInfo?.is_admin === 1)

const formatExecutionSeconds = (seconds) => {
  const value = Number(seconds || 0)
  if (value < 10) return `${value.toFixed(1)}s`
  return `${Math.round(value)}s`
}

const stopExecutionTimer = () => {
  if (executionTimerId.value) {
    window.clearInterval(executionTimerId.value)
    executionTimerId.value = null
  }
}

const startExecutionTimer = () => {
  stopExecutionTimer()
  executionStartedAt.value = Date.now()
  executionElapsedSeconds.value = 0
  executionTimerId.value = window.setInterval(() => {
    executionElapsedSeconds.value = (Date.now() - executionStartedAt.value) / 1000
    const lastMessage = chatStore.currentMessages[chatStore.currentMessages.length - 1]
    if (lastMessage && lastMessage.role === 'assistant') {
      lastMessage.executionElapsedSeconds = executionElapsedSeconds.value
      lastMessage.executionRunning = true
    }
  }, 100)
}

const finishExecutionTimer = (elapsedSeconds = null) => {
  const finalSeconds = elapsedSeconds !== null && elapsedSeconds !== undefined
    ? Number(elapsedSeconds)
    : (Date.now() - executionStartedAt.value) / 1000
  executionElapsedSeconds.value = finalSeconds
  const lastMessage = chatStore.currentMessages[chatStore.currentMessages.length - 1]
  if (lastMessage && lastMessage.role === 'assistant') {
    lastMessage.executionElapsedSeconds = finalSeconds
    lastMessage.executionRunning = false
  }
  stopExecutionTimer()
}

const cleanupStreamingState = () => {
  streamAbortController.value = null
  isStreaming.value = false
}

const handlePauseStreaming = () => {
  if (!isStreaming.value || !streamAbortController.value) return
  streamPausedByUser.value = true
  streamAbortController.value.abort()
  finishExecutionTimer()
  resetScrollState()
  cleanupStreamingState()
}

const contextUsageLabel = computed(() => {
  if (!contextUsage.value) return '0%'
  const prefix = contextUsage.value.count_type === 'estimated' ? '约' : ''
  const percent = Number(contextUsage.value.percent || 0)
  if (percent > 0 && percent < 1) return `${prefix}<1%`
  const label = percent % 1 === 0 ? String(Math.round(percent)) : percent.toFixed(2)
  return `${prefix}${label}%`
})

const contextUsageLevel = computed(() => {
  const percent = primaryContextUsage.value?.percent || 0
  if (percent >= 85) return 'is-high'
  if (percent >= 60) return 'is-medium'
  return 'is-low'
})

const primaryContextUsage = computed(() => {
  if (!contextUsage.value) return null
  return contextUsage.value.primary_agent_usage || contextUsage.value
})

const childAgentUsages = computed(() => contextUsage.value?.child_agent_usages || [])

const contextUsageSections = computed(() => primaryContextUsage.value?.sections || primaryContextUsage.value?.items || [])

const contextUsageTitle = computed(() => {
  if (!primaryContextUsage.value) return '上下文占用'
  return `${formatToken(primaryContextUsage.value.used_tokens)} / ${formatToken(primaryContextUsage.value.context_window)}`
})

const contextSourceLabel = computed(() => {
  if (!primaryContextUsage.value) return ''
  return '当前上下文'
})

const contextMeterWidth = computed(() => {
  const percent = Math.min(100, Math.max(0, Number(primaryContextUsage.value?.percent || 0)))
  return `${percent}%`
})

const formatToken = (value) => {
  const number = Number(value || 0)
  return `${number.toLocaleString()} tokens`
}

const sectionPercent = (tokens, contextWindow) => {
  const total = Number(contextWindow || 0)
  const value = Number(tokens || 0)
  if (!total || !value) return '0%'
  const percent = Math.min(100, (value / total) * 100)
  if (percent > 0 && percent < 1) return '<1%'
  return `${percent.toFixed(1)}%`
}

const usagePercent = (percent) => {
  const value = Number(percent || 0)
  if (value > 0 && value < 1) return '<1%'
  return `${value % 1 === 0 ? Math.round(value) : value.toFixed(2)}%`
}

// 判断是否为最后一条消息
const isLastMessage = (index) => {
  return index === chatStore.currentMessages.length - 1
}

// 滚动到底部（带条件判断）
const scrollToBottom = (force = false) => {
  nextTick(() => {
    if (messagesContainer.value) {
      // 如果强制滚动，或者不在流式输出中，或者未允许自由滚动，则滚动到底部
      if (force || !isStreaming.value || !allowFreeScroll.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    }
  })
}

const restoreScrollAfterPrepend = () => {
  nextTick(() => {
    const container = messagesContainer.value
    const previous = preserveScrollAfterPrepend.value
    if (!container || !previous) return

    container.scrollTop = container.scrollHeight - previous.scrollHeight + previous.scrollTop
    preserveScrollAfterPrepend.value = null
  })
}

// 处理用户滚动事件
const handleScroll = (event) => {
  const container = messagesContainer.value
  if (!container) return

  if (!isStreaming.value) {
    const scrollableHeight = container.scrollHeight - container.clientHeight
    if (scrollableHeight <= 0) return

    const scrollRatio = container.scrollTop / scrollableHeight
    if (
      scrollRatio <= 0.3 &&
      chatStore.hasOlderMessages &&
      !chatStore.olderMessagesLoading &&
      !chatStore.messagesLoading
    ) {
      preserveScrollAfterPrepend.value = {
        scrollTop: container.scrollTop,
        scrollHeight: container.scrollHeight
      }
      chatStore.loadOlderMessages()
    }
    return
  }
  
  // 检测是否向上滚动（用户想查看历史）
  const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50
  
  if (!isAtBottom && !allowFreeScroll.value) {
    // 用户尝试向上滚动
    userScrollAttempts.value++
    
    if (userScrollAttempts.value >= 2) {
      // 第二次尝试，允许自由滚动
      allowFreeScroll.value = true
    } else {
      // 第一次尝试，阻止并滚动回底部
      scrollToBottom(true)
    }
  }
}

// 重置滚动状态（流式输出结束时调用）
const resetScrollState = () => {
  userScrollAttempts.value = 0
  allowFreeScroll.value = false
}

const refreshContextUsage = async () => {
  if (!canViewContextUsage.value || !chatStore.currentSessionId) return
  try {
    contextLoading.value = true
    contextUsage.value = await getContextUsage(chatStore.currentSessionId)
  } catch (error) {
    contextUsage.value = null
  } finally {
    contextLoading.value = false
  }
}

const openContextUsage = async () => {
  contextDialogVisible.value = true
  await refreshContextUsage()
}

// 发送消息（SSE 流式）
const handleSendMessage = async ({ content, showThinking, agentMode = chatStore.agentMode, files = [], location = null, skipCache = false, regenerateMessageId = null }) => {
  if (!content.trim()) return

  // 添加用户消息
  const userMessage = {
    role: 'user',
    content: content,
    create_at: new Date().toISOString()
  }
  
  // 如果有文件上传，添加文件信息（与数据库结构一致）
  if (files && files.length > 0) {
    const firstFile = files[0]
    userMessage.file_name = firstFile.name
    userMessage.file_size = firstFile.size.toString()
    userMessage.file_type = firstFile.type
  }
  
  // 如果有位置信息，添加到用户消息（用于显示）
  if (location) {
    userMessage.location = location
  }
  
  chatStore.addMessage(userMessage)
  startExecutionTimer()
  
  // 🔥 用户发送问题时，重置滚动状态并强制滚动到底部
  resetScrollState()
  scrollToBottom(true)

  // 创建 AI 消息占位符
  const aiMessage = {
    role: 'assistant',
    content: '',
    thinking: '',
    action: '',
    observation: '',
    agentManifest: [],
    agentProcesses: [],
    documents: [],
    executionElapsedSeconds: 0,
    executionRunning: true,
    create_at: new Date().toISOString()
  }
  chatStore.addMessage(aiMessage)

  isStreaming.value = true
  streamPausedByUser.value = false
  streamAbortController.value = new AbortController()

  try {
    // 统一使用 FormData 发送（无论是否有文件）
    const formData = new FormData()
    formData.append('content', content)
    formData.append('user_id', userStore.userId)
    if (chatStore.currentSessionId) {
      formData.append('session_id', chatStore.currentSessionId)
    }
    formData.append('show_thinking', showThinking ? 'true' : 'false')
    formData.append('agent_mode', agentMode)
    
    // 如果有位置信息，添加到 FormData（作为 JSON 字符串）
    if (location) {
      formData.append('location', JSON.stringify(location))
    }
    
    // 如果有文件，添加文件（只支持单个文件）
    if (files && files.length > 0) {
      formData.append('file', files[0].file)
      if (files.length > 1) {
        ElMessage.warning('当前只支持上传一个文件，已自动选择第一个文件')
      }
    }
    
    // 使用支持额外选项的 API（跳过缓存、重新生成）
    const response = await sendMessageStreamWithOptions(formData, true, {
      skipCache: skipCache,
      regenerateMessageId: regenerateMessageId,
      signal: streamAbortController.value.signal
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventType = ''

    while (true) {
      if (streamPausedByUser.value) break
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (streamPausedByUser.value) break
        if (!line.trim()) continue

        if (line.startsWith('event: ')) {
          eventType = line.substring(7).trim()
          continue
        }

        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            if (streamPausedByUser.value) break
            await handleSSEEvent(eventType, data)
          } catch (error) {
            ElMessage.error('消息接收失败，请重试')
          }
        }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      finishExecutionTimer()
      return
    }

    ElMessage.error('发送消息失败，请重试')
    
    // 移除失败的消息
    chatStore.currentMessages.pop()
    finishExecutionTimer()
  } finally {
    cleanupStreamingState()
  }
}

// 处理 SSE 事件
const handleSSEEvent = async (eventType, data) => {
  if (streamPausedByUser.value) return

  const lastMessage = chatStore.currentMessages[chatStore.currentMessages.length - 1]

  switch (eventType) {
    case 'session_created':
      // 会话创建成功，设置当前会话ID并刷新会话列表
      if (data.session_id) {
        chatStore.addSession({
          uuid: data.session_id,
          id: data.session_id,
          name: data.session_name || '新会话',
          session_name: data.session_name || '新会话',
          update_at: new Date().toISOString()
        })
        chatStore.currentSessionId = data.session_id
        // 刷新会话列表
        await chatStore.fetchSessionList(userStore.userId)
      }
      break
      
    case 'user_message_saved':
      // 用户消息已保存
      break
      
    case 'thought':
      // Agent 思考过程
      if (lastMessage && data.content) {
        if (!lastMessage.thinking) {
          lastMessage.thinking = data.content
        } else {
          lastMessage.thinking += data.content
        }
      }
      break
      
    case 'action':
      // Agent 执行动作
      if (lastMessage && data.content) {
        if (!lastMessage.action) {
          lastMessage.action = data.content
        } else {
          lastMessage.action += `\n${data.content}`
        }
      }
      break
      
    case 'observation':
      // 观察结果
      if (lastMessage && data.content) {
        if (!lastMessage.observation) {
          lastMessage.observation = data.content
        } else {
          lastMessage.observation += `\n${data.content}`
        }
      }
      break

    case 'expert_manifest':
      if (lastMessage) {
        applyAgentManifest(lastMessage, data)
      }
      break

    case 'agent_process':
      if (lastMessage) {
        applyAgentProcess(lastMessage, data)
      }
      break

    case 'expert_task_status':
      break

    case 'agent_context_usage':
      if (lastMessage) {
        lastMessage.extra_data = {
          ...(lastMessage.extra_data || {}),
          agent_context_usage: data
        }
      }
      break
      
    case 'answer_chunk':
      // 答案片段
      if (lastMessage && data.content) {
        lastMessage.content += data.content
        scrollToBottom()
      }
      break
      
    case 'documents':
      // 引用文档列表
      if (lastMessage && data.documents) {
        lastMessage.documents = data.documents
        scrollToBottom()
      }
      break
      
    case 'ai_message_saved':
      // AI 消息已保存，保存 thought_chain_id 用于反馈功能
      if (lastMessage && data) {
        // 使用 Vue 响应式方式更新 extra_data
        // 创建新的 extra_data 对象以触发响应式更新
        const newExtraData = {
          ...(lastMessage.extra_data || {}),
          thought_chain_id: data.thought_chain_id || null,
          like_count: data.like_count || 0,
          dislike_count: data.dislike_count || 0
        }
        // 替换整个 extra_data 对象
        lastMessage.extra_data = newExtraData
      }
      break
      
    case 'done':
      // 流式输出完成
      finishExecutionTimer(data.elapsed_seconds)
      if (lastMessage) {
        lastMessage.extra_data = {
          ...(lastMessage.extra_data || {}),
          elapsed_seconds: data.elapsed_seconds || lastMessage.executionElapsedSeconds
        }
      }
      isStreaming.value = false
      
      // 🔥 重置滚动状态
      resetScrollState()
      
      // 立即刷新会话列表以更新最后消息时间
      await chatStore.fetchSessionList(userStore.userId)
      await refreshContextUsage()
      
      // 🔥 检测是否是第1轮对话，如果是则延迟刷新以获取自动生成的会话名称
      const currentMessageCount = chatStore.currentMessages.length
      
      if (currentMessageCount === 2) {
        // 延迟2秒后再次刷新，等待后端生成会话名称
        setTimeout(async () => {
          await chatStore.fetchSessionList(userStore.userId)
        }, 2000)
      }
      break
      
    case 'error':
      // 错误
      ElMessage.error(data.message || '发生错误')
      finishExecutionTimer()
      isStreaming.value = false
      // 🔥 错误时也重置滚动状态
      resetScrollState()
      break
  }
}

// 重新生成消息
const handleRegenerate = (message) => {
  // 找到用户的上一条消息
  const messageIndex = chatStore.currentMessages.findIndex(m => m === message)
  if (messageIndex > 0) {
    const userMessage = chatStore.currentMessages[messageIndex - 1]
    if (userMessage.role === 'user') {
      // 获取原消息的 thought_chain_id（用于删除旧缓存）
      const regenerateMessageId = message.extra_data?.thought_chain_id || null
      
      // 移除当前 AI 消息
      chatStore.currentMessages.splice(messageIndex, 1)
      
      // 重新发送，跳过缓存并传递原消息ID
      handleSendMessage({
        content: userMessage.content,
        showThinking: chatStore.showThinking,
        skipCache: true,  // 跳过缓存
        regenerateMessageId: regenerateMessageId  // 用于删除旧缓存
      })
    }
  }
}

// 监听当前会话变化
watch(
  () => chatStore.currentSessionId,
  async () => {
    if (chatStore.currentSessionId) {
      shouldScrollAfterSessionLoad.value = true
    }
    await refreshContextUsage()
  }
)

// 监听消息变化
watch(
  () => chatStore.currentMessages.length,
  () => {
    if (preserveScrollAfterPrepend.value) {
      restoreScrollAfterPrepend()
      return
    }

    if (shouldScrollAfterSessionLoad.value || isStreaming.value) {
      scrollToBottom(true)
      shouldScrollAfterSessionLoad.value = false
    }
  }
)

onMounted(async () => {
  // 确保有 userId 才获取会话列表
  if (userStore.userId) {
    // 进入页面时立即获取会话列表
    await chatStore.fetchSessionList(userStore.userId)
  }

  if (chatStore.currentSessionId && chatStore.currentMessages.length === 0) {
    shouldScrollAfterSessionLoad.value = true
    await chatStore.switchSession(chatStore.currentSessionId)
  } else {
    scrollToBottom()
  }
})

// 组件激活时（从其他页面返回）
onActivated(async () => {
  // 如果会话列表为空且有 userId，重新获取会话列表
  if (chatStore.sessionList.length === 0 && userStore.userId) {
    await chatStore.fetchSessionList(userStore.userId)
  }
  
  // 恢复滚动位置
  nextTick(() => {
    if (messagesContainer.value && savedScrollPosition.value > 0) {
      messagesContainer.value.scrollTop = savedScrollPosition.value
    }
  })
})

// 组件停用时（离开页面）
onDeactivated(() => {
  // 保存滚动位置
  if (messagesContainer.value) {
    savedScrollPosition.value = messagesContainer.value.scrollTop
  }
})

onBeforeUnmount(() => {
  if (streamAbortController.value) {
    streamAbortController.value.abort()
  }
  stopExecutionTimer()
})

// 监听 userId 变化，当登录后 userId 从空变为有值时，自动获取会话列表
watch(
  () => userStore.userId,
  async (newUserId, oldUserId) => {
    if (newUserId && !oldUserId && chatStore.sessionList.length === 0) {
      await chatStore.fetchSessionList(newUserId)
    }
  }
)

watch(
  () => chatStore.olderMessagesLoading,
  (loading, wasLoading) => {
    if (!loading && wasLoading && preserveScrollAfterPrepend.value) {
      restoreScrollAfterPrepend()
    }
  }
)
</script>

<style scoped>
.chat-view {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.chat-sidebar {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
  padding: 8px 20px;
  background: var(--component-bg);
  border-bottom: 1px solid var(--border-color);
}

.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.message-count {
  font-size: 12px;
  color: var(--text-tertiary);
}

.context-usage-button {
  min-width: 64px;
  height: 28px;
  border-radius: 999px;
  border: 1px solid var(--control-border);
  background: var(--component-muted-bg);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 0 12px;
  box-shadow: none;
  transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.context-usage-button:hover {
  background: var(--control-hover-bg);
  border-color: var(--primary-color);
}

.context-usage-button.is-low {
  border-color: rgba(34, 197, 94, 0.45);
  color: var(--text-secondary);
}

.context-usage-button.is-medium {
  border-color: rgba(245, 158, 11, 0.58);
  color: var(--warning-color);
}

.context-usage-button.is-high {
  border-color: rgba(239, 68, 68, 0.62);
  color: var(--danger-color);
}

:deep(.context-usage-drawer) {
  background: var(--bg-primary);
  border-left: 1px solid var(--border-color);
  color: var(--text-primary);
}

:deep(.context-usage-drawer .el-drawer__header) {
  margin-bottom: 0;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

:deep(.context-usage-drawer .el-drawer__title) {
  color: var(--text-primary);
  font-weight: 600;
}

:deep(.context-usage-drawer .el-drawer__close-btn) {
  color: var(--text-secondary);
}

:deep(.context-usage-drawer .el-drawer__close-btn:hover) {
  color: var(--neon-blue);
}

:deep(.context-usage-drawer .el-drawer__body) {
  padding: 20px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

:deep(.context-usage-drawer .el-collapse) {
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
}

:deep(.context-usage-drawer .el-collapse-item__header) {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 0 12px;
}

:deep(.context-usage-drawer .el-collapse-item__wrap) {
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
}

:deep(.context-usage-drawer .el-collapse-item__content) {
  padding: 12px;
  color: var(--text-secondary);
}

.context-panel {
  height: calc(100vh - 96px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.context-summary {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.context-summary-item {
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.summary-label {
  display: block;
  margin-bottom: 6px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.summary-value {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 600;
}

.context-meter {
  flex-shrink: 0;
  margin-bottom: 16px;
}

.context-meter-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.context-meter-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
  overflow: hidden;
}

.context-meter-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22c55e, #38bdf8);
}

.context-section-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.context-child-agents {
  flex-shrink: 0;
  max-height: 34vh;
  overflow-y: auto;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.context-child-title {
  margin-bottom: 10px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}

.context-agent-summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.context-child-section + .context-child-section {
  margin-top: 12px;
}

.context-section-title {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-primary);
  font-size: 13px;
}

.context-section-content {
  max-height: 320px;
  overflow: auto;
  margin: 0;
  padding: 12px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.38);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 768px) {
  .chat-header {
    padding: 8px 12px;
  }

  .chat-title {
    font-size: 16px;
  }

  .chat-info {
    gap: 10px;
  }

  .context-summary {
    grid-template-columns: 1fr;
  }

  :deep(.context-usage-drawer) {
    width: 100vw !important;
  }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px 12px;
}

.messages-loading {
  min-height: 100%;
}

.messages-list {
  width: 85%;
  max-width: 85%;
  margin: 0 auto;
}

.streaming-indicator {
  display: flex;
  gap: 8px;
  padding: 10px;
  align-items: center;
  justify-content: center;
}

.indicator-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--neon-blue);
  animation: bounce 1.4s ease-in-out infinite;
}

.indicator-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.indicator-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.chat-input-wrapper {
  flex-shrink: 0;
}

@media (max-width: 1024px) {
  .messages-list {
    width: 100%;
    max-width: 100%;
  }
}
</style>
