<template>
  <div class="qa-cache-3d-view" ref="containerRef">
    <!-- 返回按钮 -->
    <div class="back-button" @click="handleBack">
      <el-icon><ArrowLeft /></el-icon>
    </div>
    
    <!-- 搜索框 -->
    <div class="search-box">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索问题..."
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
    
    <!-- QA 信息卡片 -->
    <transition name="fade">
      <div 
        v-if="hoveredItem" 
        class="qa-info-card"
        :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }"
      >
        <div class="qa-info-header">
          <span class="qa-type-icon">Q</span>
          <span class="qa-question">{{ hoveredItem.question }}</span>
        </div>
        <div class="qa-info-content">
          <p class="qa-answer">{{ hoveredItem.answer_preview || '暂无预览' }}</p>
        </div>
        <div class="qa-info-meta">
          <span class="meta-item">
            <el-icon><Clock /></el-icon>
            {{ formatDate(hoveredItem.created_at) }}
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
      <span>QA 缓存: {{ items.length }}</span>
    </div>
    
    <!-- 图例 -->
    <div class="legend">
      <div class="legend-item">
        <span class="legend-shape sphere" style="background: #6366F1;"></span>
        <span>QA 缓存</span>
      </div>
    </div>
    
    <!-- Three.js 画布 -->
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<script setup>
// 组件名称，用于 keep-alive
defineOptions({
  name: 'QACache3DView'
})

import { ref, onMounted, onUnmounted, shallowRef, onActivated, onDeactivated } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Search, Clock, RefreshRight } from '@element-plus/icons-vue'
import { getQACache3D, refreshQACache3D } from '@/api'
import { ElMessage } from 'element-plus'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const router = useRouter()

// 响应式数据
const containerRef = ref(null)
const canvasRef = ref(null)
const loading = ref(true)
const items = ref([])
const searchKeyword = ref('')
const hoveredItem = ref(null)
const tooltipPos = ref({ x: 0, y: 0 })

// 使用 shallowRef 避免 Three.js 对象被深度代理
const sceneRef = shallowRef(null)
const cameraRef = shallowRef(null)
const rendererRef = shallowRef(null)
const controlsRef = shallowRef(null)

// Three.js 变量
let animationId = null
let raycaster, mouse
let qaMeshes = []
let connectionLines = []
let flowParticles = []
let glowMeshes = []
let clock = new THREE.Clock()

// QA 缓存颜色配置
const qaColor = '#6366F1'  // 紫色

