<template>
  <section class="invoice-page">
    <header class="page-heading">
      <div>
        <h2>发票与红冲</h2>
        <p>按实际票据事实办理。买家税号仅显示掩码，原文交付目前关闭。</p>
      </div>
      <el-button data-test="reload" :loading="loading" @click="load">
        刷新
      </el-button>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="filters">
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
          <el-button link @click="router.push(`/mall/invoices/${row.id}`)">
            查看办理
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
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listAdminMallInvoiceRequests } from '@/api/mall-invoices'

const requestStates = {
  submitted: '待领取',
  needs_info: '待买家补充',
  issuing: '财务办理中',
  unknown: '结果待核实',
  delivered: '已回传票据',
  withdrawn: '已撤回',
  closed: '已关闭',
}
const router = useRouter()
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const statusFilter = ref('')
const keyword = ref('')
const appliedStatus = ref('')
const appliedKeyword = ref('')
const cursor = ref(null)
const nextCursor = ref(null)
const history = ref([])

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
      pageSize: 20,
      ...(appliedStatus.value ? { status: appliedStatus.value } : {}),
      ...(cursor.value ? { cursor: cursor.value } : {}),
    })
    items.value = result.items || []
    total.value = result.total || 0
    nextCursor.value = result.nextCursor || null
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '发票申请读取失败'
    total.value = 0
    nextCursor.value = null
  } finally {
    loading.value = false
  }
}

async function searchLocal() {
  appliedStatus.value = statusFilter.value
  appliedKeyword.value = keyword.value.trim()
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

function reload() {
  cursor.value = null
  history.value = []
  return load()
}

onMounted(load)
defineExpose({ load, reload, searchLocal, next, previous, items, visibleItems })
</script>

<style scoped>
.invoice-page {
  padding: 20px;
}
.page-heading,
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 12px 0 20px;
}
.page-heading h2 {
  margin: 0 0 6px;
}
.page-heading p {
  margin: 0;
  color: #6b7280;
}
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  max-width: 760px;
}
.filters .el-input {
  max-width: 320px;
}
.pager {
  justify-content: flex-end;
  color: #606266;
}
</style>
