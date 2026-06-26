<template>
  <div class="particle-background">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)
let animationId = null
let particles = []

// 粒子类
class Particle {
  constructor(canvas) {
    this.canvas = canvas
    this.reset()
  }

  reset() {
    this.x = Math.random() * this.canvas.width
    this.y = Math.random() * this.canvas.height
    this.vx = (Math.random() - 0.5) * 0.5
    this.vy = (Math.random() - 0.5) * 0.5
    this.radius = Math.random() * 2 + 1
    this.opacity = Math.random() * 0.5 + 0.2
    this.color = this.randomColor()
  }

  randomColor() {
    const colors = [
      'rgba(0, 217, 255, ',  // neon blue
      'rgba(168, 85, 247, ', // neon purple
      'rgba(236, 72, 153, '  // neon pink
    ]
    return colors[Math.floor(Math.random() * colors.length)]
  }

  update() {
    this.x += this.vx
    this.y += this.vy

    // 边界检测
    if (this.x < 0 || this.x > this.canvas.width) {
      this.vx *= -1
    }
    if (this.y < 0 || this.y > this.canvas.height) {
      this.vy *= -1
    }
  }

  draw(ctx) {
    ctx.beginPath()
    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2)
    ctx.fillStyle = this.color + this.opacity + ')'
    ctx.fill()

    // 发光效果
    ctx.shadowBlur = 10
    ctx.shadowColor = this.color + '0.8)'
  }
}

// 初始化画布
const initCanvas = () => {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  
  // 设置画布大小
  const resizeCanvas = () => {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
  }
  
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)

  // 创建粒子（减少数量以提升性能）
  const particleCount = 50  // 从 100 减少到 50
  particles = []
  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle(canvas))
  }

  // 动画循环
  const animate = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 更新和绘制粒子
    particles.forEach(particle => {
      particle.update()
      particle.draw(ctx)
    })

    // 连接距离近的粒子（优化：减少连接距离，降低计算量）
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (distance < 120) {  // 从 150 减少到 120
          ctx.beginPath()
          ctx.moveTo(particles[i].x, particles[i].y)
          ctx.lineTo(particles[j].x, particles[j].y)
          ctx.strokeStyle = `rgba(99, 102, 241, ${0.15 * (1 - distance / 120)})`  // 降低透明度
          ctx.lineWidth = 0.5
          ctx.stroke()
        }
      }
    }

    animationId = requestAnimationFrame(animate)
  }

  animate()

  // 清理函数
  return () => {
    window.removeEventListener('resize', resizeCanvas)
    if (animationId) {
      cancelAnimationFrame(animationId)
    }
  }
}

onMounted(() => {
  const cleanup = initCanvas()
  
  onUnmounted(() => {
    if (cleanup) cleanup()
  })
})
</script>

<style scoped>
.particle-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: -1;
  background:
    linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 52%, var(--bg-tertiary) 100%);
  overflow: hidden;
}

html.light .particle-background canvas {
  opacity: 0.18;
}

html.dark .particle-background canvas {
  opacity: 1;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
