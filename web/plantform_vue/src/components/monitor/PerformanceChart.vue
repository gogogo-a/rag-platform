<template>
  <div ref="chartRef" class="performance-chart"></div>
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
  },
  unit: {
    type: String,
    default: 'ms'
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
  if (!chartRef.value) return

  chartInstance?.dispose()
  const colors = getChartColors()
  
  chartInstance = echarts.init(chartRef.value, getChartTheme())
  
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
      },
      axisPointer: {
        type: 'cross',
        lineStyle: {
          color: '#6366f1',
          type: 'dashed'
        }
      },
      formatter: (params) => {
        if (!params || params.length === 0) return ''
        const param = params[0]
        const dataIndex = param.dataIndex
        const item = props.data[dataIndex]
        
        // 判断是否使用 s/10k tokens 作为主指标
        const useTokenMetric = props.unit === 's/10k tokens' && item.ms_per_10k_tokens !== undefined
        
        let tooltipText = `<div style="padding: 8px;">
          <div style="font-weight: bold; margin-bottom: 8px;">${param.axisValue}</div>
          <div style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="display: inline-block; width: 10px; height: 10px; background: #6366f1; border-radius: 50%; margin-right: 8px;"></span>`
        
        if (useTokenMetric) {
          tooltipText += `<span style="color: ${colors.muted};">每1万token: </span>
            <span style="color: ${colors.text}; font-weight: bold; margin-left: 8px;">${param.value.toFixed(4)} 秒</span>
          </div>`
          
          if (item.duration_s !== undefined) {
            tooltipText += `<div style="margin-left: 18px; color: ${colors.muted}; font-size: 12px;">
              耗时: ${item.duration_s.toFixed(3)} 秒
            </div>`
          }
          
          if (item.tokens_per_second !== undefined) {
            tooltipText += `<div style="margin-left: 18px; color: ${colors.muted}; font-size: 12px;">
              速度: ${item.tokens_per_second.toFixed(0)} tokens/s
            </div>`
          }
          
          if (item.metadata?.token_count !== undefined) {
            tooltipText += `<div style="margin-left: 18px; color: ${colors.muted}; font-size: 12px;">
              Token数: ${item.metadata.token_count}
            </div>`
          }
        } else {
          // 使用耗时作为主指标
          tooltipText += `<span style="color: ${colors.muted};">耗时: </span>
            <span style="color: ${colors.text}; font-weight: bold; margin-left: 8px;">${param.value.toFixed(3)} 秒</span>
          </div>`
          
          if (item.metadata?.status) {
            tooltipText += `<div style="margin-left: 18px; color: ${colors.muted}; font-size: 12px;">
              状态: ${item.metadata.status}
            </div>`
          }
        }
        
        tooltipText += '</div>'
        return tooltipText
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.data.map(item => {
        const time = new Date(item.timestamp)
        return `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}`
      }),
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
      name: props.unit,
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
        name: props.title,
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {
          width: 3,
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#6366f1' },
            { offset: 1, color: '#a855f7' }
          ])
        },
        itemStyle: {
          color: '#6366f1',
          borderColor: '#fff',
          borderWidth: 2
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(99, 102, 241, 0.4)' },
            { offset: 1, color: 'rgba(99, 102, 241, 0.05)' }
          ])
        },
        data: props.data.map(item => {
          // 只有当单位是 s/10k tokens 时才使用该指标（仅 embedding），将 ms 转换为 s
          if (props.unit === 's/10k tokens' && item.ms_per_10k_tokens !== undefined) {
            return parseFloat((item.ms_per_10k_tokens / 1000).toFixed(4))
          }
          // 其他情况使用耗时（秒）
          else if (item.duration_s !== undefined) {
            return item.duration_s
          } else if (item.duration_ms !== undefined) {
            return parseFloat((item.duration_ms / 1000).toFixed(3))
          }
          return 0
        })
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
.performance-chart {
  width: 100%;
  height: 300px;
}
</style>
