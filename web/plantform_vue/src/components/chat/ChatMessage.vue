<template>
  <div class="chat-message" :class="{ 'is-user': isUser, 'is-ai': !isUser }">
    <div class="message-avatar">
      <el-avatar :size="36" :class="{ 'user-avatar': isUser, 'ai-avatar': !isUser }">
        <el-icon><component :is="isUser ? User : Service" /></el-icon>
      </el-avatar>
    </div>

    <div class="message-content">
      <div class="message-header">
        <span class="message-sender">{{ isUser ? '我' : 'AI 助手' }}</span>
        <span class="message-time">{{ formatTime(message.create_at) }}</span>
      </div>

      <div class="message-body">
        <!-- 思考过程 -->
        <div v-if="!isUser && message.thinking" class="thinking-process">
          <div 
            class="thinking-header" 
            :class="{ 'is-active': isThinkingExpanded }"
            @click="toggleThinking"
          >
            <el-icon class="thinking-icon"><MagicStick /></el-icon>
            <span>{{ isThinkingExpanded ? '隐藏思考过程' : '显示思考过程' }}</span>
            <el-icon class="toggle-icon" :class="{ 'is-expanded': isThinkingExpanded }">
              <ArrowDown />
            </el-icon>
          </div>
          <transition name="thinking-expand">
            <div v-show="isThinkingExpanded" class="thinking-content">{{ message.thinking }}</div>
          </transition>
        </div>

        <!-- 观察结果 -->
        <div v-if="!isUser && message.observation" class="observation-process">
          <div 
            class="observation-header" 
            :class="{ 'is-active': isObservationExpanded }"
            @click="toggleObservation"
          >
            <el-icon class="observation-icon"><View /></el-icon>
            <span>{{ isObservationExpanded ? '隐藏观察结果' : '显示观察结果' }}</span>
            <el-icon class="toggle-icon" :class="{ 'is-expanded': isObservationExpanded }">
              <ArrowDown />
            </el-icon>
          </div>
          <transition name="observation-expand">
            <div v-show="isObservationExpanded" class="observation-content">
              <template v-if="isObservationTruncated && !isObservationFullExpanded">
                {{ truncatedObservation }}
                <span class="expand-dots" @click.stop="expandObservationFull">......</span>
              </template>
              <template v-else>
                {{ message.observation }}
              </template>
            </div>
          </transition>
        </div>

        <!-- 操作过程 -->
        <div v-if="!isUser && message.action" class="action-process">
          <div 
            class="action-header" 
            :class="{ 'is-active': isActionExpanded }"
            @click="toggleAction"
          >
            <el-icon class="action-icon"><Tools /></el-icon>
            <span>{{ isActionExpanded ? '隐藏操作过程' : '显示操作过程' }}</span>
            <el-icon class="toggle-icon" :class="{ 'is-expanded': isActionExpanded }">
              <ArrowDown />
            </el-icon>
          </div>
          <transition name="action-expand">
            <div v-show="isActionExpanded" class="action-content">{{ message.action }}</div>
          </transition>
        </div>

        <!-- 用户上传的文件（支持图片预览和文件下载） -->
        <div v-if="isUser && message.file_name" class="uploaded-file">
          <div 
            class="uploaded-file-card" 
            :class="{ 'is-expanded': isFileExpanded, 'is-image': isImageFile }"
          >
            <!-- 图片类型：直接显示预览 -->
            <template v-if="isImageFile && fileUrl">
              <div class="image-preview-container">
                <img 
                  :src="getFullFileUrl(fileUrl)" 
                  :alt="message.file_name"
                  class="image-preview"
                  @click="handleImageClick"
                />
                <div class="image-overlay">
                  <div class="image-info">
                    <el-icon class="file-icon"><Picture /></el-icon>
                    <span class="file-name">{{ message.file_name }}</span>
                    <span class="file-size">{{ formatFileSize(message.file_size) }}</span>
                  </div>
                  <div class="image-actions">
                    <el-button 
                      type="primary" 
                      size="small" 
                      :icon="View"
                      @click.stop="handleImageClick"
                    >
                      查看大图
                    </el-button>
                    <el-button 
                      size="small" 
                      :icon="Download"
                      @click.stop="handleDownloadFile"
                    >
                      下载
                    </el-button>
                  </div>
                </div>
              </div>
            </template>

            <!-- 非图片文件：显示文件卡片 -->
            <template v-else>
              <div class="file-header" @click="toggleFileContent">
                <el-icon class="file-icon"><Document /></el-icon>
                <div class="file-info">
                  <span class="file-name">{{ message.file_name }}</span>
                  <span class="file-size">{{ formatFileSize(message.file_size) }}</span>
                </div>
                <el-button 
                  v-if="fileUrl"
                  size="small" 
                  type="primary"
                  :icon="Download"
                  @click.stop="handleDownloadFile"
                >
                  下载文件
                </el-button>
                <el-icon 
                  v-if="hasFileContent"
                  class="toggle-icon" 
                  :class="{ 'is-expanded': isFileExpanded }"
                >
                  <ArrowDown />
                </el-icon>
              </div>
              <transition name="file-expand">
                <div v-show="isFileExpanded && hasFileContent" class="file-content">
                  <pre>{{ fileContent }}</pre>
                </div>
              </transition>
            </template>
          </div>
        </div>

        <!-- 图片查看对话框 -->
        <el-dialog 
          v-model="imageDialogVisible" 
          :title="message.file_name"
          width="80%"
          class="image-dialog"
        >
          <div class="dialog-image-container">
            <img 
              :src="getFullFileUrl(fileUrl)" 
              :alt="message.file_name"
              class="dialog-image"
            />
          </div>
        </el-dialog>

        <!-- 消息文本 -->
        <div class="message-text" v-html="formatMessage(message.content)"></div>

        <!-- 流式输出动画 -->
        <span v-if="isStreaming" class="cursor-blink">|</span>

        <!-- 引用文档列表 -->
        <div v-if="!isUser && message.documents && message.documents.length > 0" class="documents-list">
          <div class="documents-header">
            <el-icon class="documents-icon"><Document /></el-icon>
            <span>引用文档 ({{ message.documents.length }})</span>
          </div>
          <div class="documents-items">
            <div
              v-for="doc in message.documents"
              :key="doc.uuid"
              class="document-item"
              @click="handleDocumentClick(doc.uuid)"
            >
              <el-icon class="doc-icon"><DocumentCopy /></el-icon>
              <span class="doc-name">{{ doc.name }}</span>
              <el-icon class="doc-arrow"><Right /></el-icon>
            </div>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="message-actions">
        <el-button
          v-if="!isUser"
          text
          size="small"
          :icon="CopyDocument"
          @click="handleCopy"
        >
          复制
        </el-button>
        <!-- 点赞按钮 -->
        <el-button
          v-if="!isUser && thoughtChainId"
          text
          size="small"
          :icon="likeActive ? StarFilled : Star"
          :class="{ 'is-liked': likeActive }"
          @click="handleLike"
          :loading="feedbackLoading"
        >
          {{ likeCount > 0 ? likeCount : '' }} 赞
        </el-button>
        <!-- 踩按钮 -->
        <el-button
          v-if="!isUser && thoughtChainId"
          text
          size="small"
          :icon="dislikeActive ? CircleCloseFilled : CircleClose"
          :class="{ 'is-disliked': dislikeActive }"
          @click="handleDislike"
          :loading="feedbackLoading"
        >
          {{ dislikeCount > 0 ? dislikeCount : '' }} 踩
        </el-button>
        <el-button
          v-if="!isUser"
          text
          size="small"
          :icon="RefreshRight"
          @click="handleRegenerate"
        >
          重新生成
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store'
import { User, Service, CopyDocument, RefreshRight, ArrowDown, MagicStick, Tools, View, Document, DocumentCopy, Right, Picture, Download, Star, StarFilled, CircleClose, CircleCloseFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { submitFeedback } from '@/api/message'

const props = defineProps({
  message: {
    type: Object,
    required: true
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['regenerate'])
const router = useRouter()
const userStore = useUserStore()

const isUser = props.message.role === 'user'
const isThinkingExpanded = ref(true) // 默认展开思考过程
const isObservationExpanded = ref(true) // 默认展开观察结果
const isActionExpanded = ref(true) // 默认展开操作过程
const isObservationFullExpanded = ref(false) // 观察结果是否完全展开

// 观察结果截取逻辑
const MAX_OBSERVATION_LENGTH = 200
const isObservationTruncated = ref(false)
const truncatedObservation = ref('')

// 计算观察结果是否需要截取
const checkObservationTruncation = () => {
  if (props.message.observation && props.message.observation.length > MAX_OBSERVATION_LENGTH) {
    isObservationTruncated.value = true
    truncatedObservation.value = props.message.observation.substring(0, MAX_OBSERVATION_LENGTH)
  } else {
    isObservationTruncated.value = false
    truncatedObservation.value = props.message.observation || ''
  }
}

// 初始化时检查
checkObservationTruncation()

// 切换思考过程展开/折叠
const toggleThinking = () => {
  isThinkingExpanded.value = !isThinkingExpanded.value
}

// 切换观察结果展开/折叠
const toggleObservation = () => {
  isObservationExpanded.value = !isObservationExpanded.value
}

// 切换操作过程展开/折叠
const toggleAction = () => {
  isActionExpanded.value = !isActionExpanded.value
}

// 展开观察结果全部内容
const expandObservationFull = () => {
  isObservationFullExpanded.value = true
}

// 文件展开/折叠
const isFileExpanded = ref(false)
const imageDialogVisible = ref(false)
const isDownloading = ref(false) // 下载状态锁

const toggleFileContent = () => {
  // 只有当有文件内容时才允许展开
  if (hasFileContent.value) {
    isFileExpanded.value = !isFileExpanded.value
  }
}

// 文件URL（从 extra_data 获取）
const fileUrl = computed(() => {
  if (props.message.extra_data && props.message.extra_data.file_url) {
    return props.message.extra_data.file_url
  }
  return null
})

// 文件类型（从 extra_data 或 file_type 获取）
const fileType = computed(() => {
  if (props.message.extra_data && props.message.extra_data.file_type) {
    return props.message.extra_data.file_type.toLowerCase()
  }
  if (props.message.file_type) {
    return props.message.file_type.toLowerCase()
  }
  return ''
})

// 判断是否为图片文件
const isImageFile = computed(() => {
  const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif']
  return imageTypes.includes(fileType.value)
})

// 文件内容（从 extra_data 获取，用于文本文件预览）
const fileContent = computed(() => {
  if (props.message.extra_data && props.message.extra_data.file_content) {
    return props.message.extra_data.file_content
  }
  return '文件内容不可用'
})

// 是否有文件内容可以展开
const hasFileContent = computed(() => {
  return props.message.extra_data && 
         props.message.extra_data.file_content && 
         props.message.extra_data.file_content !== '文件内容不可用'
})

// 获取完整的文件URL（添加API基础路径和token）
const getFullFileUrl = (url) => {
  if (!url) return ''
  
  let fullUrl = url
  
  // 如果不是完整URL，拼接API基础路径
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    fullUrl = `${baseURL}${url}`
  }
  
  // 添加token参数
  const token = userStore.token
  if (token) {
    const separator = fullUrl.includes('?') ? '&' : '?'
    fullUrl = `${fullUrl}${separator}token=${encodeURIComponent(token)}`
  }
  
  return fullUrl
}

// 处理图片点击（显示大图）
const handleImageClick = () => {
  imageDialogVisible.value = true
}

// 处理文件下载
const handleDownloadFile = async () => {
  // 防止重复下载
  if (isDownloading.value) {
    console.log('正在下载中，请勿重复点击')
    return
  }
  
  if (!fileUrl.value) {
    ElMessage.warning('文件链接不可用')
    return
  }
  
  try {
    isDownloading.value = true
    
    // 构建不带 token 的完整 URL（token 通过 headers 传递）
    let fullUrl = fileUrl.value
    if (!fullUrl.startsWith('http://') && !fullUrl.startsWith('https://')) {
      const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
      fullUrl = `${baseURL}${fullUrl}`
    }
    
    // 使用 fetch 下载文件，通过 headers 携带 token
    const response = await fetch(fullUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${userStore.token}`
      }
    })
    
    if (!response.ok) {
      throw new Error(`下载失败: ${response.statusText}`)
    }
    
    // 获取文件 blob
    const blob = await response.blob()
    
    // 创建一个临时的 URL
    const blobUrl = window.URL.createObjectURL(blob)
    
    // 创建一个隐藏的 a 标签来触发下载
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = props.message.file_name || 'download'
    document.body.appendChild(link)
    link.click()
    
    // 清理
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)
    
    // 只在成功下载后显示一次提示
    ElMessage.success('下载成功')
  } catch (error) {
    console.error('下载文件失败:', error)
    ElMessage.error('下载失败: ' + error.message)
  } finally {
    // 释放下载锁
    isDownloading.value = false
  }
}

// 点击文档跳转到详情页
const handleDocumentClick = (uuid) => {
  // 所有用户都跳转到 /documents/:id，组件内部会根据角色显示不同内容
  router.push(`/documents/${uuid}`)
}

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
}

// 格式化消息（支持 Markdown 简单格式）
const formatMessage = (content) => {
  if (!content) return ''
  
  // 简单的 Markdown 格式支持
  return content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // 加粗
    .replace(/\*(.*?)\*/g, '<em>$1</em>') // 斜体
    .replace(/`(.*?)`/g, '<code>$1</code>') // 行内代码
    .replace(/\n/g, '<br>') // 换行
}

// 复制消息
const handleCopy = async () => {
  try {
    await navigator.clipboard.writeText(props.message.content)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    console.error('复制失败:', error)
    ElMessage.error('复制失败')
  }
}

// 重新生成
const handleRegenerate = () => {
  emit('regenerate', props.message)
}

// ========== 反馈功能 ==========

// 从 extra_data 获取 thought_chain_id
const thoughtChainId = computed(() => {
  return props.message.extra_data?.thought_chain_id || null
})

// 反馈状态
const feedbackLoading = ref(false)
const likeActive = ref(false)
const dislikeActive = ref(false)
const likeCount = ref(props.message.extra_data?.like_count || 0)
const dislikeCount = ref(props.message.extra_data?.dislike_count || 0)

// 点赞
const handleLike = async () => {
  if (feedbackLoading.value) return
  
  // 如果没有 thought_chain_id，提示用户
  if (!thoughtChainId.value) {
    ElMessage.info('请稍等，正在处理中...')
    return
  }
  
  feedbackLoading.value = true
  try {
    const result = await submitFeedback(thoughtChainId.value, 'like')
    // 更新计数
    likeCount.value = result.like_count ?? likeCount.value
    dislikeCount.value = result.dislike_count ?? dislikeCount.value
    // 更新状态
    likeActive.value = true
    dislikeActive.value = false
    ElMessage.success('感谢您的反馈！')
  } catch (error) {
    console.error('点赞失败:', error)
    // 如果是重复操作，显示提示
    if (error.message?.includes('已经提交过')) {
      ElMessage.info('您已经点过赞了')
      likeActive.value = true
    }
  } finally {
    feedbackLoading.value = false
  }
}

// 踩
const handleDislike = async () => {
  if (feedbackLoading.value) return
  
  // 如果没有 thought_chain_id，提示用户
  if (!thoughtChainId.value) {
    ElMessage.info('请稍等，正在处理中...')
    return
  }
  
  feedbackLoading.value = true
  try {
    const result = await submitFeedback(thoughtChainId.value, 'dislike')
    // 更新计数
    likeCount.value = result.like_count ?? likeCount.value
    dislikeCount.value = result.dislike_count ?? dislikeCount.value
    // 更新状态
    dislikeActive.value = true
    likeActive.value = false
    
    // 根据缓存状态显示不同提示
    if (result.cache_deleted) {
      // 本次操作删除了缓存
      ElMessage.warning('该回答已从缓存中移除')
    } else {
      ElMessage.success('感谢您的反馈！')
    }
  } catch (error) {
    console.error('踩失败:', error)
    // 如果是重复操作，显示提示
    if (error.message?.includes('已经提交过')) {
      ElMessage.info('您已经反馈过了')
      dislikeActive.value = true
    }
  } finally {
    feedbackLoading.value = false
  }
}
</script>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 16px;
  animation: slideInUp 0.3s ease-out;
}

.chat-message.is-user {
  background: rgba(99, 102, 241, 0.05);
}

.chat-message.is-ai:hover {
  background: rgba(255, 255, 255, 0.02);
}

.message-avatar {
  flex-shrink: 0;
}

.user-avatar {
  background: var(--primary-color);
}

.ai-avatar {
  background: linear-gradient(135deg, var(--neon-purple), var(--neon-blue));
}

.message-content {
  flex: 1;
  min-width: 0;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.message-sender {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.message-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.message-body {
  margin-bottom: 8px;
}

.thinking-process {
  background: rgba(168, 85, 247, 0.1);
  border-left: 3px solid var(--neon-purple);
  padding: 8px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--neon-purple);
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  padding: 8px 12px;
  border-radius: 6px;
  background: transparent;
}

.thinking-header:hover {
  color: var(--neon-blue);
}

.thinking-header.is-active {
  background: rgba(168, 85, 247, 0.15);
}

.thinking-icon {
  font-size: 16px;
}

.toggle-icon {
  margin-left: auto;
  font-size: 14px;
  transition: transform 0.3s ease;
}

.toggle-icon.is-expanded {
  transform: rotate(180deg);
}

.thinking-content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 4px;
  padding: 4px 12px;
}

/* 思考过程展开/折叠动画 */
.thinking-expand-enter-active,
.thinking-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.thinking-expand-enter-from,
.thinking-expand-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
}

.thinking-expand-enter-to,
.thinking-expand-leave-from {
  max-height: 500px;
  opacity: 1;
  margin-top: 8px;
}

/* 操作过程样式 */
.action-process {
  background: rgba(59, 130, 246, 0.1);
  border-left: 3px solid var(--neon-blue);
  padding: 8px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.action-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--neon-blue);
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  padding: 8px 12px;
  border-radius: 6px;
  background: transparent;
}

.action-header:hover {
  color: var(--primary-color);
}

.action-header.is-active {
  background: rgba(59, 130, 246, 0.15);
}

.action-icon {
  font-size: 16px;
}

.action-content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 4px;
  padding: 4px 12px;
  font-family: 'Courier New', monospace;
}

/* 操作过程展开/折叠动画 */
.action-expand-enter-active,
.action-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.action-expand-enter-from,
.action-expand-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
}

.action-expand-enter-to,
.action-expand-leave-from {
  max-height: 500px;
  opacity: 1;
  margin-top: 8px;
}

/* 观察结果样式 */
.observation-process {
  background: rgba(16, 185, 129, 0.1);
  border-left: 3px solid #10b981;
  padding: 8px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.observation-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #10b981;
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  padding: 8px 12px;
  border-radius: 6px;
  background: transparent;
}

.observation-header:hover {
  color: #34d399;
}

.observation-header.is-active {
  background: rgba(16, 185, 129, 0.15);
}

.observation-icon {
  font-size: 16px;
}

.observation-content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 4px;
  padding: 4px 12px;
  white-space: pre-wrap;
}

.expand-dots {
  color: #10b981;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  padding: 2px 4px;
  border-radius: 4px;
  display: inline-block;
}

.expand-dots:hover {
  color: #34d399;
  background: rgba(16, 185, 129, 0.1);
}

/* 观察结果展开/折叠动画 */
.observation-expand-enter-active,
.observation-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.observation-expand-enter-from,
.observation-expand-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
}

.observation-expand-enter-to,
.observation-expand-leave-from {
  max-height: 500px;
  opacity: 1;
  margin-top: 8px;
}

/* 用户上传的文件样式 */
.uploaded-file {
  margin-bottom: 12px;
}

.uploaded-file-card {
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px;
  transition: all 0.3s ease;
  overflow: hidden;
}

.uploaded-file-card:not(.is-image) {
  cursor: pointer;
}

.uploaded-file-card:not(.is-image):hover {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.3);
}

.uploaded-file-card.is-expanded {
  background: rgba(99, 102, 241, 0.12);
}

/* 图片预览容器 */
.image-preview-container {
  position: relative;
  width: 100%;
  max-width: 400px;
  border-radius: 8px;
  overflow: hidden;
}

.image-preview {
  width: 100%;
  height: auto;
  display: block;
  cursor: pointer;
  transition: transform 0.3s ease;
}

.image-preview:hover {
  transform: scale(1.02);
}

.image-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
  padding: 16px 12px;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.image-preview-container:hover .image-overlay {
  opacity: 1;
}

.image-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.image-info .file-icon {
  font-size: 18px;
  color: var(--neon-purple);
}

.image-info .file-name {
  flex: 1;
  font-size: 13px;
  color: #fff;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-info .file-size {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.image-actions {
  display: flex;
  gap: 8px;
}

/* 普通文件样式 */
.file-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
}

.file-header .file-icon {
  font-size: 20px;
  color: var(--neon-purple);
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-info .file-name {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-info .file-size {
  font-size: 12px;
  color: var(--text-tertiary);
}

.file-header .toggle-icon {
  font-size: 16px;
  color: var(--neon-purple);
  transition: transform 0.3s ease;
  flex-shrink: 0;
  margin-left: 8px;
}

.file-header .toggle-icon.is-expanded {
  transform: rotate(180deg);
}

.file-content {
  max-height: 400px;
  overflow-y: auto;
  padding: 12px 14px;
  border-top: 1px solid rgba(99, 102, 241, 0.2);
  background: rgba(0, 0, 0, 0.2);
}

.file-content pre {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  font-family: 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 文件展开/折叠动画 */
.file-expand-enter-active,
.file-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.file-expand-enter-from,
.file-expand-leave-to {
  max-height: 0;
  opacity: 0;
}

.file-expand-enter-to,
.file-expand-leave-from {
  max-height: 400px;
  opacity: 1;
}

/* 图片查看对话框 */
.dialog-image-container {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  background: var(--bg-primary);
}

.dialog-image {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 8px;
}

/* 对话框深色样式 */
:deep(.image-dialog .el-dialog) {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
}

:deep(.image-dialog .el-dialog__header) {
  border-bottom: 1px solid var(--border-color);
}

:deep(.image-dialog .el-dialog__title) {
  color: var(--text-primary);
  font-weight: 600;
}

:deep(.image-dialog .el-dialog__close) {
  color: var(--text-tertiary);
}

:deep(.image-dialog .el-dialog__close:hover) {
  color: var(--primary-color);
}

.documents-list {
  margin-top: 16px;
  padding: 12px;
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px;
}

.documents-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-color);
  margin-bottom: 8px;
}

.documents-icon {
  font-size: 16px;
}

.documents-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.document-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.document-item:hover {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.3);
  transform: translateX(4px);
}

.doc-icon {
  font-size: 16px;
  color: var(--primary-color);
  flex-shrink: 0;
}

.doc-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-arrow {
  font-size: 14px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  transition: transform 0.3s ease;
}

.document-item:hover .doc-arrow {
  transform: translateX(4px);
  color: var(--primary-color);
}

.message-text {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.8;
  word-wrap: break-word;
}

.message-text :deep(strong) {
  font-weight: 600;
  color: var(--neon-blue);
}

.message-text :deep(em) {
  font-style: italic;
  color: var(--text-secondary);
}

.message-text :deep(code) {
  background: rgba(99, 102, 241, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--neon-blue);
}

.cursor-blink {
  display: inline-block;
  width: 8px;
  height: 16px;
  margin-left: 2px;
  background: var(--neon-blue);
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.message-actions {
  display: flex;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.chat-message:hover .message-actions {
  opacity: 1;
}

.message-actions .el-button {
  color: var(--text-tertiary);
}

.message-actions .el-button:hover {
  color: var(--primary-color);
}

/* 点赞/踩按钮样式 */
.message-actions .el-button.is-liked {
  color: #f59e0b;
}

.message-actions .el-button.is-liked:hover {
  color: #fbbf24;
}

.message-actions .el-button.is-disliked {
  color: #ef4444;
}

.message-actions .el-button.is-disliked:hover {
  color: #f87171;
}
</style>


