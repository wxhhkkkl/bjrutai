<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">消费业绩</h2>
      <el-button @click="loadAll"><el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新</el-button>
    </div>

    <!-- 筛选栏：月份 + 组织树选择器 -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-row">
        <el-date-picker v-model="month" type="month" value-format="YYYY-MM" placeholder="选择月份" style="width: 140px" @change="loadAll" />
        <el-tree-select
          v-model="orgId"
          :data="treeData"
          :props="{ label: 'name', children: 'children' }"
          node-key="orgId"
          check-strictly
          default-expand-all
          clearable
          placeholder="全部组织（选择组织按子树过滤）"
          style="width: 280px"
          @change="loadAll"
        />
      </div>
    </el-card>

    <!-- 统计数据 -->
    <el-row :gutter="16" class="stats-row" v-if="stats">
      <el-col v-for="s in statCards" :key="s.key" :span="6">
        <div class="stat-card" :style="{ borderTopColor: s.color }">
          <div class="stat-label">{{ s.label }}</div>
          <div class="stat-value" :style="{ color: s.color }">{{ s.format(stats[s.key]) }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 月度趋势 -->
    <el-card class="chart-card" shadow="never">
      <template #header><span>总体消费月度趋势</span></template>
      <div class="trend-bars" v-if="trend.length">
        <div v-for="t in trend" :key="t.month" class="trend-bar-wrapper">
          <div class="trend-bar-label">{{ t.month.substring(5) }}月</div>
          <div class="trend-bar" :style="{ height: barHeight(t.amountCent) + 'px' }" :title="`${t.month}: ¥${fmtYuan(t.amountCent)}`">
            <span class="trend-bar-value">¥{{ fmtYuan(t.amountCent) }}</span>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无数据" :image-size="60" />
    </el-card>

    <!-- 排名 -->
    <el-card class="chart-card" shadow="never">
      <template #header><span>业绩排名</span></template>
      <el-tabs v-model="rankTab" @tab-change="loadRankings">
        <el-tab-pane label="组织业绩排名" name="orgs">
          <el-table :data="orgsRanking.items" v-loading="rankLoading" stripe size="small">
            <el-table-column prop="rank" label="名次" width="70" align="center" />
            <el-table-column prop="orgName" label="组织" min-width="140" />
            <el-table-column label="当月消费" width="140" align="right"><template #default="{ row }">¥{{ fmtYuan(row.amountCent) }}</template></el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="个人业绩排名" name="persons">
          <el-table :data="personsRanking.items" v-loading="rankLoading" stripe size="small">
            <el-table-column prop="rank" label="名次" width="70" align="center" />
            <el-table-column prop="name" label="人员" min-width="100" />
            <el-table-column prop="orgName" label="组织" min-width="120" />
            <el-table-column label="当月消费" width="140" align="right"><template #default="{ row }">¥{{ fmtYuan(row.amountCent) }}</template></el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="绑定数量排名" name="bindings">
          <div class="bindings-toolbar">
            <el-radio-group v-model="bindScope" size="small" @change="loadRankings">
              <el-radio-button label="person">按个人</el-radio-button>
              <el-radio-button label="org">按组织</el-radio-button>
            </el-radio-group>
          </div>
          <el-table :data="bindingsRanking.items" v-loading="rankLoading" stripe size="small">
            <el-table-column prop="rank" label="名次" width="70" align="center" />
            <el-table-column :prop="bindScope === 'person' ? 'name' : 'orgName'" label="主体" min-width="140" />
            <el-table-column label="绑定客户数" width="140" align="right"><template #default="{ row }">{{ row.boundCount }}</template></el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 最新 30 条消费明细 -->
    <el-card class="chart-card" shadow="never">
      <template #header><span>最新消费明细（30 条）</span></template>
      <el-table :data="latest" v-loading="loading" stripe size="small">
        <el-table-column prop="personName" label="人员" min-width="90" />
        <el-table-column prop="orgName" label="组织" min-width="110" />
        <el-table-column prop="title" label="标题" min-width="150" show-overflow-tooltip />
        <el-table-column label="消费金额" width="110" align="right"><template #default="{ row }">¥{{ fmtYuan(row.amountCent) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }">{{ statusLabel(row.status) }}</template></el-table-column>
        <el-table-column label="时间" width="160"><template #default="{ row }">{{ formatTime(row.occurredAt) }}</template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { orgApi } from '@/api/org'
import { contributionDashboardApi } from '@/api/contributions'

const loading = ref(false)
const rankLoading = ref(false)
const month = ref('')
const orgId = ref(null)
const treeData = ref([])

const stats = ref(null)

function fmtYuan(cent) {
  return (Number(cent || 0) / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const statCards = computed(() => [
  { key: 'monthlyAmountCent', label: '当月总消费', color: '#409eff', format: (v) => `¥${fmtYuan(v)}` },
  { key: 'totalAmountCent', label: '累计消费', color: '#67c23a', format: (v) => `¥${fmtYuan(v)}` },
  { key: 'personCount', label: '人员数', color: '#f56c6c', format: (v) => v ?? 0 },
  { key: 'boundUserCount', label: '绑定用户数', color: '#909399', format: (v) => v ?? 0 },
])
const trend = ref([])
const latest = ref([])
const rankTab = ref('orgs')
const bindScope = ref('person')
const orgsRanking = ref({ items: [] })
const personsRanking = ref({ items: [] })
const bindingsRanking = ref({ items: [] })

function statusLabel(s) {
  return { paid: '已支付', partially_refunded: '部分退款', refunded: '已退款', cancelled: '已取消' }[s] || s
}

async function loadOrgTree() {
  try {
    const data = await orgApi.getTree()
    treeData.value = Array.isArray(data.tree) ? data.tree : (data.tree ? [data.tree] : [])
  } catch {
    treeData.value = []
  }
}

async function loadDashboard() {
  loading.value = true
  try {
    const params = { month: month.value }
    if (orgId.value) params.orgId = orgId.value
    const data = await contributionDashboardApi.dashboard(params)
    stats.value = data.stats
    trend.value = data.trend || []
    latest.value = data.latest || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载消费看板失败')
  } finally {
    loading.value = false
  }
}

async function loadRankings() {
  rankLoading.value = true
  try {
    const common = { month: month.value, pageSize: 50 }
    if (orgId.value) common.orgId = orgId.value
    if (rankTab.value === 'orgs') orgsRanking.value = await contributionDashboardApi.orgsRanking(common)
    if (rankTab.value === 'persons') personsRanking.value = await contributionDashboardApi.personsRanking(common)
    if (rankTab.value === 'bindings') {
      bindingsRanking.value = await contributionDashboardApi.bindingsRanking({ ...common, scope: bindScope.value })
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载排名失败')
  } finally {
    rankLoading.value = false
  }
}

function barHeight(v) {
  const max = Math.max(...trend.value.map((t) => t.amountCent), 1)
  return Math.max(4, Math.round((v / max) * 180))
}

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

async function loadAll() {
  await Promise.all([loadDashboard(), loadRankings()])
}

onMounted(async () => {
  if (!month.value) {
    const now = new Date()
    month.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  }
  await loadOrgTree()
  await loadAll()
})
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.filter-card { margin-bottom: 14px; }
.filter-row { display: flex; gap: 12px; align-items: center; }
.stats-row { margin-bottom: 14px; }
.stat-card { border: 1px solid #ebeef5; border-top: 3px solid; border-radius: 8px; padding: 14px 16px; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04); }
.stat-label { font-size: 13px; color: #909399; margin-bottom: 6px; }
.stat-value { font-size: 26px; font-weight: 700; line-height: 1.2; }
.chart-card { margin-bottom: 14px; }
.trend-bars { display: flex; align-items: flex-end; gap: 4px; height: 200px; padding: 16px 4px 0; }
.trend-bar-wrapper { flex: 1; min-width: 24px; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
.trend-bar-label { font-size: 12px; color: #909399; margin-top: 4px; }
.trend-bar { width: 60%; max-width: 40px; background: linear-gradient(180deg, #409eff, #66b1ff); border-radius: 3px 3px 0 0; position: relative; }
.trend-bar-value { position: absolute; top: -16px; left: 0; right: 0; font-size: 10px; color: #606266; text-align: center; white-space: nowrap; }
.bindings-toolbar { margin-bottom: 10px; }
</style>
