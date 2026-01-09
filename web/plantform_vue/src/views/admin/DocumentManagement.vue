<template>
  <div class="document-management">
    <div class="page-header">
      <h2 class="page-title">文档管理</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索文档..."
          :prefix-icon="Search"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 240px"
        />
        <el-button type="success" :icon="View" @click="handleOpen3DView">
          3D 视图
        </el-button>
        <el-button type="primary" :icon="Upload" @click="showUploadDialog = true">
          上传文档
        </el-button>
        <el-button :icon="RefreshRight" @click="handleRefresh">
          刷新
        </el-button>
      </div>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="documentList"
        stripe
        class="document-table"
        @row-click="handleRowClick"
      >
        <el-table-column prop="uuid" label="文档 ID" width="280" show-overflow-tooltip />
        
        <el-table-column prop="name" label="文件名" min-width="200">
          <template #default="{ row }">
            <div class="file-name-cell clickable">
              <el-icon class="file-icon"><Document /></el-icon>
              <span class="file-name">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ row.status_text || '未知' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="权限" width="180">
          <template #default="{ row }">
            <el-tag v-if="row.permission === 1" type="warning" size="small">
              <el-icon style="margin-right: 4px;"><Lock /></el-icon>
              仅管理员
            </el-tag>
            <el-tag v-else type="success" size="small">
              <el-icon style="margin-right: 4px;"><User /></el-icon>
              所有用户和管理员
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="chunk_count" label="分块数" width="100" />
        
        <el-table-column prop="uploaded_at" label="上传时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.uploaded_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              text
              type="primary"
              size="small"
              @click.stop="handleViewDetail(row)"
            >
              查看
            </el-button>
            <el-button
              text
              type="danger"
              size="small"
              @click.stop="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <CustomPagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          @page-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <!-- 上传文档对话框 -->
    <el-dialog
      v-model="showUploadDialog"
      title="上传文档"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px">
        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleFileSelect"
            :on-remove="handleFileRemove"
            accept=".pdf,.docx,.pptx,.doc,.ppt,.txt,.md,.xlsx,.csv,.html,.rtf,.epub,.json,.xml"
            multiple
            drag
          >
            <el-icon class="el-icon--upload"><Upload /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处或 <em>点击选择</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                支持 PDF、Word、PPT、Excel、TXT、Markdown、HTML、EPUB、JSON、XML 等格式，支持多文件上传，单个文件最大 1000MB
              </div>
            </template>
          </el-upload>
        </el-form-item>
        
        <el-form-item label="访问权限">
          <el-radio-group v-model="uploadForm.permission" class="permission-selector">
            <el-radio :label="0">
              <div class="radio-content">
                <el-icon><User /></el-icon>
                <span>普通文档（所有用户和管理员可见）</span>
              </div>
            </el-radio>
            <el-radio :label="1">
              <div class="radio-content">
                <el-icon><Lock /></el-icon>
                <span>管理员文档（仅管理员可见）</span>
              </div>
            </el-radio>
          </el-radio-group>
          <div class="permission-tip" v-if="uploadForm.files.length > 1">
            <el-icon><InfoFilled /></el-icon>
            <span>所有文件将共享此权限设置（{{ uploadForm.files.length }} 个文件）</span>
          </div>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="handleCancelUpload">取消</el-button>
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="!uploadForm.files || uploadForm.files.length === 0"
          @click="handleConfirmUpload"
        >
          {{ uploading ? '上传中...' : (uploadForm.files.length > 1 ? `确认上传 (${uploadForm.files.length} 个文件)` : '确认上传') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getDocumentList, deleteDocument, uploadDocument } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Upload, RefreshRight, Document, User, Lock, InfoFilled, View } from '@element-plus/icons-vue'
import CustomPagination from '@/components/public/CustomPagination.vue'

const router = useRouter()

const loading = ref(false)
const documentList = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchKeyword = ref('')

