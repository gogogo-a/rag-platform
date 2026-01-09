/**
 * 3D 可视化相关 API
 */

import request from './request'

/**
 * 获取文档 3D 可视化数据
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页数量
 * @param {string} params.keyword - 搜索关键词
 */
export function getDocuments3D(params) {
  return request({
    url: '/visualization/documents/3d',
    method: 'get',
    params
  })
}

/**
 * 刷新 3D 可视化缓存
 */
export function refresh3DCache() {
  return request({
    url: '/visualization/documents/3d/refresh',
    method: 'post'
  })
}
