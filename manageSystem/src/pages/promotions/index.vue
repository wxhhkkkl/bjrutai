<template>
  <div class="promotions-page">
    <div class="page-header">
      <h2 class="page-title">推广码管理</h2>
      <div class="header-actions">
        <el-button @click="refreshData">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <!-- Stats summary -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ stats.totalCodes }}</div>
        <div class="stat-label">推广码总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-success">{{ stats.activeCodes }}</div>
        <div class="stat-label">生效中</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-primary">{{ stats.totalScans }}</div>
        <div class="stat-label">总扫码次数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-primary">{{ stats.totalBinds }}</div>
        <div class="stat-label">总绑定数</div>
      </div>
    </div>

    <!-- Table -->
    <div class="table-container" v-loading="loading">
      <el-empty v-if="!loading && promotionList.length === 0" description="暂无推广码数据" />
      <el-table v-else :data="promotionList" border stripe style="width: 100%">
        <el-table-column label="推广员" width="150">
          <template #default="{ row }">
            {{ row.promoter_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="推广码" width="180">
          <template #default="{ row }">
            <el-tooltip :content="row.refToken || ''" placement="top" :disabled="!row.refToken">
              <span>{{ maskToken(row.refToken) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="扫码次数" width="100" align="center">
          <template #default="{ row }">
            {{ row.scan_count ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="留资数" width="100" align="center">
          <template #default="{ row }">
            {{ row.lead_count ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="绑定数" width="100" align="center">
          <template #default="{ row }">
            {{ row.bind_count ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="转化率" width="100" align="center">
          <template #default="{ row }">
            {{ calcConversionRate(row) }}
          </template>
        </el-table-column>
        <el-table-column label="有效期至" width="170">
          <template #default="{ row }">
            {{ formatDate(row.expires_at) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div v-if="total > 0" class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @change="fetchPromotions"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

// State
const loading = ref(false)
const promotionList = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const stats = reactive({
  totalCodes: 0,
  activeCodes: 0,
  totalScans: 0,
  totalBinds: 0,
})

// Status helpers
function getStatusLabel(status) {
  const labels = {
    available: '可用',
    disabled: '已禁用',
    expired: '已过期',
  }
  return labels[status] || status
}

function getStatusType(status) {
  const types = {
    available: 'success',
    disabled: 'warning',
    expired: 'info',
  }
  return types[status] || 'info'
}

function formatDate(isoStr) {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function maskToken(token) {
  if (!token) return '-'
  if (token.length <= 8) return token.slice(0, 2) + '****'
  return token.slice(0, 4) + '****' + token.slice(-4)
}

function calcConversionRate(row) {
  const scan = row.scan_count || 0
  const bind = row.bind_count || 0
  if (scan === 0) return '0%'
  return ((bind / scan) * 100).toFixed(1) + '%'
}

// Actions
async function fetchPromotions() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      pageSize: pageSize.value,
    }
    const res = await http.get('/admin/promotion-codes', { params })
    const data = res.data.data

    promotionList.value = data.items || []
    total.value = data.total || 0

    // Extract summary stats if available from response
    if (data.summary) {
      stats.totalCodes = data.summary.totalCodes ?? 0
      stats.activeCodes = data.summary.activeCodes ?? 0
      stats.totalScans = data.summary.totalScans ?? 0
      stats.totalBinds = data.summary.totalBinds ?? 0
    } else {
      // Fallback: compute from list if no summary
      stats.totalCodes = total.value
      stats.activeCodes = promotionList.value.filter((c) => c.status === 'available').length
      stats.totalScans = promotionList.value.reduce((sum, c) => sum + (c.scan_count || 0), 0)
      stats.totalBinds = promotionList.value.reduce((sum, c) => sum + (c.bind_count || 0), 0)
    }
  } catch (e) {
    ElMessage.error(e.userMessage || '获取推广码列表失败')
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  try {
    const res = await http.get('/admin/promotion-codes/summary')
    const data = res.data.data
    stats.totalCodes = data.totalCodes ?? 0
    stats.activeCodes = data.activeCodes ?? 0
    stats.totalScans = data.totalScans ?? 0
    stats.totalBinds = data.totalBinds ?? 0
  } catch {
    // Summary endpoint is optional; stats computed from list in fetchPromotions fallback
  }
}

function refreshData() {
  currentPage.value = 1
  fetchPromotions()
}

onMounted(() => {
  fetchSummary()
  fetchPromotions()
})
</script>

<style scoped>
.promotions-page { padding: 10px 0; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.stat-value.stat-success {
  color: #67c23a;
}

.stat-value.stat-primary {
  color: #409eff;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}

.table-container {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 16px;
  min-height: 200px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
