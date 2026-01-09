<template>
  <header class="app-header">
    <div class="header-left">
      <div class="logo">
        <img src="/logo.png" alt="RAG Platform Logo" class="logo-icon" />
        <span class="logo-text gradient-text">RAG 智能问答平台</span>
      </div>
    </div>

    <div class="header-center">
      <nav class="nav-menu" v-if="userStore.isLoggedIn">
        <router-link 
          to="/chat" 
          class="nav-item"
          :class="{ active: $route.path === '/chat' }"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span>聊天</span>
        </router-link>
        
        <router-link 
          v-if="userStore.isAdmin"
          to="/admin/users" 
          class="nav-item"
          :class="{ active: $route.path.startsWith('/admin') }"
        >
          <el-icon><Setting /></el-icon>
          <span>管理</span>
        </router-link>
      </nav>
    </div>

    <div class="header-right">
      <div v-if="userStore.isLoggedIn" class="user-info">
        <el-dropdown trigger="click" @command="handleCommand">
          <div class="user-avatar">
            <el-avatar :size="36">
              <el-icon><User /></el-icon>
            </el-avatar>
            <span class="username">{{ userStore.nickname }}</span>
            <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>
                <div class="user-info-item">
                  <div class="label">昵称</div>
                  <div class="value">{{ userStore.nickname }}</div>
                </div>
              </el-dropdown-item>
              <el-dropdown-item disabled>
                <div class="user-info-item">
                  <div class="label">角色</div>
                  <div class="value">{{ userStore.isAdmin ? '管理员' : '普通用户' }}</div>
                </div>
              </el-dropdown-item>
              <el-dropdown-item divided command="profile">
                <el-icon><User /></el-icon>
                <span>个人设置</span>
              </el-dropdown-item>
              <el-dropdown-item command="logout">
                <el-icon><SwitchButton /></el-icon>
                <span>退出登录</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <router-link v-else to="/login" class="login-btn">
        <el-button type="primary">登录</el-button>
      </router-link>
    </div>
    
    <!-- 个人设置对话框 -->
    <el-dialog
      v-model="profileDialogVisible"
      title="个人设置"
      width="500px"
      :close-on-click-modal="false"
      append-to-body
      destroy-on-close
    >
      <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-width="80px">
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model="profileForm.nickname" placeholder="请输入昵称" />
        </el-form-item>
        
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="profileForm.email" placeholder="请输入邮箱" disabled />
        </el-form-item>
        
        <el-form-item label="头像">
          <el-input v-model="profileForm.avatar" placeholder="请输入头像 URL" />
        </el-form-item>
        
        <el-form-item label="性别">
          <el-radio-group v-model="profileForm.gender">
            <el-radio :label="0">男</el-radio>
            <el-radio :label="1">女</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="生日">
          <el-date-picker
            v-model="profileForm.birthday"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="profileDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleUpdateProfile">
          保存
        </el-button>
      </template>
    </el-dialog>
  </header>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore, useChatStore } from '@/store'
import { updateUserInfo } from '@/api'
import { ElMessage } from 'element-plus'
import { User, ArrowDown, SwitchButton, ChatDotRound, Setting } from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()

const profileDialogVisible = ref(false)
const updating = ref(false)
const profileFormRef = ref(null)

const profileForm = reactive({
  nickname: '',
  email: '',
  avatar: '',
  gender: 0,
  birthday: ''
})

const profileRules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 2, max: 50, message: '昵称长度在 2 到 50 个字符', trigger: 'blur' }
  ]
}

