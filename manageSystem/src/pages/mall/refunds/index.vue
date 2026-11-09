<template>
  <section class="finance-page">
    <header class="page-heading">
      <div>
        <h2>退款订单</h2>
        <p>商品退款与运费退款分列展示；只有渠道确认成功的退款才计入成功退款。</p>
      </div>
      <el-button data-test="reload" :loading="loading" @click="load">刷新</el-button>
    </header>

    <el-form inline class="filters" @submit.prevent="search">
      <el-form-item label="退款状态">
        <el-select v-model="filters.status" clearable placeholder="全部状态">
          <el-option
            v-for="(label, value) in refundStates"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="订单号">
        <el-input
          v-model="filters.orderNo"
          clearable
          maxlength="32"
          placeholder="完整订单号"
        />
      </el-form-item>
      <el-form-item label="退款时间">
        <el-date-picker
          v-model="filters.range"
          type="datetimerange"
          start-placeholder="开始时间"
          end-placeholder="结束时间（不含）"
        />
      </el-form-item>
      <el-form-item>
        <el-button data-test="search" type="primary" @click="search">查询</el-button>
      </el-form-item>
      <el-form-item v-if="canExport">
        <el-select v-model="exportFormat" aria-label="导出格式" class="format">
          <el-option label="Excel" value="xlsx" />
          <el-option label="CSV" value="csv" />
        </el-select>
        <el-button
          data-test="export"
          :disabled="loading || exportBusy || !!applied.orderNo"
          @click="exportVisibleRows"
        >
          导出退款
        </el-button>
      </el-form-item>
    </el-form>
    <el-alert
      v-if="canExport && applied.orderNo"
      title="导出支持状态和时间范围；请清空订单号筛选后导出。"
      type="info"
      :closable="false"
    />

    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="exportError"
      :title="exportError"
      type="error"
      :closable="false"
    />
    <el-alert
      v-if="exportNotice"
      :title="exportNotice"
      type="success"
      :closable="false"
    />
    <section v-if="exportIntent" class="export-state" aria-live="polite">
      <div>
        <strong>{{ exportStatusLabel || '导出请求处理中' }}</strong>
        <span v-if="exportResult?.rowCount != null">· {{ exportResult.rowCount }} 条记录</span>
        <span v-if="exportResult?.errorCode">· {{ exportResult.errorCode }}</span>
      </div>
      <div class="export-actions">
        <el-button
          data-test="refresh-export"
          :loading="exportBusy"
          @click="refreshExport"
        >
          刷新状态
        </el-button>
        <el-button
          v-if="exportResult?.status === 'failed'"
          data-test="retry-export"
          type="warning"
          :loading="exportBusy"
          @click="retryExport"
        >
          重新领取
        </el-button>
        <el-button
          v-if="exportResult?.status === 'completed'"
          data-test="download-export"
          type="primary"
          @click="downloadExport"
        >
          下载文件
        </el-button>
      </div>
    </section>

    <el-table v-loading="loading" :data="items" empty-text="暂无退款记录">
      <el-table-column prop="outRefundNo" label="商户退款单号" min-width="190" />
      <el-table-column label="订单ID" min-width="180">
        <template #default="{ row }">
          <el-button link @click="router.push(`/mall/orders/${row.orderId}`)">
            {{ row.orderId }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="商品退款" width="120" align="right">
        <template #default="{ row }">{{ money(row.goodsRefundCent) }}</template>
      </el-table-column>
      <el-table-column label="运费退款" width="120" align="right">
        <template #default="{ row }">{{ money(row.freightRefundCent) }}</template>
      </el-table-column>
      <el-table-column label="退款合计" width="120" align="right">
        <template #default="{ row }">{{ money(row.totalCent) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-tag :type="refundStateType(row.status)">
            {{ refundStates[row.status] || '待核实' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="退款时间" min-width="170">
        <template #default="{ row }">{{ time(row.confirmedAt) }}</template>
      </el-table-column>
      <el-table-column label="关联售后" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link @click="router.push(`/mall/aftersales/${row.aftersaleId}`)">
            查看售后
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="pager">
      <span>共 {{ total }} 条</span>
      <el-button :disabled="loading || !history.length" @click="previous">上一页</el-button>
      <el-button :disabled="loading || !nextCursor" @click="next">下一页</el-button>
    </footer>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  exportAdminMallRefunds,
  listAdminMallRefunds,
} from '@/api/mall-finance'
import { useMallFinanceExport } from '@/composables/useMallFinanceExport'

const refundStates = {
  prepared: '待提交渠道',
  processing: '退款处理中',
  unknown: '结果待核实',
  succeeded: '退款成功',
  closed: '已关闭',
  abnormal: '退款异常',
  rejected_unaccepted: '渠道未受理',
}
const router = useRouter()
const auth = useAuthStore()
const canReadRefunds = computed(() => auth.hasPermission('mall.refunds.read'))
const canExport = computed(() => auth.hasPermission('mall.finance.export'))
const filters = reactive({ status: '', orderNo: '', range: [] })
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const cursor = ref(null)
const nextCursor = ref(null)
const history = ref([])
const applied = ref({})
const exportFormat = ref('xlsx')
const {
  exportIntent,
  exportResult,
  exportBusy,
  exportError,
  exportNotice,
  exportStatusLabel,
  exportFiltered,
  refreshExport,
  retryExport,
  downloadExport,
  restoreExport,
} = useMallFinanceExport('refunds', exportAdminMallRefunds, auth.user?.userId)

function money(cent) {
  return `¥${(Number(cent || 0) / 100).toFixed(2)}`
}
function time(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}
function refundStateType(status) {
  if (status === 'succeeded') return 'success'
  if (status === 'unknown' || status === 'processing') return 'warning'
  if (status === 'closed' || status === 'rejected_unaccepted') return 'info'
  return 'primary'
}
function iso(value) {
  return value instanceof Date && !Number.isNaN(value.getTime())
    ? value.toISOString()
    : null
}
function activeDateRange() {
  if (!Array.isArray(filters.range) || filters.range.length !== 2) return null
  const from = iso(filters.range[0])
  const to = iso(filters.range[1])
  return from && to ? { from, to } : null
}

async function load() {
  if (!canReadRefunds.value || loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listAdminMallRefunds({
      ...applied.value,
      pageSize: 20,
      ...(cursor.value ? { cursor: cursor.value } : {}),
    })
    items.value = result.items || []
    total.value = result.total || 0
    nextCursor.value = result.nextCursor || null
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '退款记录读取失败'
    total.value = 0
    nextCursor.value = null
  } finally {
    loading.value = false
  }
}

async function search() {
  if (loading.value) return
  const range = activeDateRange()
  applied.value = {
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.orderNo.trim() ? { orderNo: filters.orderNo.trim() } : {}),
    ...(range ? { fromAt: range.from, toAt: range.to } : {}),
  }
  cursor.value = null
  history.value = []
  await load()
}
async function next() {
  if (loading.value || !nextCursor.value) return
  history.value.push(cursor.value)
  cursor.value = nextCursor.value
  await load()
}
async function previous() {
  if (loading.value || !history.value.length) return
  cursor.value = history.value.pop()
  await load()
}
async function exportVisibleRows() {
  if (applied.value.orderNo) {
    error.value = '导出支持状态和时间范围；请清空订单号筛选后再导出'
    return
  }
  const range = activeDateRange()
  if (!range) {
    error.value = '导出前请选择明确的开始和结束时间'
    return
  }
  const span = new Date(range.to) - new Date(range.from)
  if (span <= 0 || span > 31 * 24 * 60 * 60 * 1000) {
    error.value = '导出时间范围必须大于零且不超过31天'
    return
  }
  error.value = ''
  await exportFiltered({
    from: range.from,
    to: range.to,
    ...(applied.value.status ? { status: applied.value.status } : {}),
    format: exportFormat.value,
  })
}

onMounted(async () => {
  await load()
  if (canExport.value) await restoreExport()
})

defineExpose({
  filters,
  items,
  applied,
  exportFormat,
  load,
  search,
  next,
  previous,
  exportFiltered: exportVisibleRows,
  exportVisibleRows,
  refreshExport,
  retryExport,
})
</script>

<style scoped>
.finance-page {
  padding: 20px;
}
.page-heading,
.pager,
.export-state,
.export-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-heading,
.export-state {
  justify-content: space-between;
}
.page-heading {
  margin: 12px 0 18px;
}
.page-heading h2 {
  margin: 0 0 6px;
}
.page-heading p {
  margin: 0;
  color: #6b7280;
}
.filters {
  margin-bottom: 10px;
}
.format {
  width: 100px;
  margin-right: 8px;
}
.export-state {
  padding: 12px 16px;
  margin: 12px 0;
  background: #f5f7fa;
  border-radius: 6px;
  color: #303133;
}
.export-state span {
  color: #606266;
  margin-left: 4px;
}
.pager {
  justify-content: flex-end;
  margin-top: 16px;
  color: #606266;
}
@media (max-width: 720px) {
  .page-heading,
  .export-state {
    align-items: flex-start;
    flex-direction: column;
  }
  .filters {
    display: block;
  }
}
</style>
