<template>
  <section class="mall-page mall-management-page product-page">
    <header class="page-header">
      <h2 class="page-title">商品分类</h2>
      <div class="product-toolbar">
        <el-button
          v-if="canWrite"
          data-test="new-category"
          type="primary"
          @click="edit()"
        >
          新增分类
        </el-button>
      </div>
    </header>
    <el-table
      v-loading="loading"
      class="product-surface product-table product-list"
      :data="visibleItems"
      empty-text="暂无分类"
    >
      <el-table-column prop="name" label="分类名称" />
      <el-table-column prop="sort" label="排序" />
      <el-table-column label="状态">
        <template #default="{ row }">
          <el-tag
            :type="row.status === 'enabled' ? 'success' : 'info'"
            effect="light"
          >
            {{ row.status === 'enabled' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite" label="操作">
        <template #default="{ row }">
          <el-button link type="primary" @click="edit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
    <MallPagination
      :current-page="currentPage"
      :page-size="pageSize"
      :total="items.length"
      :disabled="loading"
      @change="currentPage = $event"
    />
    <el-dialog
      v-model="opened"
      title="分类编辑"
      class="mall-management-overlay product-overlay"
      :before-close="close"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <div class="product-form-stack">
        <el-form label-position="top" :disabled="command.pending.value">
          <el-form-item label="分类名称" required>
            <el-input v-model="form.name" maxlength="64" />
          </el-form-item>
          <el-form-item label="排序">
            <div class="product-sort-field">
              <el-input-number v-model="form.sort" :precision="0" />
              <span class="product-hint">数值越小越靠前</span>
            </div>
          </el-form-item>
          <el-form-item label="状态">
            <el-radio-group v-model="form.status">
              <el-radio value="enabled">启用</el-radio>
              <el-radio value="disabled">停用</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <footer class="product-toolbar product-dialog-footer">
          <el-button :disabled="command.pending.value" @click="opened = false">
            取消
          </el-button>
          <el-button
            v-if="command.pending.value"
            :loading="command.busy.value"
            @click="retry"
          >
            重试原操作
          </el-button>
          <el-button v-else type="primary" @click="save">保存</el-button>
        </footer>
      </template>
    </el-dialog>
  </section>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { listCategories, saveCategory } from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import MallPagination from '@/components/mall/MallPagination.vue'
import '../product-management.css'
const auth = useAuthStore()
const canWrite = computed(() => auth.hasPermission('mall.products.write'))
const items = ref([]),
  loading = ref(false),
  error = ref(''),
  opened = ref(false)
useMallToast(error)
const pageSize = MALL_PAGE_SIZE
const currentPage = ref(1)
const visibleItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return items.value.slice(start, start + pageSize)
})
const form = reactive({}),
  command = useMallCommand()
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const rows = []
    let cursor
    do {
      const data = await listCategories({
        pageSize: 100,
        ...(cursor ? { cursor } : {}),
      })
      rows.push(...data.items)
      cursor = data.nextCursor
    } while (cursor)
    items.value = rows
    currentPage.value = 1
  } catch (e) {
    error.value = e.userMessage || e.message
  } finally {
    loading.value = false
  }
}
function edit(row) {
  if (!canWrite.value || command.pending.value) return
  Object.assign(
    form,
    {
      id: null,
      version: null,
      name: '',
      sort: 0,
      status: 'enabled',
    },
    row || {}
  )
  command.error.value = ''
  opened.value = true
}
function close(done) {
  if (!command.pending.value) done()
}
async function finish(result) {
  if (result) {
    opened.value = false
    await load()
  }
}
async function save() {
  if (!canWrite.value) return
  if (!form.name.trim()) {
    command.error.value = '请填写分类名称'
    return
  }
  await finish(
    await command.run(saveCategory, {
      id: form.id,
      expectedVersion: form.version,
      category: {
        name: form.name.trim(),
        parentId: null,
        sort: form.sort,
        status: form.status,
      },
    })
  )
}
async function retry() {
  await finish(await command.retry())
}
onMounted(load)
</script>