const handleCommand = (command) => {
  console.log('handleCommand called with:', command)
  if (command === 'logout') {
    // 清除用户数据
    userStore.logout()
    // 清除聊天数据
    chatStore.clearAll()
    ElMessage.success('已退出登录')
    router.push('/login')
  } else if (command === 'profile') {
    console.log('Opening profile dialog...')
    // 打开个人设置对话框
    profileForm.nickname = userStore.userInfo.nickname || ''
    profileForm.email = userStore.userInfo.email || ''
    profileForm.avatar = userStore.userInfo.avatar || ''
    profileForm.gender = userStore.userInfo.gender || 0
    profileForm.birthday = userStore.userInfo.birthday || ''
    profileDialogVisible.value = true
    console.log('profileDialogVisible set to:', profileDialogVisible.value)
  }
}

const handleUpdateProfile = async () => {
  if (!profileFormRef.value) return
  
  await profileFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    updating.value = true
    try {
      const userId = userStore.userInfo.uuid || userStore.userInfo.id
      await updateUserInfo(userId, {
        uuid: userId,  // 后端需要 uuid 字段
        nickname: profileForm.nickname,
        avatar: profileForm.avatar,
        gender: profileForm.gender,
        birthday: profileForm.birthday
      })
      
      // 刷新用户信息
      await userStore.refreshUserInfo()
      
      ElMessage.success('个人信息更新成功')
      profileDialogVisible.value = false
    } catch (error) {
      console.error('更新个人信息失败:', error)
      ElMessage.error('更新失败，请重试')
    } finally {
      updating.value = false
    }
  })
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 24px;
  background: rgba(21, 25, 50, 0.8);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border-color);
  position: relative;
  z-index: 100;
}

/* Logo */
.header-left {
  flex: 0 0 auto;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}

.logo-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: contain;
  animation: pulse 2s ease-in-out infinite;
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* 导航菜单 */
.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.nav-menu {
  display: flex;
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  color: var(--text-secondary);
  text-decoration: none;
  border-radius: 8px;
  transition: all 0.3s ease;
  font-size: 14px;
}

.nav-item:hover {
  color: var(--text-primary);
  background: rgba(99, 102, 241, 0.1);
}

.nav-item.active {
  color: var(--primary-color);
  background: rgba(99, 102, 241, 0.15);
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
}

/* 用户信息 */
.header-right {
  flex: 0 0 auto;
}

.user-info {
  display: flex;
  align-items: center;
}

.user-avatar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  cursor: pointer;
  border-radius: 20px;
  transition: all 0.3s ease;
}

.user-avatar:hover {
  background: rgba(99, 102, 241, 0.1);
}

.username {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
}

.dropdown-icon {
  color: var(--text-secondary);
  font-size: 12px;
}

.user-info-item {
  padding: 4px 0;
}

.user-info-item .label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 2px;
}

.user-info-item .value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.login-btn {
  text-decoration: none;
}

/* 个人设置对话框样式 */
:deep(.el-dialog) {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
}

:deep(.el-overlay) {
  z-index: 3000 !important;
}

:deep(.el-dialog__wrapper) {
  z-index: 3000 !important;
}

:deep(.el-dialog__header) {
  border-bottom: 1px solid var(--border-color);
}

:deep(.el-dialog__title) {
  color: var(--text-primary);
}

:deep(.el-dialog__body) {
  color: var(--text-primary);
}

:deep(.el-dialog__footer) {
  border-top: 1px solid var(--border-color);
}

:deep(.el-form-item__label) {
  color: var(--text-primary);
}

/* 日期选择器样式 */
:deep(.el-date-picker) {
  background-color: var(--bg-secondary) !important;
  border-color: var(--border-color) !important;
}

:deep(.el-date-picker .el-picker-panel__body) {
  background-color: var(--bg-secondary) !important;
}

:deep(.el-date-picker .el-date-table td.today .el-date-table-cell__text) {
  color: var(--primary-color) !important;
}

:deep(.el-date-picker .el-date-table td.current:not(.disabled) .el-date-table-cell__text) {
  background-color: var(--primary-color) !important;
  color: white !important;
}

:deep(.el-date-picker .el-date-table td .el-date-table-cell__text:hover) {
  background-color: rgba(64, 158, 255, 0.2) !important;
}
</style>

