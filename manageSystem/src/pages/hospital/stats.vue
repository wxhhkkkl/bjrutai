<template>
  <section class="hospital-stats-page">
    <header class="page-header">
      <h2 class="page-title">互联网医院统计</h2>
    </header>

    <div class="hospital-stats-note">
      <strong>统计口径</strong>
      <p>统计「点击进入按钮」和「长按小程序码」两类事件。长按识别后由微信直接打开对方小程序，系统无法确认对方是否真的打开。</p>
    </div>

    <el-form inline class="mall-management-filters" @submit.prevent="search">
      <el-form-item label="统计日期">
        <el-date-picker
          v-model="range"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          :clearable="false"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :disabled="loading" @click="search">
          查询
        </el-button>
      </el-form-item>
      <el-form-item>
        <el-button :disabled="loading" :loading="exporting" @click="exportUsers">
          导出
        </el-button>
      </el-form-item>
    </el-form>

    <div v-loading="loading" class="hospital-summary">
      <div class="hospital-summary__card">
        <span class="hospital-summary__label">点击进入按钮</span>
        <strong>{{ summary.entryTapCount }}<small> 次</small></strong>
        <span class="hospital-summary__sub">{{ summary.entryTapUsers }} 人</span>
      </div>
      <div class="hospital-summary__card">
        <span class="hospital-summary__label">长按小程序码</span>
        <strong>{{ summary.qrLongpressCount }}<small> 次</small></strong>
        <span class="hospital-summary__sub">{{ summary.qrLongpressUsers }} 人</span>
      </div>
      <div class="hospital-summary__card">
        <span class="hospital-summary__label">长按转化率</span>
        <strong>{{ longpressRate }}</strong>
        <span class="hospital-summary__sub">长按人数 / 点击人数</span>
      </div>
      <div class="hospital-summary__card">
        <span class="hospital-summary__label">匿名事件</span>
        <strong>{{ summary.anonymousCount }}<small> 次</small></strong>
        <span class="hospital-summary__sub">未携带登录态的上报</span>
      </div>
    </div>

    <el-card shadow="never" class="hospital-table-card">
      <template #header>
        <div class="hospital-table-head">
          <span>按用户统计</span>
          <span class="hospital-table-head__count">共 {{ users.total }} 人</span>
        </div>
      </template>
      <el-table :data="users.items" empty-text="所选日期内暂无数据">
        <el-table-column prop="name" label="用户" min-width="120" />
        <el-table-column label="手机号" min-width="130">
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="身份" min-width="110">
          <template #default="{ row }">{{ roleLabel(row.userType) }}</template>
        </el-table-column>
        <el-table-column label="组织" min-width="160">
          <template #default="{ row }">{{ row.organization || '—' }}</template>
        </el-table-column>
        <el-table-column prop="entryTapCount" label="点击次数" width="100" />
        <el-table-column prop="qrLongpressCount" label="长按次数" width="100" />
        <el-table-column label="首次" min-width="150">
          <template #default="{ row }">{{ time(row.firstAt) }}</template>
        </el-table-column>
        <el-table-column label="最近" min-width="150">
          <template #default="{ row }">{{ time(row.lastAt) }}</template>
        </el-table-column>
      </el-table>
      <div class="hospital-pager">
        <el-pagination
          layout="prev, pager, next, total"
          :total="users.total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="changePage"
        />
      </div>
    </el-card>

    <el-card shadow="never" class="hospital-table-card">
      <template #header><span>按日统计</span></template>
      <el-table :data="pagedDaily" empty-text="所选日期内暂无数据">
        <el-table-column prop="date" label="日期" min-width="120" />
        <el-table-column prop="entryTapCount" label="点击次数" min-width="100" />
        <el-table-column prop="entryTapUsers" label="点击人数" min-width="100" />
        <el-table-column prop="qrLongpressCount" label="长按次数" min-width="100" />
        <el-table-column prop="qrLongpressUsers" label="长按人数" min-width="100" />
      </el-table>
      <div class="hospital-pager">
        <el-pagination
          layout="prev, pager, next, total"
          :total="daily.length"
          :page-size="DAILY_PAGE_SIZE"
          :current-page="dailyPage"
          @current-change="changeDailyPage"
        />
      </div>
    </el-card>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '@/api/hospital-stats'

