<template>
  <div 
    class="message-input"
    :class="{ 'is-dragging': isDragging }"
    @drop.prevent="handleDrop"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @dragenter.prevent="handleDragEnter"
  >
    <!-- 拖拽提示遮罩 -->
    <div v-if="isDragging" class="drag-overlay">
      <div class="drag-hint">
        <el-icon class="drag-icon"><Upload /></el-icon>
        <p>释放以上传文件或图片</p>
      </div>
    </div>

    <div class="input-toolbar">
      <el-segmented
        v-model="selectedAgentMode"
        :options="agentModeOptions"
        size="small"
        class="agent-mode-toggle"
      />

      <el-button
        text
        :icon="showThinking ? View : Hide"
        @click="handleToggleThinking"
        size="small"
        :class="{ 'thinking-active': showThinking }"
        class="toolbar-button thinking-button"
      >
        {{ showThinking ? '隐藏过程' : '显示过程' }}
      </el-button>

      <el-button text :icon="Upload" size="small" class="toolbar-button upload-button" @click="handleSelectFile">
        上传文件
      </el-button>
      <input
        ref="fileInputRef"
        type="file"
        accept=".pdf,.docx,.pptx,.doc,.ppt,.txt,.md,.xlsx,.csv,.html,.rtf,.epub,.json,.xml,.jpg,.jpeg,.png,.webp,.gif,.bmp,.tiff,.tif"
        style="display: none"
        @change="handleFileChange"
      />
    </div>

    <div class="input-container">
      <el-input
        ref="textareaRef"
        v-model="inputMessage"
        type="textarea"
        :rows="2"
        placeholder="输入您的问题..."
        :disabled="isSending"
        @keydown.enter="handleKeyDown"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @paste="handlePaste"
        class="message-textarea"
      />
      
      <el-button
        type="primary"
        :icon="isSending ? VideoPause : Promotion"
        @click="isSending ? handlePause() : handleSend()"
        :disabled="!inputMessage.trim() && !isSending"
        class="send-button"
        :class="{ 'is-pausing': isSending }"
        size="large"
      >
        {{ isSending ? '暂停' : '发送' }}
      </el-button>
    </div>

    <!-- 已上传文件列表 -->
    <div v-if="uploadedFiles.length > 0" class="uploaded-files">
      <div
        v-for="(file, index) in uploadedFiles"
        :key="index"
        class="file-item"
      >
        <el-icon class="file-icon"><Document /></el-icon>
        <span class="file-name">{{ file.name }}</span>
        <el-icon class="remove-icon" @click="handleRemoveFile(index)"><Close /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useUserStore, useChatStore } from '@/store'
import { Upload, Promotion, VideoPause, Document, Close, View, Hide } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const emit = defineEmits(['send', 'pause'])
const props = defineProps({
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const userStore = useUserStore()
const chatStore = useChatStore()

const inputMessage = ref('')
const isPreparing = ref(false)
const uploadedFiles = ref([]) // 暂存的文件列表
const fileInputRef = ref(null)
const textareaRef = ref(null)
const isDragging = ref(false) // 拖拽状态
const userLocation = ref(null) // 用户位置信息
const isComposing = ref(false) // 输入法状态（是否正在输入中文）
const showThinking = computed(() => chatStore.showThinking)
const isSending = computed(() => isPreparing.value || props.isStreaming)
const selectedAgentMode = computed({
  get: () => chatStore.agentMode,
  set: (mode) => chatStore.setAgentMode(mode)
})
const agentModeOptions = [
  { label: '普通模式', value: 'single' },
  { label: '专家模式', value: 'expert' }
]

// 获取用户位置信息
const getUserLocation = () => {
  return new Promise((resolve) => {
    // 检查浏览器是否支持地理位置
    if (!navigator.geolocation) {
      resolve(null)
      return
    }
    
    // 获取位置信息，设置超时时间为 5 秒
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const locationData = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          timestamp: new Date(position.timestamp).toISOString()
        }
        resolve(locationData)
      },
      () => {
        // 即使失败也不影响消息发送
        resolve(null)
      },
      {
        enableHighAccuracy: true, // 高精度模式
        timeout: 5000, // 5秒超时
        maximumAge: 60000 // 使用1分钟内的缓存位置
      }
    )
  })
}

const handleToggleThinking = () => {
  chatStore.toggleShowThinking()
}

// 选择文件
const handleSelectFile = () => {
  fileInputRef.value?.click()
}

