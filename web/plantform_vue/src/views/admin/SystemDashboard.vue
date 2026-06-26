<template>
  <div class="system-dashboard" v-loading="loading">
    <div class="dashboard-header">
      <div>
        <h2 class="page-title">系统总览</h2>
        <p class="page-subtitle">文档、处理队列与运行状态</p>
      </div>
      <div class="header-actions">
        <span v-if="lastUpdated" class="updated-at">{{ lastUpdated }}</span>
        <el-button :icon="RefreshRight" :loading="loading" @click="fetchOverview">刷新</el-button>
      </div>
    </div>

    <section class="metric-grid">
      <div v-for="item in metrics" :key="item.label" class="metric-tile" :class="item.tone">
        <div class="metric-icon">
          <el-icon><component :is="item.icon" /></el-icon>
        </div>
        <div class="metric-copy">
          <span class="metric-label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <span class="metric-note">{{ item.note }}</span>
        </div>
      </div>
    </section>

    <section class="dashboard-grid">
      <div class="chart-panel chart-panel-trend">
        <div class="panel-head">
          <h3>文档块更新趋势</h3>
          <span>近 7 天</span>
        </div>
        <div ref="trendChartRef" class="chart-box"></div>
      </div>

      <div class="chart-panel chart-panel-type">
        <div class="panel-head">
          <h3>文档类型分布</h3>
          <span>{{ documents.document_total || 0 }} 个文档</span>
        </div>
        <div ref="typeChartRef" class="chart-box"></div>
      </div>

      <div class="chart-panel chart-panel-status">
        <div class="panel-head">
          <h3>处理状态</h3>
          <span>{{ summary.failed_documents || 0 }} 个失败</span>
        </div>
        <div ref="statusChartRef" class="chart-box"></div>
      </div>

      <div class="chart-panel chart-panel-topic">
        <div class="panel-head">
          <h3>任务分布</h3>
          <span>{{ kafka.unavailable ? '暂不可读' : `${summary.kafka_messages || 0} 条消息` }}</span>
        </div>
        <div ref="topicChartRef" class="chart-box"></div>
      </div>

      <div class="chart-panel chart-panel-partition">
        <div class="panel-head">
          <h3>分区负载</h3>
          <span>{{ kafka.unavailable ? '暂不可读' : `${summary.active_partitions || 0} 个活跃分区` }}</span>
        </div>
        <div ref="partitionChartRef" class="chart-box"></div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Collection, DataLine, Document, RefreshRight, Warning, Share } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboardOverview } from '@/api'
import { getCurrentTheme } from '@/utils/theme'

const loading = ref(false)
const overview = ref({})
const trendChartRef = ref(null)
const typeChartRef = ref(null)
const statusChartRef = ref(null)
const topicChartRef = ref(null)
const partitionChartRef = ref(null)
const charts = []

const summary = computed(() => overview.value.summary || {})
const documents = computed(() => overview.value.documents || {})
const kafka = computed(() => overview.value.kafka || {})
const hasOverview = computed(() => Boolean(overview.value.generated_at))

