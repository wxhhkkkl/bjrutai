<template>
  <div class="page-container">
    <h2 class="page-title">客户管理</h2>

    <!-- Filters -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="12" align="middle">
        <el-col :xs="24" :sm="16">
          <el-radio-group v-model="filterStatus" size="small" @change="handleFilterChange">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button label="bound">已绑定</el-radio-button>
            <el-radio-button label="unbound">未绑定</el-radio-button>
            <el-radio-button label="pending">待绑定</el-radio-button>
          </el-radio-group>
        </el-col>
        <el-col :xs="24" :sm="8" class="search-col">
          <el-input
            v-model="keyword"
            placeholder="搜索姓名或电话..."
            clearable
            size="small"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
      </el-row>
    </el-card>

    <!-- Table -->
    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="items"
        stripe
        empty-text="暂无客户数据"
        @row-click="goDetail"
        style="cursor: pointer;"
      >
        <el-table-column prop="name" label="姓名" min-width="120" />
        <el-table-column prop="phoneMasked" label="手机号" min-width="130" />
        <el-table-column label="绑定状态" width="100">
          <template #default="{ row }">
            <el-tag :type="bindingStatusType(row.bindingStatus)" size="small">
              {{ bindingStatusLabel(row.bindingStatus) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="promoterName" label="推广员" min-width="120" />
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.updatedAt) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- Load more -->
      <div class="load-more" v-if="hasMore">
        <el-button
          :loading="loadingMore"
          text
          size="small"
          @click="loadMore"
        >
          加载更多
        </el-button>
      </div>
      <div class="load-more" v-else-if="items.length > 0">
        <span class="all-loaded">已加载全部数据</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/api/http'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

const router = useRouter()

const loading = ref(false)
const loadingMore = ref(false)
const items = ref([])
const filterStatus = ref('')
const keyword = ref('')
const nextCursor = ref(null)
const hasMore = ref(false)

const bindingStatusLabels = { bound: '已绑定', unbound: '未绑定', pending: '待绑定' }
const bindingStatusTypes = { bound: 'success', unbound: 'info', pending: 'warning' }

function bindingStatusLabel(s) { return bindingStatusLabels[s] || s || '-' }
function bindingStatusType(s) { return bindingStatusTypes[s] || 'info' }

onMounted(() => { fetchData() })

async function fetchData(cursor = null) {
  loading.value = true
  try {
    const params = { pageSize: 20 }
    if (filterStatus.value) params.status = filterStatus.value
    if (keyword.value) params.keyword = keyword.value
    if (cursor) params.cursor = cursor

    const res = await http.get('/customers', { params })
    const data = res.data?.data || res.data
    const newItems = data.items || []

    if (cursor) {
      items.value = [...items.value, ...newItems]
    } else {
      items.value = newItems
    }

    nextCursor.value = data.nextCursor || null
    hasMore.value = !!data.hasMore
  } catch (e) {
    ElMessage.error(e.userMessage || '加载客户列表失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function handleFilterChange() { fetchData() }

function handleSearch() { fetchData() }

async function loadMore() {
  loadingMore.value = true
  await fetchData(nextCursor.value)
}

function goDetail(row) {
  router.push(`/customers/${row.id}`)
}

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin-bottom: 16px; }

.filter-card { margin-bottom: 12px; }
.search-col { text-align: right; }

.table-card { min-height: 200px; }

.load-more { text-align: center; padding: 14px 0; }
.all-loaded { color: #b0b4bb; font-size: 12px; }
</style>
