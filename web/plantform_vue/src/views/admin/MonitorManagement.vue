<template>
  <div class="monitor-management">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">
          <el-icon class="title-icon"><Monitor /></el-icon>
          系统监控
        </h2>
      </div>
      <div class="toolbar-right">
        <el-date-picker
          v-model="selectedDate"
          type="date"
          placeholder="选择日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          @change="handleDateChange"
          class="date-picker"
        />
        <el-button
          type="primary"
          :icon="Refresh"
          @click="fetchAllData"
          :loading="loading"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 概览卡片 -->
    <div class="overview-cards">
      <div class="stat-card cpu-card">
        <div class="card-icon">
          <el-icon><Cpu /></el-icon>
        </div>
        <div class="card-content">
          <div class="card-label">CPU 使用率 (平均)</div>
          <div class="card-value">{{ displayCpuUsage }}%</div>
          <div class="card-sub">最大: {{ statistics?.resource_stats?.cpu?.max?.toFixed(1) || 0 }}%</div>
        </div>
        <div class="card-trend" :class="getTrendClass(statistics?.resource_stats?.cpu?.avg || latestResource?.system?.cpu_percent)">
          <el-icon><TrendCharts /></el-icon>
        </div>
      </div>

      <div class="stat-card memory-card">
        <div class="card-icon">
          <el-icon><Coin /></el-icon>
        </div>
        <div class="card-content">
          <div class="card-label">内存使用率 (平均)</div>
          <div class="card-value">{{ displayMemoryUsage }}%</div>
          <div class="card-sub">最大: {{ statistics?.resource_stats?.memory?.max?.toFixed(1) || 0 }}%</div>
        </div>
        <div class="card-trend" :class="getTrendClass(statistics?.resource_stats?.memory?.avg || latestResource?.system?.memory_percent)">
          <el-icon><TrendCharts /></el-icon>
        </div>
      </div>

      <div class="stat-card disk-card">
        <div class="card-icon">
          <el-icon><FolderOpened /></el-icon>
        </div>
        <div class="card-content">
          <div class="card-label">磁盘使用率 (当前)</div>
          <div class="card-value">{{ latestResource?.system?.disk_percent?.toFixed(1) || 0 }}%</div>
          <div class="card-sub">总计: {{ latestResource?.system?.disk_total_gb?.toFixed(1) || 0 }} GB</div>
        </div>
        <div class="card-trend" :class="getTrendClass(latestResource?.system?.disk_percent)">
          <el-icon><TrendCharts /></el-icon>
        </div>
      </div>

      <div class="stat-card response-card">
        <div class="card-icon">
          <el-icon><Timer /></el-icon>
        </div>
        <div class="card-content">
          <div class="card-label">监控记录数</div>
          <div class="card-value">{{ statistics?.resource_stats?.count || 0 }}</div>
          <div class="card-sub">今日: {{ statistics?.today_date || '--' }}</div>
        </div>
        <div class="card-trend trend-good">
          <el-icon><TrendCharts /></el-icon>
        </div>
      </div>
    </div>

    <!-- 资源监控图表 -->
    <div class="chart-section">
      <div class="section-header">
        <h3>
          <el-icon><DataAnalysis /></el-icon>
          资源监控
        </h3>
      </div>
      <div class="chart-container">
        <ResourceChart
          v-if="resourceData.length > 0"
          title="系统资源使用趋势"
          :data="resourceData"
        />
        <div v-else class="no-data">
          <el-empty description="暂无数据" />
        </div>
      </div>
    </div>

    <!-- 性能监控图表 -->
    <div class="chart-section">
      <div class="section-header">
        <h3>
          <el-icon><Odometer /></el-icon>
          性能监控
        </h3>
        <el-segmented v-model="activePerformanceType" :options="performanceTypeOptions" @change="handlePerformanceTypeChange" />
      </div>
      <div class="chart-grid">
        <div class="chart-item" v-for="type in visiblePerformanceTypes" :key="type.value">
          <PerformanceChart
            v-if="performanceData[type.value]?.length > 0"
            :title="type.label"
            :data="performanceData[type.value]"
            :unit="type.unit"
          />
          <div v-else class="no-data-small">
            <el-empty :image-size="80" description="暂无数据" />
          </div>
        </div>
      </div>
    </div>

    <!-- 数据库状态 -->
    <div class="database-section">
      <div class="section-header">
        <h3>
          <el-icon><Connection /></el-icon>
          数据库状态
        </h3>
      </div>
      <div class="database-cards">
        <div class="db-card">
          <div class="db-header">
            <el-icon class="db-icon mongodb-icon"><DataBoard /></el-icon>
            <span class="db-name">MongoDB</span>
            <el-tag :type="mongodbStatus === '正常' ? 'success' : 'danger'" size="small">
              {{ mongodbStatus }}
            </el-tag>
          </div>
          <div class="db-stats">
            <div class="db-stat">
              <span class="stat-label">当前连接数</span>
              <span class="stat-value">{{ latestResource?.mongodb?.connections_current || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">可用连接数</span>
              <span class="stat-value">{{ formatLargeNumber(latestResource?.mongodb?.connections_available || 0) }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">集合数</span>
              <span class="stat-value">{{ latestResource?.mongodb?.db_collections || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">文档数</span>
              <span class="stat-value">{{ latestResource?.mongodb?.db_documents || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">数据库大小</span>
              <span class="stat-value">{{ latestResource?.mongodb?.db_size_mb?.toFixed(2) || 0 }} MB</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">查询次数</span>
              <span class="stat-value">{{ latestResource?.mongodb?.opcounters_query || 0 }}</span>
            </div>
          </div>
        </div>

        <div class="db-card">
          <div class="db-header">
            <el-icon class="db-icon qdrant-icon"><Box /></el-icon>
            <span class="db-name">Qdrant</span>
            <el-tag type="success" size="small">
              正常
            </el-tag>
          </div>
          <div class="db-stats">
            <div class="db-stat">
              <span class="stat-label">检索次数</span>
              <span class="stat-value">{{ latestResource?.app_stats?.vector_total_searches || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">Embedding</span>
              <span class="stat-value">{{ latestResource?.app_stats?.embedding_total_calls || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">MongoDB 查询</span>
              <span class="stat-value">{{ latestResource?.app_stats?.mongodb_total_queries || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">LLM 调用</span>
              <span class="stat-value">{{ latestResource?.app_stats?.llm_total_calls || 0 }}</span>
            </div>
            <div class="db-stat">
              <span class="stat-label">LLM 错误</span>
              <span class="stat-value">{{ latestResource?.app_stats?.llm_total_errors || 0 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Refresh, Odometer, DataAnalysis, Monitor, Timer, TrendCharts,
  Connection, DataBoard, Box, Cpu, Coin, FolderOpened
} from '@element-plus/icons-vue'
import { getPerformanceMonitor, getResourceMonitor, getAllMonitors, getMonitorStatistics } from '@/api/monitor'
import PerformanceChart from '@/components/monitor/PerformanceChart.vue'
import ResourceChart from '@/components/monitor/ResourceChart.vue'
import { useUserStore } from '@/store'

const userStore = useUserStore()
const selectedDate = ref(null)
const loading = ref(false)
const resourceData = ref([])
const statistics = ref(null) // 统计信息
let refreshTimer = null // 定时器
const performanceData = reactive({
  embedding: [],
  vector_search: [],
  llm_think: [],
  llm_action: [],
  llm_answer: [],
  llm_total: [],
  agent_total: []
})

const activePerformanceType = ref('全部')
const performanceTypeOptions = [
  { label: '全部', value: '全部' },
  { label: 'Embedding', value: 'embedding' },
  { label: '向量检索', value: 'vector_search' },
  { label: 'LLM', value: 'llm' }
]

const performanceTypes = [
  { value: 'embedding', label: 'Embedding 性能', unit: 's/10k tokens' },
  { value: 'vector_search', label: '向量检索性能', unit: 's' },
  { value: 'llm_think', label: 'LLM 思考性能', unit: 's' },
  { value: 'llm_answer', label: 'LLM 答案性能', unit: 's' },
  { value: 'llm_total', label: 'LLM 总体性能', unit: 's' },
  { value: 'agent_total', label: 'Agent 总体性能', unit: 's' }
]

const visiblePerformanceTypes = computed(() => {
  if (activePerformanceType.value === '全部') {
    return performanceTypes
  } else if (activePerformanceType.value === 'llm') {
    return performanceTypes.filter(t => t.value.startsWith('llm'))
  } else {
    return performanceTypes.filter(t => t.value === activePerformanceType.value)
  }
})

const latestResource = computed(() => {
  // 优先使用统计数据中的 recent[0]，因为它包含完整的数据库状态信息
  if (statistics.value?.resource_stats?.recent && statistics.value.resource_stats.recent.length > 0) {
    return statistics.value.resource_stats.recent[0]
  }
  // 回退到 resourceData 的最后一条
  return resourceData.value.length > 0 ? resourceData.value[resourceData.value.length - 1] : null
})

const displayCpuUsage = computed(() => {
  // 优先使用统计数据的平均值
  if (statistics.value?.resource_stats?.cpu?.avg) {
    return statistics.value.resource_stats.cpu.avg.toFixed(1)
  }
  // 回退到最新资源数据
  return latestResource.value?.system?.cpu_percent?.toFixed(1) || 0
})

const displayMemoryUsage = computed(() => {
  // 优先使用统计数据的平均值
  if (statistics.value?.resource_stats?.memory?.avg) {
    return statistics.value.resource_stats.memory.avg.toFixed(1)
  }
  // 回退到最新资源数据
  return latestResource.value?.system?.memory_percent?.toFixed(1) || 0
})

const avgResponseTime = computed(() => {
  if (performanceData.agent_total.length === 0) return 0
  const sum = performanceData.agent_total.reduce((acc, item) => acc + (item.duration_ms || 0), 0)
  return (sum / performanceData.agent_total.length).toFixed(0)
})

const mongodbStatus = computed(() => {
  const status = latestResource.value?.mongodb?.status
  return status === 'healthy' ? '正常' : '异常'
})

const getTrendClass = (value) => {
  if (!value) return 'trend-good'
  if (value < 50) return 'trend-good'
  if (value < 80) return 'trend-warning'
  return 'trend-danger'
}

const formatLargeNumber = (num) => {
  if (!num) return '0'
  if (num >= 1000000) {
    return (num / 1000000).toFixed(2) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(2) + 'K'
  }
  return num.toString()
}

const handleDateChange = () => {
  fetchAllData()
}

const handlePerformanceTypeChange = () => {
  // 切换性能类型时自动调整
}

const fetchAllData = async () => {
  // 检查用户权限：必须有 token 且 is_admin 为 1
  if (!userStore.token || userStore.userInfo.is_admin !== 1) {
    return
  }
  
  loading.value = true
  try {
    // 获取资源监控数据
    const resourceRes = await getResourceMonitor(selectedDate.value, 50, 0)
    
    // 按时间戳排序，确保从旧到新（左到右递增）
    const rawData = resourceRes.data || []
    resourceData.value = rawData.sort((a, b) => {
      const timeA = new Date(a.timestamp).getTime()
      const timeB = new Date(b.timestamp).getTime()
      return timeA - timeB // 从旧到新
    })

    // 获取各类性能监控数据
    for (const type of performanceTypes) {
      // 再次检查权限（防止异步期间退出登录）
      if (!userStore.token || userStore.userInfo.is_admin !== 1) {
        return
      }
      
      const res = await getPerformanceMonitor(type.value, selectedDate.value, 50, 0)
      
      // 按时间戳排序，确保从旧到新（左到右递增）
      const rawPerf = res.data || []
      performanceData[type.value] = rawPerf.sort((a, b) => {
        const timeA = new Date(a.timestamp).getTime()
        const timeB = new Date(b.timestamp).getTime()
        return timeA - timeB // 从旧到新
      })
    }

  } catch (error) {
    // 检查权限，避免在无权限时显示错误消息
    if (!userStore.token || userStore.userInfo.is_admin !== 1) {
      return
    }
    ElMessage.error(`获取监控数据失败: ${error.message}`)
  } finally {
    // finally 中也要检查权限再更新 loading 状态
    if (userStore.token && userStore.userInfo.is_admin === 1) {
      loading.value = false
    }
  }
}

const fetchStatistics = async () => {
  // 检查用户权限：必须有 token 且 is_admin 为 1
  if (!userStore.token || userStore.userInfo.is_admin !== 1) {
    return
  }
  
  try {
    const res = await getMonitorStatistics()
    
    // request.js 拦截器已经返回了 res.data，所以直接使用
    statistics.value = res
  } catch (error) {
    // 检查权限，避免在无权限时显示错误消息
    if (!userStore.token || userStore.userInfo.is_admin !== 1) {
      return
    }
  }
}

// 启动定时器
const startTimer = () => {
  // 检查权限
  if (!userStore.token || userStore.userInfo.is_admin !== 1) {
    return
  }
  
  // 如果定时器已存在，先停止
  if (refreshTimer) {
    stopTimer()
  }
  
  // 每30秒刷新一次
  refreshTimer = setInterval(() => {
    // 再次检查权限
    if (!userStore.token || userStore.userInfo.is_admin !== 1) {
      stopTimer()
      return
    }
    
    fetchAllData()
    fetchStatistics()
  }, 30000)
  
}

// 停止定时器
const stopTimer = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  // 有权限时加载数据并启动定时器
  if (userStore.token && userStore.userInfo.is_admin === 1) {
    fetchAllData()
    fetchStatistics()
    startTimer()
  }
})

onBeforeUnmount(() => {
  // 组件卸载时停止定时器
  stopTimer()
})

// 监听权限变化
watch(
  () => [userStore.token, userStore.userInfo.is_admin],
  ([newToken, newIsAdmin]) => {
    if (!newToken || newIsAdmin !== 1) {
      // 权限失效，停止定时器
      stopTimer()
    } else if (!refreshTimer) {
      // 权限恢复且定时器未运行，启动定时器
      startTimer()
    }
  }
)
</script>

<style scoped>
.monitor-management {
  padding: 24px;
  padding-bottom: 150px; /* 增加底部间距，避免被导航栏遮挡 */
  min-height: 100vh;
  overflow-y: auto;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.toolbar-left {
  display: flex;
  align-items: center;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.title-icon {
  font-size: 28px;
  color: var(--neon-purple);
}

.toolbar-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.date-picker {
  width: 180px;
}

/* 性能筛选器暗色主题 */
:deep(.el-segmented) {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  padding: 2px !important;
}

:deep(.el-segmented__item-label) {
  color: var(--text-secondary) !important;
  font-size: 13px !important;
}

:deep(.el-segmented__item.is-selected .el-segmented__item-label) {
  color: var(--text-primary) !important;
}

:deep(.el-segmented__item-selected) {
  background: rgba(99, 102, 241, 0.2) !important;
  border: 1px solid rgba(99, 102, 241, 0.3) !important;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.2) !important;
}

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  position: relative;
  padding: 24px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  overflow: hidden;
  transition: all 0.3s ease;
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--neon-blue), var(--neon-purple));
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.3);
  box-shadow: 0 8px 16px rgba(99, 102, 241, 0.1);
}

.stat-card .card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  border-radius: 12px;
  margin-bottom: 12px;
  font-size: 24px;
}

.cpu-card .card-icon {
  background: rgba(0, 217, 255, 0.1);
  color: var(--neon-blue);
}

.memory-card .card-icon {
  background: rgba(168, 85, 247, 0.1);
  color: var(--neon-purple);
}

.disk-card .card-icon {
  background: rgba(16, 185, 129, 0.1);
  color: var(--success-color);
}

.response-card .card-icon {
  background: rgba(236, 72, 153, 0.1);
  color: var(--neon-pink);
}

.card-content {
  margin-bottom: 8px;
}

.card-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.card-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.card-sub {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 6px;
  opacity: 0.8;
}

.card-trend {
  position: absolute;
  top: 20px;
  right: 20px;
  font-size: 20px;
}

.trend-good {
  color: var(--success-color);
}

.trend-warning {
  color: var(--warning-color);
}

.trend-danger {
  color: var(--danger-color);
}

/* 图表区域 */
.chart-section {
  margin-bottom: 24px;
  padding: 24px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.section-header h3 .el-icon {
  font-size: 20px;
  color: var(--neon-purple);
}

.chart-container {
  min-height: 350px;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}

.chart-item {
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.03);
}

.no-data,
.no-data-small {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.no-data-small {
  min-height: 200px;
}

/* 数据库状态 */
.database-section {
  padding: 24px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.database-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.db-card {
  padding: 20px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  transition: all 0.3s ease;
}

.db-card:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.3);
}

.db-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.db-icon {
  font-size: 24px;
}

.mongodb-icon {
  color: #10b981;
}

.qdrant-icon {
  color: #00d9ff;
}

.db-name {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.db-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.db-stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.db-stat:hover {
  background: rgba(255, 255, 255, 0.05);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}
</style>

