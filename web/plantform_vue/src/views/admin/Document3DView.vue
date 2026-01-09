<template>
  <div class="document-3d-view" ref="containerRef">
    <!-- 返回按钮 -->
    <div class="back-button" @click="handleBack">
      <el-icon><ArrowLeft /></el-icon>
    </div>
    
    <!-- 搜索框 -->
    <div class="search-box">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索文档..."
        :prefix-icon="Search"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button 
        type="primary" 
        :icon="RefreshRight" 
        circle 
        @click="handleRefresh"
        title="刷新数据"
        class="refresh-btn"
      />
    </div>
    
    <!-- 文档信息卡片 -->
    <transition name="fade">
      <div 
        v-if="hoveredDoc" 
        class="doc-info-card"
        :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }"
      >
        <div class="doc-info-header">
          <span class="doc-type-icon" :style="{ background: getFileTypeColor(hoveredDoc.file_type) }">
            {{ hoveredDoc.file_type?.toUpperCase()?.slice(0, 3) }}
          </span>
          <span class="doc-filename">{{ hoveredDoc.filename }}</span>
        </div>
        <div class="doc-info-content">
          <p class="doc-preview">{{ hoveredDoc.text_preview || '暂无预览' }}</p>
        </div>
        <div class="doc-info-meta">
          <span class="meta-item">
            <el-icon><Clock /></el-icon>
            {{ formatDate(hoveredDoc.created_at) }}
          </span>
        </div>
      </div>
    </transition>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>正在加载 3D 场景...</p>
    </div>
    
    <!-- 统计信息 -->
    <div class="stats-info">
      <span>文档: {{ documents.length }}</span>
    </div>
    
    <!-- 图例 -->
    <div class="legend">
      <div class="legend-item" v-for="item in legendItems" :key="item.type">
        <span class="legend-shape" :class="item.shape" :style="{ background: item.color }"></span>
        <span>{{ item.label }}</span>
      </div>
    </div>
    
    <!-- Three.js 画布 -->
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<script setup>
// 组件名称，用于 keep-alive
defineOptions({
  name: 'Document3DView'
})

import { ref, onMounted, onUnmounted, shallowRef, onActivated, onDeactivated } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Search, Clock, RefreshRight } from '@element-plus/icons-vue'
import { getDocuments3D, refresh3DCache } from '@/api'
import { ElMessage } from 'element-plus'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const router = useRouter()

// 响应式数据
const containerRef = ref(null)
const canvasRef = ref(null)
const loading = ref(true)
const documents = ref([])
const searchKeyword = ref('')
const hoveredDoc = ref(null)
const tooltipPos = ref({ x: 0, y: 0 })

// 使用 shallowRef 避免 Three.js 对象被深度代理
const sceneRef = shallowRef(null)
const cameraRef = shallowRef(null)
const rendererRef = shallowRef(null)
const controlsRef = shallowRef(null)

// Three.js 变量（不需要响应式）
let animationId = null
let raycaster, mouse
let documentMeshes = []
let connectionLines = []
let flowParticles = []
let glowMeshes = []
let clock = new THREE.Clock()

