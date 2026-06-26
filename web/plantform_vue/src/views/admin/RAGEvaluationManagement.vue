<template>
  <div class="rag-evaluation-management">
    <div class="page-header">
      <h2 class="page-title">评估管理</h2>
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

    <div class="case-panel">
      <div class="case-panel-header">
        <div>
          <h3>固定测试集</h3>
          <p>按 MCP、Agent 和组合流程分别验证对话质量</p>
        </div>
        <div class="case-actions">
          <el-segmented v-model="caseSuiteType" :options="caseSuiteOptions" @change="fetchCases" />
          <el-button :icon="RefreshRight" @click="fetchCases">刷新测试集</el-button>
        </div>
      </div>
      <el-table
        v-loading="caseLoading"
        :data="cases"
        stripe
        class="case-table"
      >
        <el-table-column prop="name" label="测试集" min-width="160" show-overflow-tooltip />
        <el-table-column label="分类" width="90">
          <template #default="{ row }">{{ suiteTypeText(row.suite_type) }}</template>
        </el-table-column>
        <el-table-column label="模式" width="90">
          <template #default="{ row }">{{ row.agent_mode === 'expert' ? '专家' : '普通' }}</template>
        </el-table-column>
        <el-table-column label="目标" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ caseTargetText(row) }}</template>
        </el-table-column>
        <el-table-column label="轮次" width="80">
          <template #default="{ row }">{{ row.turn_count }}</template>
        </el-table-column>
        <el-table-column label="最低分" width="90">
          <template #default="{ row }">{{ formatScore(row.min_score) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              text
              type="primary"
              size="small"
              :loading="runningCaseId === row.case_id"
              @click="handleRunCase(row)"
            >
              执行
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="lastCaseRun" class="case-run-summary">
        <span>{{ lastCaseRun.case?.name }}</span>
        <span>完成 {{ lastCaseRun.completed_turns }}/{{ lastCaseRun.total_turns }}</span>
        <span>平均分 {{ formatScore(lastCaseRun.avg_score) }}</span>
      </div>
    </div>

    <nav class="evaluation-subnav" aria-label="评估分类">
      <button
        v-for="item in evaluationTypes"
        :key="item.value"
        class="subnav-item"
        :class="{ active: activeType === item.value }"
        @click="changeType(item.value)"
      >
        <span>{{ item.label }}</span>
        <em>{{ summary.type_counts?.[item.value] || 0 }}</em>
      </button>
    </nav>

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
        <span class="summary-label">平均综合分</span>
        <strong>{{ formatScore(summary.avg_overall_score) }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">平均 RAGAS 分</span>
        <strong>{{ formatScore(summary.avg_ragas_score) }}</strong>
      </div>
    </div>

    <div class="config-panel">
      <div class="config-field switch-field">
        <span>回复质量评估</span>
        <el-switch v-model="configForm.evaluation_enabled" />
      </div>
      <div class="config-field wide-field">
        <span>评估抽样比例</span>
        <el-slider
          v-model="evaluationSamplePercent"
          :min="0"
          :max="100"
          :step="5"
          show-input
          :show-input-controls="false"
        />
      </div>
      <div class="config-field switch-field">
        <span>RAGAS 评估</span>
        <el-switch v-model="configForm.ragas_enabled" />
      </div>
      <div class="config-field switch-field">
        <span>自动评估 RAG</span>
        <el-switch v-model="configForm.ragas_queue_enabled" />
      </div>
      <div class="config-field">
        <span>最低规则分</span>
        <el-input-number v-model="configForm.ragas_min_retrieval_score" :min="0" :max="1" :step="0.05" controls-position="right" />
      </div>
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
        <el-table-column label="测试集" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.case_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="分类" width="90">
          <template #default="{ row }">{{ row.suite_type ? suiteTypeText(row.suite_type) : '-' }}</template>
        </el-table-column>
        <el-table-column label="评估类型" width="130">
          <template #default="{ row }">{{ evaluationTypeText(row.evaluation_type) }}</template>
        </el-table-column>
        <el-table-column label="综合评分" width="110">
          <template #default="{ row }">{{ formatScore(row.overall_score) }}</template>
        </el-table-column>
        <el-table-column prop="score_reason" label="评分原因" min-width="280" show-overflow-tooltip />
        <el-table-column label="LLM 评分" width="110">
          <template #default="{ row }">{{ formatScore(row.llm_score) }}</template>
        </el-table-column>
        <el-table-column label="规则评分" width="110">
          <template #default="{ row }">{{ formatScore(row.rule_score) }}</template>
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
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.evaluation_type === 'rag'"
              text
              type="primary"
              size="small"
              @click.stop="handleRequeue(row)"
            >
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

    <el-dialog v-model="showDetailDialog" title="评估详情" width="760px">
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
          <h4>评分原因</h4>
          <p>{{ detailData.score_reason || '暂无评分原因' }}</p>
        </div>
        <div class="score-list">
          <span>综合评分：{{ formatScore(detailData.overall_score) }}</span>
          <span>LLM 评分：{{ formatScore(detailData.llm_score) }}</span>
          <span>规则评分：{{ formatScore(detailData.rule_score) }}</span>
          <span>评估类型：{{ evaluationTypeText(detailData.evaluation_type) }}</span>
          <span v-if="detailData.case_name">测试集：{{ detailData.case_name }}</span>
          <span v-if="detailData.turn_index">轮次：{{ detailData.turn_index }}</span>
        </div>
        <template v-if="detailData.evaluation_type === 'rag'">
          <div class="detail-section">
            <h4>返回文本</h4>
            <p>{{ detailData.retrieved_text || '暂无返回文本' }}</p>
          </div>
          <div class="score-list">
            <span>向量分数：{{ formatScore(detailData.vector_score) }}</span>
            <span>重排分数：{{ formatScore(detailData.rerank_score) }}</span>
            <span>忠实度：{{ formatScore(detailData.faithfulness) }}</span>
            <span>回答相关度：{{ formatScore(detailData.answer_relevance) }}</span>
            <span>上下文精准度：{{ formatScore(detailData.context_precision) }}</span>
            <span>RAGAS：{{ formatRagasScore(detailData) }}</span>
          </div>
        </template>
        <div class="detail-meta">
          <span>{{ detailData.filename || evaluationTypeText(detailData.evaluation_type) }}</span>
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
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight, Search } from '@element-plus/icons-vue'
import {
  getEvaluationCases,
  getEvaluationList,
  getRAGEvaluationConfig,
  requeueRAGEvaluation,
  runEvaluationCase,
  updateRAGEvaluationConfig
} from '@/api'
import CustomPagination from '@/components/public/CustomPagination.vue'
import { useRoute } from 'vue-router'

