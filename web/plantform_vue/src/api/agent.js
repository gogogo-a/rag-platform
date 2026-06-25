import request from './request'

export function getAgentList(params) {
  return request({
    url: '/agents',
    method: 'get',
    params
  })
}

export function getAgentOptions() {
  return request({
    url: '/agents/options',
    method: 'get'
  })
}

export function createAgent(data) {
  return request({
    url: '/agents',
    method: 'post',
    data
  })
}

export function updateAgent(agentUuid, data) {
  return request({
    url: `/agents/${agentUuid}`,
    method: 'patch',
    data
  })
}

export function setAgentEnabled(agentUuid, enabled) {
  return request({
    url: `/agents/${agentUuid}/enable`,
    method: 'patch',
    data: { enabled }
  })
}
