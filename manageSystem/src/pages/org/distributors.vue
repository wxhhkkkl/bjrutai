<template>
  <div class="distributors">
    <el-page-header @back="$router.back()" :content="`分销员管理 — ${orgName}`" />
    <div style="margin: 16px 0">
      <el-button type="primary" @click="openCreate">新建分销员</el-button>
      <el-checkbox v-model="includeSubtree" style="margin-left: 12px" @change="load">
        包含下级组织
      </el-checkbox>
    </div>

    <el-table :data="items" v-loading="loading" border style="width: 100%">
      <el-table-column prop="distributorId" label="ID" width="80" />
      <el-table-column prop="name" label="姓名" />
      <el-table-column prop="phone" label="手机号" />
      <el-table-column label="身份" width="110">
        <template #default="{ row }">
          <el-tag :type="row.orgRole === 'admin' ? 'warning' : 'info'">
            {{ row.orgRole === 'admin' ? '组织管理员' : '成员' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
            {{ row.status === 'active' ? '正常' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="warning" @click="toggleStatus(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button>
          <el-button size="small" @click="openReset(row)">重置密码</el-button>
          <el-button size="small" :type="row.orgRole === 'admin' ? 'danger' : 'success'" @click="toggleRole(row)">
            {{ row.orgRole === 'admin' ? '撤销管理员' : '设为管理员' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="新建分销员" width="460px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="姓名" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="手机号" required><el-input v-model="form.phone" maxlength="11" /></el-form-item>
        <el-form-item label="初始密码" required><el-input v-model="form.initialPassword" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <el-input v-model="newPassword" type="password" show-password placeholder="新密码（至少8位）" />
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReset">重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { distributorApi } from '@/api/org'

const route = useRoute()
const orgId = route.params.orgId || route.query.orgId
const orgName = ref(route.query.orgName || `组织 #${orgId}`)

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const includeSubtree = ref(false)
const createVisible = ref(false)
const resetVisible = ref(false)
const newPassword = ref('')
const activeRow = ref(null)
const form = ref({ name: '', phone: '', initialPassword: '' })

async function load() {
  loading.value = true
  try {
    const data = await distributorApi.list(orgId, { includeSubtree: includeSubtree.value, limit: 100 })
    items.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载分销员失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { name: '', phone: '', initialPassword: '' }
  createVisible.value = true
}

async function submitCreate() {
  if (!form.value.name || !form.value.phone || form.value.initialPassword.length < 8) {
    ElMessage.warning('请填写完整信息（密码至少8位）')
    return
  }
  saving.value = true
  try {
    await distributorApi.create(orgId, form.value)
    ElMessage.success('创建成功')
    createVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '创建失败')
  } finally {
    saving.value = false
  }
}

async function toggleStatus(row) {
  try {
    await distributorApi.update(row.distributorId, { status: row.status === 'active' ? 'disabled' : 'active' })
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '操作失败')
  }
}

function openReset(row) {
  activeRow.value = row
  newPassword.value = ''
  resetVisible.value = true
}

async function submitReset() {
  if (!activeRow.value || newPassword.value.length < 8) {
    ElMessage.warning('密码至少8位')
    return
  }
  await distributorApi.resetPassword(activeRow.value.distributorId, newPassword.value)
  ElMessage.success('已重置')
  resetVisible.value = false
}

async function toggleRole(row) {
  const target = row.orgRole === 'admin' ? 'member' : 'admin'
  try {
    await ElMessageBox.confirm(target === 'admin' ? `确认将「${row.name}」设为组织管理员？` : `确认撤销「${row.name}」的组织管理员身份？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await distributorApi.setRole(row.distributorId, target)
    ElMessage.success('已更新')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '操作失败')
  }
}

onMounted(load)
</script>

<style scoped>
.distributors { padding: 16px; }
</style>
