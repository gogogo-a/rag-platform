/**
 * QA 缓存管理 API
 */

import request from './request'

/**
 * 获取 QA 缓存列表（管理后台）
 */
export const getQACacheListAdmin = (params) => {
  return request({
    url: '/qa-cache',
    method: 'get',
    params
  })
}

/**
 * 获取 QA 缓存详情（管理后台）
 */
export const getQACacheDetailAdmin = (cacheId) => {
  return request({
    url: `/qa-cache/${cacheId}`,
    method: 'get'
  })
}

/**
 * 删除 QA 缓存（管理后台）
 */
export const deleteQACacheAdmin = (cacheId) => {
  return request({
    url: `/qa-cache/${cacheId}`,
    method: 'delete'
  })
}

/**
 * 获取 QA 缓存 3D 数据
 */
export const getQACache3D = (params) => {
  return request({
    url: '/visualization/qa-cache/3d',
    method: 'get',
    params
  })
}

/**
 * 刷新 QA 缓存 3D 缓存
 */
export const refreshQACache3D = () => {
  return request({
    url: '/visualization/qa-cache/3d/refresh',
    method: 'post'
  })
}
