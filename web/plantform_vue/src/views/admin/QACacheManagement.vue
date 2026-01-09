<template>
  <div class="qa-cache-management">
    <div class="page-header">
      <h2 class="page-title">QA 缓存管理</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索问题..."
          :prefix-icon="Search"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 240px"
        />
        <el-button type="success" :icon="View" @click="handleOpen3DView">
          3D 视图
        </el-button>
        <el-button :icon="RefreshRight" @click="handleRefresh">
          刷新
        </el-button>
      </div>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="cacheList"
        stripe
        class="cache-table"
        @row-click="handleRowClick"
      >
        <el-table-column prop="thought_chain_id" label="缓存 ID" width="280" show-overflow-tooltip />
        
        <el-table-column prop="question" label="问题" min-width="300">
          <template #default="{ row }">
            <div class="question-cell clickable">
              <el-icon class="question-icon"><ChatDotRound /></el-icon>
              <span class="question-text">{{ row.question }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="answer_preview" label="答案预览" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="answer-preview">{{ row.answer_preview || '暂无预览' }}</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
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

    <!-- 详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="QA 缓存详情"
      width="700px"
      :close-on-click-modal="true"
    >
      <div v-if="detailData" class="detail-content">
        <div class="detail-section">
          <h4>问题</h4>
          <p class="detail-question">{{ detailData.question }}</p>
        </div>
        <div class="detail-section">
          <h4>答案</h4>
          <p class="detail-answer">{{ detailData.answer }}</p>
        </div>
        <div class="detail-section" v-if="detailData.references?.length">
          <h4>引用文档</h4>
          <div class="reference-list">
            <el-tag 
              v-for="(ref, idx) in detailData.references" 
              :key="idx"
              size="small"
              class="reference-tag"
            >
              {{ ref.filename || ref }}
            </el-tag>
          </div>
        </div>
        <div class="detail-meta">
          <span>缓存 ID: {{ detailData.thought_chain_id }}</span>
          <span>创建时间: {{ formatDate(detailData.created_at) }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
        <el-button type="danger" @click="handleDeleteFromDetail">删除此缓存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getQACacheListAdmin, getQACacheDetailAdmin, deleteQACacheAdmin } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, RefreshRight, ChatDotRound, View } from '@element-plus/icons-vue'
import CustomPagination from '@/components/public/CustomPagination.vue'

const router = useRouter()

const loading = ref(false)
const cacheList = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchKeyword = ref('')

// 详情对话框
const showDetailDialog = ref(false)
const detailData = ref(null)

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

// 获取缓存列表
const fetchCacheList = async () => {
  loading.value = true
  try {
    const data = await getQACacheListAdmin({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined
    })
    
    if (Array.isArray(data)) {
      cacheList.value = data
      total.value = data.length
    } else if (data.items) {
      cacheList.value = data.items
      total.value = data.total || 0
    } else {
      cacheList.value = []
      total.value = 0
    }
  } catch (error) {
    console.error('获取 QA 缓存列表失败:', error)
    ElMessage.error('获取 QA 缓存列表失败')
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  fetchCacheList()
}

// 刷新
const handleRefresh = () => {
  currentPage.value = 1
  searchKeyword.value = ''
  fetchCacheList()
}

// 页码变化
const handlePageChange = () => {
  fetchCacheList()
}

// 页大小变化
const handleSizeChange = () => {
  currentPage.value = 1
  fetchCacheList()
}

// 点击行查看详情
const handleRowClick = async (row) => {
  try {
    // 优先使用 thought_chain_id，否则使用 milvus_id
    const cacheId = row.thought_chain_id || String(row.milvus_id)
    const data = await getQACacheDetailAdmin(cacheId)
    detailData.value = { ...data, milvus_id: row.milvus_id }
    showDetailDialog.value = true
  } catch (error) {
    console.error('获取详情失败:', error)
    ElMessage.error('获取详情失败')
  }
}

// 打开 3D 视图
const handleOpen3DView = () => {
  router.push('/qa-cache/3d')
}

// 删除缓存
const handleDelete = async (cache) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除此 QA 缓存吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      }
    )
    
    // 优先使用 thought_chain_id，否则使用 milvus_id
    const cacheId = cache.thought_chain_id || String(cache.milvus_id)
    await deleteQACacheAdmin(cacheId)
    
    ElMessage.success('删除成功')
    fetchCacheList()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除 QA 缓存失败:', error)
      ElMessage.error('删除 QA 缓存失败')
    }
  }
}

// 从详情对话框删除
const handleDeleteFromDetail = async () => {
  if (!detailData.value) return
  
  try {
    await ElMessageBox.confirm(
      `确定要删除此 QA 缓存吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      }
    )
    
    // 优先使用 thought_chain_id，否则使用 milvus_id
    const cacheId = detailData.value.thought_chain_id || String(detailData.value.milvus_id)
    await deleteQACacheAdmin(cacheId)
    
    ElMessage.success('删除成功')
    showDetailDialog.value = false
    fetchCacheList()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除 QA 缓存失败:', error)
      ElMessage.error('删除 QA 缓存失败')
    }
  }
}

onMounted(() => {
  fetchCacheList()
})
</script>

<style scoped>
.qa-cache-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
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

.cache-table {
  flex: 1;
  overflow: auto;
}

.cache-table :deep(.el-table__header) {
  background: var(--bg-tertiary);
}

.cache-table :deep(.el-table__row) {
  background: transparent;
}

.cache-table :deep(.el-table__row:hover) {
  background: rgba(99, 102, 241, 0.05);
}

.question-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.question-cell.clickable {
  cursor: pointer;
}

.question-cell.clickable:hover .question-text {
  color: var(--primary-color);
  text-decoration: underline;
}

.question-icon {
  color: var(--primary-color);
  font-size: 16px;
}

.question-text {
  transition: all 0.3s ease;
}

.answer-preview {
  color: var(--text-secondary);
  font-size: 13px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

/* 详情对话框样式 */
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

.detail-content {
  max-height: 500px;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h4 {
  margin: 0 0 8px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.detail-question {
  margin: 0;
  padding: 12px;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 8px;
  color: var(--text-primary);
  line-height: 1.6;
}

.detail-answer {
  margin: 0;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.reference-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.reference-tag {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.3);
  color: #10B981;
}

.detail-meta {
  display: flex;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