const formatNumber = (value) => Number(value || 0).toLocaleString('zh-CN')
const lastUpdated = computed(() => {
  if (!overview.value.generated_at) return ''
  const date = new Date(overview.value.generated_at)
  if (Number.isNaN(date.getTime())) return ''
  return `更新于 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
})

const metrics = computed(() => {
  const change = Number(summary.value.chunk_change || 0)
  return [
    {
      label: '文档总数',
      value: formatNumber(summary.value.document_total),
      note: '已纳入知识库',
      tone: 'neutral',
      icon: Document
    },
    {
      label: '文本块总数',
      value: formatNumber(summary.value.chunk_total),
      note: '可检索内容块',
      tone: 'info',
      icon: Collection
    },
    {
      label: '今日更新块',
      value: formatNumber(summary.value.today_updated_chunks),
      note: `${change >= 0 ? '+' : ''}${formatNumber(change)} 较昨日`,
      tone: change >= 0 ? 'positive' : 'negative',
      icon: DataLine
    },
    {
      label: '处理失败',
      value: formatNumber(summary.value.failed_documents),
      note: Number(summary.value.failed_documents || 0) > 0 ? '需要处理' : '运行正常',
      tone: Number(summary.value.failed_documents || 0) > 0 ? 'negative' : 'positive',
      icon: Warning
    },
    {
      label: '队列消息',
      value: formatNumber(summary.value.kafka_messages),
      note: kafka.value.unavailable ? '暂时无法读取' : `${formatNumber(summary.value.active_partitions)} 个活跃分区`,
      tone: kafka.value.unavailable ? 'muted' : 'info',
      icon: Share
    }
  ]
})

const palette = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316', '#64748b']

const theme = () => {
  const dark = getCurrentTheme() === 'dark'
  return {
    text: dark ? '#e5edf8' : '#162033',
    muted: dark ? '#91a0b8' : '#667085',
    line: dark ? 'rgba(148, 163, 184, 0.18)' : 'rgba(15, 23, 42, 0.1)',
    panel: dark ? 'rgba(15, 23, 42, 0.94)' : 'rgba(255, 255, 255, 0.96)'
  }
}

const chartBase = () => {
  const colors = theme()
  return {
    backgroundColor: 'transparent',
    color: palette,
    textStyle: { color: colors.text },
    tooltip: {
      trigger: 'item',
      backgroundColor: colors.panel,
      borderColor: 'rgba(59, 130, 246, 0.35)',
      borderWidth: 1,
      textStyle: { color: colors.text }
    }
  }
}

const emptyOption = (text) => ({
  ...chartBase(),
  title: {
    text,
    left: 'center',
    top: 'middle',
    textStyle: {
      color: theme().muted,
      fontSize: 14,
      fontWeight: 500
    }
  }
})

const disposeCharts = () => {
  while (charts.length) {
    charts.pop()?.dispose()
  }
}

const createChart = (el, option) => {
  if (!el) return
  const chart = echarts.init(el, getCurrentTheme() === 'dark' ? 'dark' : undefined)
  chart.setOption(option)
  charts.push(chart)
}

const renderCharts = async () => {
  await nextTick()
  disposeCharts()
  const colors = theme()
  const trend = documents.value.chunk_trend || []
  const typeData = documents.value.type_distribution || []
  const statusData = documents.value.status_distribution || []
  const topicData = kafka.value.topic_distribution || []
  const partitionData = kafka.value.partition_heatmap || []

  createChart(trendChartRef.value, trend.length ? {
    ...chartBase(),
    grid: { top: 22, left: 52, right: 22, bottom: 34 },
    tooltip: { ...chartBase().tooltip, trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: trend.map(item => item.date),
      axisLine: { lineStyle: { color: colors.line } },
      axisLabel: { color: colors.muted }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: colors.line, type: 'dashed' } },
      axisLabel: { color: colors.muted }
    },
    series: [{
      type: 'line',
      smooth: true,
      symbolSize: 8,
      data: trend.map(item => item.chunks),
      lineStyle: { width: 4, color: '#3b82f6' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(59, 130, 246, 0.34)' },
          { offset: 1, color: 'rgba(59, 130, 246, 0.02)' }
        ])
      }
    }]
  } : emptyOption('暂无更新数据'))

  createChart(typeChartRef.value, typeData.length ? {
    ...chartBase(),
    legend: {
      bottom: 0,
      left: 'center',
      itemWidth: 12,
      itemHeight: 8,
      itemGap: 10,
      textStyle: { color: colors.muted, fontSize: 11 }
    },
    series: [{
      type: 'pie',
      radius: ['48%', '68%'],
      center: ['50%', '42%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{d}%', color: colors.text, fontSize: 11 },
      labelLine: { length: 10, length2: 10 },
      itemStyle: { borderRadius: 8, borderColor: colors.panel, borderWidth: 2 },
      data: typeData
    }]
  } : emptyOption('暂无文档数据'))

  createChart(statusChartRef.value, statusData.length ? {
    ...chartBase(),
    radar: {
      center: ['50%', '52%'],
      radius: '58%',
      indicator: statusData.map(item => ({ name: item.name, max: Math.max(...statusData.map(row => row.value), 1) })),
      axisName: { color: colors.muted, fontSize: 11 },
      splitLine: { lineStyle: { color: colors.line } },
      splitArea: { areaStyle: { color: ['rgba(59,130,246,0.06)', 'rgba(16,185,129,0.04)'] } }
    },
    series: [{
      type: 'radar',
      areaStyle: { color: 'rgba(16, 185, 129, 0.22)' },
      lineStyle: { color: '#10b981', width: 3 },
      data: [{ value: statusData.map(item => item.value), name: '处理状态' }]
    }]
  } : emptyOption('暂无处理数据'))

  createChart(topicChartRef.value, topicData.length ? {
    ...chartBase(),
    grid: { top: 18, left: 92, right: 18, bottom: 26 },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: colors.line, type: 'dashed' } },
      axisLabel: { color: colors.muted }
    },
    yAxis: {
      type: 'category',
      data: topicData.map(item => item.name).reverse(),
      axisLine: { lineStyle: { color: colors.line } },
      axisLabel: { color: colors.muted }
    },
    series: [{
      type: 'bar',
      data: topicData.map(item => item.value).reverse(),
      barWidth: 14,
      itemStyle: {
        borderRadius: [0, 10, 10, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#14b8a6' },
          { offset: 1, color: '#3b82f6' }
        ])
      }
    }]
  } : emptyOption(kafka.value.message || '暂无任务数据'))

  const partitionTopics = [...new Set(partitionData.map(item => item.topic))]
  const partitionNames = [...new Set(partitionData.map(item => item.partition))]
  createChart(partitionChartRef.value, partitionData.length ? {
    ...chartBase(),
    grid: { top: 18, left: 116, right: 24, bottom: 34 },
    tooltip: {
      ...chartBase().tooltip,
      formatter: (params) => {
        const item = partitionData[params.dataIndex] || {}
        return `${item.topic} ${item.partition}<br/>消息数：${formatNumber(item.messages)}`
      }
    },
    xAxis: {
      type: 'category',
      data: partitionNames,
      axisLabel: { color: colors.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: colors.line } }
    },
    yAxis: {
      type: 'category',
      data: partitionTopics,
      axisLabel: { color: colors.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: colors.line } }
    },
    visualMap: {
      min: 0,
      max: Math.max(...partitionData.map(item => item.messages), 1),
      show: false,
      inRange: { color: ['rgba(59,130,246,0.12)', '#3b82f6', '#f59e0b'] }
    },
    series: [{
      type: 'heatmap',
      data: partitionData.map((item) => [
        partitionNames.indexOf(item.partition),
        partitionTopics.indexOf(item.topic),
        item.messages
      ]),
      itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: getCurrentTheme() === 'dark' ? '#111827' : '#ffffff' },
      emphasis: { itemStyle: { borderColor: '#111827', borderWidth: 1 } }
    }]
  } : emptyOption(kafka.value.message || '暂无分区数据'))
}

const fetchOverview = async () => {
  loading.value = true
  try {
    overview.value = await getDashboardOverview()
    await renderCharts()
  } catch (error) {
    if (!hasOverview.value) {
      await renderCharts()
    }
    ElMessage.error('系统总览暂时无法读取')
  } finally {
    loading.value = false
  }
}

const resizeCharts = () => charts.forEach(chart => chart.resize())
const handleThemeChange = () => renderCharts()

onMounted(() => {
  fetchOverview()
  window.addEventListener('resize', resizeCharts)
  window.addEventListener('plantform-theme-change', handleThemeChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  window.removeEventListener('plantform-theme-change', handleThemeChange)
  disposeCharts()
})
</script>

<style scoped>
.system-dashboard {
  height: 100%;
  overflow-y: auto;
  padding: 24px 28px;
  background: var(--bg-primary);
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-color);
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0;
}

.page-subtitle {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.updated-at {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.metric-tile,
.chart-panel {
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
}

.metric-tile {
  min-height: 110px;
  border-radius: 8px;
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.metric-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: #2563eb;
  background: rgba(37, 99, 235, 0.10);
}

.metric-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.metric-label {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.metric-tile strong {
  font-size: 30px;
  line-height: 1;
  color: var(--text-primary);
  letter-spacing: 0;
}

.metric-note {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.metric-tile.positive .metric-icon {
  color: #059669;
  background: rgba(5, 150, 105, 0.10);
}

.metric-tile.positive .metric-note {
  color: #10b981;
}

.metric-tile.negative .metric-icon {
  color: #dc2626;
  background: rgba(220, 38, 38, 0.10);
}

.metric-tile.negative .metric-note {
  color: #ef4444;
}

.metric-tile.info .metric-icon {
  color: #0f766e;
  background: rgba(15, 118, 110, 0.10);
}

.metric-tile.muted .metric-icon {
  color: var(--text-secondary);
  background: var(--component-hover-bg);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-auto-flow: dense;
  gap: 18px;
  align-items: stretch;
}

.chart-panel {
  border-radius: 8px;
  min-height: 344px;
  padding: 18px;
  display: flex;
  flex-direction: column;
}

.chart-panel-trend {
  grid-column: span 6;
}

.chart-panel-type,
.chart-panel-status {
  grid-column: span 3;
}

.chart-panel-topic {
  grid-column: span 4;
}

.chart-panel-partition {
  grid-column: span 8;
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-height: 24px;
  margin-bottom: 12px;
}

.panel-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: 0;
}

.panel-head span {
  font-size: 12px;
  color: var(--text-secondary);
}

.chart-box {
  height: 288px;
  min-width: 0;
  flex: 1;
}

@media (max-width: 1280px) {
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .dashboard-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .chart-panel-trend,
  .chart-panel-partition {
    grid-column: span 6;
  }

  .chart-panel-type,
  .chart-panel-status,
  .chart-panel-topic {
    grid-column: span 3;
  }

  .chart-panel-partition {
    grid-column: span 6;
  }
}

@media (max-width: 760px) {
  .system-dashboard {
    padding: 16px;
  }

  .dashboard-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .metric-grid,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .chart-panel-trend,
  .chart-panel-type,
  .chart-panel-status,
  .chart-panel-topic,
  .chart-panel-partition {
    grid-column: span 1;
  }

  .metric-tile {
    min-height: 96px;
  }
}
</style>
