/**
 * 会话相关 API
 */

import request from './request'

/**
 * 获取会话列表
 */
export function getSessionList(params) {
  return request({
    url: '/sessions',
    method: 'get',
    params
  })
}

/**
 * 获取会话详情
 */
export function getSessionDetail(sessionId) {
  return request({
    url: `/sessions/${sessionId}`,
    method: 'get'
  })
}

/**
 * 更新会话
 */
export function updateSession(sessionId, data) {
  return request({
    url: `/sessions/${sessionId}`,
    method: 'patch',
    data
  })
}

/**
 * 删除会话
 */
export function deleteSession(sessionId) {
  return request({
    url: `/sessions/${sessionId}`,
    method: 'delete'
  })
}

