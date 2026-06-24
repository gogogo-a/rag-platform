/**
 * 聊天状态管理
 */

import { defineStore } from 'pinia'
import { getSessionList, getMessageList } from '@/api'
import {
  DEFAULT_MESSAGE_PAGE_SIZE,
  getInitialMessagePage,
  getOlderMessagePage,
  normalizeChatMessages
} from './chatPagination'

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
    messagesLoading: false,
    olderMessagesLoading: false,
    currentMessagePage: 1,
    messagePageSize: DEFAULT_MESSAGE_PAGE_SIZE,
    totalMessages: 0,
    hasOlderMessages: false,
    showThinking: true
  }),

  getters: {
    // 当前会话对象
    currentSession: (state) => {
      return state.sessionList.find(s => String(s.uuid || s.id || '') === String(state.currentSessionId || '')) || null
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
        return { success: false, error }
      } finally {
        this.loading = false
      }
    },

    /**
     * 获取当前会话的消息列表
     */
    async fetchMessages(sessionId, page = 1, pageSize = this.messagePageSize, options = {}) {
      const targetSessionId = String(sessionId || '')
      if (!targetSessionId) return { success: false, error: new Error('会话不存在') }
      const appendMode = options.mode === 'prepend'
      
      try {
        if (appendMode) {
          this.olderMessagesLoading = true
        } else {
          this.messagesLoading = true
        }

        const data = await getMessageList(targetSessionId, {
          page,
          page_size: pageSize
        })
        
        const messages = normalizeChatMessages(data.messages || [])
        
        if (String(this.currentSessionId || '') === targetSessionId) {
          this.currentMessagePage = page
          this.totalMessages = Number(data.total || 0)
          this.hasOlderMessages = page > 1
          this.currentMessages = appendMode
            ? [...messages, ...this.currentMessages]
            : messages
        }
        
        return { success: true, data }
      } catch (error) {
        return { success: false, error }
      } finally {
        this.messagesLoading = false
        this.olderMessagesLoading = false
      }
    },

    /**
     * 切换当前会话
     */
    async switchSession(sessionId) {
      const nextSessionId = String(sessionId || '')
      if (!nextSessionId) {
        return { success: false, error: new Error('会话不存在') }
      }

      this.currentSessionId = nextSessionId
      this.currentMessages = []
      this.currentMessagePage = 1
      this.totalMessages = 0
      this.hasOlderMessages = false

      try {
        this.messagesLoading = true
        const firstPage = await getMessageList(nextSessionId, {
          page: 1,
          page_size: this.messagePageSize
        })
        const lastPage = getInitialMessagePage(firstPage.total, this.messagePageSize)
        const targetPageData = lastPage === 1
          ? firstPage
          : await getMessageList(nextSessionId, {
            page: lastPage,
            page_size: this.messagePageSize
          })

        if (String(this.currentSessionId || '') === nextSessionId) {
          this.currentMessagePage = lastPage
          this.totalMessages = Number(targetPageData.total || firstPage.total || 0)
          this.hasOlderMessages = lastPage > 1
          this.currentMessages = normalizeChatMessages(targetPageData.messages || [])
        }

        return { success: true, data: targetPageData }
      } catch (error) {
        return { success: false, error }
      } finally {
        this.messagesLoading = false
      }
    },

    async loadOlderMessages() {
      if (!this.currentSessionId || this.olderMessagesLoading || this.messagesLoading || !this.hasOlderMessages) {
        return { success: false }
      }

      const olderPage = getOlderMessagePage(this.currentMessagePage)
      if (!olderPage) {
        this.hasOlderMessages = false
        return { success: false }
      }

      return await this.fetchMessages(
        this.currentSessionId,
        olderPage,
        this.messagePageSize,
        { mode: 'prepend' }
      )
    },

    /**
     * 添加新会话到列表
     */
    addSession(session) {
      const sessionId = String(session.uuid || session.id || '')
      // 检查是否已存在
      const exists = this.sessionList.find(s => String(s.uuid || s.id || '') === sessionId)
      if (!exists) {
        this.sessionList.unshift(session)
      }
      this.currentSessionId = sessionId
    },

    /**
     * 从列表中移除会话
     */
    removeSession(sessionId) {
      const targetSessionId = String(sessionId || '')
      const index = this.sessionList.findIndex(s => String(s.uuid || s.id || '') === targetSessionId)
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
      this.currentMessagePage = 1
      this.totalMessages = 0
      this.hasOlderMessages = false
    },

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
      this.messagesLoading = false
      this.olderMessagesLoading = false
      this.currentMessagePage = 1
      this.totalMessages = 0
      this.hasOlderMessages = false
    }
  }
})