// 文件类型配置 - 后端支持: pdf, docx, pptx, doc, ppt, txt, md, xlsx, csv, html, rtf, epub, json, xml
const fileTypeConfig = {
  // PDF - 立方体（稳固）
  pdf: { color: '#FF2E2E', shape: 'box', label: 'PDF' },
  // Word - 球体（通用）
  docx: { color: '#00A2FF', shape: 'sphere', label: 'Word' },
  doc: { color: '#00A2FF', shape: 'sphere', label: 'Word' },
  // Excel/CSV - 八面体（数据）
  xlsx: { color: '#10B981', shape: 'octahedron', label: 'Excel' },
  xls: { color: '#10B981', shape: 'octahedron', label: 'Excel' },
  csv: { color: '#10B981', shape: 'octahedron', label: 'CSV' },
  // PPT - 圆锥（演示）
  pptx: { color: '#FF8C00', shape: 'cone', label: 'PPT' },
  ppt: { color: '#FF8C00', shape: 'cone', label: 'PPT' },
  // 文本类 - 圆柱体
  txt: { color: '#A78BFA', shape: 'cylinder', label: 'TXT' },
  md: { color: '#34D399', shape: 'cylinder', label: 'MD' },
  // 网页/标记语言 - 十二面体
  html: { color: '#F472B6', shape: 'dodecahedron', label: 'HTML' },
  json: { color: '#FBBF24', shape: 'dodecahedron', label: 'JSON' },
  xml: { color: '#FB923C', shape: 'dodecahedron', label: 'XML' },
  // 电子书/富文本 - 环形
  epub: { color: '#8B5CF6', shape: 'torus', label: 'EPUB' },
  rtf: { color: '#EC4899', shape: 'torus', label: 'RTF' },
  // 默认 - 球体
  default: { color: '#94A3B8', shape: 'sphere', label: '其他' }
}

// 图例数据 - 主要类型
const legendItems = [
  { type: 'pdf', color: '#FF2E2E', shape: 'box', label: 'PDF' },
  { type: 'docx', color: '#00A2FF', shape: 'sphere', label: 'Word' },
  { type: 'xlsx', color: '#10B981', shape: 'octahedron', label: 'Excel' },
  { type: 'pptx', color: '#FF8C00', shape: 'cone', label: 'PPT' },
  { type: 'txt', color: '#A78BFA', shape: 'cylinder', label: 'TXT' },
  { type: 'default', color: '#94A3B8', shape: 'sphere', label: '其他' }
]

const getFileTypeColor = (type) => {
  return fileTypeConfig[type?.toLowerCase()]?.color || fileTypeConfig.default.color
}

const getFileTypeConfig = (type) => {
  return fileTypeConfig[type?.toLowerCase()] || fileTypeConfig.default
}

const formatDate = (dateStr) => {
  if (!dateStr) return '未知'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// 创建不同形状的几何体
const createGeometry = (shape) => {
  switch (shape) {
    case 'box':
      return new THREE.BoxGeometry(2.2, 2.2, 2.2)
    case 'sphere':
      return new THREE.SphereGeometry(1.4, 16, 16)
    case 'octahedron':
      return new THREE.OctahedronGeometry(1.6)
    case 'cone':
      return new THREE.ConeGeometry(1.3, 2.2, 8)
    case 'cylinder':
      return new THREE.CylinderGeometry(1.2, 1.2, 2, 12)
    case 'torus':
      return new THREE.TorusGeometry(1.1, 0.4, 8, 16)
    case 'dodecahedron':
      return new THREE.DodecahedronGeometry(1.4)
    default:
      return new THREE.SphereGeometry(1.4, 16, 16)
  }
}

// 初始化场景
const initScene = () => {
  const container = containerRef.value
  const canvas = canvasRef.value
  
  // 场景
  const scene = new THREE.Scene()
  // 使用透明背景，让 CSS 背景显示
  sceneRef.value = scene
  
  // 相机
  const camera = new THREE.PerspectiveCamera(
    60,
    container.clientWidth / container.clientHeight,
    0.1,
    500
  )
  camera.position.set(0, 30, 100)
  cameraRef.value = camera
  
  // 渲染器 - 优化性能
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false,
    alpha: true,  // 透明背景
    powerPreference: 'high-performance'
  })
  renderer.setSize(container.clientWidth, container.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
  renderer.setClearColor(0x000000, 0)  // 透明
  rendererRef.value = renderer
  
  // 控制器
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05
  controls.minDistance = 30
  controls.maxDistance = 250
  controls.autoRotate = true
  controls.autoRotateSpeed = 0.3
  controlsRef.value = controls
  
  // 射线检测
  raycaster = new THREE.Raycaster()
  mouse = new THREE.Vector2()
  
  // 光照
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.4)
  scene.add(ambientLight)
  
  const pointLight = new THREE.PointLight(0xffffff, 0.6, 300)
  pointLight.position.set(50, 50, 50)
  scene.add(pointLight)
  
  // 添加背景星空
  addStarField(scene)
  
  // 事件监听
  renderer.domElement.addEventListener('mousemove', onMouseMove)
  renderer.domElement.addEventListener('click', onMouseClick)
  window.addEventListener('resize', onWindowResize)
}

