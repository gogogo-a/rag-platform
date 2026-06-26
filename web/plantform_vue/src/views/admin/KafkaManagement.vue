<template>
  <div class="kafka-management">
    <div class="page-header">
      <h2 class="page-title">Kafka 可视化</h2>
      <div class="header-actions">
        <el-select
          v-model="filterForm.topic"
          placeholder="主题"
          clearable
          style="width: 190px"
          @change="handleSearch"
        >
          <el-option
            v-for="item in topicCards"
            :key="item.key"
            :label="item.topic"
            :value="item.key"
          />
        </el-select>
        <el-input
          v-model="filterForm.keyword"
          placeholder="搜索消息"
          :prefix-icon="Search"
          clearable
          style="width: 220px"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        />
        <el-button :icon="RefreshRight" @click="handleRefresh">刷新</el-button>
      </div>
    </div>

    <div ref="topicGridRef" class="topic-grid" @scroll="saveViewState">
      <button
        v-for="item in topicCards"
        :key="item.key"
        class="topic-card"
        :class="{ active: filterForm.topic === item.key }"
        type="button"
        @click="selectTopic(item.key)"
      >
        <span class="topic-name">{{ item.topic }}</span>
        <strong>{{ item.latest_offset || 0 }}</strong>
        <span class="topic-meta">
          {{ item.partition_count || 0 }} 个分区 / {{ item.active_partition_count || 0 }} 个有消息 / {{ item.empty_partition_count || 0 }} 个为空
        </span>
        <span class="topic-group">{{ item.consumer_group || '未配置消费组' }}</span>
        <div class="partition-list">
          <span
            v-for="partition in item.partitions || []"
            :key="partition.partition"
            class="partition-pill"
            :class="{ empty: !partition.message_count }"
          >
            P{{ partition.partition }} {{ partition.message_count || 0 }}
          </span>
        </div>
      </button>
    </div>

    <div class="filter-panel">
      <el-select v-model="filterForm.status" placeholder="状态" clearable @change="handleSearch">
        <el-option label="待处理" value="待处理" />
        <el-option label="排队中" value="排队中" />
        <el-option label="评估中" value="评估中" />
        <el-option label="已完成" value="已完成" />
        <el-option label="失败" value="失败" />
      </el-select>
      <el-input v-model="filterForm.user_id" placeholder="用户 ID" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-input v-model="filterForm.session_id" placeholder="会话 ID" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-input v-model="filterForm.question_id" placeholder="问题 ID" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-input v-model="filterForm.task_id" placeholder="任务 ID" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-input v-model="filterForm.document_uuid" placeholder="文档 ID" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-input v-model="filterForm.expert_key" placeholder="专家标识" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-input v-model="filterForm.evaluation_id" placeholder="评估 ID" clearable @clear="handleSearch" @keyup.enter="handleSearch" />
      <el-date-picker
        v-model="timeRange"
        type="datetimerange"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        value-format="YYYY-MM-DDTHH:mm:ss"
        @change="handleSearch"
      />
      <el-button type="primary" :icon="Search" @click="handleSearch">筛选</el-button>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="messages"
        stripe
        class="kafka-table"
        @row-click="openDetail"
      >
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.timestamp) }}</template>
        </el-table-column>
        <el-table-column prop="topic" label="主题" width="180" show-overflow-tooltip />
        <el-table-column prop="message_type" label="类型" width="110" />
        <el-table-column v-if="isExpertTopic" label="专家" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.expert_name || row.expert_key || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status || '待处理' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="用户" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_name || row.user_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="会话" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.session_name || row.session_id || '-' }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="260" show-overflow-tooltip />
        <el-table-column prop="key" label="Key" min-width="150" show-overflow-tooltip />
        <el-table-column prop="partition" label="分区" width="80" />
        <el-table-column prop="offset" label="Offset" width="100" />
        <el-table-column label="操作" width="150" fixed="right" class-name="operation-column">
          <template #default="{ row }">
            <div class="action-buttons">
              <el-button type="primary" size="small" @click.stop="openDetail(row)">详情</el-button>
              <el-button
                v-if="row.evaluation_id"
                type="primary"
                size="small"
                @click.stop="openEvaluation(row)"
              >
                查看评估
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <CustomPagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          @page-change="fetchMessages"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="showDetailDialog" title="消息详情" width="820px" class="kafka-detail-dialog">
      <div v-if="detailData" class="detail-content">
        <div class="detail-grid">
          <span>主题：{{ detailData.topic }}</span>
          <span>类型：{{ detailData.message_type }}</span>
          <span>状态：{{ detailData.status || '-' }}</span>
          <span>时间：{{ formatDate(detailData.timestamp) }}</span>
          <span>用户：{{ detailData.user_name || detailData.user_id || '-' }}</span>
          <span>会话：{{ detailData.session_name || detailData.session_id || '-' }}</span>
          <span>分区：{{ detailData.partition }}</span>
          <span>Offset：{{ detailData.offset }}</span>
        </div>
        <div class="detail-section">
          <h4>摘要</h4>
          <p>{{ detailData.summary || '-' }}</p>
        </div>
        <div class="detail-section">
          <h4>消息内容</h4>
          <pre>{{ formatPayload(detailData.payload) }}</pre>
        </div>
        <div v-if="detailData.related_evaluation" class="detail-section">
          <h4>评估结果</h4>
          <div class="evaluation-detail">
            <span>问题：{{ detailData.related_evaluation.question || '-' }}</span>
            <span>状态：{{ detailData.related_evaluation.status || '-' }}</span>
            <span>检索分数：{{ formatScore(detailData.related_evaluation.overall_score) }}</span>
            <span>忠实度：{{ formatScore(detailData.related_evaluation.faithfulness) }}</span>
            <span>回答相关度：{{ formatScore(detailData.related_evaluation.answer_relevance) }}</span>
            <span>上下文精准度：{{ formatScore(detailData.related_evaluation.context_precision) }}</span>
          </div>
          <p>{{ detailData.related_evaluation.answer || '暂无回答' }}</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight, Search } from '@element-plus/icons-vue'
