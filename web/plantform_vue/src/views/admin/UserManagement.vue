<template>
  <div class="user-management">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索用户..."
          :prefix-icon="Search"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 240px"
        />
        <el-button type="primary" :icon="RefreshRight" @click="handleRefresh">
          刷新
        </el-button>
      </div>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="userList"
        stripe
        class="user-table"
      >
        <el-table-column prop="id" label="用户 ID" width="100" />
        
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        
        <el-table-column prop="email" label="邮箱" min-width="180" />
        
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">
              {{ row.is_admin ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="create_at" label="注册时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.create_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_admin"
              text
              type="primary"
              size="small"
              @click="handleSetAdmin(row)"
            >
              设为管理员
            </el-button>
            <el-button
              text
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <CustomPagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          @page-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getUserList, deleteUsers, setAdmin } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, RefreshRight } from '@element-plus/icons-vue'
import CustomPagination from '@/components/public/CustomPagination.vue'

const loading = ref(false)
const userList = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchKeyword = ref('')

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 获取用户列表
const fetchUserList = async () => {
  loading.value = true
  try {
    const data = await getUserList({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined
    })
    
    
    // 处理不同的返回格式
    if (Array.isArray(data)) {
      // 如果直接返回数组
      userList.value = data
      total.value = data.length
    } else if (data.users) {
      // 如果返回带分页信息的对象
      userList.value = data.users
      total.value = data.total || 0
    } else {
      userList.value = []
      total.value = 0
    }
  } catch (error) {
    ElMessage.error('获取用户列表失败')
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  fetchUserList()
}

// 刷新
const handleRefresh = () => {
  currentPage.value = 1
  searchKeyword.value = ''
  fetchUserList()
}

// 页码变化
const handlePageChange = () => {
  fetchUserList()
}

// 页大小变化
const handleSizeChange = () => {
  currentPage.value = 1
  fetchUserList()
}

// 设为管理员
const handleSetAdmin = async (user) => {
  try {
    await ElMessageBox.confirm(
      `确定要将用户 "${user.nickname}" 设为管理员吗？`,
      '确认操作',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await setAdmin({
      user_id: user.id,
      is_admin: true
    })
    
    ElMessage.success('设置成功')
    fetchUserList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('设置管理员失败')
    }
  }
}

// 删除用户
const handleDelete = async (user) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${user.nickname}" 吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      }
    )
    
    await deleteUsers([user.id])
    
    ElMessage.success('删除成功')
    fetchUserList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除用户失败')
    }
  }
}

onMounted(() => {
  fetchUserList()
})
</script>

<style scoped>
.user-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  padding-bottom: 80px; /* 增加底部间距，避免被导航栏遮挡 */
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
  overflow: hidden;
}

.user-table {
  flex: 1;
  overflow: auto;
}

.user-table :deep(.el-table__header) {
  background: var(--bg-tertiary);
}

.user-table :deep(.el-table__row) {
  background: transparent;
}

.user-table :deep(.el-table__row:hover) {
  background: rgba(99, 102, 241, 0.05);
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}
</style>

