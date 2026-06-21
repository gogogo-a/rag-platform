<template>
  <div class="document-detail">
    <div class="detail-header">
      <el-button class="back-button" :icon="ArrowLeft" @click="goBack">返回</el-button>
      <h2 class="page-title">文档详情</h2>
      <div class="header-actions">
        <!-- 所有用户都可以下载 -->
        <el-button 
          type="primary" 
          :icon="Download" 
          @click="handleDownload"
          :loading="isDownloading"
          :disabled="!document || !document.url"
        >
          {{ isDownloading ? '下载中...' : '下载文档' }}
        </el-button>
        <!-- 只有管理员可以删除 -->
        <el-button 
          v-if="isAdmin"
          type="danger" 
          :icon="Delete" 
          @click="handleDelete"
        >
          删除文档
        </el-button>
      </div>
    </div>

    <div class="detail-content" v-loading="loading">
      <div v-if="document" class="document-info">
        <!-- 基本信息卡片 -->
        <div class="info-card" v-if="isAdmin">
          <div class="card-header">
            <el-icon class="header-icon"><Document /></el-icon>
            <h3>基本信息</h3>
          </div>
          <div class="card-body">
            <div class="info-item">
              <span class="label">文档 ID：</span>
              <span class="value">{{ document.uuid }}</span>
            </div>
            <div class="info-item">
              <span class="label">文件名：</span>
              <span class="value">{{ document.name }}</span>
            </div>
            <div class="info-item">
              <span class="label">文件大小：</span>
              <span class="value">{{ formatFileSize(document.size) }}</span>
            </div>
            <div class="info-item">
              <span class="label">页数：</span>
              <span class="value">{{ document.page || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="label">访问权限：</span>
              <span class="value">
                <el-tag v-if="document.permission === 1" type="warning" size="small">
                  <el-icon style="margin-right: 4px;"><Lock /></el-icon>
                  仅管理员可见
                </el-tag>
                <el-tag v-else type="success" size="small">
                  <el-icon style="margin-right: 4px;"><User /></el-icon>
                  所有用户和管理员可见
                </el-tag>
              </span>
            </div>
            <div class="info-item">
              <span class="label">上传时间：</span>
              <span class="value">{{ formatDate(document.uploaded_at) }}</span>
            </div>
            <div class="info-item" v-if="document.updated_at">
              <span class="label">更新时间：</span>
              <span class="value">{{ formatDate(document.updated_at) }}</span>
            </div>
            <div class="info-item">
              <span class="label">文本块数量：</span>
              <span class="value">{{ document.chunk_count || 0 }}</span>
            </div>
            <div class="info-item">
              <span class="label">内容长度：</span>
              <span class="value">{{ document.content_length || 0 }} 字符</span>
            </div>
            <!-- <div class="info-item">
              <span class="label">文档 URL：</span>
              <span class="value">
                <a :href="document.url" target="_blank" class="document-link">
                  {{ document.url }}
                  <el-icon><Link /></el-icon>
                </a>
              </span>
            </div> -->
          </div>
        </div>

        <!-- 处理状态卡片 -->
        <div class="info-card" v-if="isAdmin">
          <div class="card-header">
            <el-icon class="header-icon"><Operation /></el-icon>
            <h3>处理状态</h3>
          </div>
          <div class="card-body">
            <div class="status-info">
              <el-tag 
                :type="getStatusType(document.status)"
                size="large"
              >
                {{ document.status_text || '未知' }}
              </el-tag>
              <p class="status-desc">
                {{ getStatusDescription(document.status, document.chunk_count) }}
              </p>
            </div>
          </div>
        </div>

        <!-- 上传者信息卡片 -->
        <div class="info-card" v-if="isAdmin && document.extra_data">
          <div class="card-header">
            <el-icon class="header-icon"><User /></el-icon>
            <h3>上传者信息</h3>
          </div>
          <div class="card-body">
            <div class="info-item" v-if="document.extra_data.uploader_name">
              <span class="label">上传者：</span>
              <span class="value">{{ document.extra_data.uploader_name }}</span>
            </div>
            <div class="info-item" v-if="document.extra_data.uploader_id">
              <span class="label">上传者 ID：</span>
              <span class="value">{{ document.extra_data.uploader_id }}</span>
            </div>
            <div class="info-item" v-if="document.extra_data.upload_time">
              <span class="label">上传时间：</span>
              <span class="value">{{ formatDate(document.extra_data.upload_time) }}</span>
            </div>
            <div class="info-item" v-if="document.extra_data.file_extension">
              <span class="label">文件类型：</span>
              <span class="value">{{ document.extra_data.file_extension }}</span>
            </div>
            <div class="info-item" v-if="document.extra_data.processing_time">
              <span class="label">处理耗时：</span>
              <span class="value">{{ formatDuration(document.extra_data.processing_time) }}</span>
            </div>
            <div class="info-item" v-if="document.extra_data.embedding_model">
              <span class="label">Embedding 模型：</span>
              <span class="value">{{ document.extra_data.embedding_model }}</span>
            </div>
            <div class="info-item" v-if="document.extra_data.chunk_size">
              <span class="label">分块大小：</span>
              <span class="value">{{ document.extra_data.chunk_size }} 字符</span>
            </div>
            <div class="info-item" v-if="document.extra_data.chunk_overlap">
              <span class="label">分块重叠：</span>
              <span class="value">{{ document.extra_data.chunk_overlap }} 字符</span>
            </div>
          </div>
        </div>

        <!-- 访问权限卡片（所有用户可见） -->
        <div class="info-card" v-if="isAdmin">
          <div class="card-header">
            <el-icon class="header-icon"><Lock /></el-icon>
            <h3>文档信息</h3>
          </div>
          <div class="card-body">
            <div class="info-item">
              <span class="label">文件名：</span>
              <span class="value">{{ document.name }}</span>
            </div>
            <div class="info-item">
              <span class="label">访问权限：</span>
              <span class="value">
                <el-tag v-if="document.permission === 1" type="warning" size="small">
                  <el-icon style="margin-right: 4px;"><Lock /></el-icon>
                  仅管理员可见
                </el-tag>
                <el-tag v-else type="success" size="small">
                  <el-icon style="margin-right: 4px;"><User /></el-icon>
                  所有用户和管理员可见
                </el-tag>
              </span>
            </div>
            <div class="info-item">
              <span class="label">上传时间：</span>
              <span class="value">{{ formatDate(document.uploaded_at) }}</span>
            </div>
          </div>
        </div>

        <!-- 文档内容卡片 -->
        <div class="info-card" v-if="document.content">
          <div class="card-header">
            <el-icon class="header-icon"><Reading /></el-icon>
            <h3>文档内容</h3>
          </div>
          <div class="card-body">
            <div class="content-container">
              <pre class="document-content">{{ document.content }}</pre>
            </div>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="stats-grid" v-if="isAdmin">
          <div class="stat-card">
            <div class="stat-icon">
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ document.chunk_count || 0 }}</div>
              <div class="stat-label">文本块</div>
            </div>
          </div>
          
          <div class="stat-card">
            <div class="stat-icon">
              <el-icon><Tickets /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ document.page || 0 }}</div>
              <div class="stat-label">页数</div>
            </div>
          </div>
          
          <div class="stat-card">
            <div class="stat-icon">
              <el-icon><FolderOpened /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatFileSize(document.size) }}</div>
              <div class="stat-label">文件大小</div>
            </div>
          </div>
        </div>
      </div>

      <el-empty v-else description="文档不存在" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store'
