import request from './request'

export function getRAGEvaluationList(params) {
  return request({
    url: '/evaluations/rag',
    method: 'get',
    params
  })
}

export function getRAGEvaluationConfig() {
  return request({
    url: '/evaluations/rag/config',
    method: 'get'
  })
}

export function updateRAGEvaluationConfig(data) {
  return request({
    url: '/evaluations/rag/config',
    method: 'patch',
    data
  })
}

export function requeueRAGEvaluation(evaluationId) {
  return request({
    url: `/evaluations/rag/${evaluationId}/requeue`,
    method: 'post'
  })
}
