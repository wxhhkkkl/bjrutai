<template>
  <section class="invoice-page mall-management-page">
    <header class="page-heading page-header">
      <div>
        <h2 class="page-title">发票与红冲</h2>
        <p>按实际票据事实办理。买家税号仅显示掩码，原文交付目前关闭。</p>
      </div>
    </header>

    <div class="filters mall-management-filters">
      <el-select v-model="statusFilter" clearable placeholder="全部申请状态">
        <el-option
          v-for="(label, status) in requestStates"
          :key="status"
          :label="label"
          :value="status"
        />
      </el-select>
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索申请单号或订单号"
        @keyup.enter="searchLocal"
      />
      <el-button data-test="search" type="primary" @click="searchLocal">
        查询本页
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="visibleItems"
      empty-text="暂无开票申请"
    >
      <el-table-column prop="requestNo" label="申请单号" min-width="190" />
      <el-table-column prop="orderId" label="订单号" min-width="100" />
      <el-table-column label="商品名称" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.productName || '—' }}</template>
      </el-table-column>
      <el-table-column label="抬头类型" width="110">
        <template #default="{ row }">
          {{ row.buyerType === 'company' ? '企业' : '个人' }}
        </template>
      </el-table-column>
      <el-table-column prop="title" label="发票抬头" min-width="190" />
      <el-table-column label="纳税人识别号" min-width="170">
        <template #default="{ row }">{{ row.taxNoMasked || '—' }}</template>
      </el-table-column>
      <el-table-column label="申请金额" width="130">
        <template #default="{ row }">
          ¥{{ money(row.requestedGoodsCent + row.requestedFreightCent) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-tag :type="stateType(row.status)">
            {{ requestStates[row.status] || '待核实' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="票据数" width="90">
        <template #default="{ row }">{{ row.invoices?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/mall/invoices/${row.id}`)">
            查看办理
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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listAdminMallInvoiceRequests } from '@/api/mall-invoices'
import MallPagination from '@/components/mall/MallPagination.vue'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import { useMallCursorPagination } from '@/composables/useMallCursorPagination'
import { useMallToast } from '@/composables/useMallToast'

const requestStates = {
  submitted: '待处理',
  needs_info: '待买家补充',
  issuing: '财务办理中',
  unknown: '结果待核实',
  delivered: '已完成（发票已上传）',
  withdrawn: '已撤回',
  closed: '已关闭',
}
const router = useRouter()
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
useMallToast(error)
const statusFilter = ref('')
const keyword = ref('')
const appliedStatus = ref('')
const appliedKeyword = ref('')
const {
  currentPage,
  cursorForPage,
  loadPage: loadCursorPage,
  recordPage,
  resetPages,
} = useMallCursorPagination()

const visibleItems = computed(() =>
  items.value.filter((item) => {
    const value = appliedKeyword.value.toLowerCase()
    return (
      !value ||
      item.requestNo.toLowerCase().includes(value) ||
      item.orderId.includes(value)
    )
  })
)

function money(cent) {
  return (Number(cent || 0) / 100).toFixed(2)
}

function stateType(status) {
  if (status === 'delivered') return 'success'
  if (status === 'unknown' || status === 'needs_info') return 'warning'
  if (status === 'closed' || status === 'withdrawn') return 'info'
  return 'primary'
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listAdminMallInvoiceRequests({
      pageSize: MALL_PAGE_SIZE,
      ...(appliedStatus.value ? { status: appliedStatus.value } : {}),
      ...(cursorForPage(currentPage.value)
        ? { cursor: cursorForPage(currentPage.value) }
        : {}),
    })
    items.value = result.items || []
    total.value = result.total || 0
    recordPage(currentPage.value, result)
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '发票申请读取失败'
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function searchLocal() {
  appliedStatus.value = statusFilter.value
  appliedKeyword.value = keyword.value.trim()
  resetPages()
  await load()
}

async function changePage(page) {
  if (loading.value || page === currentPage.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await loadCursorPage(page, (cursor) =>
      listAdminMallInvoiceRequests({
        pageSize: MALL_PAGE_SIZE,
        ...(appliedStatus.value ? { status: appliedStatus.value } : {}),
        ...(cursor ? { cursor } : {}),
      })
    )
    if (!result) {
      error.value = '发票申请数据已变化，请刷新后重试'
      return
    }
    items.value = result.items || []
    total.value = result.total || 0
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '发票申请读取失败'
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

function reload() {
  resetPages()
  return load()
}

onMounted(load)
defineExpose({ load, reload, searchLocal, next, previous, items, visibleItems })
</script>