// 上传相关
const showUploadDialog = ref(false)
const uploading = ref(false)
const uploadRef = ref(null)
const uploadForm = ref({
  files: [], // 改为数组，支持多文件
  permission: 0 // 默认为普通文档
})

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return '-'
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

// 获取文档列表
const fetchDocumentList = async () => {
  loading.value = true
  try {
    const data = await getDocumentList({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined
    })
    
    console.log('文档列表数据:', data)  // 调试日志
    
    // 处理不同的返回格式
    if (Array.isArray(data)) {
      // 如果直接返回数组
      documentList.value = data
      total.value = data.length
    } else if (data.documents) {
      // 如果返回带分页信息的对象
      documentList.value = data.documents
      total.value = data.total || 0
    } else {
      documentList.value = []
      total.value = 0
    }
  } catch (error) {
    console.error('获取文档列表失败:', error)
    ElMessage.error('获取文档列表失败')
  } finally {
    loading.value = false
  }
}

// 文件选择处理
const handleFileSelect = (file, fileList) => {
  const maxSize = 1000 * 1024 * 1024 // 1000MB
  
  // 验证单个文件大小
  if (file.size > maxSize) {
    ElMessage.error(`文件 ${file.name} 大小超过 1000MB，已自动移除`)
    // 从 fileList 中移除这个文件
    const index = fileList.findIndex(f => f.uid === file.uid)
    if (index > -1) {
      fileList.splice(index, 1)
    }
    return
  }
  
  const allowedTypes = [
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
    'text/xml'                                                                             // XML (alternative)
  ]
  
  const allowedExtensions = ['.pdf', '.docx', '.pptx', '.doc', '.ppt', '.txt', '.md', '.xlsx', '.csv', '.html', '.rtf', '.epub', '.json', '.xml']
  
  // 验证文件类型（通过 MIME 类型或文件扩展名）
  const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  const isValidType = allowedTypes.includes(file.raw.type) || allowedExtensions.includes(fileExtension)
  
  if (!isValidType) {
    ElMessage.error(`文件 ${file.name} 格式不支持。支持的格式：PDF、Word、PPT、Excel、TXT、Markdown、HTML、EPUB、JSON、XML 等`)
    // 从 fileList 中移除这个文件
    const index = fileList.findIndex(f => f.uid === file.uid)
    if (index > -1) {
      fileList.splice(index, 1)
    }
    return
  }
  
  // 更新文件列表
  uploadForm.value.files = fileList.map(f => f.raw)
}

// 文件移除处理
const handleFileRemove = (file, fileList) => {
  uploadForm.value.files = fileList.map(f => f.raw)
}

// 取消上传
const handleCancelUpload = () => {
  showUploadDialog.value = false
  uploadForm.value.files = []
  uploadForm.value.permission = 0
  uploadRef.value?.clearFiles()
}