const loading = ref(false)
const caseLoading = ref(false)
const route = useRoute()
const records = ref([])
const cases = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const statusFilter = ref('')
const activeType = ref('rag')
const showDetailDialog = ref(false)
const detailData = ref(null)
const caseSuiteType = ref('')
const runningCaseId = ref('')
const lastCaseRun = ref(null)
const caseSuiteOptions = [
  { label: '全部', value: '' },
  { label: 'MCP', value: 'mcp' },
  { label: 'Agent', value: 'agent' },
  { label: '组合流程', value: 'flow' }
]
const evaluationTypes = [
  { label: 'RAG 评估', value: 'rag' },
  { label: '正常回复评估', value: 'normal_reply' },
  { label: '长上下文评估', value: 'long_context' },
  { label: '工具调用评估', value: 'tool_call' },
  { label: '多 Agent 评估', value: 'multi_agent' }
]
const summary = ref({
  total: 0,
  completed_count: 0,
  pending_count: 0,
  queued_count: 0,
  running_count: 0,
  failed_count: 0,
  skipped_count: 0,
  avg_overall_score: 0,
  avg_retrieval_score: 0,
  avg_ragas_score: 0,
  type_counts: {}
})
const configForm = ref({
  evaluation_enabled: true,
  evaluation_sample_rate: 0.3,
  ragas_enabled: true,
  ragas_queue_enabled: true,
  ragas_min_retrieval_score: 0
})
const evaluationSamplePercent = computed({
  get: () => Math.round((Number(configForm.value.evaluation_sample_rate) || 0) * 100),
  set: (value) => {
    configForm.value.evaluation_sample_rate = Number((Number(value || 0) / 100).toFixed(2))
  }
})

