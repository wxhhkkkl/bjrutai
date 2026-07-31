<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">管理员列表</h2>
      <el-button type="primary" @click="openCreateDialog">新建管理员</el-button>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="store.loading"
        :data="store.admins"
        stripe
        empty-text="暂无管理员"
      >
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">
              {{ row.status === 'active' ? '活跃' : '已禁用' }}
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
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="editAccount(row)">编辑</el-button>
            <template v-if="row.username !== 'admin'">
              <el-button
                v-if="row.status === 'active'"
                text size="small" type="danger"
                @click="toggleAccount(row, 'disable')"
              >禁用</el-button>
              <el-button
                v-else
                text size="small" type="success"
                @click="toggleAccount(row, 'enable')"
              >启用</el-button>
            </template>
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
      :title="isEditing ? '编辑管理员' : '新建管理员'"
      width="480px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="isEditing" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" :prop="isEditing ? 'passwordEdit' : 'password'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="isEditing ? '留空则不修改密码' : '请输入密码'"
          />
        </el-form-item>
        <el-form-item label="角色分配">
          <el-select v-model="form.roleIds" multiple placeholder="请选择角色" style="width: 100%">
            <el-option
              v-for="role in store.roles"
              :key="role.id"
              :label="role.name + (role.is_system ? ' (系统)' : '')"
              :value="Number(role.id)"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAccount">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRbacStore } from '@/stores/rbac'

const store = useRbacStore()

// ── Table state ────────────────────────────────────────────
const hasMore = ref(false)
const loadingMore = ref(false)

// ── Dialog state ───────────────────────────────────────────
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ username: '', password: '', roleIds: [] })

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 4, max: 64, message: '用户名长度 4-64 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码长度至少 8 位', trigger: 'blur' },
  ],
  passwordEdit: [
    { min: 8, message: '密码长度至少 8 位', trigger: 'blur' },
  ],
}

// ── Lifecycle ──────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([store.fetchAdmins(), store.fetchRoles()])
})

// ── Actions ────────────────────────────────────────────────
async function loadMore() {
  loadingMore.value = true
  // TODO: cursor pagination
  loadingMore.value = false
}

function openCreateDialog() {
  isEditing.value = false
  editingId.value = null
  form.username = ''
  form.password = ''
  form.roleIds = []
  dialogVisible.value = true
}

function editAccount(row) {
  isEditing.value = true
  editingId.value = Number(row.id)
  form.username = row.username
  form.password = ''
  form.roleIds = (row.roles || []).map((r) => Number(r.id))
  dialogVisible.value = true
}

function resetForm() {
  formRef.value?.resetFields()
}

async function saveAccount() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const payload = { roleIds: form.roleIds }
    if (form.password) payload.password = form.password

    if (isEditing.value) {
      await store.updateAdmin(editingId.value, payload)
      ElMessage.success('管理员已更新')
    } else {
      payload.username = form.username
      payload.password = form.password
      await store.createAdmin(payload)
      ElMessage.success('管理员已创建')
    }
    dialogVisible.value = false
  } catch (err) {
    ElMessage.error(err.userMessage || err.response?.data?.message || '操作失败')
  } finally {
    saving.value = false
  }
}

async function toggleAccount(row, action) {
  const label = action === 'disable' ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定要${label}管理员 "${row.username}" 吗？`, '确认操作', {
      type: 'warning',
      confirmButtonText: label,
      cancelButtonText: '取消',
    })
  } catch { return }

  try {
    if (action === 'disable') await store.disableAdmin(Number(row.id))
    else await store.enableAdmin(Number(row.id))
    ElMessage.success(`${label}成功`)
  } catch (err) {
    ElMessage.error(err.userMessage || err.response?.data?.message || `${label}失败`)
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
