import request from './request'

export function getPromptList(params) {
  return request({
    url: '/prompts',
    method: 'get',
    params
  })
}

export function getPromptOptions() {
  return request({
    url: '/prompts/options',
    method: 'get'
  })
}

export function updatePrompt(promptUuid, data) {
  return request({
    url: `/prompts/${promptUuid}`,
    method: 'patch',
    data
  })
}

export function activatePrompt(promptUuid) {
  return request({
    url: `/prompts/${promptUuid}/activate`,
    method: 'patch'
  })
}