const fetchRecords = async () => {
  loading.value = true
  try {
    const data = await getEvaluationList({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined,
      ragas_status: statusFilter.value || undefined,
      evaluation_id: route.query.evaluation_id || undefined,
      evaluation_type: activeType.value
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
      avg_overall_score: data.avg_overall_score || 0,
      avg_retrieval_score: data.avg_retrieval_score || 0,
      avg_ragas_score: data.avg_ragas_score || 0,
      type_counts: data.type_counts || {}
    }
  } catch (error) {
    ElMessage.error('获取评估记录失败')
  } finally {
    loading.value = false
  }
}

const fetchConfig = async () => {
  try {
    const data = await getRAGEvaluationConfig()
    configForm.value = {
      evaluation_enabled: data.evaluation_enabled ?? true,
      evaluation_sample_rate: data.evaluation_sample_rate ?? 0.3,
      ragas_enabled: data.ragas_enabled ?? true,
      ragas_queue_enabled: data.ragas_queue_enabled ?? true,
      ragas_min_retrieval_score: data.ragas_min_retrieval_score ?? 0
    }
  } catch (error) {
    ElMessage.error('获取评估配置失败')
  }
}

const fetchCases = async () => {
  caseLoading.value = true
  try {
    const data = await getEvaluationCases({
      suite_type: caseSuiteType.value || undefined,
      enabled: true
    })
    cases.value = data.items || []
  } catch (error) {
    ElMessage.error('获取固定测试集失败')
  } finally {
    caseLoading.value = false
  }
}

const saveConfig = async () => {
  try {
    await updateRAGEvaluationConfig({
      evaluation_enabled: configForm.value.evaluation_enabled,
      evaluation_sample_rate: configForm.value.evaluation_sample_rate,
      ragas_enabled: configForm.value.ragas_enabled,
      ragas_queue_enabled: configForm.value.ragas_queue_enabled,
      ragas_min_retrieval_score: configForm.value.ragas_min_retrieval_score
    })
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

const handleRunCase = async (row) => {
  runningCaseId.value = row.case_id
  try {
    const data = await runEvaluationCase(row.case_id)
    lastCaseRun.value = data
    ElMessage.success('执行完成')
    fetchRecords()
  } catch (error) {
    ElMessage.error('执行失败')
  } finally {
    runningCaseId.value = ''
  }
}

const changeType = (type) => {
  activeType.value = type
  currentPage.value = 1
  fetchRecords()
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

const evaluationTypeText = (type) => {
  const item = evaluationTypes.find((option) => option.value === type)
  return item ? item.label : '评估'
}

const suiteTypeText = (type) => {
  const map = {
    mcp: 'MCP',
    agent: 'Agent',
    flow: '组合'
  }
  return map[type] || '测试'
}

const caseTargetText = (row) => {
  const tools = Array.isArray(row.required_tools) ? row.required_tools.join('、') : ''
  return row.target_agent || tools || row.description || '-'
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
  fetchCases()
  fetchRecords()
})

watch(
  () => route.query.evaluation_id,
  () => {
    currentPage.value = 1
    fetchRecords()
  }
)
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

.evaluation-subnav {
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 16px;
  overflow-x: auto;
}

.subnav-item {
  height: 44px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  cursor: pointer;
  white-space: nowrap;
  font-size: 14px;
}

.subnav-item.active {
  border-bottom-color: var(--primary-color);
  color: var(--text-primary);
}

.subnav-item em {
  min-width: 24px;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(106, 99, 255, 0.16);
  color: var(--text-primary);
  font-style: normal;
  font-size: 12px;
  line-height: 20px;
  text-align: center;
}

.subnav-item.active em {
  background: var(--primary-color);
  color: #fff;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}

.case-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.case-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.case-panel-header h3 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 16px;
}

.case-panel-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.case-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.case-table {
  max-height: 260px;
  overflow: auto;
}

.case-run-summary {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.config-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, auto));
  align-items: center;
  gap: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.config-field {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.switch-field {
  min-width: 140px;
}

.wide-field {
  min-width: 280px;
  grid-column: span 2;
}

.wide-field :deep(.el-slider) {
  flex: 1;
  min-width: 180px;
}

.summary-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.summary-item strong {
  color: var(--text-primary);
  font-size: 18px;
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
