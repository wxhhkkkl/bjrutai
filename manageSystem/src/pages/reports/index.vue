<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">数据报表</h2>
    </div>

    <!-- Report list -->
    <el-card class="list-card" shadow="never">
      <template #header>
        <span>历史报表</span>
        <el-button text type="primary" @click="refreshList" style="float:right">刷新</el-button>
      </template>
      <el-table :data="store.reports" v-loading="store.loading" stripe>
        <el-table-column prop="reportId" label="报表编号" width="260" show-overflow-tooltip />
        <el-table-column label="日期范围" width="220">
          <template #default="{ row }">
            {{ row.dateRange?.startDate }} ~ {{ row.dateRange?.endDate }}
          </template>
        </el-table-column>
        <el-table-column label="维度" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="dim in row.dimensions"
              :key="dim"
              size="small"
              type="info"
              style="margin-right: 4px"
            >
              {{ store.getDimensionLabel(dim) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="showSettlementStatus" label="核算状态" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.source === 'performance_settlement'"
              size="small"
              :type="settlementStatusType(row.status)"
            >
              {{ settlementStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="generatedAt" label="生成时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.generatedAt) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDetail(row.reportId)">查看</el-button>
            <el-button link type="success" size="small" @click="downloadReport(row.reportId)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="store.reports.length === 0 && !store.loading" class="empty-text">
        暂无报表
      </div>
    </el-card>

    <!-- Report detail dialog -->
    <ReportDetail
      v-model:visible="detailVisible"
      :report="store.currentReport"
      :loading="store.loading"
      @download="downloadReport"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useReportsStore } from '@/stores/reports'
import { useAuthStore } from '@/stores/auth'
import ReportDetail from '@/components/reports/ReportDetail.vue'

const store = useReportsStore()
const authStore = useAuthStore()
const showSettlementStatus = computed(() => authStore.hasPermission('sharing_rules.read'))

function settlementStatusLabel(s) {
  return { pending: '待审核', reviewed: '已确认', rejected: '已打回' }[s] || s || '-'
}
function settlementStatusType(s) {
  return { pending: 'warning', reviewed: 'success', rejected: 'danger' }[s] || 'info'
}

const detailVisible = ref(false)

function formatDate(dateStr) {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

async function refreshList() {
  await store.fetchReports()
}

async function viewDetail(reportId) {
  try {
    await store.fetchReportDetail(reportId)
    detailVisible.value = true
  } catch {
    // Error already shown by store
  }
}

async function downloadReport(reportId) {
  const id = reportId || store.currentReport?.reportId
  if (!id) return
  try {
    await store.exportReport(id)
  } catch {
    // Error already shown by store
  }
}

onMounted(() => {
  store.fetchReports()
})
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; }

.list-card { margin-bottom: 16px; }
.empty-text { text-align: center; padding: 40px 0; color: #909399; font-size: 14px; }
</style>
