<template>
  <div class="page-dashboard">
    <h2 class="page-title">仪表盘</h2>

    <!-- Welcome -->
    <el-card class="welcome-card" shadow="never">
      <div class="welcome-content">
        <h3>{{ welcomeMessage }}</h3>
        <p class="welcome-subtitle">{{ roleLabel }} · {{ today }}</p>
      </div>
    </el-card>

    <div class="stats-row kpi-row">
      <div class="stat-card stagger-item" v-for="(k, i) in activeKpis" :key="k.key" :style="{ '--stagger': i * 80 + 'ms' }">
        <div class="stat-icon" :style="{ background: k.bg, color: k.color }">
          <el-icon :size="18"><component :is="k.icon" /></el-icon>
        </div>
        <div class="stat-value" :style="{ color: k.color }">{{ k.fmt(counts[k.key]) }}</div>
        <div class="stat-label">{{ k.label }}</div>
      </div>
    </div>

    <!-- Notices -->
    <el-card v-if="workbenchData" shadow="never" class="notices-card">
      <template #header>
        <span>通知摘要</span>
      </template>
      <el-empty v-if="!workbenchData.notices?.length" description="暂无通知" />
      <div v-else class="notices-list">
        <div
          v-for="(notice, idx) in workbenchData.notices"
          :key="idx"
          class="notice-item"
        >
          <el-tag
            :type="noticeTagType(notice.type)"
            size="small"
            :disable-transitions="true"
          >
            {{ notice.type }}
          </el-tag>
          <span class="notice-title">{{ notice.title }}</span>
          <span class="notice-time">{{ formatTime(notice.time) }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import http from '@/api/http'
import {
  User, Wallet, Link, Clock,
  UserFilled, Stamp, Warning, OfficeBuilding,
} from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()

const isAdmin = computed(() => authStore.userRole === 'admin')
const roleLabel = computed(() => {
  const map = { admin: '管理员', promoter: '推广员', finance: '财务', ops: '运营' }
  return map[authStore.userRole] || authStore.userRole || '用户'
})

const today = ref('')
const welcomeMessage = ref('欢迎使用北京儒泰分销管理系统')
const metrics = ref({})
const workbenchData = ref(null)
const recentBindings = ref([])
const contributionSummary = ref(null)

const primary = { bg: 'var(--el-color-primary-light-9)', color: 'var(--el-color-primary)' }
const warning = { bg: '#fef3c7', color: 'var(--app-warning)' }
const danger = { bg: '#fee2e2', color: 'var(--app-danger)' }
const success = { bg: '#dcfce7', color: 'var(--app-success)' }

const intFmt = (v) => (Number.isFinite(Number(v)) ? Math.round(Number(v)).toLocaleString() : '-')
const yuanFmt = (v) => `¥${((Number.isFinite(Number(v)) ? Number(v) : 0) / 100).toFixed(2)}`

// 用 reactive 存数字：模板直接解包，避免 ref 嵌套对象不解包导致 NaN
const counts = reactive({
  myCustomers: 0,
  myMonthlyConsumption: 0,
  myBindings: 0,
  pendingFollowups: 0,
  totalPromoters: 0,
  pendingQualifications: 0,
  abnormalBindings: 0,
  totalCustomers: 0,
})

function makeKpi(key, label, icon, palette, fmt) {
  return { key, label, icon, ...palette, fmt }
}

const promoterKpis = [
  makeKpi('myCustomers', '我的客户', User, primary, intFmt),
  makeKpi('myMonthlyConsumption', '本月消费 (元)', Wallet, primary, yuanFmt),
  makeKpi('myBindings', '本月新增绑定', Link, success, intFmt),
  makeKpi('pendingFollowups', '待跟进', Clock, warning, intFmt),
]

const adminKpis = [
  makeKpi('totalPromoters', '推广员总数', UserFilled, primary, intFmt),
  makeKpi('pendingQualifications', '待审核资质', Stamp, warning, intFmt),
  makeKpi('abnormalBindings', '异常绑定', Warning, danger, intFmt),
  makeKpi('totalCustomers', '客户总数', OfficeBuilding, primary, intFmt),
]

const activeKpis = computed(() => (isAdmin.value ? adminKpis : promoterKpis))

// 数字滚动：metrics 更新后逐 KPI 从 0 动画到目标值
watch(metrics, (m) => {
  const list = activeKpis.value
  list.forEach((k) => {
    const to = Number.isFinite(Number(m[k.key])) ? Number(m[k.key]) : 0
    animateCount(k.key, to)
  })
}, { immediate: true })

function animateCount(key, to) {
  const from = counts[key]
  const dur = 900
  const start = performance.now()
  const ease = (t) => 1 - Math.pow(1 - t, 3)
  const step = (now) => {
    const p = Math.min(1, (now - start) / dur)
    counts[key] = from + (to - from) * ease(p)
    if (p < 1) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

onMounted(async () => {
  const now = new Date()
  today.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  try {
    const res = await http.get('/workbench')
    const data = res.data?.data || res.data
    if (data) {
      welcomeMessage.value = data.welcomeMessage || welcomeMessage.value
      metrics.value = data.metrics || {}
    }
  } catch (e) {
    // Workbench not yet deployed — use fallback
    metrics.value = { myCustomers: 0, myMonthlyConsumption: 0, myBindings: 0, pendingFollowups: 0 }
  }

  try {
    const noticesRes = await http.get('/workbench/notices')
    workbenchData.value = noticesRes.data?.data || noticesRes.data
  } catch {
    // Silently ignore
  }

  try {
    const bindingRes = await http.get('/workbench/recent-bindings')
    const bData = bindingRes.data?.data || bindingRes.data
    recentBindings.value = bData?.items || []
  } catch {
    // Silently ignore
  }

  try {
    const contribRes = await http.get('/workbench/contribution-summary')
    contributionSummary.value = contribRes.data?.data || contribRes.data
  } catch {
    // Silently ignore
  }
})

function noticeTagType(type) {
  const map = { qualification: 'warning', binding: 'success', system: 'info' }
  return map[type] || 'info'
}

function formatTime(t) {
  if (!t) return ''
  try {
    return new Date(t).toLocaleDateString('zh-CN')
  } catch {
    return t
  }
}
</script>

<style scoped>
.page-dashboard { padding: 10px 0; }
.page-title { margin-bottom: 16px; }

.welcome-card { margin-bottom: 16px; }
.welcome-content h3 { margin: 0 0 4px 0; font-size: 18px; color: var(--app-text-primary); }
.welcome-subtitle { margin: 0; color: var(--app-text-secondary); font-size: 13px; }

.kpi-row { margin-bottom: 16px; }

.notices-list { display: flex; flex-direction: column; gap: 10px; }
.notice-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; transition: background-color 0.2s var(--app-ease); }
.notice-item:hover { background: #f5f8ff; }
.notice-title { flex: 1; font-size: 13px; color: var(--app-text-regular); }
.notice-time { font-size: 12px; color: var(--app-text-placeholder); }
</style>
