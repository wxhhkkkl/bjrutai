<template>
  <section class="mall-page">
    <header>
      <h2>售后处理</h2>
      <el-button data-test="reload" :loading="loading" @click="load">
        刷新
      </el-button>
    </header>
    <el-form inline @submit.prevent="search">
      <el-form-item label="售后状态">
        <el-select v-model="filters.status" clearable placeholder="全部状态">
          <el-option
            v-for="(label, value) in aftersaleStates"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button
          data-test="search"
          type="primary"
          :disabled="loading"
          @click="search"
        >
          查询
        </el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table
      v-loading="loading"
      :data="items"
      empty-text="暂无符合条件的售后申请"
    >
      <el-table-column prop="aftersaleNo" label="售后单号" min-width="250" />
      <el-table-column prop="orderId" label="订单ID" min-width="100" />
      <el-table-column label="类型" min-width="110">
        <template #default="{ row }">
          {{
            aftersaleMethods[row.method] || '待核实'
          }}
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="120">
        <template #default="{ row }">
          {{
            aftersaleStates[row.status] || '待核实'
          }}
        </template>
      </el-table-column>
      <el-table-column label="退款申请金额" min-width="135">
        <template #default="{ row }">
          ¥{{ money(row.goodsRefundCent + row.freightRefundCent) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link @click="router.push(`/mall/aftersales/${row.id}`)">
            查看处理
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <footer>
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
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listAdminAftersales } from '@/api/mall-aftersales'
import { aftersaleMethods, aftersaleStates, money } from './aftersale-view'

const router = useRouter()
const filters = reactive({ status: '' })
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const cursor = ref(null)
const nextCursor = ref(null)
const history = ref([])
let applied = {}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listAdminAftersales({
      ...applied,
      pageSize: 20,
      ...(cursor.value ? { cursor: cursor.value } : {}),
    })
    items.value = result.items
    total.value = result.total
    nextCursor.value = result.nextCursor
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '售后列表读取失败'
    total.value = 0
    nextCursor.value = null
  } finally {
    loading.value = false
  }
}

async function search() {
  if (loading.value) return
  applied = filters.status ? { status: filters.status } : {}
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
