import request from './request'

export function getEvaluationList(params) {
  return request({
    url: '/evaluations',
    method: 'get',
    params
  })
}

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

export function getEvaluationCases(params) {
  return request({
    url: '/evaluations/cases',
    method: 'get',
    params
  })
}

export function runEvaluationCase(caseId, data = {}) {
  return request({
    url: `/evaluations/cases/${caseId}/run`,
    method: 'post',
    data
  })
}

export function getEvaluationCaseResults(caseId) {
  return request({
    url: `/evaluations/cases/${caseId}/results`,
    method: 'get'
  })
}
