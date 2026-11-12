<template>
  <section class="finance-page mall-management-page">
    <header class="page-heading page-header">
      <div>
        <h2 class="page-title">
          支付订单
        </h2>
        <p>按支付事实查看商品金额、快递金额、成功退款和净收；待核实记录不计为实收。</p>
      </div>
    </header>

    <template v-if="canReadPayments">
      <el-form
        inline
        class="filters mall-management-filters"
        @submit.prevent="search"
      >
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
            <el-button link type="primary" @click="router.push(`/mall/orders/${row.orderId}`)">
              {{ row.orderNo }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="outTradeNo" label="商户支付单号" min-width="180" />
        <el-table-column label="买家" min-width="120">
          <template #default="{ row }">{{ row.buyer?.displayName || '—' }}</template>
        </el-table-column>
        <el-table-column label="商品金额" width="120" align="right">
          <template #default="{ row }">{{ money(row.goodsAmountCent) }}</template>
        </el-table-column>
        <el-table-column label="快递金额" width="120" align="right">
          <template #default="{ row }">{{ money(row.freightAmountCent) }}</template>
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
              type="primary"
              :disabled="queryingId === row.id"
              @click="queryPayment(row)"
            >
              刷新支付状态
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <MallPagination
        :current-page="currentPage"
        :total="total"
        :disabled="loading"
        @change="changePage"
      />
    </template>
    <el-empty
      v-else
      description="当前账号没有支付订单读取权限"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import MallPagination from '@/components/mall/MallPagination.vue'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import {
  exportAdminMallPayments,
  listAdminMallPayments,
  queryAdminMallPayment,
} from '@/api/mall-finance'
import { useMallFinanceExport } from '@/composables/useMallFinanceExport'
import { useMallCursorPagination } from '@/composables/useMallCursorPagination'
import { useMallToast } from '@/composables/useMallToast'

const paymentStates = {
  creating: '创建中',
  pending: '待付款',
  unknown: '结果待核实',
  succeeded: '支付成功',
  closed: '已关闭',
  failed: '支付失败',
}
const router = useRouter()
const auth = useAuthStore()
const canReadPayments = computed(() => auth.hasPermission('mall.payments.read'))
const canQueryPayments = computed(() => auth.hasPermission('mall.payments.query'))
const canExport = computed(() => auth.hasPermission('mall.finance.export'))
const filters = reactive({ status: '', orderNo: '', range: [] })
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
useMallToast(error)
const {
  currentPage,
  cursorForPage,
  loadPage: loadCursorPage,
  recordPage,
  resetPages,
} = useMallCursorPagination()
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
      pageSize: MALL_PAGE_SIZE,
      ...(cursorForPage(currentPage.value)
        ? { cursor: cursorForPage(currentPage.value) }
        : {}),
    })
    items.value = result.items || []
    total.value = result.total || 0
    recordPage(currentPage.value, result)
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '支付记录读取失败'
    total.value = 0
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
  resetPages()
  await load()
}

async function changePage(page) {
  if (loading.value || page === currentPage.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await loadCursorPage(page, (cursor) =>
      listAdminMallPayments({
        ...applied.value,
        pageSize: MALL_PAGE_SIZE,
        ...(cursor ? { cursor } : {}),
      })
    )
    if (!result) {
      error.value = '支付数据已变化，请刷新后重试'
      return
    }
    items.value = result.items || []
    total.value = result.total || 0
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '支付记录读取失败'
  } finally {
    loading.value = false
  }
}
async function next() {
  return changePage(currentPage.value + 1)
}
async function previous() {
  return changePage(currentPage.value - 1)
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

onMounted(async () => {
  if (canReadPayments.value) await load()
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
.format {
  width: 100px;
  margin-right: 8px;
}
</style>