const ROLE_LABELS = {
  personal: '个人用户',
  promoter: '推广员',
  distributor: '客户顾问',
  doctor: '医生',
  admin: '管理员',
  finance: '财务',
  ops: '运营',
}

function shanghaiDate(offsetDays = 0) {
  const moment = new Date(Date.now() + offsetDays * 86400000)
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(moment)
}

const range = ref([shanghaiDate(-29), shanghaiDate(0)])
const loading = ref(false)
const exporting = ref(false)
const payload = ref(null)
const page = ref(1)
const pageSize = ref(20)
const DAILY_PAGE_SIZE = 15
const dailyPage = ref(1)

const summary = computed(
  () =>
    payload.value?.summary || {
      entryTapCount: 0,
      entryTapUsers: 0,
      qrLongpressCount: 0,
      qrLongpressUsers: 0,
      anonymousCount: 0,
      longpressRate: 0,
    }
)
const users = computed(() => payload.value?.users || { items: [], total: 0 })
const daily = computed(() => payload.value?.daily || [])
const pagedDaily = computed(() =>
  daily.value.slice(
    (dailyPage.value - 1) * DAILY_PAGE_SIZE,
    dailyPage.value * DAILY_PAGE_SIZE
  )
)
const longpressRate = computed(
  () => `${Math.round((summary.value.longpressRate || 0) * 100)}%`
)

function roleLabel(value) {
  return ROLE_LABELS[value] || '—'
}

function time(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

async function load() {
  loading.value = true
  try {
    payload.value = await api.getHospitalStats({
      from: range.value[0],
      to: range.value[1],
      page: page.value,
      pageSize: pageSize.value,
    })
  } catch (error) {
    ElMessage.error(error?.userMessage || error?.message || '统计读取失败')
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  dailyPage.value = 1
  load()
}

async function exportUsers() {
  if (exporting.value) return
  exporting.value = true
  try {
    const response = await api.exportHospitalStats({
      from: range.value[0],
      to: range.value[1],
    })
    const blob =
      response.data instanceof Blob
        ? response.data
        : new Blob([response.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `互联网医院统计_${range.value[0]}_${range.value[1]}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error) {
    ElMessage.error(error?.userMessage || error?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

function changePage(next) {
  page.value = next
  load()
}

function changeDailyPage(next) {
  dailyPage.value = next
}

onMounted(load)
</script>

<style scoped>
.hospital-stats-page {
  display: grid;
  gap: 12px;
}

.hospital-stats-page > .page-header {
  margin-bottom: 0;
}

.hospital-stats-note {
  padding: 14px 18px;
  background: #f4f8ff;
  border: 1px solid #dbe7f7;
  border-left: 4px solid var(--el-color-primary, #1677ff);
  border-radius: 10px;
}

.hospital-stats-note strong {
  color: var(--app-text-primary, #151a21);
  font-size: 14px;
}

.hospital-stats-note p {
  margin: 6px 0 0;
  color: var(--app-text-regular, #4d5663);
  font-size: 13px;
  line-height: 1.7;
}

.hospital-stats-page :deep(.mall-management-filters) {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.hospital-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.hospital-summary__card {
  display: grid;
  gap: 6px;
  padding: 18px 20px;
  background: var(--app-bg-card, #ffffff);
  border: 1px solid var(--app-border-color, #e7ebf1);
  border-radius: var(--app-radius-md, 12px);
  box-shadow: var(--app-shadow-sm, 0 4px 16px rgba(31, 61, 105, 0.06));
}

.hospital-summary__label {
  color: var(--app-text-regular, #4d5663);
  font-size: 13px;
}

.hospital-summary__card strong {
  color: var(--app-text-primary, #151a21);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.hospital-summary__card small {
  font-size: 14px;
  font-weight: 500;
}

.hospital-summary__sub {
  color: var(--el-text-color-secondary, #8992a1);
  font-size: 12px;
}

.hospital-table-card {
  border-radius: var(--app-radius-md, 12px);
}

.hospital-table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.hospital-table-head__count {
  color: var(--el-text-color-secondary, #8992a1);
  font-size: 13px;
  font-weight: 400;
}

.hospital-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