// 确认上传
const handleConfirmUpload = async () => {
  if (!uploadForm.value.files || uploadForm.value.files.length === 0) {
    ElMessage.warning('请选择要上传的文件')
    return
  }
  
  uploading.value = true
  
  try {
    const formData = new FormData()
    
    // 添加所有文件
    uploadForm.value.files.forEach(file => {
      formData.append('files', file)
    })
    
    // 添加权限（所有文件共享）
    formData.append('permission', uploadForm.value.permission)
    
    const fileCount = uploadForm.value.files.length
    const permissionText = uploadForm.value.permission === 1 ? '仅管理员可见' : '所有用户和管理员可见'
    
    console.log(`批量上传 ${fileCount} 个文档，权限级别:`, uploadForm.value.permission)
    
    const response = await uploadDocument(formData)
    
    // 根据返回结果显示消息
    if (fileCount === 1) {
      // 单文件上传
      ElMessage.success(`文档上传成功！权限级别: ${permissionText}`)
    } else {
      // 多文件上传
      const successCount = response?.success_count || 0
      const failedCount = response?.failed_count || 0
      
      if (failedCount === 0) {
        ElMessage.success(`成功上传 ${successCount} 个文档！权限级别: ${permissionText}`)
      } else {
        ElMessage.warning(`上传完成：成功 ${successCount} 个，失败 ${failedCount} 个。权限级别: ${permissionText}`)
      }
    }
    
    // 关闭对话框并重置表单
    handleCancelUpload()
    
    // 刷新列表
    await fetchDocumentList()
  } catch (error) {
    console.error('文件上传失败:', error)
    ElMessage.error(error.message || '文件上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  fetchDocumentList()
}

// 刷新
const handleRefresh = () => {
  currentPage.value = 1
  searchKeyword.value = ''
  fetchDocumentList()
}

// 页码变化
const handlePageChange = () => {
  fetchDocumentList()
}

// 页大小变化
const handleSizeChange = () => {
  currentPage.value = 1
  fetchDocumentList()
}

// 点击行跳转到详情
const handleRowClick = (row) => {
  router.push(`/admin/documents/${row.uuid}`)
}

// 查看详情
const handleViewDetail = (document) => {
  router.push(`/admin/documents/${document.uuid}`)
}

// 打开 3D 视图
const handleOpen3DView = () => {
  router.push('/documents/3d')
}

// 删除文档
const handleDelete = async (document) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${document.name}" 吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      }
    )
    
    await deleteDocument(document.uuid)
    
    ElMessage.success('删除成功')
    fetchDocumentList()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除文档失败:', error)
      ElMessage.error('删除文档失败')
    }
  }
}

onMounted(() => {
  fetchDocumentList()
})
</script>

<style scoped>
.document-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  /* padding-bottom: 80px; 增加底部间距，避免被导航栏遮挡 */
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
  overflow: hidden;
}

.document-table {
  flex: 1;
  overflow: auto;
}

.document-table :deep(.el-table__header) {
  background: var(--bg-tertiary);
}

.document-table :deep(.el-table__row) {
  background: transparent;
}

.document-table :deep(.el-table__row:hover) {
  background: rgba(99, 102, 241, 0.05);
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-name-cell.clickable {
  cursor: pointer;
}

.file-name-cell.clickable:hover .file-name {
  color: var(--primary-color);
  text-decoration: underline;
}

.file-icon {
  color: var(--primary-color);
  font-size: 16px;
}

.file-name {
  transition: all 0.3s ease;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

/* 上传对话框样式 */
:deep(.el-dialog) {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
}

:deep(.el-dialog__header) {
  border-bottom: 1px solid var(--border-color);
}

:deep(.el-dialog__title) {
  color: var(--text-primary);
  font-weight: 600;
}

:deep(.el-dialog__body) {
  color: var(--text-primary);
}

/* 权限选择器样式 */
.permission-selector {
  width: 100%;
}

.permission-selector :deep(.el-radio) {
  width: 100%;
  margin-right: 0;
  margin-bottom: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.permission-selector :deep(.el-radio:hover) {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--primary-color);
}

.permission-selector :deep(.el-radio.is-checked) {
  background: rgba(99, 102, 241, 0.1);
  border-color: var(--primary-color);
}

.radio-content {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 8px;
}

.radio-content .el-icon {
  font-size: 16px;
}

/* 权限提示样式 */
.permission-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 6px;
  color: var(--primary-color);
  font-size: 13px;
}

.permission-tip .el-icon {
  font-size: 16px;
}

/* 上传组件样式 */
:deep(.el-upload-dragger) {
  background: rgba(255, 255, 255, 0.03);
  border: 2px dashed var(--border-color);
}

:deep(.el-upload-dragger:hover) {
  border-color: var(--primary-color);
}

:deep(.el-icon--upload) {
  color: var(--primary-color);
}

:deep(.el-upload__text) {
  color: var(--text-primary);
}

:deep(.el-upload__tip) {
  color: var(--text-secondary);
}
</style>

