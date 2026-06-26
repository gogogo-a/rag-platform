<template>
  <div ref="chartRef" class="resource-chart"></div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { getCurrentTheme } from '@/utils/theme'

const props = defineProps({
  title: {
    type: String,
    required: true
  },
  data: {
    type: Array,
    default: () => []
  }
})

const chartRef = ref(null)
let chartInstance = null
let resizeHandler = null

const getChartTheme = () => (getCurrentTheme() === 'dark' ? 'dark' : undefined)

const getChartColors = () => {
  const isDark = getCurrentTheme() === 'dark'
  return {
    text: isDark ? '#e2e8f0' : '#172033',
    muted: isDark ? '#94a3b8' : '#4b587c',
    border: isDark ? '#2d3250' : '#d8deef',
    tooltipBg: isDark ? 'rgba(20, 25, 47, 0.95)' : 'rgba(255, 255, 255, 0.98)'
  }
}

const initChart = () => {
  if (!chartRef.value || !props.data.length) return

  chartInstance?.dispose()
  const colors = getChartColors()
  
  chartInstance = echarts.init(chartRef.value, getChartTheme())
  
  const times = props.data.map(item => {
    const time = new Date(item.timestamp)
    return `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}`
  })
  
  const cpuData = props.data.map(item => item.system?.cpu_percent || 0)
  const memoryData = props.data.map(item => item.system?.memory_percent || 0)
  const diskData = props.data.map(item => item.system?.disk_percent || 0)
  
  const option = {
    backgroundColor: 'transparent',
    title: {
      text: props.title,
      left: 'center',
      textStyle: {
        color: colors.text,
        fontSize: 16,
        fontWeight: 'bold'
      }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.tooltipBg,
      borderColor: 'rgba(99, 102, 241, 0.5)',
      textStyle: {
        color: colors.text
      }
    },
    legend: {
      data: ['CPU', '内存', '磁盘'],
      bottom: 10,
      textStyle: {
        color: colors.muted
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: times,
      axisLine: {
        lineStyle: {
          color: colors.border
        }
      },
      axisLabel: {
        color: colors.muted,
        fontSize: 11
      }
    },
    yAxis: {
      type: 'value',
      name: '使用率 (%)',
      max: 100,
      nameTextStyle: {
        color: colors.muted
      },
      axisLine: {
        lineStyle: {
          color: colors.border
        }
      },
      axisLabel: {
        color: colors.muted,
        fontSize: 11
      },
      splitLine: {
        lineStyle: {
          color: colors.border,
          type: 'dashed'
        }
      }
    },
    series: [
      {
        name: 'CPU',
        type: 'line',
        smooth: true,
        data: cpuData,
        lineStyle: {
          width: 2,
          color: '#00d9ff'
        },
        itemStyle: {
          color: '#00d9ff'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(0, 217, 255, 0.3)' },
            { offset: 1, color: 'rgba(0, 217, 255, 0.05)' }
          ])
        }
      },
      {
        name: '内存',
        type: 'line',
        smooth: true,
        data: memoryData,
        lineStyle: {
          width: 2,
          color: '#a855f7'
        },
        itemStyle: {
          color: '#a855f7'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(168, 85, 247, 0.3)' },
            { offset: 1, color: 'rgba(168, 85, 247, 0.05)' }
          ])
        }
      },
      {
        name: '磁盘',
        type: 'line',
        smooth: true,
        data: diskData,
        lineStyle: {
          width: 2,
          color: '#10b981'
        },
        itemStyle: {
          color: '#10b981'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(16, 185, 129, 0.3)' },
            { offset: 1, color: 'rgba(16, 185, 129, 0.05)' }
          ])
        }
      }
    ]
  }
  
  chartInstance.setOption(option)
}

watch(() => props.data, () => {
  initChart()
}, { deep: true })

const handleThemeChange = () => {
  initChart()
}

onMounted(() => {
  initChart()
  resizeHandler = () => {
    chartInstance?.resize()
  }
  window.addEventListener('resize', resizeHandler)
  window.addEventListener('plantform-theme-change', handleThemeChange)
})

onUnmounted(() => {
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
  }
  window.removeEventListener('plantform-theme-change', handleThemeChange)
  chartInstance?.dispose()
})
</script>

<style scoped>
.resource-chart {
  width: 100%;
  height: 350px;
}
</style>
