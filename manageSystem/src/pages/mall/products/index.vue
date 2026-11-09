<template>
  <section class="mall-page">
    <header>
      <h2>商品管理</h2>
      <el-button data-test="reload" :disabled="loading" @click="refresh">
        刷新
      </el-button>
      <el-button
        v-if="canWrite"
        :disabled="command.pending.value"
        @click="editor.open()"
      >
        新增商品
      </el-button>
    </header>
    <el-form inline @submit.prevent="load()">
      <el-form-item label="商品名称">
        <el-input v-model="q" clearable maxlength="128" />
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="categoryId" clearable style="width: 200px">
          <el-option
            v-for="c in categories"
            :key="c.id"
            :label="c.label"
            :value="c.id"
          />
        </el-select>
      </el-form-item>
      <el-button native-type="submit" :disabled="loading">查询</el-button>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="command.error.value"
      :title="command.error.value"
      type="error"
      :closable="false"
    />
    <el-button
      v-if="command.pending.value"
      :loading="command.busy.value"
      @click="retry"
    >
      重试原操作
    </el-button>
    <el-table
      v-loading="loading"
      :data="items"
      empty-text="暂无商品，请新增草稿"
    >
      <el-table-column prop="name" label="商品名称" min-width="140" />
      <el-table-column label="状态">
        <template #default="{ row }">
          {{
            labels[row.status]
          }}
        </template>
      </el-table-column>
      <el-table-column label="规格 / 售价 / 库存" min-width="260">
        <template #default="{ row }">
          <div v-for="s in row.skus" :key="s.id">
            {{ s.skuCode }} / ¥{{ money(s.priceCent) }} / 可售
            {{ s.availableQuantity }}
            <el-button
              v-if="canStock"
              link
              :disabled="command.pending.value"
              @click="stock.open(row, s)"
            >
              库存
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite" label="操作" min-width="260">
        <template #default="{ row }">
          <template v-if="row.status !== 'archived'">
            <el-button link :disabled="command.pending.value" @click="edit(row)">
              编辑
            </el-button>
            <el-button
              link
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
            link
            :disabled="command.pending.value"
            @click="action(row, 'copy')"
          >
            复制
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button v-if="cursor" :disabled="loading" @click="load(true)">
      加载更多商品
    </el-button>
    <ProductEditor ref="editor" :categories="categories" @saved="load()" />
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
  getProduct,
  setProductStatus,
  copyProduct,
} from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { money } from '../product-form'
import ProductEditor from './ProductEditor.vue'
import StockPanel from './StockPanel.vue'
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
  categories = ref([]),
  editing = ref(false)
const q = ref(''),
  categoryId = ref(null),
  cursor = ref(null),
  loading = ref(false),
  error = ref('')
const labels = {
  draft: '草稿',
  on_sale: '在售',
  off_sale: '已下架',
  archived: '已归档',
  copy: '复制',
}
let applied = {}
async function load(more = false) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  if (!more)
    applied = {
      q: q.value || undefined,
      categoryId: categoryId.value || undefined,
    }
  try {
    const data = await listProducts({
      ...applied,
      pageSize: 20,
      ...(more ? { cursor: cursor.value } : {}),
    })
    items.value = more ? [...items.value, ...data.items] : data.items
    cursor.value = data.nextCursor
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
      label: c.parentId
        ? `${rows.find((p) => p.id === c.parentId)?.name || '父分类'} / ${c.name}`
        : c.name,
    }))
  } catch (e) {
    error.value = `分类加载失败：${e.userMessage || e.message}`
  }
}
async function edit(row) {
  if (!canWrite.value || command.pending.value || editing.value) return
  editing.value = true
  try {
    editor.value.open(await getProduct(row.id))
  } catch (e) {
    error.value = e.userMessage || e.message
  } finally {
    editing.value = false
  }
}
async function action(row, target) {
  if (!canWrite.value || command.pending.value) return
  try {
    await ElMessageBox.confirm(
      target === 'archived'
        ? '归档后保留历史订单与库存记录，确认归档？'
        : `确认${labels[target]}“${row.name}”？`,
      '确认操作',
      { type: 'warning' }
    )
  } catch {
    return
  }
  const result = await command.run(
    target === 'copy' ? copyProduct : setProductStatus,
    {
      id: row.id,
      expectedVersion: row.version,
      ...(target === 'copy' ? {} : { targetStatus: target }),
    }
  )
  if (result) await load()
}
async function retry() {
  if (await command.retry()) await load()
}
async function refresh() {
  await load()
  await loadCategories()
}
onMounted(refresh)
</script>
<style scoped>
.mall-page {
  padding: 24px;
}
header {
  display: flex;
  gap: 12px;
  align-items: center;
}
h2 {
  margin-right: auto;
}
.el-alert {
  margin: 12px 0;
}
</style>