// 文件选择变化
const handleFileChange = (event) => {
  const file = event.target.files[0]
  if (!file) return
  
  // 使用统一的验证函数
  validateAndAddFile(file)
  
  // 清空 input，以便可以再次选择相同文件
  event.target.value = ''
}

// 输入法开始（开始输入拼音）
const handleCompositionStart = () => {
  isComposing.value = true
}

// 输入法结束（确认输入中文）
const handleCompositionEnd = () => {
  isComposing.value = false
}

// 键盘事件处理
const handleKeyDown = (event) => {
  // 如果正在输入法中（输入拼音），不处理 Enter 键
  if (event.isComposing || isComposing.value) {
    return
  }
  
  // Shift + Enter: 换行
  if (event.shiftKey) {
    return
  }
  
  // Enter: 发送消息
  event.preventDefault()
  if (inputMessage.value.trim() && !isSending.value) {
    handleSend()
  }
}

const handlePause = () => {
  if (!isSending.value) return
  emit('pause')
}

// 发送消息
const handleSend = async () => {
  if (!inputMessage.value.trim() || isSending.value) return

  const message = inputMessage.value.trim()
  const files = [...uploadedFiles.value] // 复制文件列表
  
  inputMessage.value = ''
  uploadedFiles.value = [] // 清空文件列表
  isPreparing.value = true

  try {
    // 获取位置信息（异步，不阻塞消息发送）
    const location = await getUserLocation()
    
    emit('send', {
      content: message,
      showThinking: chatStore.showThinking,
      agentMode: chatStore.agentMode,
      files: files, // 传递文件列表
      location: location // 传递位置信息
    })
  } catch (error) {
    ElMessage.error('发送失败，请重试')
  } finally {
    isPreparing.value = false
  }
}

// 移除文件
const handleRemoveFile = (index) => {
  uploadedFiles.value.splice(index, 1)
  ElMessage.success('文件已移除')
}

// 验证并添加文件的通用函数
const validateAndAddFile = (file) => {
  // 验证文件类型（移除大小限制）
  const allowedTypes = [
    // 文档类型
    'application/pdf',                                                                      // PDF
    'application/msword',                                                                   // DOC
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',            // DOCX
    'application/vnd.ms-powerpoint',                                                       // PPT
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',          // PPTX
    'application/vnd.ms-excel',                                                            // XLS
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',                  // XLSX
    'text/plain',                                                                          // TXT
    'text/markdown',                                                                       // MD
    'text/csv',                                                                            // CSV
    'text/html',                                                                           // HTML
    'application/rtf',                                                                     // RTF
    'application/epub+zip',                                                                // EPUB
    'application/json',                                                                    // JSON
    'application/xml',                                                                     // XML
    'text/xml',                                                                            // XML (alternative)
    // 图片类型
    'image/jpeg',                                                                          // JPG/JPEG
    'image/png',                                                                           // PNG
    'image/webp',                                                                          // WEBP
    'image/gif',                                                                           // GIF
    'image/bmp',                                                                           // BMP
    'image/tiff'                                                                           // TIFF/TIF
  ]
  
  const allowedExtensions = [
    '.pdf', '.docx', '.pptx', '.doc', '.ppt', '.txt', '.md', '.xlsx', '.csv', 
    '.html', '.rtf', '.epub', '.json', '.xml',
    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.tif'
  ]
  
  // 验证文件类型（通过 MIME 类型或文件扩展名）
  const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  const isValidType = allowedTypes.includes(file.type) || allowedExtensions.includes(fileExtension)
  
  if (!isValidType) {
    ElMessage.error('支持的格式：PDF、Word、PPT、Excel、TXT、Markdown、HTML、EPUB、JSON、XML、图片（JPG/PNG/GIF/WEBP等）')
    return false
  }
  
  // 添加文件到列表
  uploadedFiles.value.push({
    name: file.name,
    size: file.size,
    type: file.type,
    file: file // 保存原始文件对象
  })
  
  ElMessage.success(`文件 ${file.name} 已添加`)
  return true
}

// 粘贴事件处理
const handlePaste = (event) => {
  const items = event.clipboardData?.items
  if (!items) return
  
  // 查找粘贴的文件（特别是图片）
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    
    // 如果是图片类型
    if (item.type.indexOf('image') !== -1) {
      event.preventDefault() // 阻止默认粘贴行为
      
      const file = item.getAsFile()
      if (file) {
        // 为粘贴的图片生成文件名
        const timestamp = new Date().getTime()
        const extension = file.type.split('/')[1] || 'png'
        const renamedFile = new File([file], `pasted-image-${timestamp}.${extension}`, { type: file.type })
        
        validateAndAddFile(renamedFile)
      }
      break
    }
  }
}