import { getDocumentDetail, deleteDocument } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  ArrowLeft, 
  Delete, 
  Document, 
  Link, 
  Operation,
  Tickets,
  FolderOpened,
  Reading,
  User,
  Lock,
  Download
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const document = ref(null)
const isDownloading = ref(false)

// 判断是否为管理员
const isAdmin = computed(() => userStore.userInfo.is_admin === 1)

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i]
}

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 格式化处理耗时
const formatDuration = (seconds) => {
  if (!seconds || seconds === 0) return '-'
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} 毫秒`
  if (seconds < 60) return `${seconds.toFixed(2)} 秒`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = (seconds % 60).toFixed(0)
  return `${minutes} 分 ${remainingSeconds} 秒`
}

// 获取文档详情
const fetchDocumentDetail = async () => {
  loading.value = true
  try {
    const documentId = route.params.id
    const data = await getDocumentDetail(documentId)
    document.value = data
  } catch (error) {
    console.error('获取文档详情失败:', error)
    ElMessage.error('获取文档详情失败')
  } finally {
    loading.value = false
  }
}

// 获取状态类型
const getStatusType = (status) => {
  const typeMap = {
    0: 'info',      // 未处理
    1: 'warning',   // 处理中
    2: 'success',   // 处理完成
    3: 'danger'     // 处理失败
  }
  return typeMap[status] || 'info'
}

// 获取状态描述
const getStatusDescription = (status, chunkCount) => {
  const descMap = {
    0: '文档尚未开始处理',
    1: '文档正在后台处理中，请稍后刷新...',
    2: `文档已成功处理完成，共分块为 ${chunkCount || 0} 个文本块，可用于检索`,
    3: '文档处理失败，请重新上传或联系管理员'
  }
  return descMap[status] || '状态未知'
}

// 返回
const goBack = () => {
  router.back()
}

// 下载文档
const handleDownload = async () => {
  if (isDownloading.value) {
    return
  }

  if (!document.value || !document.value.url) {
    ElMessage.warning('文档链接不可用')
    return
  }

  try {
    isDownloading.value = true

    // 构建完整 URL
    let fullUrl = document.value.url
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
    const link = window.document.createElement('a')
    link.href = blobUrl
    link.download = document.value.name || 'download'
    window.document.body.appendChild(link)
    link.click()

    // 清理
    window.document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)

    ElMessage.success('下载成功')
  } catch (error) {
    console.error('下载文档失败:', error)
    ElMessage.error('下载失败: ' + error.message)
  } finally {
    isDownloading.value = false
  }
}

// 删除文档
const handleDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${document.value.name}" 吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      }
    )
    
    await deleteDocument(document.value.uuid)
    
    ElMessage.success('删除成功')
    router.push('/admin/documents')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除文档失败:', error)
      ElMessage.error('删除文档失败')
    }
  }
}

onMounted(() => {
  fetchDocumentDetail()
})
</script>

<style scoped>
.document-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.page-title {
  flex: 1;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.back-button {
  background-color: rgba(255, 255, 255, 0.05) !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
  color: rgba(255, 255, 255, 0.9) !important;
}

.back-button:hover {
  background-color: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(102, 126, 234, 0.5) !important;
  color: #fff !important;
}

.detail-content {
  flex: 1;
  overflow-y: auto;
}

.document-info {
  max-width: 1200px;
  margin: 0 auto;
}

/* 信息卡片 */
.info-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
  transition: all 0.3s ease;
}

.info-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.2);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.header-icon {
  font-size: 24px;
  color: var(--primary-color);
}

.card-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-item {
  display: flex;
  align-items: flex-start;
  line-height: 1.6;
}

.info-item .label {
  flex: 0 0 120px;
  color: var(--text-tertiary);
  font-size: 14px;
}

.info-item .value {
  flex: 1;
  color: var(--text-primary);
  font-size: 14px;
  word-break: break-all;
}

.document-link {
  color: var(--primary-color);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.3s ease;
}

.document-link:hover {
  color: var(--primary-hover);
  text-decoration: underline;
}

/* 处理状态 */
.status-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 20px 0;
}

.status-desc {
  color: var(--text-secondary);
  font-size: 14px;
  text-align: center;
  margin: 0;
}

/* 统计卡片网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.stat-card {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 20px;
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3);
  border-color: var(--primary-color);
}

.stat-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  font-size: 28px;
  color: #fff;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
}

/* 文档内容显示 */
.content-container {
  max-height: 600px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.document-content {
  margin: 0;
  padding: 0;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* 自定义滚动条 */
.content-container::-webkit-scrollbar {
  width: 8px;
}

.content-container::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.content-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.content-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* 响应式 */
@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .info-item {
    flex-direction: column;
  }
  
  .info-item .label {
    margin-bottom: 4px;
  }
  
  .content-container {
    max-height: 400px;
  }
  
  .document-content {
    font-size: 13px;
  }
}
</style>

