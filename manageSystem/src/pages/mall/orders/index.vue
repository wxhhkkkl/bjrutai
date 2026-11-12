<template>
  <section class="mall-page mall-management-page">
    <header class="page-header">
      <h2 class="page-title">交易订单</h2>
    </header>
    <el-form inline class="mall-management-filters" @submit.prevent="search">
      <el-form-item label="订单号">
        <el-input
          v-model="filters.orderNo"
          maxlength="32"
          placeholder="完整订单号"
          clearable
        />
      </el-form-item>
      <el-form-item label="订单状态">
        <el-select
          v-model="filters.status"
          clearable
          placeholder="全部状态"
        >
          <el-option
            v-for="(label, value) in orderStates"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="下单时间">
        <el-date-picker
          v-model="filters.range"
          type="datetimerange"
          start-placeholder="开始时间"
          end-placeholder="结束时间（不含）"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :disabled="loading" @click="search">
          查询
        </el-button>
      </el-form-item>
    </el-form>
    <el-table
      v-loading="loading"
      :data="items"
      :row-class-name="tableRowClassName"
      empty-text="暂无符合条件的订单"
    >
      <el-table-column prop="orderNo" label="订单号" min-width="220" />
      <el-table-column label="商户支付单号" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.outTradeNo || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="微信支付订单号"
        min-width="220"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.channelTransactionId || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="状态">
        <template #default="{ row }">
          <el-tag :type="orderStatusType(row.status)" size="small">
            {{ orderStatusLabel(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="付款">
        <template #default="{ row }">
          {{
            paymentStates[row.paymentStatus] || '待核实'
          }}
        </template>
      </el-table-column>
      <el-table-column label="应付">
        <template #default="{ row }">
          ¥{{ money(row.payableAmountCent) }}
        </template>
      </el-table-column>
      <el-table-column label="实收 / 净收">
        <template #default="{ row }">
          ¥{{ money(row.paidAmountCent) }} / ¥{{
            money(row.netReceivedCent)
          }}
        </template>
      </el-table-column>
      <el-table-column label="下单时间" min-width="175">
        <template #default="{ row }">
          {{
            time(row.createdAt)
          }}
        </template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button
            link
            :type="row.status === 'pending_shipment' ? 'danger' : 'primary'"
            @click="router.push(`/mall/orders/${row.id}`)"
          >
            {{ row.status === 'pending_shipment' ? '优先处理' : '查看详情' }}
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
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listOrders } from '@/api/mall-orders'
import MallPagination from '@/components/mall/MallPagination.vue'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import { useMallCursorPagination } from '@/composables/useMallCursorPagination'
import { useMallToast } from '@/composables/useMallToast'
import { money, time, orderStates, paymentStates, orderStatusType, orderStatusLabel } from './order-view'

const router = useRouter()
const filters = reactive({ orderNo: '', status: '', range: [] })
const items = ref([]),
  total = ref(0),
  loading = ref(false),
  error = ref('')
useMallToast(error)
const {
  currentPage,
  cursorForPage,
  loadPage: loadCursorPage,
  recordPage,
  resetPages,
} = useMallCursorPagination()
let applied = {}
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listOrders({
      ...applied,
      pageSize: MALL_PAGE_SIZE,
      ...(cursorForPage(currentPage.value)
        ? { cursor: cursorForPage(currentPage.value) }
        : {}),
    })
    items.value = result.items
    total.value = result.total
    recordPage(currentPage.value, result)
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '订单读取失败'
    total.value = 0
  } finally {
    loading.value = false
  }
}
async function search() {
  if (loading.value) return
  const range = filters.range || []
  if (
    range.length &&
    (!(range[0] instanceof Date) ||
      !(range[1] instanceof Date) ||
      range[0] >= range[1])
  ) {
    error.value = '开始时间必须早于结束时间'
    return
  }
  applied = {
    ...(filters.orderNo.trim() ? { orderNo: filters.orderNo.trim() } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    ...(range.length
      ? { from: range[0].toISOString(), to: range[1].toISOString() }
      : {}),
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
      listOrders({
        ...applied,
        pageSize: MALL_PAGE_SIZE,
        ...(cursor ? { cursor } : {}),
      })
    )
    if (!result) {
      error.value = '订单数据已变化，请刷新后重试'
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '订单读取失败'
  } finally {
    loading.value = false
  }
}
function tableRowClassName({ row }) {
  return row.status === 'pending_shipment' ? 'pending-shipment-row' : ''
}
onMounted(load)
</script>
<style scoped>
:deep(.el-table__body tr.pending-shipment-row > td.el-table__cell) {
  background-color: var(--el-color-danger-light-9);
}

:deep(.el-table__body tr.pending-shipment-row:hover > td.el-table__cell) {
  background-color: var(--el-color-danger-light-8);
}
</style>
