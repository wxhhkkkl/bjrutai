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

    <el-row :gutter="16" class="kpi-row">
      <!-- Promoter KPIs -->
      <template v-if="!isAdmin">
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value">{{ metrics.myCustomers ?? '-' }}</div>
            <div class="kpi-label">我的客户</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value">¥{{ fmtYuan(metrics.myMonthlyConsumption) }}</div>
            <div class="kpi-label">本月消费 (元)</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value">{{ metrics.myBindings ?? '-' }}</div>
            <div class="kpi-label">本月新增绑定</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value">{{ metrics.pendingFollowups ?? '-' }}</div>
            <div class="kpi-label">待跟进</div>
          </el-card>
        </el-col>
      </template>

      <!-- Admin KPIs -->
      <template v-else>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value">{{ metrics.totalPromoters ?? '-' }}</div>
            <div class="kpi-label">推广员总数</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value pending">{{ metrics.pendingQualifications ?? '-' }}</div>
            <div class="kpi-label">待审核资质</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value abnormal">{{ metrics.abnormalBindings ?? '-' }}</div>
            <div class="kpi-label">异常绑定</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card shadow="hover" class="kpi-card">
            <div class="kpi-value">{{ metrics.totalCustomers ?? '-' }}</div>
            <div class="kpi-label">客户总数</div>
          </el-card>
        </el-col>
      </template>
    </el-row>

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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

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

function fmtYuan(cent) {
  return (Number(cent || 0) / 100).toFixed(2)
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
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin-bottom: 16px; }

.welcome-card { margin-bottom: 16px; }
.welcome-content h3 { margin: 0 0 4px 0; font-size: 18px; color: #303133; }
.welcome-subtitle { margin: 0; color: #909399; font-size: 13px; }

.kpi-row { margin-bottom: 16px; }
.kpi-card { text-align: center; }
.kpi-value { font-size: 28px; font-weight: 700; color: #409eff; }
.kpi-value.pending { color: #e6a23c; }
.kpi-value.abnormal { color: #f56c6c; }
.kpi-label { margin-top: 4px; color: #909399; font-size: 13px; }

.notices-list { display: flex; flex-direction: column; gap: 10px; }
.notice-item { display: flex; align-items: center; gap: 8px; }
.notice-title { flex: 1; font-size: 13px; color: #606266; }
.notice-time { font-size: 12px; color: #c0c4cc; }
</style>