// 添加星空背景
const addStarField = (scene) => {
  const starCount = 300
  const positions = new Float32Array(starCount * 3)
  
  for (let i = 0; i < starCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 400
    positions[i * 3 + 1] = (Math.random() - 0.5) * 400
    positions[i * 3 + 2] = (Math.random() - 0.5) * 400
  }
  
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  
  const material = new THREE.PointsMaterial({
    color: 0x4a5568,
    size: 0.8,
    transparent: true,
    opacity: 0.6
  })
  
  const stars = new THREE.Points(geometry, material)
  scene.add(stars)
}

// 创建文档节点
const createDocumentNodes = () => {
  const scene = sceneRef.value
  if (!scene) return
  
  // 清除旧对象
  clearSceneObjects()
  
  if (documents.value.length === 0) return
  
  // 创建节点
  documents.value.forEach((doc, index) => {
    const config = getFileTypeConfig(doc.file_type)
    const color = new THREE.Color(config.color)
    
    // 主体几何体
    const geometry = createGeometry(config.shape)
    const material = new THREE.MeshLambertMaterial({
      color: color,
      transparent: true,
      opacity: 0.9
    })
    
    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.set(doc.x, doc.y, doc.z)
    mesh.userData = { doc, index, fileType: doc.file_type }
    
    scene.add(mesh)
    documentMeshes.push(mesh)
    
    // 辉光效果 - 使用简单的放大半透明网格
    const glowGeometry = createGeometry(config.shape)
    const glowMaterial = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.15
    })
    const glowMesh = new THREE.Mesh(glowGeometry, glowMaterial)
    glowMesh.position.copy(mesh.position)
    glowMesh.scale.setScalar(1.4)
    glowMesh.userData = { isGlow: true, parentIndex: index }
    scene.add(glowMesh)
    glowMeshes.push(glowMesh)
  })
  
  // 创建连线
  createConnectionLines()
}

// 创建连线（带流动粒子）
const createConnectionLines = () => {
  const scene = sceneRef.value
  const threshold = 30
  let lineCount = 0
  const maxLines = 80
  
  for (let i = 0; i < documentMeshes.length && lineCount < maxLines; i++) {
    for (let j = i + 1; j < documentMeshes.length && lineCount < maxLines; j++) {
      const mesh1 = documentMeshes[i]
      const mesh2 = documentMeshes[j]
      const distance = mesh1.position.distanceTo(mesh2.position)
      
      if (distance < threshold) {
        // 计算中间色
        const color1 = new THREE.Color(getFileTypeColor(mesh1.userData.fileType))
        const color2 = new THREE.Color(getFileTypeColor(mesh2.userData.fileType))
        const midColor = color1.clone().lerp(color2, 0.5)
        
        // 创建连线
        const points = [mesh1.position.clone(), mesh2.position.clone()]
        const geometry = new THREE.BufferGeometry().setFromPoints(points)
        const material = new THREE.LineBasicMaterial({
          color: midColor,
          transparent: true,
          opacity: 0.2 * (1 - distance / threshold)
        })
        const line = new THREE.Line(geometry, material)
        scene.add(line)
        connectionLines.push(line)
        
        // 创建流动粒子
        createFlowParticle(mesh1.position, mesh2.position, color1, color2)
        
        lineCount++
      }
    }
  }
}

