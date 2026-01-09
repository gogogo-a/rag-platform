<template>
  <div id="app">
    <!-- 背景：如果性能有问题，可以将 ParticleBackground 替换为 SimpleBackground -->
    <!-- <SimpleBackground /> -->
    <ParticleBackground />
    
    <!-- 顶部导航 -->
    <AppHeader v-if="showHeader" />
    
    <!-- 主内容区 -->
    <main class="main-content" :class="{ 'no-header': !showHeader }">
      <router-view v-slot="{ Component, route }">
        <transition name="fade" mode="out-in">
          <keep-alive :include="['ChatView', 'Document3DView', 'QACache3DView']">
            <component :is="Component" :key="route.path" />
          </keep-alive>
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ParticleBackground from '@/components/public/ParticleBackground.vue'
// import SimpleBackground from '@/components/public/SimpleBackground.vue'  // 性能更好的备选背景
import AppHeader from '@/components/public/AppHeader.vue'

const route = useRoute()

// 登录和注册页面不显示 Header
const showHeader = computed(() => {
  return !['/login', '/register'].includes(route.path)
})
</script>

<style scoped>
#app {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-content {
  flex: 1;
  overflow: hidden;
  margin-top: 64px;
}

.main-content.no-header {
  margin-top: 0;
}

/* 路由过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
