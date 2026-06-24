<template>
  <div class="rag-evaluation-management">
    <div class="page-header">
      <h2 class="page-title">RAG 评估</h2>
      <div class="header-actions">
        <el-select
          v-model="statusFilter"
          placeholder="评估状态"
          clearable
          style="width: 140px"
          @change="handleSearch"
        >
          <el-option label="待评估" value="pending" />
          <el-option label="排队中" value="queued" />
          <el-option label="评估中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="失败" value="failed" />
          <el-option label="已跳过" value="skipped" />
        </el-select>
        <el-input
          v-model="searchKeyword"
          placeholder="搜索问题或文档"
          :prefix-icon="Search"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 240px"
        />
        <el-button :icon="RefreshRight" @click="handleRefresh">刷新</el-button>
      </div>
    </div>

    <div class="summary-grid">
      <div class="summary-item">
        <span class="summary-label">总记录</span>
        <strong>{{ summary.total }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">已完成</span>
        <strong>{{ summary.completed_count }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">待评估</span>
        <strong>{{ summary.queued_count }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">评估中</span>
        <strong>{{ summary.running_count }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">失败数</span>
        <strong>{{ summary.failed_count }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">已跳过</span>
        <strong>{{ summary.skipped_count }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">平均检索分</span>
        <strong>{{ formatScore(summary.avg_retrieval_score) }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">平均 RAGAS 分</span>
        <strong>{{ formatScore(summary.avg_ragas_score) }}</strong>
      </div>
    </div>

    <div class="config-panel">
      <el-switch v-model="configForm.ragas_enabled" active-text="启用 RAGAS" />
      <el-switch v-model="configForm.ragas_queue_enabled" active-text="加入 Kafka 队列" />
      <el-input-number v-model="configForm.ragas_sample_rate" :min="0" :max="1" :step="0.1" controls-position="right" />
      <el-input-number v-model="configForm.ragas_max_chunks_per_question" :min="0" :max="20" controls-position="right" />
      <el-input-number v-model="configForm.ragas_min_retrieval_score" :min="0" :max="1" :step="0.05" controls-position="right" />
      <el-button type="primary" @click="saveConfig">保存配置</el-button>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="records"
        stripe
        class="evaluation-table"
        @row-click="handleRowClick"
      >
        <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="retrieved_text" label="返回文本" min-width="300" show-overflow-tooltip />
        <el-table-column prop="filename" label="文档来源" min-width="180" show-overflow-tooltip />
        <el-table-column label="检索分数" width="110">
          <template #default="{ row }">{{ formatScore(row.overall_score) }}</template>
        </el-table-column>
        <el-table-column label="RAGAS" width="110">
          <template #default="{ row }">{{ formatRagasScore(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.queue_status || row.ragas_status)" size="small">
              {{ statusText(row.queue_status || row.ragas_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="queued_at" label="入队时间" width="180">
          <template #default="{ row }">{{ formatDate(row.queued_at) }}</template>
        </el-table-column>
        <el-table-column prop="completed_at" label="完成时间" width="180">
          <template #default="{ row }">{{ formatDate(row.completed_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click.stop="handleRequeue(row)">
              重新评估
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
          @page-change="fetchRecords"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="showDetailDialog" title="RAG 评估详情" width="760px">
      <div v-if="detailData" class="detail-content">
        <div class="detail-section">
          <h4>问题</h4>
          <p>{{ detailData.question }}</p>
        </div>
        <div class="detail-section">
          <h4>回答</h4>
          <p>{{ detailData.answer || '暂无回答' }}</p>
        </div>
        <div class="detail-section">
          <h4>返回文本</h4>
          <p>{{ detailData.retrieved_text }}</p>
        </div>
        <div class="score-list">
          <span>检索分数：{{ formatScore(detailData.overall_score) }}</span>
          <span>向量分数：{{ formatScore(detailData.vector_score) }}</span>
          <span>重排分数：{{ formatScore(detailData.rerank_score) }}</span>
          <span>忠实度：{{ formatScore(detailData.faithfulness) }}</span>
          <span>回答相关度：{{ formatScore(detailData.answer_relevance) }}</span>
          <span>上下文精准度：{{ formatScore(detailData.context_precision) }}</span>
        </div>
        <div class="detail-meta">
          <span>{{ detailData.filename || '未知文档' }}</span>
          <span>{{ formatDate(detailData.created_at) }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight, Search } from '@element-plus/icons-vue'
import { getRAGEvaluationConfig, getRAGEvaluationList, requeueRAGEvaluation, updateRAGEvaluationConfig } from '@/api'
import CustomPagination from '@/components/public/CustomPagination.vue'

const loading = ref(false)
const records = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const statusFilter = ref('')
const showDetailDialog = ref(false)
const detailData = ref(null)
const summary = ref({
  total: 0,
  completed_count: 0,
  pending_count: 0,
  queued_count: 0,
  running_count: 0,
  failed_count: 0,
  skipped_count: 0,
  avg_retrieval_score: 0,
  avg_ragas_score: 0
})
const configForm = ref({
  ragas_enabled: true,
  ragas_queue_enabled: true,
  ragas_sample_rate: 1,
  ragas_max_chunks_per_question: 3,
  ragas_min_retrieval_score: 0
})

const fetchRecords = async () => {
  loading.value = true
  try {
    const data = await getRAGEvaluationList({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined,
      ragas_status: statusFilter.value || undefined
    })
    records.value = data.items || []
    total.value = data.total || 0
    summary.value = {
      total: data.total || 0,
      completed_count: data.completed_count || 0,
      pending_count: data.pending_count || 0,
      queued_count: data.queued_count || data.pending_count || 0,
      running_count: data.running_count || 0,
      failed_count: data.failed_count || 0,
      skipped_count: data.skipped_count || 0,
      avg_retrieval_score: data.avg_retrieval_score || 0,
      avg_ragas_score: data.avg_ragas_score || 0
    }
  } catch (error) {
    ElMessage.error('获取 RAG 评估记录失败')
  } finally {
    loading.value = false
  }
}

const fetchConfig = async () => {
  try {
    const data = await getRAGEvaluationConfig()
    configForm.value = {
      ragas_enabled: data.ragas_enabled ?? true,
      ragas_queue_enabled: data.ragas_queue_enabled ?? true,
      ragas_sample_rate: data.ragas_sample_rate ?? 1,
      ragas_max_chunks_per_question: data.ragas_max_chunks_per_question ?? 3,
      ragas_min_retrieval_score: data.ragas_min_retrieval_score ?? 0
    }
  } catch (error) {
    ElMessage.error('获取评估配置失败')
  }
}

const saveConfig = async () => {
  try {
    await updateRAGEvaluationConfig(configForm.value)
    ElMessage.success('保存成功')
  } catch (error) {
    ElMessage.error('保存配置失败')
  }
}

const handleRequeue = async (row) => {
  try {
    await requeueRAGEvaluation(row.id)
    ElMessage.success('已加入队列')
    fetchRecords()
  } catch (error) {
    ElMessage.error('加入队列失败')
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchRecords()
}

const handleRefresh = () => {
  currentPage.value = 1
  searchKeyword.value = ''
  statusFilter.value = ''
  fetchRecords()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchRecords()
}

const handleRowClick = (row) => {
  detailData.value = row
  showDetailDialog.value = true
}

const formatScore = (value) => {
  const number = Number(value || 0)
  return number.toFixed(2)
}

const formatRagasScore = (row) => {
  if ((row.queue_status || row.ragas_status) !== 'completed') return '-'
  const score = ((row.faithfulness || 0) + (row.answer_relevance || 0) + (row.context_precision || 0)) / 3
  return formatScore(score)
}

const statusText = (status) => {
  const map = {
    pending: '待评估',
    queued: '排队中',
    running: '评估中',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过'
  }
  return map[status] || '未开始'
}

const statusType = (status) => {
  const map = {
    pending: 'warning',
    queued: 'warning',
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    skipped: 'info'
  }
  return map[status] || 'info'
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  fetchConfig()
  fetchRecords()
})
</script>

<style scoped>
.rag-evaluation-management {
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
  margin-bottom: 18px;
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.config-panel {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, auto));
  align-items: center;
  gap: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.summary-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.summary-item strong {
  color: var(--text-primary);
  font-size: 22px;
}

.page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  overflow: hidden;
}

.evaluation-table {
  flex: 1;
  overflow: auto;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

.detail-content {
  max-height: 560px;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 18px;
}

.detail-section h4 {
  margin: 0 0 8px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.detail-section p {
  margin: 0;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.score-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
  color: var(--text-primary);
}

.detail-meta {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
  border-top: 1px solid var(--border-color);
  padding-top: 14px;
}
</style>
