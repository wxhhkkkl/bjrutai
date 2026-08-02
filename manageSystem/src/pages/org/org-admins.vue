<template>
  <div class="org-admins">
    <el-page-header @back="$router.back()" :content="`组织管理员设置 — ${orgName}`" />
    <div style="margin: 16px 0">
      <el-button type="primary" @click="load">刷新</el-button>
      <el-tag style="margin-left: 8px" type="info">本组织管理员可在小程序查看本组织及其下级组织业绩</el-tag>
    </div>

    <el-table :data="items" v-loading="loading" border style="width: 100%">
      <el-table-column prop="distributorId" label="ID" width="80" />
      <el-table-column prop="name" label="姓名" />
      <el-table-column prop="phone" label="手机号" />
      <el-table-column label="身份" width="130">
        <template #default="{ row }">
          <el-tag :type="row.orgRole === 'admin' ? 'warning' : 'info'">
            {{ row.orgRole === 'admin' ? '组织管理员' : '成员' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button
            v-if="row.orgRole !== 'admin'"
            size="small"
            type="success"
            @click="setRole(row, 'admin')"
          >设为管理员</el-button>
          <el-button
            v-else
            size="small"
            type="danger"
            @click="setRole(row, 'member')"
          >撤销管理员</el-button>
        </template>
      </el-table-column>
    </el-table>
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
const items = ref([])

async function load() {
  loading.value = true
  try {
    const data = await distributorApi.list(orgId, { includeSubtree: true, limit: 100 })
    items.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function setRole(row, target) {
  const verb = target === 'admin' ? '设为' : '撤销'
  try {
    await ElMessageBox.confirm(`确认${verb}「${row.name}」的组织管理员身份？`, '确认', { type: 'warning' })
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
.org-admins { padding: 16px; }
</style>
