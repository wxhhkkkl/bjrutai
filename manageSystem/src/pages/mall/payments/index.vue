<template>
  <section class="finance-page">
    <header class="page-heading">
      <div>
        <h2>{{ activeView === 'reconciliation' ? '日对账' : '支付订单' }}</h2>
        <p v-if="activeView === 'payments'">
          按支付事实查看本次金额、成功退款和净收；待核实记录不计为实收。
        </p>
        <p v-else>以渠道账单和本地成功事实逐日核对，保留差异及处理证据。</p>
      </div>
      <el-button
        v-if="activeView === 'payments' && canReadPayments"
        data-test="reload"
        :loading="loading"
        @click="load"
      >
        刷新
      </el-button>
    </header>

    <nav class="finance-views" aria-label="资金视图">
      <el-button
        v-if="canReadPayments"
        data-test="payments-view"
        :type="activeView === 'payments' ? 'primary' : 'default'"
        @click="setView('payments')"
      >
        支付流水
      </el-button>
      <el-button
        v-if="canReadReconciliations"
        data-test="reconciliation-view"
        :type="activeView === 'reconciliation' ? 'primary' : 'default'"
        @click="setView('reconciliation')"
      >
        日对账
      </el-button>
    </nav>

    <ReconciliationPanel
      v-if="activeView === 'reconciliation' && canReadReconciliations"
    />

    <template v-else-if="activeView === 'payments' && canReadPayments">
      <el-form inline class="filters" @submit.prevent="search">
        <el-form-item label="支付状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态">
            <el-option
              v-for="(label, value) in paymentStates"
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
        <el-form-item label="资金时间">
          <el-date-picker
            v-model="filters.range"
            type="datetimerange"
            start-placeholder="开始时间"
            end-placeholder="结束时间（不含）"
          />
        </el-form-item>
        <el-form-item>
          <el-button data-test="search" type="primary" @click="search">
            查询
          </el-button>
        </el-form-item>
        <el-form-item v-if="canExport">
          <el-select v-model="exportFormat" aria-label="导出格式" class="format">
            <el-option label="Excel" value="xlsx" />
            <el-option label="CSV" value="csv" />
          </el-select>
          <el-button
            data-test="export"
            :disabled="loading || exportBusy || !!applied.orderNo"
            :loading="exportBusy && !exportResult"
            @click="exportVisibleRows"
          >
            导出资金
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
          <span v-if="exportResult?.rowCount != null">
            · {{ exportResult.rowCount }} 条记录
          </span>
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

      <el-table v-loading="loading" :data="items" empty-text="暂无支付记录">
        <el-table-column prop="orderNo" label="订单号" min-width="190">
          <template #default="{ row }">
            <el-button link @click="router.push(`/mall/orders/${row.orderId}`)">
              {{ row.orderNo }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="outTradeNo" label="商户支付单号" min-width="180" />
        <el-table-column label="买家" min-width="120">
          <template #default="{ row }">{{ row.buyer?.displayName || '—' }}</template>
        </el-table-column>
        <el-table-column label="本次金额" width="120" align="right">
          <template #default="{ row }">{{ money(row.amountCent) }}</template>
        </el-table-column>
        <el-table-column label="成功退款" width="120" align="right">
          <template #default="{ row }">{{ money(row.refundSucceededCent) }}</template>
        </el-table-column>
        <el-table-column label="净收" width="120" align="right">
          <template #default="{ row }">{{ maybeMoney(row.netReceivedCent) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="paymentStateType(row.status)">
              {{ paymentStates[row.status] || '待核实' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="支付时间" min-width="170">
          <template #default="{ row }">{{ time(row.confirmedAt || row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="135" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="canQueryPayments && ['creating', 'pending', 'unknown'].includes(row.status)"
              link
              :disabled="queryingId === row.id"
              @click="queryPayment(row)"
            >
              查证原支付
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <footer class="pager">
        <span>共 {{ total }} 条</span>
        <el-button :disabled="loading || !history.length" @click="previous">
          上一页
        </el-button>
        <el-button :disabled="loading || !nextCursor" @click="next">
          下一页
        </el-button>
      </footer>
    </template>
    <el-empty
      v-else-if="!canReadReconciliations"
      description="当前账号没有支付或对账读取权限"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ReconciliationPanel from '@/components/mall/ReconciliationPanel.vue'
import {
  exportAdminMallPayments,
  listAdminMallPayments,
  queryAdminMallPayment,
} from '@/api/mall-finance'
import { useMallFinanceExport } from '@/composables/useMallFinanceExport'

const paymentStates = {
  creating: '创建中',
  pending: '待付款',
  unknown: '结果待核实',
  succeeded: '支付成功',
  closed: '已关闭',
  failed: '支付失败',
}
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canReadPayments = computed(() => auth.hasPermission('mall.payments.read'))
const canQueryPayments = computed(() => auth.hasPermission('mall.payments.query'))
const canExport = computed(() => auth.hasPermission('mall.finance.export'))
const canReadReconciliations = computed(() =>
  auth.hasPermission('mall.reconciliations.read')
)
const activeView = ref(
  route.query.view === 'reconciliation' &&
    auth.hasPermission('mall.reconciliations.read')
    ? 'reconciliation'
    : 'payments'
)
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
const queryingId = ref('')
const exportController = useMallFinanceExport(
  'payments',
  exportAdminMallPayments,
  auth.user?.userId
)
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
} = exportController

function money(cent) {
  return `¥${(Number(cent || 0) / 100).toFixed(2)}`
}
function maybeMoney(cent) {
  return cent == null ? '—' : money(cent)
}
function time(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}
function paymentStateType(status) {
  if (status === 'succeeded') return 'success'
  if (status === 'unknown' || status === 'creating') return 'warning'
  if (status === 'closed' || status === 'failed') return 'info'
  return 'primary'
}
function iso(value) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null
  return value.toISOString()
}
function activeDateRange() {
  if (!Array.isArray(filters.range) || filters.range.length !== 2) return null
  const from = iso(filters.range[0])
  const to = iso(filters.range[1])
  if (!from || !to) return null
  return { from, to }
}

async function load() {
  if (!canReadPayments.value || loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listAdminMallPayments({
      ...applied.value,
      pageSize: 20,
      ...(cursor.value ? { cursor: cursor.value } : {}),
    })
    items.value = result.items || []
    total.value = result.total || 0
    nextCursor.value = result.nextCursor || null
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '支付记录读取失败'
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

async function queryPayment(row) {
  if (!canQueryPayments.value || queryingId.value) return
  queryingId.value = row.id
  error.value = ''
  try {
    await queryAdminMallPayment(
      { id: row.id, expectedVersion: row.version },
      crypto.randomUUID()
    )
    await load()
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '支付查证请求失败'
  } finally {
    queryingId.value = ''
  }
}

function setView(view) {
  activeView.value =
    view === 'reconciliation' && canReadReconciliations.value
      ? 'reconciliation'
      : 'payments'
  router.replace?.({
    path: '/mall/payments',
    query: activeView.value === 'reconciliation' ? { view: activeView.value } : {},
  })
  if (activeView.value === 'payments') void load()
}

watch(
  () => route.query.view,
  (view) => {
    activeView.value =
      view === 'reconciliation' && canReadReconciliations.value
        ? 'reconciliation'
        : 'payments'
    if (activeView.value === 'payments') void load()
  }
)

onMounted(async () => {
  if (activeView.value === 'payments') await load()
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
  exportVisibleRows,
  exportFiltered: exportVisibleRows,
  refreshExport,
  retryExport,
  queryPayment,
})
</script>

<style scoped>
.finance-page {
  padding: 20px;
}
.page-heading,
.pager,
.export-state,
.export-actions,
.finance-views {
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
.finance-views {
  margin: 0 0 18px;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 12px;
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
