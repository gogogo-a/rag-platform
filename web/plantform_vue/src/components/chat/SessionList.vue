<template>
  <div class="session-list">
    <div class="session-header">
      <h3 class="header-title">会话列表</h3>
      <el-button
        type="primary"
        size="small"
        :icon="Plus"
        @click="handleNewSession"
        class="new-session-btn"
      >
        新会话
      </el-button>
    </div>

    <div class="session-content">
      <LoadingSpinner v-if="chatStore.loading && sessionList.length === 0" text="加载中..." />
      
      <EmptyState
        v-else-if="!chatStore.loading && sessionList.length === 0"
        :icon="ChatDotRound"
        text="暂无会话"
        subtext="点击上方按钮创建新会话"
      />

      <div v-else class="session-items">
        <div
          v-for="session in sessionList"
          :key="session.uuid || session.id"
          class="session-item"
          :class="{ active: (session.uuid || session.id) === chatStore.currentSessionId }"
        >
          <div class="session-icon" @click="handleSelectSession(session.uuid || session.id)">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <div class="session-info" @click="handleSelectSession(session.uuid || session.id)">
            <div class="session-name">{{ session.name || session.session_name || '新会话' }}</div>
            <div class="session-last-message">{{ session.last_message || '暂无消息' }}</div>
          </div>
          <div class="session-actions" @click.stop>
            <el-dropdown @command="(command) => handleSessionAction(command, session)">
              <el-icon class="action-icon"><More /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">
                    <el-icon><Edit /></el-icon>
                    <span>重命名</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <el-icon><Delete /></el-icon>
                    <span style="color: #f56c6c;">删除</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 重命名对话框 -->
    <el-dialog
      v-model="renameDialogVisible"
      title="重命名会话"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form>
        <el-form-item label="会话名称">
          <el-input
            v-model="renameForm.name"
            placeholder="请输入会话名称"
            maxlength="50"
            show-word-limit
            @keyup.enter="handleRenameSession"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleRenameSession">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useUserStore, useChatStore } from '@/store'
import { Plus, ChatDotRound, More, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import LoadingSpinner from '@/components/public/LoadingSpinner.vue'
import EmptyState from '@/components/public/EmptyState.vue'
import { updateSession, deleteSession } from '@/api/session'

const userStore = useUserStore()
const chatStore = useChatStore()

const sessionList = computed(() => chatStore.sessionList)

// 重命名对话框
const renameDialogVisible = ref(false)
const renameForm = ref({
  sessionId: '',
  name: ''
})
const renamingSession = ref(null)

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date
  
  // 一分钟内
  if (diff < 60000) {
    return '刚刚'
  }
  // 一小时内
  if (diff < 3600000) {
    return `${Math.floor(diff / 60000)}分钟前`
  }
  // 一天内
  if (diff < 86400000) {
    return `${Math.floor(diff / 3600000)}小时前`
  }
  // 显示日期
  return `${date.getMonth() + 1}/${date.getDate()}`
}

// 选择会话
const handleSelectSession = (sessionId) => {
  chatStore.switchSession(sessionId)
}

// 创建新会话
const handleNewSession = () => {
  // 清空当前会话 ID，下次发送消息时会自动创建新会话
  chatStore.currentSessionId = ''
  chatStore.clearCurrentMessages()
}

// 处理会话操作
const handleSessionAction = (command, session) => {
  const sessionId = session.uuid || session.id
  
  if (command === 'rename') {
    // 重命名会话
    renamingSession.value = session
    renameForm.value = {
      sessionId: sessionId,
      name: session.name || session.session_name || '新会话'
    }
    renameDialogVisible.value = true
  } else if (command === 'delete') {
    // 删除会话
    handleDeleteSession(session)
  }
}

// 删除会话
const handleDeleteSession = async (session) => {
  const sessionId = session.uuid || session.id
  const sessionName = session.name || session.session_name || '新会话'
  
  try {
    await ElMessageBox.confirm(
      `确定要删除会话「${sessionName}」吗？删除后该会话下的所有聊天记录将被清除，此操作不可恢复。`,
      '删除会话',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    
    // 调用删除 API
    const res = await deleteSession(sessionId)
    
    // API 成功时直接返回（拦截器已处理错误情况）
    ElMessage.success('删除成功')
    
    // 刷新页面
    window.location.reload()
  } catch (error) {
    // 用户取消删除
    if (error !== 'cancel') {
      console.error('删除会话失败:', error)
      ElMessage.error('删除失败，请重试')
    }
  }
}

// 重命名会话
const handleRenameSession = async () => {
  if (!renameForm.value.name.trim()) {
    ElMessage.warning('会话名称不能为空')
    return
  }
  
  try {
    await updateSession(renameForm.value.sessionId, {
      uuid: renameForm.value.sessionId,
      name: renameForm.value.name.trim()
    })
    
    ElMessage.success('重命名成功')
    
    // 更新本地会话列表
    const session = sessionList.value.find(
      s => (s.uuid || s.id) === renameForm.value.sessionId
    )
    if (session) {
      session.name = renameForm.value.name.trim()
      if (session.session_name !== undefined) {
        session.session_name = renameForm.value.name.trim()
      }
    }
    
    renameDialogVisible.value = false
  } catch (error) {
    console.error('重命名失败:', error)
    ElMessage.error('重命名失败，请重试')
  }
}
</script>

<style scoped>
.session-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
}

.session-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.new-session-btn {
  border-radius: 8px;
}

.session-content {
  flex: 1;
  overflow-y: auto;
}

.session-items {
  padding: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.session-item:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

.session-item.active {
  background: rgba(99, 102, 241, 0.15);
  border-color: var(--primary-color);
}

.session-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 8px;
  color: var(--primary-color);
  font-size: 20px;
  cursor: pointer;
}

.session-item.active .session-icon {
  background: var(--primary-color);
  color: white;
}

.session-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.session-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-last-message {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.8;
}

.session-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.session-actions {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.session-item:hover .session-actions {
  opacity: 1;
}

.action-icon {
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 4px;
  font-size: 18px;
  transition: color 0.2s;
}

.action-icon:hover {
  color: var(--primary-color);
}

/* 重命名对话框样式 */
:deep(.el-dialog) {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
}

:deep(.el-dialog__title) {
  color: var(--text-primary);
}

:deep(.el-dialog__body) {
  color: var(--text-primary);
}

:deep(.el-form-item__label) {
  color: var(--text-primary);
}

/* 输入框字数统计样式 */
:deep(.el-input__count) {
  background-color: transparent !important;
  color: var(--text-secondary) !important;
}

:deep(.el-input__count-inner) {
  background-color: transparent !important;
  color: var(--text-secondary) !important;
}
</style>

