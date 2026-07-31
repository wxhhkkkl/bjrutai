<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">数据报表</h2>
    </div>

    <!-- Generation controls -->
    <el-card class="generate-card" shadow="never">
      <template #header><span>生成新报表</span></template>
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
        </el-col>
        <el-col :span="10">
          <el-checkbox-group v-model="selectedDimensions">
            <el-checkbox label="binding">绑定汇总</el-checkbox>
            <el-checkbox label="revenue">收入汇总</el-checkbox>
            <el-checkbox label="discount">优惠汇总</el-checkbox>
            <el-checkbox label="allocation">分配明细</el-checkbox>
          </el-checkbox-group>
        </el-col>
        <el-col :span="4">
          <el-button
            type="primary"
            :loading="store.generating"
            :disabled="!canGenerate"
            @click="handleGenerate"
          >
            生成报表
          </el-button>
        </el-col>
      </el-row>
    </el-card>

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
        暂无报表，请先生成
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
import { ElMessage } from 'element-plus'
import ReportDetail from '@/components/reports/ReportDetail.vue'

const store = useReportsStore()

const dateRange = ref(['2026-07-01', '2026-07-31'])
const selectedDimensions = ref(['revenue', 'discount', 'binding', 'allocation'])
const detailVisible = ref(false)

const canGenerate = computed(() => {
  return dateRange.value && dateRange.value.length === 2 && selectedDimensions.value.length > 0
})

function formatDate(dateStr) {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

async function handleGenerate() {
  if (!canGenerate.value) return
  try {
    await store.generateReport(
      dateRange.value[0],
      dateRange.value[1],
      selectedDimensions.value,
    )
  } catch {
    // Error already shown by store
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

.generate-card { margin-bottom: 16px; }
.list-card { margin-bottom: 16px; }
.empty-text { text-align: center; padding: 40px 0; color: #909399; font-size: 14px; }
</style>
