/**
 * 文档相关 API
 */

import request from './request'

/**
 * 上传文档
 */
export function uploadDocument(formData) {
  return request({
    url: '/documents',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    timeout: 60000 // 上传超时时间设置为 60 秒
  })
}

/**
 * 获取文档列表
 */
export function getDocumentList(params) {
  return request({
    url: '/documents',
    method: 'get',
    params
  })
}

/**
 * 获取文档详情
 */
export function getDocumentDetail(documentId) {
  return request({
    url: `/documents/${documentId}`,
    method: 'get'
  })
}

/**
 * 重新处理文档
 */
export function retryDocumentProcessing(documentId) {
  return request({
    url: `/documents/${documentId}/retry`,
    method: 'post'
  })
}

/**
 * 删除文档
 */
export function deleteDocument(documentId) {
  return request({
    url: `/documents/${documentId}`,
    method: 'delete'
  })
}