const formatDate = (dateStr) => {
  if (!dateStr) return '未知'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// 初始化场景
const initScene = () => {
  const container = containerRef.value
  const canvas = canvasRef.value
  
  // 场景
  const scene = new THREE.Scene()
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
  
  // 渲染器
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false,
    alpha: true,
    powerPreference: 'high-performance'
  })
  renderer.setSize(container.clientWidth, container.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
  renderer.setClearColor(0x000000, 0)
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

// 创建 QA 节点
const createQANodes = () => {
  const scene = sceneRef.value
  if (!scene) return
  
  // 清除旧对象
  clearSceneObjects()
  
  if (items.value.length === 0) return
  
  const color = new THREE.Color(qaColor)
  
  // 创建节点
  items.value.forEach((item, index) => {
    // 主体几何体 - 球体
    const geometry = new THREE.SphereGeometry(1.4, 16, 16)
    const material = new THREE.MeshLambertMaterial({
      color: color,
      transparent: true,
      opacity: 0.9
    })
    
    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.set(item.x, item.y, item.z)
    mesh.userData = { item, index }
    
    scene.add(mesh)
    qaMeshes.push(mesh)
    
    // 辉光效果
    const glowGeometry = new THREE.SphereGeometry(1.4, 16, 16)
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

// 创建连线
const createConnectionLines = () => {
  const scene = sceneRef.value
  const threshold = 30
  let lineCount = 0
  const maxLines = 80
  
  const color = new THREE.Color(qaColor)
  
  for (let i = 0; i < qaMeshes.length && lineCount < maxLines; i++) {
    for (let j = i + 1; j < qaMeshes.length && lineCount < maxLines; j++) {
      const mesh1 = qaMeshes[i]
      const mesh2 = qaMeshes[j]
      const distance = mesh1.position.distanceTo(mesh2.position)
      
      if (distance < threshold) {
        // 创建连线
        const points = [mesh1.position.clone(), mesh2.position.clone()]
        const geometry = new THREE.BufferGeometry().setFromPoints(points)
        const material = new THREE.LineBasicMaterial({
          color: color,
          transparent: true,
          opacity: 0.2 * (1 - distance / threshold)
        })
        const line = new THREE.Line(geometry, material)
        scene.add(line)
        connectionLines.push(line)
        
        // 创建流动粒子
        createFlowParticle(mesh1.position, mesh2.position, color)
        
        lineCount++
      }
    }
  }
}

// 创建流动粒子
const createFlowParticle = (start, end, color) => {
  const scene = sceneRef.value
  
  const geometry = new THREE.SphereGeometry(0.3, 4, 4)
  const material = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    opacity: 0.8
  })
  
  const particle = new THREE.Mesh(geometry, material)
  particle.position.copy(start)
  particle.userData = {
    start: start.clone(),
    end: end.clone(),
    progress: Math.random(),
    speed: 0.002 + Math.random() * 0.002
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
    particle.position.lerpVectors(data.start, data.end, data.progress)
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
  
  qaMeshes.forEach(mesh => {
    scene.remove(mesh)
    mesh.geometry.dispose()
    mesh.material.dispose()
  })
  qaMeshes = []
  
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
  const intersects = raycaster.intersectObjects(qaMeshes)
  
  if (intersects.length > 0) {
    const intersected = intersects[0].object
    hoveredItem.value = intersected.userData.item
    
    // 停止自动旋转
    if (controlsRef.value) {
      controlsRef.value.autoRotate = false
    }
    
    // 高亮悬停节点
    qaMeshes.forEach((mesh, idx) => {
      const isHovered = mesh === intersected
      mesh.material.opacity = isHovered ? 1 : 0.4
      mesh.scale.setScalar(isHovered ? 1.3 : 1)
      
      if (glowMeshes[idx]) {
        glowMeshes[idx].material.opacity = isHovered ? 0.3 : 0.08
      }
    })
    
    renderer.domElement.style.cursor = 'pointer'
  } else {
    hoveredItem.value = null
    
    // 恢复自动旋转
    if (controlsRef.value) {
      controlsRef.value.autoRotate = true
    }
    
    qaMeshes.forEach((mesh, idx) => {
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
  if (hoveredItem.value) {
    // 可以跳转到详情或显示弹窗
    ElMessage.info(`问题: ${hoveredItem.value.question?.slice(0, 50)}...`)
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
  
  updateFlowParticles()
  updateGlowEffect(time)
  
  controlsRef.value?.update()
  rendererRef.value?.render(sceneRef.value, cameraRef.value)
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const data = await getQACache3D({
      page: 1,
      page_size: 500,
      keyword: searchKeyword.value || undefined
    })
    
    items.value = data.items || []
    createQANodes()
    
    if (items.value.length === 0) {
      ElMessage.info('暂无 QA 缓存数据')
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
    await refreshQACache3D()
    await loadData()
    ElMessage.success('刷新成功')
  } catch (error) {
    ElMessage.error('刷新失败')
  }
}

const handleBack = () => router.push('/admin/qa-cache')

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
.qa-cache-3d-view {
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

.qa-info-card {
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

.qa-info-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.qa-type-icon {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: #6366F1;
}

.qa-question {
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.qa-answer {
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
  border-top-color: #6366F1;
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

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
