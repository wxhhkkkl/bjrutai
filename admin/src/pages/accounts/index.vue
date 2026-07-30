<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">账户管理</h2>
      <el-button type="primary" size="small" @click="openCreateDialog">新建账户</el-button>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="items"
        stripe
        empty-text="暂无账户"
      >
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">
              {{ row.status === 'active' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-for="role in row.roles"
              :key="role.id"
              size="small"
              style="margin-right: 4px;"
            >
              {{ role.name }}
            </el-tag>
            <span v-if="!row.roles?.length" class="no-roles">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="editAccount(row)">编辑</el-button>
            <el-button
              v-if="row.status === 'active'"
              text
              size="small"
              type="danger"
              @click="toggleAccount(row, 'disable')"
            >
              禁用
            </el-button>
            <el-button
              v-else
              text
              size="small"
              type="success"
              @click="toggleAccount(row, 'enable')"
            >
              启用
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="load-more" v-if="hasMore">
        <el-button text size="small" :loading="loadingMore" @click="loadMore">加载更多</el-button>
      </div>
    </el-card>

    <!-- Create/Edit dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑账户' : '新建账户'"
      width="480px"
    >
      <el-form :model="form" label-width="80px" size="small">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" :required="!isEditing">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="isEditing ? '留空则不修改' : '请输入密码'"
            show-password
          />
        </el-form-item>
        <el-form-item label="角色分配">
          <el-checkbox-group v-model="form.roleIds">
            <el-checkbox
              v-for="role in allRoles"
              :key="role.id"
              :label="role.id"
              :value="role.id"
            >
              {{ role.name }}
            </el-checkbox>
          </el-checkbox-group>
          <div v-if="!allRoles.length" style="color: #909399; font-size: 12px;">
            暂无可分配角色，
            <el-button text size="small" type="primary" @click="$router.push('/accounts/roles')">去创建角色</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" :loading="saving" @click="saveAccount">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const loadingMore = ref(false)
const items = ref([])
const hasMore = ref(false)
const nextCursor = ref(null)

// Dialog
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = reactive({ username: '', password: '', roleIds: [] })
const allRoles = ref([])

onMounted(() => { fetchData() })

async function fetchData(cursor = null) {
  loading.value = !cursor
  try {
    const params = { pageSize: 20 }
    if (cursor) params.cursor = cursor
    const res = await http.get('/admin/accounts', { params })
    const data = res.data?.data || res.data
    const newItems = data.items || []

    if (cursor) {
      items.value = [...items.value, ...newItems]
    } else {
      items.value = newItems
    }
    nextCursor.value = data.nextCursor
    hasMore.value = !!data.hasMore
  } catch (e) {
    ElMessage.error(e.userMessage || '加载账户列表失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

async function fetchRoles() {
  try {
    const res = await http.get('/admin/roles')
    const data = res.data?.data || res.data
    allRoles.value = data.items || []
  } catch {
    allRoles.value = []
  }
}

async function loadMore() {
  loadingMore.value = true
  await fetchData(nextCursor.value)
}

function editAccount(row) {
  isEditing.value = true
  editingId.value = row.id
  form.username = row.username
  form.password = ''
  form.roleIds = (row.roles || []).map(r => r.id)
  dialogVisible.value = true
}

async function openCreateDialog() {
  await fetchRoles()
  isEditing.value = false
  editingId.value = null
  form.username = ''
  form.password = ''
  form.roleIds = []
  dialogVisible.value = true
}

async function saveAccount() {
  if (!form.username) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (!isEditing.value && !form.password) {
    ElMessage.warning('请输入密码')
    return
  }

  saving.value = true
  try {
    if (isEditing.value) {
      const body = { username: form.username, roleIds: form.roleIds }
      if (form.password) body.password = form.password
      await http.put(`/admin/accounts/${editingId.value}`, body)
      ElMessage.success('更新成功')
    } else {
      await http.post('/admin/accounts', {
        username: form.username,
        password: form.password,
        roleIds: form.roleIds,
      })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    items.value = []
    await fetchData()
  } catch (e) {
    ElMessage.error(e.userMessage || '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleAccount(row, action) {
  const label = action === 'disable' ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定要${label}账户 "${row.username}" 吗？`, '确认操作', {
      type: 'warning',
      confirmButtonText: label,
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await http.post(`/admin/accounts/${row.id}/${action}`)
    ElMessage.success(`${label}成功`)
    row.status = action === 'disable' ? 'disabled' : 'active'
  } catch (e) {
    ElMessage.error(e.userMessage || `${label}失败`)
  }
}

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0; }
.load-more { text-align: center; padding: 14px 0; }
.no-roles { color: #c0c4cc; font-size: 12px; }
</style>