// 拖拽进入
const handleDragEnter = (event) => {
  isDragging.value = true
}

// 拖拽经过
const handleDragOver = (event) => {
  isDragging.value = true
}

// 拖拽离开
const handleDragLeave = (event) => {
  // 只有当离开整个 message-input 区域时才取消拖拽状态
  if (event.target.className === 'message-input' || event.target.classList.contains('message-input')) {
    isDragging.value = false
  }
}

// 拖拽释放
const handleDrop = (event) => {
  isDragging.value = false
  
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  
  // 处理拖拽的文件（只处理第一个文件）
  const file = files[0]
  validateAndAddFile(file)
}

// 暴露方法给父组件
defineExpose({
  isSending
})
</script>

<style scoped>
.message-input {
  position: relative;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-color);
  padding: 8px 14px 10px;
  transition: all 0.3s ease;
}

.message-input.is-dragging {
  background: rgba(99, 102, 241, 0.05);
  border-top-color: var(--primary-color);
}

/* 拖拽提示遮罩 */
.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(99, 102, 241, 0.1);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  border: 2px dashed var(--primary-color);
  border-radius: 8px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    border-color: var(--primary-color);
    background: rgba(99, 102, 241, 0.1);
  }
  50% {
    border-color: var(--neon-purple);
    background: rgba(168, 85, 247, 0.15);
  }
}

.drag-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px;
  background: var(--component-bg);
  border-radius: 12px;
  border: 1px solid var(--primary-color);
}

.drag-icon {
  font-size: 48px;
  color: var(--primary-color);
  animation: bounce 1s ease-in-out infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.drag-hint p {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.input-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.toolbar-button {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-color) !important;
  border-radius: 8px;
  background: var(--bg-tertiary) !important;
  color: var(--text-secondary) !important;
  font-size: 13px;
  font-weight: 500;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.toolbar-button:hover {
  border-color: rgba(129, 140, 248, 0.45) !important;
  background: rgba(99, 102, 241, 0.12) !important;
  color: var(--text-primary) !important;
}

.toolbar-button :deep(.el-icon) {
  font-size: 14px;
}

.agent-mode-toggle {
  --el-segmented-bg-color: var(--bg-tertiary);
  --el-segmented-item-selected-bg-color: rgba(99, 102, 241, 0.22);
  --el-segmented-item-selected-color: var(--primary-hover);
  --el-segmented-item-hover-bg-color: rgba(99, 102, 241, 0.12);
  --el-border-radius-base: 6px;
  padding: 2px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-tertiary);
  height: 30px;
}

.agent-mode-toggle :deep(.el-segmented__item) {
  min-width: 72px;
  height: 24px;
  padding: 0 10px;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.agent-mode-toggle :deep(.el-segmented__item-label) {
  font-size: 13px;
  line-height: 24px;
  font-weight: 500;
}

.agent-mode-toggle :deep(.el-segmented__item-selected) {
  color: var(--text-primary);
  box-shadow: inset 0 0 0 1px rgba(129, 140, 248, 0.35);
}

.thinking-button {
  min-width: 78px;
}

.thinking-button.thinking-active {
  border-color: rgba(129, 140, 248, 0.45) !important;
  background: rgba(99, 102, 241, 0.22) !important;
  color: var(--text-primary) !important;
}

.thinking-button.thinking-active:hover {
  background: rgba(99, 102, 241, 0.28) !important;
}

.input-container {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.message-textarea {
  flex: 1;
}

.message-textarea :deep(.el-textarea__inner) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.5;
  min-height: 54px !important;
  resize: none;
  transition: all 0.3s ease;
}

.message-textarea :deep(.el-textarea__inner):focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
}

.send-button {
  height: 42px;
  padding: 0 24px;
  border-radius: 21px;
  font-weight: 600;
  background: linear-gradient(135deg, var(--neon-purple), var(--neon-blue));
  border: none;
  transition: all 0.3s ease;
}

.send-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.uploaded-files {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.file-icon {
  color: var(--primary-color);
  font-size: 16px;
}

.file-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-icon {
  cursor: pointer;
  color: var(--text-tertiary);
  font-size: 14px;
  transition: color 0.3s ease;
}

.remove-icon:hover {
  color: var(--danger-color);
}
</style>
