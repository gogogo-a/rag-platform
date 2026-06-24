export const DEFAULT_MESSAGE_PAGE_SIZE = 10

export const getInitialMessagePage = (total, pageSize = DEFAULT_MESSAGE_PAGE_SIZE) => {
  const totalCount = Number(total || 0)
  const size = Number(pageSize || DEFAULT_MESSAGE_PAGE_SIZE)
  if (totalCount <= 0 || size <= 0) return 1
  return Math.max(1, Math.ceil(totalCount / size))
}

export const getOlderMessagePage = (currentPage) => {
  const page = Number(currentPage || 1)
  return page > 1 ? page - 1 : null
}

export const normalizeChatMessages = (messages = []) => {
  return messages
    .filter((msg) => msg.send_type !== 2)
    .map((msg) => {
      const role = msg.send_type === 0 ? 'user' : 'assistant'
      const processedMsg = {
        ...msg,
        role,
        create_at: msg.send_at || msg.created_at
      }

      if (msg.extra_data) {
        if (msg.extra_data.thoughts && msg.extra_data.thoughts.length > 0) {
          processedMsg.thinking = msg.extra_data.thoughts.join('\n\n')
        }

        if (msg.extra_data.actions && msg.extra_data.actions.length > 0) {
          processedMsg.action = msg.extra_data.actions.join('\n\n')
        }

        if (msg.extra_data.observations && msg.extra_data.observations.length > 0) {
          processedMsg.observation = msg.extra_data.observations.join('\n\n')
        }

        if (msg.extra_data.documents && msg.extra_data.documents.length > 0) {
          processedMsg.documents = msg.extra_data.documents
        }
      }

      return processedMsg
    })
}
