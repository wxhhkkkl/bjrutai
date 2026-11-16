<template>
  <section class="mall-page mall-management-page product-page">
    <header class="page-header">
      <h2 class="page-title">商品管理</h2>
      <div class="product-toolbar">
        <el-button
          v-if="canWrite"
          type="primary"
          :disabled="command.pending.value"
          @click="editor.open()"
        >
          新增商品
        </el-button>
      </div>
    </header>
    <el-form
      inline
      class="product-surface product-filters mall-management-filters"
      @submit.prevent="load()"
    >
      <el-form-item label="商品名称">
        <el-input v-model="q" clearable maxlength="128" placeholder="请输入商品名称" />
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="categoryId" clearable placeholder="全部分类">
          <el-option
            v-for="c in categories"
            :key="c.id"
            :label="c.label"
            :value="c.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" native-type="submit" :disabled="loading">
          查询
        </el-button>
      </el-form-item>
    </el-form>
    <div v-if="command.pending.value" class="product-toolbar product-pending-actions">
      <el-button :loading="command.busy.value" @click="retry">
        重试原操作
      </el-button>
    </div>
    <el-table
      class="product-surface product-table product-list"
      v-loading="loading"
      :data="items"
      empty-text="暂无商品，请新增草稿"
    >
      <el-table-column prop="name" label="商品名称" min-width="140" />
      <el-table-column label="规格" min-width="160">
        <template #default="{ row }">
          <div v-if="row.skus.length" class="sku-lines">
            <div v-for="s in row.skus" :key="s.id" class="sku-line" :title="specLabel(s)">
              {{ specLabel(s) }}
            </div>
          </div>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="售价" min-width="120" align="right">
        <template #default="{ row }">
          <div v-if="row.skus.length" class="sku-lines">
            <div v-for="s in row.skus" :key="s.id" class="sku-line">
              ¥{{ money(s.priceCent) }}
            </div>
          </div>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="库存" min-width="130" align="right">
        <template #default="{ row }">
          <div v-if="row.skus.length" class="sku-lines">
            <div v-for="s in row.skus" :key="s.id" class="sku-line">
              {{ s.availableQuantity }}
              <el-tag
                v-if="s.availableQuantity <= s.warningQuantity"
                class="stock-warning"
                type="danger"
                size="small"
                effect="light"
              >
                库存预警
              </el-tag>
            </div>
          </div>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="statusTypes[row.status] || 'info'" effect="light">
            {{ labels[row.status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite || canStock" label="操作" min-width="320">
        <template #default="{ row }">
          <div class="row-actions">
            <template v-if="canWrite && row.status !== 'archived'">
              <el-button
                link
                type="primary"
                :disabled="command.pending.value || row.status === 'on_sale'"
                :title="
                  row.status === 'on_sale' ? '上架中的商品需先下架再编辑' : ''
                "
                @click="edit(row)"
              >
                编辑
              </el-button>
              <el-button
                link
                type="primary"
                :disabled="command.pending.value"
                @click="
                  action(row, row.status === 'on_sale' ? 'off_sale' : 'on_sale')
                "
              >
                {{ row.status === 'on_sale' ? '下架' : '上架' }}
              </el-button>
              <el-button
                link
                type="danger"
                :disabled="command.pending.value"
                @click="action(row, 'archived')"
              >
                归档
              </el-button>
            </template>
            <el-button
              v-for="s in canStock ? row.skus : []"
              :key="s.id"
              link
              type="primary"
              :title="`调整${specLabel(s)}的库存`"
              :aria-label="`调整${specLabel(s)}的库存`"
              :disabled="command.pending.value"
              @click="stock.open(row, s)"
            >
              调整库存
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <MallPagination
      :current-page="currentPage"
      :page-size="pageSize"
      :total="total"
      :disabled="loading"
      @change="changePage"
    />
    <ProductEditor ref="editor" @saved="load()" />
    <StockPanel ref="stock" @changed="load()" />
  </section>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  listCategories,
  listProducts,
  setProductStatus,
} from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
import { money, specLabel } from '../product-form'
import { useMallCursorPagination } from '@/composables/useMallCursorPagination'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import MallPagination from '@/components/mall/MallPagination.vue'
import ProductEditor from './ProductEditor.vue'
import StockPanel from './StockPanel.vue'
import '../product-management.css'
const auth = useAuthStore(),
  command = useMallCommand()
const canWrite = computed(() => auth.hasPermission('mall.products.write'))
const canStock = computed(
  () =>
    auth.hasPermission('mall.stock.read') ||
    auth.hasPermission('mall.stock.write')
)
const editor = ref(null),
  stock = ref(null),
  items = ref([]),
  categories = ref([])
const q = ref(''),
  categoryId = ref(null),
  loading = ref(false),
  error = ref('')
useMallToast(error)
const pageSize = MALL_PAGE_SIZE
const {
  currentPage,
  loadPage: loadCursorPage,
  recordPage,
  resetPages,
} = useMallCursorPagination()
const total = ref(0)
const labels = {
  draft: '下架',
  on_sale: '上架',
  off_sale: '下架',
  archived: '归档',
}
const statusTypes = { on_sale: 'success', archived: 'warning' }
let applied = {}
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  applied = {
    q: q.value || undefined,
    categoryId: categoryId.value || undefined,
  }
  resetPages()
  try {
    const data = await listProducts({ ...applied, pageSize })
    items.value = data.items
    total.value = data.total
    recordPage(1, data)
  } catch (e) {
    error.value = e.userMessage || e.message
  } finally {
    loading.value = false
  }
}
async function changePage(page) {
  if (loading.value || page === currentPage.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await loadCursorPage(page, (cursor) =>
      listProducts({
        ...applied,
        pageSize,
        ...(cursor ? { cursor } : {}),
      })
    )
    if (!data) {
      error.value = '商品数据已变化，请刷新后重试'
      return
    }
    items.value = data.items
    total.value = data.total
  } catch (e) {
    error.value = e.userMessage || e.message
  } finally {
    loading.value = false
  }
}
async function loadCategories() {
  try {
    const rows = []
    let next
    do {
      const data = await listCategories({
        pageSize: 100,
        ...(next ? { cursor: next } : {}),
      })
      rows.push(...data.items)
      next = data.nextCursor
    } while (next)
    categories.value = rows.map((c) => ({
      ...c,
      label: c.name,
    }))
  } catch (e) {
    error.value = `分类加载失败：${e.userMessage || e.message}`
  }
}
function edit(row) {
  editor.value?.open(row.id)
}
async function action(row, target) {
  if (!canWrite.value || command.pending.value) return
  try {
    const actionLabel = labels[target]
    await ElMessageBox.confirm(
      target === 'archived'
        ? '归档后保留历史订单与库存记录，确认归档？'
        : `确定${actionLabel}“${row.name}”吗？`,
      '确认操作',
      { type: 'warning' }
    )
  } catch {
    return
  }
  const result = await command.run(setProductStatus, {
    id: row.id,
    expectedVersion: row.version,
    targetStatus: target,
  })
  if (result) {
    await load()
    return
  }
}
async function retry() {
  const result = await command.retry()
  if (result) {
    await load()
    return
  }
}
async function refresh() {
  await load()
  await loadCategories()
}
onMounted(refresh)
</script>
<style scoped>
.sku-lines {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sku-line {
  overflow: hidden;
  line-height: 24px;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}
.stock-warning {
  margin-left: 4px;
  vertical-align: 1px;
}
.row-actions {
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: thin;
}
.row-actions :deep(.el-button) {
  flex: 0 0 auto;
  margin-left: 0;
}
</style>
