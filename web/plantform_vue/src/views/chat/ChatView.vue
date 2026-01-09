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
          <span class="message-count">
            {{ chatStore.messageCount }} 条消息
          </span>
        </div>
      </div>

      <div class="chat-messages" ref="messagesContainer" @scroll="handleScroll">
        <EmptyState
          v-if="!chatStore.loading && chatStore.currentMessages.length === 0"
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
        <MessageInput ref="messageInputRef" @send="handleSendMessage" />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onActivated, onDeactivated, watch, defineOptions } from 'vue'
import { useUserStore, useChatStore } from '@/store'
import { sendMessageStream, sendMessageStreamWithOptions } from '@/api'
import { ElMessage } from 'element-plus'
import { ChatDotRound } from '@element-plus/icons-vue'

import SessionList from '@/components/chat/SessionList.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import MessageInput from '@/components/chat/MessageInput.vue'
import EmptyState from '@/components/public/EmptyState.vue'

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

// 🔥 滚动控制：流式输出时允许用户滑动一次后自由滚动
const userScrollAttempts = ref(0) // 用户尝试滚动的次数
const allowFreeScroll = ref(false) // 是否允许自由滚动

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

// 处理用户滚动事件
const handleScroll = (event) => {
  if (!isStreaming.value) return
  
  const container = messagesContainer.value
  if (!container) return
  
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

// 发送消息（SSE 流式）
const handleSendMessage = async ({ content, showThinking, files = [], location = null, skipCache = false, regenerateMessageId = null }) => {
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
    console.log('用户位置信息:', location)
  }
  
  chatStore.addMessage(userMessage)
  
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
    documents: [],
    create_at: new Date().toISOString()
  }
  chatStore.addMessage(aiMessage)

  isStreaming.value = true

  try {
    // 统一使用 FormData 发送（无论是否有文件）
    const formData = new FormData()
    formData.append('content', content)
    formData.append('user_id', userStore.userId)
    if (chatStore.currentSessionId) {
      formData.append('session_id', chatStore.currentSessionId)
    }
    formData.append('show_thinking', showThinking ? 'true' : 'false')
    
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
      regenerateMessageId: regenerateMessageId
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventType = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.trim()) continue

        if (line.startsWith('event: ')) {
          eventType = line.substring(7).trim()
          continue
        }

        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            await handleSSEEvent(eventType, data)
          } catch (error) {
            console.error('解析 SSE 数据失败:', error)
          }
        }
      }
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    ElMessage.error('发送消息失败，请重试')
    
    // 移除失败的消息
    chatStore.currentMessages.pop()
  } finally {
    isStreaming.value = false
  }
}

// 处理 SSE 事件
const handleSSEEvent = async (eventType, data) => {
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
      console.log('用户消息已保存')
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
          lastMessage.action += data.content
        }
        console.log('动作:', data.content)
      }
      break
      
    case 'observation':
      // 观察结果
      if (lastMessage && data.content) {
        if (!lastMessage.observation) {
          lastMessage.observation = data.content
        } else {
          lastMessage.observation += data.content
        }
        console.log('观察:', data.content)
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
        console.log('引用文档:', data.documents)
        scrollToBottom()
      }
      break
      
    case 'ai_message_saved':
      // AI 消息已保存，保存 thought_chain_id 用于反馈功能
      console.log('AI 消息已保存:', data)
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
        console.log('已更新 extra_data:', lastMessage.extra_data)
      }
      break
      
    case 'done':
      // 流式输出完成
      console.log('流式输出完成')
      isStreaming.value = false
      
      // 🔥 重置滚动状态
      resetScrollState()
      
      // 立即刷新会话列表以更新最后消息时间
      await chatStore.fetchSessionList(userStore.userId)
      
      // 🔥 检测是否是第1轮对话，如果是则延迟刷新以获取自动生成的会话名称
      const currentMessageCount = chatStore.currentMessages.length
      console.log('当前消息数量:', currentMessageCount)
      
      if (currentMessageCount === 2) {
        console.log('检测到第1轮对话，2秒后刷新会话列表以获取自动生成的名称')
        // 延迟2秒后再次刷新，等待后端生成会话名称
        setTimeout(async () => {
          console.log('刷新会话列表以更新自动生成的会话名称')
          await chatStore.fetchSessionList(userStore.userId)
        }, 2000)
      }
      break
      
    case 'error':
      // 错误
      ElMessage.error(data.message || '发生错误')
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
  () => {
    scrollToBottom()
  }
)

// 监听消息变化
watch(
  () => chatStore.currentMessages.length,
  () => {
    scrollToBottom()
  }
)

onMounted(async () => {
  console.log('ChatView mounted, userId:', userStore.userId)
  
  // 确保有 userId 才获取会话列表
  if (userStore.userId) {
    // 进入页面时立即获取会话列表
    await chatStore.fetchSessionList(userStore.userId)
    console.log('会话列表已加载，数量:', chatStore.sessionList.length)
  } else {
    console.warn('userId 不存在，无法获取会话列表')
  }
  
  // 清空当前会话，准备创建新会话
  chatStore.currentSessionId = ''
  chatStore.clearCurrentMessages()
  
  scrollToBottom()
})

// 组件激活时（从其他页面返回）
onActivated(async () => {
  console.log('ChatView activated: 恢复滚动位置', savedScrollPosition.value)
  
  // 如果会话列表为空且有 userId，重新获取会话列表
  if (chatStore.sessionList.length === 0 && userStore.userId) {
    console.log('会话列表为空，重新获取...')
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
    console.log('ChatView deactivated: 保存滚动位置', savedScrollPosition.value)
  }
})

// 监听 userId 变化，当登录后 userId 从空变为有值时，自动获取会话列表
watch(
  () => userStore.userId,
  async (newUserId, oldUserId) => {
    console.log('userId 变化:', oldUserId, '->', newUserId)
    if (newUserId && !oldUserId && chatStore.sessionList.length === 0) {
      console.log('检测到登录，获取会话列表...')
      await chatStore.fetchSessionList(newUserId)
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
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.chat-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.chat-info {
  display: flex;
  align-items: center;
  gap: 16px;
}

.message-count {
  font-size: 13px;
  color: var(--text-tertiary);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.messages-list {
  max-width: 900px;
  margin: 0 auto;
}

.streaming-indicator {
  display: flex;
  gap: 8px;
  padding: 16px;
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
</style>

