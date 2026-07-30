<template>
  <div class="page-container">
    <div class="page-header">
      <el-button text @click="$router.push('/accounts')">
        <el-icon><ArrowLeft /></el-icon> 返回账户管理
      </el-button>
      <h2 class="page-title">角色管理</h2>
      <el-button type="primary" size="small" @click="openCreate">新建角色</el-button>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="items"
        stripe
        empty-text="暂无角色"
      >
        <el-table-column prop="name" label="角色名称" min-width="140" />
        <el-table-column label="权限" min-width="300">
          <template #default="{ row }">
            <template v-if="row.permissions?.permissions?.length">
              <el-tag
                v-for="perm in row.permissions.permissions"
                :key="perm"
                size="small"
                style="margin: 2px;"
              >
                {{ perm }}
              </el-tag>
            </template>
            <span v-else class="no-perms">无权限</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="editRow(row)">编辑</el-button>
            <el-button text size="small" type="danger" @click="deleteRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create / Edit dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑角色' : '新建角色'"
      width="520px"
    >
      <el-form :model="form" label-width="80px" size="small">
        <el-form-item label="角色名称" required>
          <el-input v-model="form.name" placeholder="例如：管理员、运营、财务" />
        </el-form-item>
        <el-form-item label="权限分配">
          <el-checkbox-group v-model="form.permList" class="perm-matrix">
            <div v-for="group in permissionGroups" :key="group.label" class="perm-group">
              <div class="perm-group-label">{{ group.label }}</div>
              <el-checkbox
                v-for="perm in group.items"
                :key="perm.value"
                :label="perm.value"
                :value="perm.value"
              >
                {{ perm.label }}
              </el-checkbox>
            </div>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" :loading="saving" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

const loading = ref(false)
const items = ref([])

// Dialog
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = reactive({ name: '', permList: [] })

// Permission matrix
const permissionGroups = [
  {
    label: '层级管理',
    items: [
      { value: 'hierarchy.view', label: '查看层级' },
      { value: 'hierarchy.edit', label: '编辑层级' },
      { value: 'hierarchy.delete', label: '删除层级' },
      { value: 'hierarchy.migrate', label: '迁移分支' },
    ],
  },
  {
    label: '资质审核',
    items: [
      { value: 'qualification.view', label: '查看资质' },
      { value: 'qualification.review', label: '审核资质' },
    ],
  },
  {
    label: '客户管理',
    items: [
      { value: 'customer.view', label: '查看客户' },
      { value: 'customer.edit', label: '编辑客户' },
      { value: 'customer.unbind', label: '解绑客户' },
      { value: 'customer.transfer', label: '转移客户' },
    ],
  },
  {
    label: '业绩分成',
    items: [
      { value: 'contribution.view', label: '查看业绩' },
      { value: 'sharing.edit', label: '编辑分成规则' },
      { value: 'report.view', label: '查看报表' },
    ],
  },
  {
    label: '系统管理',
    items: [
      { value: 'account.manage', label: '账户管理' },
      { value: 'role.manage', label: '角色管理' },
      { value: 'sync.manage', label: '同步管理' },
      { value: 'article.manage', label: '文章管理' },
    ],
  },
]

onMounted(() => { fetchRoles() })

async function fetchRoles() {
  loading.value = true
  try {
    const res = await http.get('/admin/roles')
    const data = res.data?.data || res.data
    items.value = data.items || []
  } catch (e) {
    ElMessage.error(e.userMessage || '加载角色列表失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEditing.value = false
  editingId.value = null
  form.name = ''
  form.permList = []
  dialogVisible.value = true
}

function editRow(row) {
  isEditing.value = true
  editingId.value = row.id
  form.name = row.name
  form.permList = row.permissions?.permissions || []
  dialogVisible.value = true
}

async function saveRole() {
  if (!form.name) {
    ElMessage.warning('请输入角色名称')
    return
  }

  saving.value = true
  try {
    const body = {
      name: form.name,
      permissions: { permissions: form.permList },
    }

    if (isEditing.value) {
      await http.put(`/admin/roles/${editingId.value}`, body)
      ElMessage.success('更新成功')
    } else {
      await http.post('/admin/roles', body)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await fetchRoles()
  } catch (e) {
    ElMessage.error(e.userMessage || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteRow(row) {
  try {
    await ElMessageBox.confirm(`确定要删除角色 "${row.name}" 吗？未分配的角色才可删除。`, '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await http.delete(`/admin/roles/${row.id}`)
    ElMessage.success('删除成功')
    await fetchRoles()
  } catch (e) {
    ElMessage.error(e.userMessage || '删除失败')
  }
}

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0; flex: 1; }
.no-perms { color: #c0c4cc; font-size: 12px; }

.perm-matrix { width: 100%; }
.perm-group { margin-bottom: 10px; }
.perm-group-label { font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 600; }
</style>
