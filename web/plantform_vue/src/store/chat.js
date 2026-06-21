/**
 * 聊天状态管理
 */

import { defineStore } from 'pinia'
import { getSessionList, getMessageList } from '@/api'

export const useChatStore = defineStore('chat', {
  state: () => ({
    // 会话列表
    sessionList: [],
    // 当前活动的会话 ID
    currentSessionId: '',
    // 当前会话的消息列表
    currentMessages: [],
    // 是否正在加载
    loading: false,
    // 是否显示思考过程
    showThinking: true
  }),

  getters: {
    // 当前会话对象
    currentSession: (state) => {
      return state.sessionList.find(s => (s.uuid || s.id) === state.currentSessionId) || null
    },
    
    // 消息总数
    messageCount: (state) => state.currentMessages.length
  },

  actions: {
    /**
     * 获取会话列表
     */
    async fetchSessionList(userId, page = 1, pageSize = 50) {
      try {
        this.loading = true
        const data = await getSessionList({
          user_id: userId,
          page,
          page_size: pageSize
        })
        
        this.sessionList = data.sessions || []
        
        // 不自动选择会话，让用户手动选择或创建新会话
        
        return { success: true, data }
      } catch (error) {
        console.error('获取会话列表失败:', error)
        return { success: false, error }
      } finally {
        this.loading = false
      }
    },

    /**
     * 获取当前会话的消息列表
     */
    async fetchMessages(sessionId, page = 1, pageSize = 100) {
      if (!sessionId) return
      
      try {
        this.loading = true
        const data = await getMessageList(sessionId, {
          page,
          page_size: pageSize
        })
        
        // 处理消息，将 extra_data 中的数据提取到顶层
        const messages = (data.messages || [])
          // 🔥 过滤掉系统总结消息（send_type === 2）
          .filter(msg => msg.send_type !== 2)
          .map(msg => {
          // 转换消息角色
          const role = msg.send_type === 0 ? 'user' : 'assistant'
          
          // 构建基础消息对象
          const processedMsg = {
            ...msg,
            role,
            create_at: msg.send_at || msg.created_at
          }
          
          // 如果有 extra_data，提取其中的数据
          if (msg.extra_data) {
            // 思考过程 - 合并数组为字符串
            if (msg.extra_data.thoughts && msg.extra_data.thoughts.length > 0) {
              processedMsg.thinking = msg.extra_data.thoughts.join('\n\n')
            }
            
            // 操作过程 - 合并数组为字符串
            if (msg.extra_data.actions && msg.extra_data.actions.length > 0) {
              processedMsg.action = msg.extra_data.actions.join('\n\n')
            }
            
            // 观察结果 - 合并数组为字符串
            if (msg.extra_data.observations && msg.extra_data.observations.length > 0) {
              processedMsg.observation = msg.extra_data.observations.join('\n\n')
            }
            
            // 文档列表 - 保持数组格式
            if (msg.extra_data.documents && msg.extra_data.documents.length > 0) {
              processedMsg.documents = msg.extra_data.documents
            }
          }
          
          return processedMsg
        })
        
        this.currentMessages = messages
        
        return { success: true, data }
      } catch (error) {
        console.error('获取消息列表失败:', error)
        return { success: false, error }
      } finally {
        this.loading = false
      }
    },

    /**
     * 切换当前会话
     */
    async switchSession(sessionId) {
      this.currentSessionId = sessionId
      this.currentMessages = []
      await this.fetchMessages(sessionId)
    },

    /**
     * 添加新会话到列表
     */
    addSession(session) {
      const sessionId = session.uuid || session.id
      // 检查是否已存在
      const exists = this.sessionList.find(s => (s.uuid || s.id) === sessionId)
      if (!exists) {
        this.sessionList.unshift(session)
      }
      this.currentSessionId = sessionId
    },

    /**
     * 从列表中移除会话
     */
    removeSession(sessionId) {
      const index = this.sessionList.findIndex(s => (s.uuid || s.id) === sessionId)
      if (index !== -1) {
        this.sessionList.splice(index, 1)
      }
    },

    /**
     * 添加消息到当前会话
     */
    addMessage(message) {
      this.currentMessages.push(message)
    },

    /**
     * 更新最后一条消息（用于流式输出）
     */
    updateLastMessage(content) {
      if (this.currentMessages.length > 0) {
        const lastMsg = this.currentMessages[this.currentMessages.length - 1]
        lastMsg.content += content
      }
    },

    /**
     * 清空当前会话消息
     */
    clearCurrentMessages() {
      this.currentMessages = []
    },

    /**
     * 切换思考过程显示
     */
    toggleShowThinking() {
      this.showThinking = !this.showThinking
    },

    /**
     * 清除所有聊天数据（用户登出时调用）
     */
    clearAll() {
      this.sessionList = []
      this.currentSessionId = ''
      this.currentMessages = []
      this.loading = false
    }
  }
})

