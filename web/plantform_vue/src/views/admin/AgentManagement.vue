<template>
  <div class="agent-management">
    <div class="page-header">
      <h2 class="page-title">Agent 管理</h2>
      <div class="header-actions">
        <el-select
          v-model="enabledFilter"
          placeholder="状态"
          clearable
          style="width: 140px"
          @change="handleSearch"
        >
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-input
          v-model="searchKeyword"
          placeholder="搜索 Agent"
          :prefix-icon="Search"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
          style="width: 240px"
        />
        <el-button :icon="RefreshRight" @click="handleRefresh">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="handleCreate">新增</el-button>
      </div>
    </div>

    <div class="page-content">
      <el-table
        v-loading="loading"
        :data="agentList"
        stripe
        class="agent-table"
        @row-click="handleEdit"
      >
        <el-table-column prop="agent_name" label="名称" width="150" />
        <el-table-column prop="agent_key" label="标识" width="150" />
        <el-table-column prop="description" label="描述" min-width="260" show-overflow-tooltip />
        <el-table-column label="MCP 工具" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ (row.mcp_tools || []).join('、') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="prompt_key" label="Prompt" width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="90" />
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click.stop="handleEdit(row)">
              编辑
            </el-button>
            <el-button
              text
              :type="row.enabled ? 'warning' : 'success'"
              size="small"
              @click.stop="handleToggle(row)"
            >
              {{ row.enabled ? '禁用' : '启用' }}
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
          @page-change="fetchAgents"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="showEditDialog" :title="editForm.uuid ? '编辑 Agent' : '新增 Agent'" width="720px">
      <el-form :model="editForm" label-width="100px" class="agent-form">
        <el-form-item label="名称">
          <el-input v-model="editForm.agent_name" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item label="标识">
          <el-input v-model="editForm.agent_key" placeholder="请输入唯一标识" :disabled="Boolean(editForm.uuid)" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" resize="vertical" placeholder="请输入描述" />
        </el-form-item>
        <el-form-item label="MCP 工具">
          <el-select v-model="editForm.mcp_tools" multiple filterable placeholder="请选择 MCP 工具" style="width: 100%">
            <el-option
              v-for="tool in toolOptions"
              :key="tool.name"
              :label="tool.description"
              :value="tool.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Prompt">
          <el-select v-model="editForm.prompt_key" filterable allow-create placeholder="请选择或输入 Prompt" style="width: 100%">
            <el-option
              v-for="prompt in promptOptions"
              :key="prompt.agent_key"
              :label="prompt.agent_name"
              :value="prompt.agent_key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="editForm.sort_order" :min="0" :step="10" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
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
import { Plus, RefreshRight, Search } from '@element-plus/icons-vue'
import { createAgent, getAgentList, getAgentOptions, setAgentEnabled, updateAgent } from '@/api'
import CustomPagination from '@/components/public/CustomPagination.vue'

const loading = ref(false)
const saving = ref(false)
const agentList = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const enabledFilter = ref('')
const toolOptions = ref([])
const promptOptions = ref([])
const showEditDialog = ref(false)
const editForm = ref({
  uuid: '',
  agent_key: '',
  agent_name: '',
  description: '',
  mcp_tools: [],
  prompt_key: '',
  enabled: true,
  sort_order: 0
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
    const data = await getAgentOptions()
    toolOptions.value = data.tools || []
    promptOptions.value = data.prompts || []
  } catch (error) {
    ElMessage.error('获取选项失败')
  }
}

const fetchAgents = async () => {
  loading.value = true
  try {
    const data = await getAgentList({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: searchKeyword.value || undefined,
      enabled: enabledFilter.value === '' ? undefined : enabledFilter.value
    })
    agentList.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    ElMessage.error('获取 Agent 列表失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  editForm.value = {
    uuid: '',
    agent_key: '',
    agent_name: '',
    description: '',
    mcp_tools: [],
    prompt_key: '',
    enabled: true,
    sort_order: 0
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchAgents()
}

const handleRefresh = () => {
  currentPage.value = 1
  searchKeyword.value = ''
  enabledFilter.value = ''
  fetchAgents()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchAgents()
}

const handleCreate = () => {
  resetForm()
  showEditDialog.value = true
}

const handleEdit = (row) => {
  editForm.value = {
    uuid: row.uuid,
    agent_key: row.agent_key,
    agent_name: row.agent_name,
    description: row.description,
    mcp_tools: [...(row.mcp_tools || [])],
    prompt_key: row.prompt_key,
    enabled: row.enabled,
    sort_order: row.sort_order || 0
  }
  showEditDialog.value = true
}

const validateForm = () => {
  if (!editForm.value.agent_name.trim()) return '名称不能为空'
  if (!editForm.value.agent_key.trim()) return '标识不能为空'
  if (!editForm.value.description.trim()) return '描述不能为空'
  if (!editForm.value.prompt_key.trim()) return 'Prompt 不能为空'
  if (!editForm.value.mcp_tools.length) return 'MCP 工具不能为空'
  return ''
}

const handleSave = async () => {
  const message = validateForm()
  if (message) {
    ElMessage.warning(message)
    return
  }
  saving.value = true
  try {
    const payload = {
      agent_key: editForm.value.agent_key.trim(),
      agent_name: editForm.value.agent_name.trim(),
      description: editForm.value.description.trim(),
      mcp_tools: editForm.value.mcp_tools,
      prompt_key: editForm.value.prompt_key.trim(),
      enabled: editForm.value.enabled,
      sort_order: editForm.value.sort_order || 0
    }
    if (editForm.value.uuid) {
      await updateAgent(editForm.value.uuid, payload)
    } else {
      await createAgent(payload)
    }
    ElMessage.success('保存成功')
    showEditDialog.value = false
    fetchOptions()
    fetchAgents()
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const handleToggle = async (row) => {
  try {
    await setAgentEnabled(row.uuid, !row.enabled)
    ElMessage.success('保存成功')
    fetchAgents()
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

onMounted(() => {
  fetchOptions()
  fetchAgents()
})
</script>

<style scoped>
.agent-management {
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

.agent-table {
  flex: 1;
  min-height: 0;
}

.pagination-wrapper {
  padding-top: 16px;
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.agent-form {
  padding-right: 12px;
}
</style>