// 创建流动粒子
const createFlowParticle = (start, end, color1, color2) => {
  const scene = sceneRef.value
  
  const geometry = new THREE.SphereGeometry(0.3, 4, 4)
  const material = new THREE.MeshBasicMaterial({
    color: color1,
    transparent: true,
    opacity: 0.8
  })
  
  const particle = new THREE.Mesh(geometry, material)
  particle.position.copy(start)
  particle.userData = {
    start: start.clone(),
    end: end.clone(),
    progress: Math.random(),
    speed: 0.002 + Math.random() * 0.002,
    color1: color1.clone(),
    color2: color2.clone()
  }
  
  scene.add(particle)
  flowParticles.push(particle)
}

// 更新流动粒子
const updateFlowParticles = () => {
  flowParticles.forEach(particle => {
    const data = particle.userData
    data.progress += data.speed
    if (data.progress > 1) data.progress = 0
    
    // 更新位置
    particle.position.lerpVectors(data.start, data.end, data.progress)
    
    // 更新颜色
    particle.material.color.copy(data.color1).lerp(data.color2, data.progress)
  })
}

// 更新辉光呼吸效果
const updateGlowEffect = (time) => {
  const breathe = 0.15 + Math.sin(time * 2) * 0.05
  glowMeshes.forEach(glow => {
    glow.material.opacity = breathe
  })
}

// 清除场景对象
const clearSceneObjects = () => {
  const scene = sceneRef.value
  
  documentMeshes.forEach(mesh => {
    scene.remove(mesh)
    mesh.geometry.dispose()
    mesh.material.dispose()
  })
  documentMeshes = []
  
  glowMeshes.forEach(mesh => {
    scene.remove(mesh)
    mesh.geometry.dispose()
    mesh.material.dispose()
  })
  glowMeshes = []
  
  connectionLines.forEach(line => {
    scene.remove(line)
    line.geometry.dispose()
    line.material.dispose()
  })
  connectionLines = []
  
  flowParticles.forEach(p => {
    scene.remove(p)
    p.geometry.dispose()
    p.material.dispose()
  })
  flowParticles = []
}

// 鼠标移动
const onMouseMove = (event) => {
  const renderer = rendererRef.value
  if (!renderer) return
  
  const rect = renderer.domElement.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  
  tooltipPos.value = { x: event.clientX + 15, y: event.clientY + 15 }
  
  raycaster.setFromCamera(mouse, cameraRef.value)
  const intersects = raycaster.intersectObjects(documentMeshes)
  
  if (intersects.length > 0) {
    const intersected = intersects[0].object
    const hoveredType = intersected.userData.fileType
    hoveredDoc.value = intersected.userData.doc
    
    // 停止自动旋转
    if (controlsRef.value) {
      controlsRef.value.autoRotate = false
    }
    
    // 同类型高亮，其他变暗
    documentMeshes.forEach((mesh, idx) => {
      const isSameType = mesh.userData.fileType === hoveredType
      mesh.material.opacity = isSameType ? 1 : 0.2
      mesh.scale.setScalar(mesh === intersected ? 1.3 : 1)
      
      // 辉光也同步
      if (glowMeshes[idx]) {
        glowMeshes[idx].material.opacity = isSameType ? 0.3 : 0.05
      }
    })
    
    renderer.domElement.style.cursor = 'pointer'
  } else {
    hoveredDoc.value = null
    
    // 恢复自动旋转
    if (controlsRef.value) {
      controlsRef.value.autoRotate = true
    }
    
    documentMeshes.forEach((mesh, idx) => {
      mesh.material.opacity = 0.9
      mesh.scale.setScalar(1)
      if (glowMeshes[idx]) {
        glowMeshes[idx].material.opacity = 0.15
      }
    })
    renderer.domElement.style.cursor = 'default'
  }
}

// 鼠标点击
const onMouseClick = () => {
  if (hoveredDoc.value) {
    router.push(`/admin/documents/${hoveredDoc.value.uuid}`)
  }
}

