<template>
  <div class="admin-layout">
    <!-- 左侧菜单 -->
    <aside class="admin-sidebar">
      <div class="sidebar-header">
        <h3 class="header-title gradient-text">管理中心</h3>
      </div>
      
      <el-menu
        :default-active="$route.path"
        router
        class="admin-menu"
        background-color="transparent"
        text-color="var(--text-secondary)"
        active-text-color="var(--primary-color)"
      >
        <el-menu-item index="/admin/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        
        <el-menu-item index="/admin/documents">
          <el-icon><Document /></el-icon>
          <span>文档管理</span>
        </el-menu-item>

        <el-menu-item index="/admin/qa-cache">
          <el-icon><ChatDotRound /></el-icon>
          <span>QA 缓存管理</span>
        </el-menu-item>

        <el-menu-item index="/admin/monitor">
          <el-icon><Monitor /></el-icon>
          <span>系统监控</span>
        </el-menu-item>

        <el-menu-item index="/admin/logs">
          <el-icon><DocumentCopy /></el-icon>
          <span>错误日志</span>
        </el-menu-item>
      </el-menu>
    </aside>

    <!-- 右侧内容区 -->
    <main class="admin-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { User, Document, Monitor, DocumentCopy, ChatDotRound } from '@element-plus/icons-vue'
</script>

<style scoped>
.admin-layout {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.admin-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid var(--border-color);
}

.header-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

.admin-menu {
  flex: 1;
  border: none;
  padding: 12px 0;
}

.admin-menu .el-menu-item {
  border-radius: 8px;
  margin: 0 12px 4px;
  transition: all 0.3s ease;
}

.admin-menu .el-menu-item:hover {
  background: rgba(99, 102, 241, 0.1);
}

.admin-menu .el-menu-item.is-active {
  background: rgba(99, 102, 241, 0.15);
  color: var(--primary-color);
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
}

.admin-main {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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

