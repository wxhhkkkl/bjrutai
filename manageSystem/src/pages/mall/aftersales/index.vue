<template>
  <section class="mall-page mall-management-page">
    <header class="page-header">
      <h2 class="page-title">售后处理</h2>
    </header>
    <el-form inline class="mall-management-filters" @submit.prevent="search">
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
    <el-table
      v-loading="loading"
      :data="items"
      empty-text="暂无符合条件的售后申请"
    >
      <el-table-column prop="aftersaleNo" label="售后单号" min-width="250" />
      <el-table-column label="商品名称" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ productNames(row) }}</template>
      </el-table-column>
      <el-table-column prop="orderNo" label="订单号" min-width="220" show-overflow-tooltip />
      <el-table-column prop="orderId" label="订单ID" min-width="100" />
      <el-table-column label="申请时间" min-width="170">
        <template #default="{ row }">{{ time(row.createdAt) }}</template>
      </el-table-column>
      <el-table-column label="类型" min-width="110">
        <template #default="{ row }">
          {{
            aftersaleMethods[row.method] || '待核实'
          }}
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="120">
        <template #default="{ row }">
          <el-tag :type="aftersaleStateType(row.status)">
            {{
              aftersaleStates[row.status] || '待核实'
            }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="退款申请金额" min-width="135">
        <template #default="{ row }">
          ¥{{ money(row.goodsRefundCent + row.freightRefundCent) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/mall/aftersales/${row.id}`)">
            查看处理
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
import { listAdminAftersales } from '@/api/mall-aftersales'
import MallPagination from '@/components/mall/MallPagination.vue'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import { useMallCursorPagination } from '@/composables/useMallCursorPagination'
import { useMallToast } from '@/composables/useMallToast'
import {
  aftersaleMethods,
  aftersaleStateType,
  aftersaleStates,
  money,
  time,
} from './aftersale-view'

const router = useRouter()
const filters = reactive({ status: '' })
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
let applied = {}

function productNames(row) {
  const names = [
    ...new Set(
      (row.items || [])
        .map((item) => item.productName)
        .filter((name) => typeof name === 'string' && name.trim())
    ),
  ]
  if (names.length) return names.join('、')
  return Number(row.goodsRefundCent || 0) === 0
    ? '运费退款'
    : '商品信息缺失'
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  items.value = []
  try {
    const result = await listAdminAftersales({
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
    error.value = failure.userMessage || failure.message || '售后列表读取失败'
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function search() {
  if (loading.value) return
  applied = filters.status ? { status: filters.status } : {}
  resetPages()
  await load()
}

async function changePage(page) {
  if (loading.value || page === currentPage.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await loadCursorPage(page, (cursor) =>
      listAdminAftersales({
        ...applied,
        pageSize: MALL_PAGE_SIZE,
        ...(cursor ? { cursor } : {}),
      })
    )
    if (!result) {
      error.value = '售后数据已变化，请刷新后重试'
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '售后列表读取失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