// 窗口大小变化
const onWindowResize = () => {
  const container = containerRef.value
  const camera = cameraRef.value
  const renderer = rendererRef.value
  if (!container || !camera || !renderer) return
  
  camera.aspect = container.clientWidth / container.clientHeight
  camera.updateProjectionMatrix()
  renderer.setSize(container.clientWidth, container.clientHeight)
}

// 动画循环
const animate = () => {
  animationId = requestAnimationFrame(animate)
  
  const time = clock.getElapsedTime()
  
  // 更新流动粒子
  updateFlowParticles()
  
  // 更新辉光呼吸
  updateGlowEffect(time)
  
  controlsRef.value?.update()
  rendererRef.value?.render(sceneRef.value, cameraRef.value)
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const data = await getDocuments3D({
      page: 1,
      page_size: 500,
      keyword: searchKeyword.value || undefined
    })
    
    documents.value = data.documents || []
    createDocumentNodes()
    
    if (documents.value.length === 0) {
      ElMessage.info('暂无文档数据')
    }
  } catch (error) {
    console.error('加载失败:', error)
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => loadData()

const handleRefresh = async () => {
  loading.value = true
  try {
    await refresh3DCache()
    await loadData()
    ElMessage.success('刷新成功')
  } catch (error) {
    ElMessage.error('刷新失败')
  }
}

const handleBack = () => router.push('/admin/documents')

// 清理
const cleanup = () => {
  if (animationId) cancelAnimationFrame(animationId)
  
  rendererRef.value?.domElement.removeEventListener('mousemove', onMouseMove)
  rendererRef.value?.domElement.removeEventListener('click', onMouseClick)
  window.removeEventListener('resize', onWindowResize)
  
  clearSceneObjects()
  rendererRef.value?.dispose()
  controlsRef.value?.dispose()
}

onMounted(async () => {
  initScene()
  animate()
  await loadData()
})

onUnmounted(() => cleanup())

// keep-alive 激活时恢复动画
onActivated(() => {
  if (sceneRef.value && !animationId) {
    animate()
  }
})

// keep-alive 停用时暂停动画
onDeactivated(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
    animationId = null
  }
})
</script>

<style scoped>
.document-3d-view {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: var(--bg-primary);
  overflow: hidden;
  z-index: 9999;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.back-button {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  color: #fff;
  cursor: pointer;
  transition: all 0.3s;
  z-index: 100;
}

.back-button:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.1);
}

.search-box {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  z-index: 100;
}

.search-box :deep(.el-input) {
  width: 260px;
}

.search-box :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.08) !important;
  border: 1px solid rgba(255, 255, 255, 0.15) !important;
}

.refresh-btn {
  background: rgba(255, 255, 255, 0.1) !important;
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
}

.doc-info-card {
  position: fixed;
  min-width: 260px;
  max-width: 320px;
  background: rgba(11, 14, 20, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  padding: 14px;
  backdrop-filter: blur(10px);
  z-index: 1000;
  pointer-events: none;
}

.doc-info-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.doc-type-icon {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
}

.doc-filename {
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-preview {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  line-height: 1.5;
  margin: 0 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
}

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(11, 14, 20, 0.9);
  z-index: 200;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255, 255, 255, 0.1);
  border-top-color: #00A2FF;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-overlay p {
  margin-top: 12px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
}

.stats-info {
  position: absolute;
  bottom: 20px;
  left: 20px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  z-index: 100;
}

.legend {
  position: absolute;
  bottom: 20px;
  right: 20px;
  display: flex;
  gap: 16px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  z-index: 100;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
}

.legend-shape {
  width: 14px;
  height: 14px;
}

.legend-shape.sphere { border-radius: 50%; }
.legend-shape.box { border-radius: 2px; }
.legend-shape.octahedron { 
  clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);
}
.legend-shape.cone {
  clip-path: polygon(50% 0%, 100% 100%, 0% 100%);
}
.legend-shape.cylinder {
  border-radius: 3px;
  height: 16px;
  width: 12px;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
