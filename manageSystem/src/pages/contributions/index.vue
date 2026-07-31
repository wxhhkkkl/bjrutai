<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">业绩贡献</h2>
    </div>

    <!-- Month selector and controls -->
    <el-card class="filter-card" shadow="never">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-date-picker
            v-model="selectedMonth"
            type="month"
            placeholder="选择月份"
            format="YYYY-MM"
            value-format="YYYY-MM"
            @change="onMonthChange"
          />
        </el-col>
        <el-col :span="6">
          <el-select v-model="filters.status" placeholder="状态筛选" clearable @change="onFilterChange">
            <el-option label="待确认" value="pending" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="已结算" value="settled" />
            <el-option label="已冲正" value="reversed" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filters.category" placeholder="类别筛选" clearable @change="onFilterChange">
            <el-option label="消费贡献" value="bill" />
            <el-option label="绑定贡献" value="binding" />
            <el-option label="服务贡献" value="service" />
            <el-option label="跟进贡献" value="followup" />
            <el-option label="调整贡献" value="adjustment" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-button type="primary" :loading="settling" @click="handleSettle">
            月度结算
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- Overview stats -->
    <el-row :gutter="16" class="stats-row" v-if="store.overview">
      <el-col :span="6">
        <el-statistic title="本月贡献值" :value="store.overview.monthlyPoints" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="累计贡献值" :value="store.overview.totalPoints" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="环比增长">
          <template #suffix>
            <span :style="{ color: growthColor }">{{ growthDisplay }}</span>
          </template>
        </el-statistic>
      </el-col>
      <el-col :span="6">
        <el-statistic title="待确认" :value="pendingCount" />
      </el-col>
    </el-row>

    <!-- Trend chart placeholder -->
    <el-card class="chart-card" shadow="never" v-if="store.trend">
      <template #header><span>贡献趋势</span></template>
      <div class="trend-chart-placeholder">
        <div class="trend-bars">
          <div
            v-for="(val, idx) in store.trend.values"
            :key="store.trend.categories[idx]"
            class="trend-bar-wrapper"
          >
            <div class="trend-bar-label">{{ store.trend.categories[idx].substring(5) }}月</div>
            <div class="trend-bar" :style="{ height: barHeight(val) + 'px' }" :title="val">
              <span class="trend-bar-value">{{ val }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- Composition and list -->
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card class="comp-card" shadow="never" v-if="store.composition">
          <template #header><span>贡献构成</span></template>
          <div v-if="store.composition.categories.length === 0" class="empty-text">暂无数据</div>
          <div v-for="cat in store.composition.categories" :key="cat.category" class="comp-item">
            <span class="comp-label">{{ cat.label }}</span>
            <el-progress :percentage="cat.percent" :stroke-width="16" :text-inside="false" />
            <span class="comp-points">{{ cat.points }}</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card class="list-card" shadow="never">
          <template #header><span>贡献明细</span></template>
          <el-table :data="store.items" v-loading="store.loading" stripe size="small">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
            <el-table-column prop="category" label="类别" width="100">
              <template #default="{ row }">
                <el-tag size="small" type="info">{{ store.getCategoryLabel(row.category) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="points" label="贡献值" width="100" align="right" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="store.getStatusType(row.status)">
                  {{ store.getStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="occurredAt" label="时间" width="160">
              <template #default="{ row }">
                {{ formatDate(row.occurredAt) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="showDetail(row.id)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="load-more" v-if="store.hasMore">
            <el-button text @click="handleLoadMore">加载更多</el-button>
          </div>
          <div v-if="store.items.length === 0 && !store.loading" class="empty-text">暂无贡献记录</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Detail dialog -->
    <el-dialog v-model="detailVisible" title="贡献详情" width="560px">
      <el-descriptions v-if="store.detail" :column="1" border>
        <el-descriptions-item label="ID">{{ store.detail.id }}</el-descriptions-item>
        <el-descriptions-item label="标题">{{ store.detail.title }}</el-descriptions-item>
        <el-descriptions-item label="贡献值">{{ store.detail.points }}</el-descriptions-item>
        <el-descriptions-item label="类别">
          <el-tag size="small">{{ store.getCategoryLabel(store.detail.category) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="store.getStatusType(store.detail.status)">
            {{ store.getStatusLabel(store.detail.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="计算基数">{{ store.detail.calculationBase || '-' }}</el-descriptions-item>
        <el-descriptions-item label="系数">{{ store.detail.coefficient || '-' }}</el-descriptions-item>
        <el-descriptions-item label="计算说明">{{ store.detail.calculationDescription || '-' }}</el-descriptions-item>
        <el-descriptions-item label="调整原因">{{ store.detail.adjustmentReason || '-' }}</el-descriptions-item>
        <el-descriptions-item label="发生时间">{{ formatDate(store.detail.occurredAt) }}</el-descriptions-item>
        <el-descriptions-item label="结算时间">{{ formatDate(store.detail.settledAt) || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useContributionsStore } from '@/stores/contributions'
import { ElMessage } from 'element-plus'

const store = useContributionsStore()

const selectedMonth = ref('2026-07')
const settling = ref(false)
const detailVisible = ref(false)
const filters = ref({ status: '', category: '' })

// Computed
const pendingCount = computed(() => {
  return store.overview?.statusCounts?.pending || 0
})

const growthDisplay = computed(() => {
  const rate = store.overview?.growthRate
  if (rate === null || rate === undefined) return '--'
  return (rate >= 0 ? '+' : '') + rate.toFixed(1) + '%'
})

const growthColor = computed(() => {
  const rate = store.overview?.growthRate
  if (rate === null || rate === undefined) return '#909399'
  return rate >= 0 ? '#67c23a' : '#f56c6c'
})

// Methods
function barHeight(val) {
  const maxVal = Math.max(...(store.trend?.values?.map(v => parseFloat(v) || 0) || [1]), 1)
  return Math.max((parseFloat(val) || 0) / maxVal * 120, 2)
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

async function onMonthChange() {
  await loadAll()
}

async function onFilterChange() {
  store.setFilters(filters.value)
  await store.fetchList({ month: selectedMonth.value })
}

async function loadAll() {
  const month = selectedMonth.value
  await Promise.all([
    store.fetchOverview(month),
    store.fetchTrend('6m'),
    store.fetchComposition(month),
    store.fetchList({ month }),
  ])
}

async function handleSettle() {
  settling.value = true
  try {
    await store.settleMonth(selectedMonth.value)
    await store.fetchOverview(selectedMonth.value)
    await store.fetchList({ month: selectedMonth.value })
  } finally {
    settling.value = false
  }
}

async function handleLoadMore() {
  await store.loadMore()
}

async function showDetail(id) {
  await store.fetchDetail(id)
  detailVisible.value = true
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; }

.filter-card { margin-bottom: 16px; }

.stats-row { margin-bottom: 16px; }
.stats-row .el-col { margin-bottom: 8px; }

.chart-card { margin-bottom: 16px; }
.trend-chart-placeholder { padding: 10px 0; }
.trend-bars { display: flex; align-items: flex-end; justify-content: space-around; height: 180px; padding-top: 20px; }
.trend-bar-wrapper { display: flex; flex-direction: column; align-items: center; flex: 1; }
.trend-bar { width: 32px; background: linear-gradient(180deg, #409eff, #79bbff); border-radius: 4px 4px 0 0; min-height: 2px; transition: height 0.3s; position: relative; }
.trend-bar-value { position: absolute; top: -18px; left: 50%; transform: translateX(-50%); font-size: 10px; color: #606266; white-space: nowrap; }
.trend-bar-label { font-size: 11px; color: #909399; margin-top: 4px; }

.comp-card { margin-bottom: 16px; }
.comp-item { margin-bottom: 12px; }
.comp-label { font-size: 13px; color: #606266; display: block; margin-bottom: 4px; }
.comp-points { font-size: 12px; color: #909399; display: block; text-align: right; margin-top: 2px; }

.list-card { margin-bottom: 16px; }
.load-more { text-align: center; padding: 12px 0; }
.empty-text { text-align: center; padding: 40px 0; color: #909399; font-size: 14px; }
</style>
