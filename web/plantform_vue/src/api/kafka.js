import request from './request'

export function getKafkaTopics() {
  return request({
    url: '/kafka/topics',
    method: 'get'
  })
}

export function getKafkaMessages(params) {
  return request({
    url: '/kafka/messages',
    method: 'get',
    params
  })
}

export function getKafkaMessageDetail(params) {
  return request({
    url: '/kafka/messages/detail',
    method: 'get',
    params
  })
}
