<template>
  <div class="prompt-management">
    <div class="page-header">
      <h2 class="page-title">Prompt 管理</h2>
      <div class="header-actions">
        <el-select
          v-model="agentFilter"
          placeholder="Agent"
          clearable
          style="width: 160px"
          @change="handleSearch"
        >
          <el-option
            v-for="agent in agentOptions"
            :key="agent.agent_key"
            :label="agent.agent_name"
            :value="agent.agent_key"
          />
        </el-select>
        <el-select
          v-model="categoryFilter"
          placeholder="类别"
          clearable
          style="width: 160px"
          @change="handleSearch"
        >
          <el-option
            v-for="category in categoryOptions"
            :key="category"
            :label="category"
            :value="category"
          />
        </el-select>
        <el-input
          v-model="searchKeyword"
          placeholder="搜索 Prompt"
          :prefix-icon="Search"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 240px"
        />
        <el-button :icon="RefreshRight" @click="handleRefresh">刷新</el-button>
      </div>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="promptList"
        stripe
        class="prompt-table"
        @row-click="handleEdit"
      >
        <el-table-column prop="agent_name" label="Agent" width="160" />
        <el-table-column prop="category" label="类别" width="150" />
        <el-table-column prop="version_name" label="版本" min-width="220" show-overflow-tooltip />
        <el-table-column prop="content" label="内容预览" min-width="360" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '使用中' : '未启用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="副本" width="90">
          <template #default="{ row }">
            <span>{{ row.is_copy ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click.stop="handleEdit(row)">
              编辑
            </el-button>
            <el-button
              v-if="!row.is_active"
              text
              type="success"
              size="small"
              @click.stop="handleActivate(row)"
            >
              启用
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
          @page-change="fetchPrompts"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="showEditDialog" title="编辑 Prompt" width="820px">
      <div v-if="editForm.uuid" class="edit-content">
        <div class="prompt-meta">
          <span>{{ editForm.agent_name }}</span>
          <span>{{ editForm.category }}</span>
          <span>{{ editForm.version_name }}</span>
        </div>
        <el-input
          v-model="editForm.content"
          type="textarea"
          :rows="18"
          resize="vertical"
          placeholder="请输入 Prompt 内容"
        />
        <el-checkbox v-model="editForm.save_copy" class="copy-checkbox">
          保存为副本
        </el-checkbox>
      </div>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight, Search } from '@element-plus/icons-vue'
import { activatePrompt, getPromptList, getPromptOptions, updatePrompt } from '@/api'
import CustomPagination from '@/components/public/CustomPagination.vue'

const loading = ref(false)
const saving = ref(false)
const promptList = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const agentFilter = ref('')
const categoryFilter = ref('')
const agentOptions = ref([])
const categoryOptions = ref([])
const showEditDialog = ref(false)
const editForm = ref({
  uuid: '',
  agent_name: '',
  category: '',
  version_name: '',
  content: '',
  save_copy: false
})

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

const fetchOptions = async () => {
  try {
    const data = await getPromptOptions()
    agentOptions.value = data.agents || []
    categoryOptions.value = data.categories || []
  } catch (error) {
    ElMessage.error('获取选项失败')
  }
}

const fetchPrompts = async () => {
  loading.value = true
  try {
    const data = await getPromptList({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined,
      agent_key: agentFilter.value || undefined,
      category: categoryFilter.value || undefined
    })
    promptList.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    ElMessage.error('获取 Prompt 列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchPrompts()
}

const handleRefresh = () => {
  currentPage.value = 1
  searchKeyword.value = ''
  agentFilter.value = ''
  categoryFilter.value = ''
  fetchPrompts()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchPrompts()
}

const handleEdit = (row) => {
  editForm.value = {
    uuid: row.uuid,
    agent_name: row.agent_name,
    category: row.category,
    version_name: row.version_name,
    content: row.content,
    save_copy: false
  }
  showEditDialog.value = true
}

const handleSave = async () => {
  if (!editForm.value.content.trim()) {
    ElMessage.warning('Prompt 内容不能为空')
    return
  }
  saving.value = true
  try {
    await updatePrompt(editForm.value.uuid, {
      content: editForm.value.content,
      save_copy: editForm.value.save_copy
    })
    ElMessage.success('保存成功')
    showEditDialog.value = false
    fetchPrompts()
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const handleActivate = async (row) => {
  try {
    await activatePrompt(row.uuid)
    ElMessage.success('启用成功')
    fetchPrompts()
  } catch (error) {
    ElMessage.error('启用失败')
  }
}

onMounted(() => {
  fetchOptions()
  fetchPrompts()
})
</script>

<style scoped>
.prompt-management {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-content {
  flex: 1;
  min-height: 0;
  padding: 24px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.prompt-table {
  flex: 1;
  min-height: 0;
}

.pagination-wrapper {
  padding-top: 16px;
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.edit-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.prompt-meta {
  display: flex;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 14px;
}

.copy-checkbox {
  align-self: flex-start;
}
</style>