import { getKafkaMessageDetail, getKafkaMessages, getKafkaTopics } from '@/api'
import { useRouter } from 'vue-router'
import CustomPagination from '@/components/public/CustomPagination.vue'

const loading = ref(false)
const router = useRouter()
const topicCards = ref([])
const messages = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const topicGridRef = ref(null)
const showDetailDialog = ref(false)
const detailData = ref(null)
const timeRange = ref([])
const filterForm = ref({
  topic: '',
  keyword: '',
  status: '',
  user_id: '',
  session_id: '',
  question_id: '',
  task_id: '',
  document_uuid: '',
  expert_key: '',
  evaluation_id: ''
})
const stateStorageKey = 'kafka-management-view-state'
const isExpertTopic = computed(() => [
  'expert_tasks',
  'expert_results',
  'expert_dead_letters'
].includes(filterForm.value.topic))

const saveViewState = () => {
  const state = {
    filterForm: filterForm.value,
    timeRange: timeRange.value,
    currentPage: currentPage.value,
    pageSize: pageSize.value,
    topicScrollLeft: topicGridRef.value?.scrollLeft || 0
  }
  sessionStorage.setItem(stateStorageKey, JSON.stringify(state))
}

const restoreViewState = () => {
  try {
    const state = JSON.parse(sessionStorage.getItem(stateStorageKey) || '{}')
    if (!state || typeof state !== 'object') return
    if (state.filterForm) {
      filterForm.value = { ...filterForm.value, ...state.filterForm }
    }
    timeRange.value = Array.isArray(state.timeRange) ? state.timeRange : []
    currentPage.value = Number(state.currentPage || 1)
    pageSize.value = Number(state.pageSize || 20)
    nextTick(() => {
      if (topicGridRef.value) {
        topicGridRef.value.scrollLeft = Number(state.topicScrollLeft || 0)
      }
    })
  } catch (error) {
    sessionStorage.removeItem(stateStorageKey)
  }
}

const fetchTopics = async () => {
  try {
    const data = await getKafkaTopics()
    topicCards.value = data.topics || []
  } catch (error) {
    ElMessage.error('获取主题失败')
  }
}

