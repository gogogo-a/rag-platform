import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const globalCss = readFileSync(join(rootDir, 'src/assets/css/global.css'), 'utf8')
const headerSource = readFileSync(join(rootDir, 'src/components/public/AppHeader.vue'), 'utf8')
const themeSource = readFileSync(join(rootDir, 'src/utils/theme.js'), 'utf8')
const resourceChartSource = readFileSync(join(rootDir, 'src/components/monitor/ResourceChart.vue'), 'utf8')
const performanceChartSource = readFileSync(join(rootDir, 'src/components/monitor/PerformanceChart.vue'), 'utf8')
const chatViewSource = readFileSync(join(rootDir, 'src/views/chat/ChatView.vue'), 'utf8')
const contextUsageButtonStyle = chatViewSource.match(/\.context-usage-button\s*\{[\s\S]*?\}/)?.[0] || ''

assert.match(themeSource, /THEME_STORAGE_KEY\s*=\s*'plantform-theme'/)
assert.match(themeSource, /applyTheme/)
assert.match(themeSource, /localStorage\.setItem\(THEME_STORAGE_KEY/)
assert.match(themeSource, /document\.documentElement/)
assert.match(themeSource, /classList\.toggle\('dark'/)
assert.match(themeSource, /classList\.toggle\('light'/)
assert.match(themeSource, /window\.dispatchEvent\(new CustomEvent\('plantform-theme-change'/)

assert.match(headerSource, /theme-toggle/)
assert.match(headerSource, /theme-toggle-track/)
assert.match(headerSource, /theme-toggle-thumb/)
assert.match(headerSource, /toggleTheme/)
assert.match(headerSource, /Sunny/)
assert.match(headerSource, /Moon/)

assert.match(globalCss, /html\.light/)
assert.match(globalCss, /html\.dark/)
assert.match(globalCss, /--header-bg/)
assert.match(globalCss, /--component-bg/)
assert.match(globalCss, /--table-row-bg/)
assert.match(globalCss, /--input-bg/)
assert.match(globalCss, /--overlay-bg/)
assert.match(globalCss, /--bg-secondary:\s*rgb\(252,\s*252,\s*252\)/)
assert.match(globalCss, /--component-bg:\s*rgb\(252,\s*252,\s*252\)/)
assert.match(globalCss, /--control-bg:\s*rgb\(252,\s*252,\s*252\)/)
assert.doesNotMatch(globalCss, /--control-bg:\s*var\(--control-bg\)/)
assert.doesNotMatch(globalCss, /--control-hover-bg:\s*var\(--control-hover-bg\)/)
assert.doesNotMatch(globalCss, /--control-border:\s*var\(--control-border\)/)
assert.doesNotMatch(globalCss, /--overlay-bg:\s*var\(--overlay-bg\)/)

assert.match(globalCss, /\.admin-main \.header-actions \.el-input__wrapper/)
assert.match(globalCss, /\.admin-main \.header-actions \.el-select__wrapper/)
assert.match(globalCss, /\.admin-main \.header-actions \.el-button\.el-button--default/)
assert.match(globalCss, /\.admin-main \.el-table \.el-table-fixed-column--right/)
assert.match(globalCss, /\.admin-main \.el-table \.el-button\.is-text/)
assert.match(globalCss, /\.admin-main \.el-input-number__decrease/)
assert.match(globalCss, /\.admin-main \.custom-pagination \.jump-input/)
assert.match(globalCss, /\.admin-main \.custom-pagination \.page-size-select/)
assert.match(globalCss, /\.admin-main \.custom-pagination \.page-btn/)

assert.match(chatViewSource, /context-usage-button/)
assert.match(contextUsageButtonStyle, /border-radius:\s*999px/)
assert.match(contextUsageButtonStyle, /var\(--component-muted-bg\)/)
assert.doesNotMatch(contextUsageButtonStyle, /border-radius:\s*50%/)
assert.doesNotMatch(contextUsageButtonStyle, /background:\s*rgba\(15,\s*23,\s*42,\s*0\.72\)/)

assert.match(resourceChartSource, /getCurrentTheme/)
assert.match(resourceChartSource, /plantform-theme-change/)
assert.match(resourceChartSource, /echarts\.init\(chartRef\.value,\s*getChartTheme\(\)\)/)
assert.match(performanceChartSource, /getCurrentTheme/)
assert.match(performanceChartSource, /plantform-theme-change/)
assert.match(performanceChartSource, /echarts\.init\(chartRef\.value,\s*getChartTheme\(\)\)/)

console.log('admin theme verified')
