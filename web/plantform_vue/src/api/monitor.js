import request from './request'

/**
 * 获取性能监控数据
 * @param {string} monitorType - 监控类型（embedding, vector_search, llm_think, llm_action, llm_answer, llm_total, agent_total）
 * @param {string} date - 日期（格式：YYYY-MM-DD）
 * @param {number} limit - 每页数量
 * @param {number} offset - 偏移量
 */
export function getPerformanceMonitor(monitorType, date = null, limit = 100, offset = 0) {
  return request({
    url: `/monitors/performance/${monitorType}`,
    method: 'get',
    params: { date, limit, offset }
  })
}

/**
 * 获取资源监控数据
 * @param {string} date - 日期（格式：YYYY-MM-DD）
 * @param {number} limit - 每页数量
 * @param {number} offset - 偏移量
 */
export function getResourceMonitor(date = null, limit = 100, offset = 0) {
  return request({
    url: '/monitors/resource',
    method: 'get',
    params: { date, limit, offset }
  })
}

/**
 * 获取所有监控数据（概览）
 * @param {string} date - 日期（格式：YYYY-MM-DD）
 * @param {number} limit - 每种类型返回的记录数
 */
export function getAllMonitors(date = null, limit = 10) {
  return request({
    url: '/monitors/all',
    method: 'get',
    params: { date, limit }
  })
}

/**
 * 获取可用的监控日期
 */
export function getAvailableMonitorDates() {
  return request({
    url: '/monitors/dates',
    method: 'get'
  })
}

/**
 * 获取所有监控类型
 */
export function getMonitorTypes() {
  return request({
    url: '/monitors/types',
    method: 'get'
  })
}

/**
 * 获取监控统计信息
 */
export function getMonitorStatistics() {
  return request({
    url: '/monitors/statistics',
    method: 'get'
  })
}

