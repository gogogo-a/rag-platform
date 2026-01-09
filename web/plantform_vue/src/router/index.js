/**
 * Vue Router 配置
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store'

const routes = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/login/RegisterView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/chat/ChatView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/documents/3d',
    name: 'Document3D',
    component: () => import('@/views/admin/Document3DView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/qa-cache/3d',
    name: 'QACache3D',
    component: () => import('@/views/admin/QACache3DView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/documents/:id',
    name: 'DocumentDetail',
    component: () => import('@/views/admin/DocumentDetail.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin',
    name: 'Admin',
    redirect: '/admin/users',
    component: () => import('@/views/admin/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      {
        path: 'users',
        name: 'AdminUsers',
        component: () => import('@/views/admin/UserManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'documents',
        name: 'AdminDocuments',
        component: () => import('@/views/admin/DocumentManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'documents/:id',
        name: 'AdminDocumentDetail',
        component: () => import('@/views/admin/DocumentDetail.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'monitor',
        name: 'AdminMonitor',
        component: () => import('@/views/admin/MonitorManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'logs',
        name: 'AdminLogs',
        component: () => import('@/views/admin/LogManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      },
      {
        path: 'qa-cache',
        name: 'AdminQACache',
        component: () => import('@/views/admin/QACacheManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()

  // 检查是否需要登录
  if (to.meta.requiresAuth) {
    if (!userStore.isLoggedIn) {
      // 未登录，跳转到登录页
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      })
      return
    }

    // 检查是否需要管理员权限
    if (to.meta.requiresAdmin && !userStore.isAdmin) {
      // 不是管理员，跳转到聊天页
      next('/chat')
      return
    }
  }

  // 已登录用户访问登录页，跳转到聊天页
  if (to.path === '/login' && userStore.isLoggedIn) {
    next('/chat')
    return
  }

  next()
})

export default router

