<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">客户管理</h2>
      <el-button @click="loadAll">
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <div class="cust-layout">
      <!-- 左侧：组织结构树 -->
      <div class="tree-panel" v-loading="loading">
        <div class="panel-title"><span>组织结构</span></div>
        <el-empty v-if="treeData.length === 0" description="暂无组织" :image-size="60" />
        <el-tree
          v-else
          ref="treeRef"
          :data="treeData"
          :props="{ label: 'name', children: 'children' }"
          node-key="orgId"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          @node-click="handleSelect"
        >
          <template #default="{ data }">
            <div class="tree-node-content">
              <span class="node-name">{{ data.name }}</span>
              <span class="node-level">L{{ data.level }}</span>
            </div>
          </template>
        </el-tree>
      </div>

      <!-- 右侧：选中组织下的客户 -->
      <div class="detail-panel">
        <el-empty v-if="!selected" description="请在左侧选择组织查看其下客户" :image-size="80" />

        <template v-else>
          <div class="cust-header">
            <span class="org-title">{{ selected.name }}</span>
            <el-tag size="small" type="info" effect="plain">L{{ selected.level }}</el-tag>
            <el-space wrap class="header-actions">
              <el-button size="small" type="primary" :disabled="!canWrite" @click="openCreate">
                <el-icon style="margin-right: 4px"><Plus /></el-icon>新建客户
              </el-button>
            </el-space>
          </div>

          <!-- 筛选 -->
          <div class="filter-card">
            <el-radio-group v-model="filterStatus" size="small" @change="fetchData()">
              <el-radio-button label="">全部</el-radio-button>
              <el-radio-button label="bound">已绑定</el-radio-button>
              <el-radio-button label="pending">待绑定</el-radio-button>
              <el-radio-button label="unbound">已解绑</el-radio-button>
            </el-radio-group>
            <el-input
              v-model="keyword"
              placeholder="搜索姓名或手机号..."
              clearable
              size="small"
              class="search-input"
              @keyup.enter="fetchData()"
              @clear="fetchData()"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
          </div>

          <!-- 客户表格 -->
          <el-table v-loading="loading" :data="items" stripe border size="small" style="width: 100%">
            <el-table-column prop="name" label="姓名" min-width="100" />
            <el-table-column prop="phoneMasked" label="手机号" min-width="120" />
            <el-table-column label="绑定状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="bindingStatusType(row.bindingStatus)" size="small">
                  {{ bindingStatusLabel(row.bindingStatus) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="promoterName" label="推广员" min-width="100" />
            <el-table-column prop="orgName" label="所属组织" min-width="120" />
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{ formatTime(row.updatedAt) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click.stop="goDetail(row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="load-more" v-if="hasMore">
            <el-button :loading="loadingMore" text size="small" @click="loadMore">加载更多</el-button>
          </div>
          <div class="load-more" v-else-if="items.length > 0">
            <span class="all-loaded">已加载全部数据</span>
          </div>
        </template>
      </div>
    </div>

    <!-- 新建客户 -->
    <CreateCustomerDialog
      v-model="createVisible"
      :org-id="selected?.orgId"
      :org-name="selected?.name"
      @created="handleCreated"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { orgApi } from '@/api/org'
import { adminCustomerApi } from '@/api/customers'
import { useAuthStore } from '@/stores/auth'
import CreateCustomerDialog from '@/components/customers/CreateCustomerDialog.vue'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const loadingMore = ref(false)
const tree = ref(null)
const treeRef = ref(null)
const selected = ref(null)
const items = ref([])
const filterStatus = ref('')
const keyword = ref('')
const page = ref(1)
const hasMore = ref(false)
const createVisible = ref(false)

const canWrite = computed(() => authStore.hasPermission('customers.write'))
const treeData = computed(() => tree.value || [])

const bindingStatusLabels = { bound: '已绑定', pending: '待绑定', unbound: '已解绑' }
const bindingStatusTypes = { bound: 'success', pending: 'warning', unbound: 'info' }

function bindingStatusLabel(s) { return bindingStatusLabels[s] || s || '-' }
function bindingStatusType(s) { return bindingStatusTypes[s] || 'info' }

function flatten(n, acc = []) {
  acc.push(n)
  ;(n.children || []).forEach((c) => flatten(c, acc))
  return acc
}

async function loadAll() {
  loading.value = true
  try {
    const data = await orgApi.getTree()
    const roots = Array.isArray(data.tree) ? data.tree : (data.tree ? [data.tree] : [])
    tree.value = roots
    // 展平所有根子树，用于重新定位当前选中组织
    const flatAll = roots.flatMap((r) => flatten(r))
    if (selected.value) {
      const fresh = flatAll.find((o) => o.orgId === selected.value.orgId)
      handleSelect(fresh || flatAll[0] || null)
    } else if (flatAll.length > 0) {
      handleSelect(flatAll[0])  // 默认选中第一个根组织
    }
    // 重载后同步左侧树的高亮
    if (selected.value) {
      treeRef.value?.setCurrentKey(selected.value.orgId)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载组织树失败')
  } finally {
    loading.value = false
  }
}

function handleSelect(node) {
  selected.value = node
  fetchData()
}

async function fetchData() {
  if (!selected.value) return
  loading.value = true
  page.value = 1
  try {
    const params = { page: 1, pageSize: 20 }
    if (filterStatus.value) params.status = filterStatus.value
    if (keyword.value) params.keyword = keyword.value
    const data = await adminCustomerApi.list(selected.value.orgId, params)
    items.value = data.items || []
    hasMore.value = !!data.hasMore
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载客户列表失败')
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loadingMore.value = true
  try {
    const params = { page: page.value + 1, pageSize: 20 }
    if (filterStatus.value) params.status = filterStatus.value
    if (keyword.value) params.keyword = keyword.value
    const data = await adminCustomerApi.list(selected.value.orgId, params)
    page.value += 1
    items.value = [...items.value, ...(data.items || [])]
    hasMore.value = !!data.hasMore
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载更多失败')
  } finally {
    loadingMore.value = false
  }
}

function openCreate() {
  createVisible.value = true
}

function handleCreated() {
  createVisible.value = false
  fetchData()
}

function goDetail(row) {
  router.push(`/customers/${row.id}`)
}

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

onMounted(loadAll)
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }

.cust-layout { display: flex; gap: 14px; align-items: flex-start; }

.tree-panel {
  width: 280px; flex-shrink: 0; border: 1px solid #e4e7ed; border-radius: 6px;
  padding: 10px; background: #fff; min-height: 480px;
}
.panel-title { font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #303133; }
.tree-node-content { display: flex; align-items: center; gap: 8px; }
.node-level { color: #909399; font-size: 12px; }

.detail-panel { flex: 1; min-width: 0; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; padding: 14px; }
.cust-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.org-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { margin-left: auto; }

.filter-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.search-input { width: 240px; }

.load-more { text-align: center; padding: 12px 0; }
.all-loaded { color: #b0b4bb; font-size: 12px; }
</style>