const buildParams = () => ({
  topic: filterForm.value.topic || undefined,
  keyword: filterForm.value.keyword || undefined,
  status: filterForm.value.status || undefined,
  user_id: filterForm.value.user_id || undefined,
  session_id: filterForm.value.session_id || undefined,
  question_id: filterForm.value.question_id || undefined,
  task_id: filterForm.value.task_id || undefined,
  document_uuid: filterForm.value.document_uuid || undefined,
  expert_key: filterForm.value.expert_key || undefined,
  evaluation_id: filterForm.value.evaluation_id || undefined,
  start_time: timeRange.value?.[0] || undefined,
  end_time: timeRange.value?.[1] || undefined,
  page: currentPage.value,
  page_size: pageSize.value
})

const fetchMessages = async () => {
  if (!filterForm.value.topic) {
    messages.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const data = await getKafkaMessages(buildParams())
    messages.value = data.messages || []
    total.value = data.total || 0
    saveViewState()
  } catch (error) {
    ElMessage.error('获取消息失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchMessages()
}

const handleRefresh = () => {
  filterForm.value = {
    topic: '',
    keyword: '',
    status: '',
    user_id: '',
    session_id: '',
    question_id: '',
    task_id: '',
    document_uuid: '',
    expert_key: '',
    evaluation_id: ''
  }
  timeRange.value = []
  currentPage.value = 1
  messages.value = []
  total.value = 0
  sessionStorage.removeItem(stateStorageKey)
  fetchTopics()
}

const selectTopic = (topic) => {
  filterForm.value.topic = topic
  currentPage.value = 1
  saveViewState()
  fetchMessages()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchMessages()
}

const openDetail = async (row) => {
  saveViewState()
  detailData.value = row
  showDetailDialog.value = true
  try {
    const data = await getKafkaMessageDetail({
      topic: row.topic_key || row.topic,
      partition: row.partition,
      offset: row.offset
    })
    detailData.value = data || row
  } catch (error) {
    detailData.value = row
  }
}

const openEvaluation = (row) => {
  saveViewState()
  router.push({
    path: '/admin/evaluations',
    query: { evaluation_id: row.evaluation_id }
  })
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

const formatPayload = (payload) => JSON.stringify(payload || {}, null, 2)

const formatScore = (value) => Number(value || 0).toFixed(2)

const statusType = (status) => {
  if (status === '已完成') return 'success'
  if (status === '失败') return 'danger'
  if (status === '评估中') return 'primary'
  if (status === '排队中' || status === '待处理' || status === '待评估') return 'warning'
  return 'info'
}

onMounted(() => {
  restoreViewState()
  fetchTopics().then(() => {
    nextTick(() => {
      if (filterForm.value.topic) {
        fetchMessages()
      }
    })
  })
})

onBeforeUnmount(() => {
  saveViewState()
})
</script>

<style scoped>
.kafka-management {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topic-grid {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(220px, 1fr);
  grid-template-rows: 1fr;
  gap: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
  overflow-x: auto;
  padding-bottom: 2px;
}

.topic-card {
  min-height: 96px;
  text-align: left;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  cursor: pointer;
}

.topic-card.active,
.topic-card:hover {
  border-color: var(--primary-color);
  background: var(--bg-tertiary);
}

.topic-name {
  color: var(--text-secondary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topic-card strong {
  font-size: 22px;
  line-height: 1;
}

.topic-meta,
.topic-group {
  color: var(--text-tertiary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.partition-list {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  margin-top: auto;
  overflow: hidden;
}

.partition-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 7px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1;
}

.partition-pill.empty {
  color: var(--text-tertiary);
}

.filter-panel {
  display: grid;
  grid-template-columns: repeat(5, minmax(150px, 1fr));
  gap: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.filter-panel :deep(.el-date-editor) {
  width: 100%;
}

.page-content {
  flex: 0 0 auto;
  min-height: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.kafka-table {
  width: 100%;
}

.kafka-table :deep(.operation-column .cell) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.action-buttons {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 6px;
  width: 88px;
}

.action-buttons :deep(.el-button) {
  width: 88px;
  height: 28px;
  margin: 0;
  border-radius: 7px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  color: var(--text-secondary);
}

.detail-section {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px;
}

.detail-section h4 {
  margin: 0 0 10px;
  color: var(--text-primary);
}

.detail-section p,
.detail-section pre {
  margin: 0;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-section pre {
  max-height: 360px;
  overflow: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.evaluation-detail {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
  color: var(--text-secondary);
}

@media (max-width: 1200px) {
  .filter-panel {
    grid-template-columns: repeat(2, minmax(160px, 1fr));
  }
}
</style>
