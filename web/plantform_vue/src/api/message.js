/**
 * 消息相关 API
 */

import request from './request'

/**
 * 获取会话的消息列表
 */
export function getMessageList(sessionId, params) {
  return request({
    url: `/messages/${sessionId}`,
    method: 'get',
    params
  })
}

/**
 * 发送消息（流式）
 * 使用 Server-Sent Events (SSE)
 * @param {Object|FormData} data - 消息数据或 FormData
 * @param {Boolean} isFormData - 是否为 FormData
 */
export function sendMessageStream(data, isFormData = false) {
  const token = localStorage.getItem('token')
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
  
  const headers = {
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
  
  // 如果不是 FormData，则添加 Content-Type
  if (!isFormData) {
    headers['Content-Type'] = 'application/json'
  }
  
  // SSE 不使用 axios，使用原生 fetch
  return fetch(`${baseURL}/messages`, {
    method: 'POST',
    headers: headers,
    body: isFormData ? data : JSON.stringify(data)
  })
}

/**
 * 发送消息（非流式，备用）
 */
export function sendMessage(data) {
  return request({
    url: '/messages',
    method: 'post',
    data
  })
}

/**
 * 提交消息反馈（点赞/踩）
 * @param {String} thoughtChainId - 思维链ID
 * @param {String} feedbackType - 反馈类型：like 或 dislike
 */
export function submitFeedback(thoughtChainId, feedbackType) {
  const formData = new FormData()
  formData.append('thought_chain_id', thoughtChainId)
  formData.append('feedback_type', feedbackType)
  
  return request({
    url: '/messages/feedback',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 删除 QA 缓存
 * @param {String} thoughtChainId - 思维链ID
 */
export function deleteQACache(thoughtChainId) {
  return request({
    url: `/messages/cache/${thoughtChainId}`,
    method: 'delete'
  })
}

/**
 * 发送消息（流式，支持重新生成）
 * @param {Object|FormData} data - 消息数据或 FormData
 * @param {Boolean} isFormData - 是否为 FormData
 * @param {Object} options - 额外选项
 * @param {Boolean} options.skipCache - 是否跳过缓存
 * @param {String} options.regenerateMessageId - 重新生成时的原消息ID
 */
export function sendMessageStreamWithOptions(data, isFormData = false, options = {}) {
  const token = localStorage.getItem('token')
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
  
  const headers = {
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
  
  // 处理 FormData
  let body
  if (isFormData) {
    // 添加额外选项到 FormData
    if (options.skipCache) {
      data.append('skip_cache', 'true')
    }
    if (options.regenerateMessageId) {
      data.append('regenerate_message_id', options.regenerateMessageId)
    }
    body = data
  } else {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify({
      ...data,
      skip_cache: options.skipCache ? 'true' : 'false',
      regenerate_message_id: options.regenerateMessageId || null
    })
  }
  
  return fetch(`${baseURL}/messages`, {
    method: 'POST',
    headers: headers,
    body: body
  })
}

