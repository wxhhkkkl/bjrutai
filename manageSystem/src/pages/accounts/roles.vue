<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">角色管理</h2>
      <el-button type="primary" @click="openCreate">新建角色</el-button>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="store.loading"
        :data="store.roles"
        stripe
        empty-text="暂无角色"
      >
        <el-table-column prop="name" label="角色名称" min-width="140">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_system" size="small" type="info" style="margin-left: 6px">系统</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="权限数量" width="100">
          <template #default="{ row }">
            {{ permCount(row) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="editRow(row)">编辑</el-button>
            <el-button
              v-if="!row.is_system"
              text size="small" type="danger"
              @click="deleteRow(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create / Edit dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑角色' : '新建角色'"
      width="520px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="角色名称" prop="name">
          <el-input
            v-model="form.name"
            :disabled="isEditing && editingIsSystem"
            placeholder="请输入角色名称"
          />
        </el-form-item>
        <el-form-item label="权限配置">
          <PermissionTree v-model="form.permList" ref="permTreeRef" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRbacStore } from '@/stores/rbac'
import PermissionTree from '@/components/PermissionTree.vue'

const store = useRbacStore()

// ── Dialog state ───────────────────────────────────────────
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const editingIsSystem = ref(false)
const saving = ref(false)
const formRef = ref(null)
const permTreeRef = ref(null)
const form = reactive({ name: '', permList: [] })

const rules = {
  name: [
    { required: true, message: '请输入角色名称', trigger: 'blur' },
    { max: 100, message: '角色名称最长 100 个字符', trigger: 'blur' },
  ],
}

// ── Lifecycle ──────────────────────────────────────────────
onMounted(async () => {
  await store.fetchRoles()
})

// ── Helpers ────────────────────────────────────────────────
function permCount(row) {
  const perms = row.permissions?.permissions
  return Array.isArray(perms) ? perms.length : 0
}

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

// ── Actions ────────────────────────────────────────────────
function openCreate() {
  isEditing.value = false
  editingId.value = null
  editingIsSystem.value = false
  form.name = ''
  form.permList = []
  dialogVisible.value = true
}

function editRow(row) {
  isEditing.value = true
  editingId.value = Number(row.id)
  editingIsSystem.value = !!row.is_system
  form.name = row.name
  form.permList = row.permissions?.permissions || []
  dialogVisible.value = true
}

function resetForm() {
  formRef.value?.resetFields()
}

async function saveRole() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const body = {
      name: form.name,
      permissions: { permissions: form.permList },
    }

    if (isEditing.value) {
      if (!editingIsSystem.value) {
        body.name = form.name
      }
      await store.updateRole(editingId.value, body)
      ElMessage.success('角色已更新')
    } else {
      await store.createRole(body)
      ElMessage.success('角色已创建')
    }
    dialogVisible.value = false
  } catch (err) {
    ElMessage.error(err.userMessage || err.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色 "${row.name}" 吗？仅未被分配的角色可删除。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }

  try {
    await store.deleteRole(Number(row.id))
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error(err.userMessage || err.response?.data?.message || '删除失败')
  }
}
</script>

<style scoped>
.page-title { flex: 1; }
</style>
