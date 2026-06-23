<template>
  <div class="log-management">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">
          <el-icon class="title-icon"><DocumentCopy /></el-icon>
          错误日志
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
          @click="fetchLogs"
          :loading="loading"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 统计概览 -->
    <div class="stats-overview">
      <div class="stat-card error-stat">
        <div class="stat-icon">
          <el-icon><Warning /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">总错误数</div>
          <div class="stat-value">{{ totalLogs }}</div>
        </div>
      </div>

      <div class="stat-card rate-stat">
        <div class="stat-icon">
          <el-icon><TrendCharts /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">错误率</div>
          <div class="stat-value">{{ errorRate }}%</div>
        </div>
      </div>

      <div class="stat-card time-stat">
        <div class="stat-icon">
          <el-icon><Clock /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">最近错误</div>
          <div class="stat-value">{{ lastErrorTime }}</div>
        </div>
      </div>
    </div>

    <!-- 日志列表 -->
    <div class="log-list-section">
      <div class="section-header">
        <h3>
          <el-icon><List /></el-icon>
          日志详情
        </h3>
        <div class="header-actions">
          <el-input
            v-model="searchText"
            placeholder="搜索日志..."
            :prefix-icon="Search"
            clearable
            class="search-input"
          />
        </div>
      </div>

      <div class="log-list">
        <div
          v-for="(log, index) in filteredLogs"
          :key="index"
          class="log-item"
          :class="{ 'log-expanded': expandedLogs.has(index) }"
          @click="toggleLogExpand(index)"
        >
          <div class="log-header">
            <div class="log-meta">
              <el-tag type="danger" size="small">{{ log.record?.level?.name || 'ERROR' }}</el-tag>
              <span class="log-time">{{ formatTime(log.record?.time?.repr || log.record?.time?.timestamp) }}</span>
            </div>
            <el-icon class="expand-icon" :class="{ 'is-expanded': expandedLogs.has(index) }">
              <ArrowDown />
            </el-icon>
          </div>
          
          <div class="log-message">
            {{ log.text || log.record?.message || 'N/A' }}
          </div>

          <transition name="log-detail-expand">
            <div v-show="expandedLogs.has(index)" class="log-detail">
              <div class="detail-section">
                <div class="detail-label">文件位置</div>
                <div class="detail-value">{{ log.record?.file?.path || log.record?.file?.name || 'N/A' }}:{{ log.record?.line || 'N/A' }}</div>
              </div>
              
              <div class="detail-section">
                <div class="detail-label">函数</div>
                <div class="detail-value">{{ log.record?.function || 'N/A' }}</div>
              </div>

              <div class="detail-section">
                <div class="detail-label">模块</div>
                <div class="detail-value">{{ log.record?.module || log.record?.name || 'N/A' }}</div>
              </div>

              <div v-if="log.record?.exception" class="detail-section exception-section">
                <div class="detail-label">堆栈跟踪</div>
                <pre class="exception-trace">{{ log.record.exception }}</pre>
              </div>

              <div class="detail-section">
                <div class="detail-label">完整记录</div>
                <pre class="record-json">{{ JSON.stringify(log.record, null, 2) }}</pre>
              </div>
            </div>
          </transition>
        </div>

        <div v-if="filteredLogs.length === 0" class="no-logs">
          <el-empty description="暂无错误日志" />
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="totalLogs > pageSize" class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="totalLogs"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Refresh, DocumentCopy, Warning, TrendCharts, Clock, List, Search, ArrowDown
} from '@element-plus/icons-vue'
import { getErrorLogs, getAvailableLogDates, getErrorStatistics } from '@/api/log'

const selectedDate = ref(null)
const loading = ref(false)
const logs = ref([])
const totalLogs = ref(0)
const currentPage = ref(1)
const pageSize = ref(50)
const searchText = ref('')
const expandedLogs = ref(new Set())
const statistics = ref(null) // 统计信息

const filteredLogs = computed(() => {
  if (!searchText.value) return logs.value
  const keyword = searchText.value.toLowerCase()
  return logs.value.filter(log => {
    const message = (log.text || log.record?.message || '').toLowerCase()
    const file = (log.record?.file?.path || log.record?.file?.name || '').toLowerCase()
    const func = (log.record?.function || '').toLowerCase()
    return message.includes(keyword) || file.includes(keyword) || func.includes(keyword)
  })
})

const errorRate = computed(() => {
  // 使用统计信息中的错误率
  if (statistics.value && statistics.value.error_rate !== undefined) {
    return statistics.value.error_rate.toFixed(2)
  }
  return '0.00'
})

const lastErrorTime = computed(() => {
  // 优先从统计信息中获取
  if (statistics.value && statistics.value.recent_errors && statistics.value.recent_errors.length > 0) {
    const firstError = statistics.value.recent_errors[0]
    return formatTime(firstError.timestamp || firstError.record?.time?.repr)
  }
  if (logs.value.length === 0) return '--'
  const latest = logs.value[0]
  return formatTime(latest.record?.time?.repr || latest.record?.time?.timestamp)
})

