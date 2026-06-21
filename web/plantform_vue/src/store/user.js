/**
 * 用户状态管理
 */

import { defineStore } from 'pinia'
import { login, emailLogin, getUserInfo } from '@/api'

export const useUserStore = defineStore('user', {
  state: () => {
    // 安全地读取 localStorage
    let userInfo = {}
    try {
      const storedUserInfo = localStorage.getItem('userInfo')
      if (storedUserInfo && storedUserInfo !== 'undefined') {
        userInfo = JSON.parse(storedUserInfo)
      }
    } catch (e) {
      console.warn('解析 userInfo 失败:', e)
      localStorage.removeItem('userInfo')
    }

    return {
      token: localStorage.getItem('token') || '',
      userInfo: userInfo,
      isLoggedIn: !!localStorage.getItem('token')
    }
  },

  getters: {
    // 是否为管理员
    isAdmin: (state) => state.userInfo.is_admin || false,
    
    // 用户 ID
    userId: (state) => state.userInfo.uuid || state.userInfo.id || '',
    
    // 用户昵称
    nickname: (state) => state.userInfo.nickname || '游客'
  },

  actions: {
    /**
     * 用户登录（昵称+密码）
     */
    async login(loginForm) {
      try {
        const data = await login(loginForm)
        
        
        // 保存 token 和用户信息
        this.token = data.token || ''
        this.userInfo = data.user_info || data
        this.isLoggedIn = true
        
        if (this.token) {
          localStorage.setItem('token', this.token)
        }
        localStorage.setItem('userInfo', JSON.stringify(this.userInfo))
        
        return { success: true, data }
      } catch (error) {
        console.error('登录失败:', error)
        return { success: false, error }
      }
    },

    /**
     * 邮箱验证码登录
     */
    async emailLogin(loginForm) {
      try {
        const data = await emailLogin(loginForm)
        
        
        // 保存 token 和用户信息
        this.token = data.token || ''
        this.userInfo = data.user_info || data
        this.isLoggedIn = true
        
        if (this.token) {
          localStorage.setItem('token', this.token)
        }
        localStorage.setItem('userInfo', JSON.stringify(this.userInfo))
        
        return { success: true, data }
      } catch (error) {
        console.error('邮箱登录失败:', error)
        return { success: false, error }
      }
    },

    /**
     * 刷新用户信息
     */
    async refreshUserInfo() {
      const userId = this.userInfo.uuid || this.userInfo.id
      if (!userId) return
      
      try {
        const data = await getUserInfo(userId)
        this.userInfo = data
        localStorage.setItem('userInfo', JSON.stringify(data))
      } catch (error) {
        console.error('刷新用户信息失败:', error)
      }
    },

    /**
     * 退出登录
     */
    logout() {
      this.token = ''
      this.userInfo = {}
      this.isLoggedIn = false
      
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
    }
  }
})

