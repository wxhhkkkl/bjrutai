<template>
  <section class="mall-page">
    <header>
      <h2>交易订单</h2>
      <el-button data-test="reload" :loading="loading" @click="load">
        刷新
      </el-button>
    </header>
    <el-form inline @submit.prevent="search">
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
          style="width: 150px"
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
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="items" empty-text="暂无符合条件的订单">
      <el-table-column prop="orderNo" label="订单号" min-width="220" />
      <el-table-column label="状态">
        <template #default="{ row }">
          {{
            orderStates[row.status] || '待核实'
          }}
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
          <el-button link @click="router.push(`/mall/orders/${row.id}`)">
            查看详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <footer>
      <span>共 {{ total }} 条</span><el-button :disabled="loading || !history.length" @click="previous">
        上一页
      </el-button><el-button :disabled="loading || !nextCursor" @click="next">
        下一页
      </el-button>
    </footer>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listOrders } from '@/api/mall-orders'
import { money, time, orderStates, paymentStates } from './order-view'

const router = useRouter()
const filters = reactive({ orderNo: '', status: '', range: [] })
const items = ref([]),
  total = ref(0),
  loading = ref(false),
  error = ref('')
const cursor = ref(null),
  nextCursor = ref(null),
  history = ref([])
let applied = {}
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listOrders({
      ...applied,
      pageSize: 20,
      ...(cursor.value ? { cursor: cursor.value } : {}),
    })
    items.value = result.items
    total.value = result.total
    nextCursor.value = result.nextCursor
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '订单读取失败'
    nextCursor.value = null
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
onMounted(load)
</script>
<style scoped>
.mall-page {
  padding: 20px;
}
header,
footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}
header {
  justify-content: space-between;
}
</style>