const toggleLogExpand = (index) => {
  if (expandedLogs.value.has(index)) {
    expandedLogs.value.delete(index)
  } else {
    expandedLogs.value.add(index)
  }
  // 强制更新
  expandedLogs.value = new Set(expandedLogs.value)
}

const formatTime = (timestamp) => {
  if (!timestamp) return '--'
  
  // 如果是字符串格式（如 "2025-10-26 10:56:27.140536+08:00"）
  if (typeof timestamp === 'string') {
    try {
      const date = new Date(timestamp)
      if (!isNaN(date.getTime())) {
        return date.toLocaleString('zh-CN', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        })
      }
      // 如果是特殊格式，直接返回前19个字符（YYYY-MM-DD HH:MM:SS）
      return timestamp.substring(0, 19).replace('T', ' ')
    } catch (e) {
      return timestamp
    }
  }
  
  // 如果是数字时间戳（秒或毫秒）
  if (typeof timestamp === 'number') {
    // 如果是秒级时间戳，转换为毫秒
    const ms = timestamp < 10000000000 ? timestamp * 1000 : timestamp
    const date = new Date(ms)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }
  
  return '--'
}

const handleDateChange = () => {
  currentPage.value = 1
  fetchLogs()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchLogs()
}

const handlePageChange = () => {
  fetchLogs()
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const offset = (currentPage.value - 1) * pageSize.value
    const res = await getErrorLogs(selectedDate.value, pageSize.value, offset)
    
    
    // request.js 拦截器已经返回了 res.data，所以直接使用
    logs.value = res.logs || []
    totalLogs.value = res.total || 0
  } catch (error) {
    ElMessage.error(`获取错误日志失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const fetchStatistics = async () => {
  try {
    const res = await getErrorStatistics()
    
    // request.js 拦截器已经返回了 res.data，所以直接使用
    statistics.value = res
  } catch (error) {
  }
}

onMounted(() => {
  fetchLogs()
  fetchStatistics()
})
</script>

<style scoped>
.log-management {
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
  color: var(--danger-color);
}

.toolbar-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.date-picker {
  width: 180px;
}

/* 统计概览 */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(239, 68, 68, 0.3);
  box-shadow: 0 8px 16px rgba(239, 68, 68, 0.1);
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 60px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger-color);
  font-size: 28px;
}

.rate-stat .stat-icon {
  background: rgba(245, 158, 11, 0.1);
  color: var(--warning-color);
}

.time-stat .stat-icon {
  background: rgba(99, 102, 241, 0.1);
  color: var(--primary-color);
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

/* 日志列表 */
.log-list-section {
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
  color: var(--danger-color);
}

.header-actions {
  display: flex;
  gap: 12px;
}

.search-input {
  width: 300px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.log-item {
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  transition: all 0.3s ease;
}

.log-item:hover {
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(255, 255, 255, 0.04);
}

.log-item.log-expanded {
  border-color: rgba(239, 68, 68, 0.5);
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.log-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.log-time {
  font-size: 13px;
  color: var(--text-secondary);
}

.expand-icon {
  font-size: 18px;
  color: var(--text-secondary);
  transition: transform 0.3s ease;
}

.expand-icon.is-expanded {
  transform: rotate(180deg);
}

.log-message {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  word-break: break-all;
}

.log-detail {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-section {
  margin-bottom: 12px;
}

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
  font-weight: 600;
}

.detail-value {
  font-size: 13px;
  color: var(--text-primary);
  font-family: 'Courier New', monospace;
}

.exception-section {
  margin-top: 16px;
}

.exception-trace,
.record-json {
  margin-top: 8px;
  padding: 12px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: #ef4444;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
}

.exception-trace {
  max-height: 400px;
  overflow-y: auto;
}

.record-json {
  color: var(--text-secondary);
  max-height: 500px;
  overflow-y: auto;
}

/* 滚动条样式 */
.record-json::-webkit-scrollbar,
.exception-trace::-webkit-scrollbar {
  width: 8px;
}

.record-json::-webkit-scrollbar-track,
.exception-trace::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.record-json::-webkit-scrollbar-thumb,
.exception-trace::-webkit-scrollbar-thumb {
  background: rgba(239, 68, 68, 0.3);
  border-radius: 4px;
}

.record-json::-webkit-scrollbar-thumb:hover,
.exception-trace::-webkit-scrollbar-thumb:hover {
  background: rgba(239, 68, 68, 0.5);
}

.log-detail-expand-enter-active,
.log-detail-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.log-detail-expand-enter-from,
.log-detail-expand-leave-to {
  max-height: 0;
  opacity: 0;
}

.log-detail-expand-enter-to,
.log-detail-expand-leave-from {
  max-height: 1000px;
  opacity: 1;
}

.no-logs {
  padding: 40px;
  text-align: center;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>

