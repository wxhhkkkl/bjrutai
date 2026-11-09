<template>
  <section class="mall-page">
    <header>
      <h2>商品分类</h2>
      <el-button data-test="reload" @click="load">刷新</el-button>
      <el-button
        v-if="canWrite"
        data-test="new-category"
        type="primary"
        @click="edit()"
      >
        新增分类
      </el-button>
    </header>
    <p>最多两级；停用分类前需先下架关联商品。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="items" empty-text="暂无分类">
      <el-table-column prop="name" label="分类名称" />
      <el-table-column label="父分类">
        <template #default="{ row }">
          {{
            parentName(row.parentId)
          }}
        </template>
      </el-table-column>
      <el-table-column prop="sort" label="排序" />
      <el-table-column label="状态">
        <template #default="{ row }">
          {{
            row.status === 'enabled' ? '启用' : '停用'
          }}
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite" label="操作">
        <template #default="{ row }">
          <el-button link @click="edit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog
      v-model="opened"
      title="分类编辑"
      :before-close="close"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <el-alert
        v-if="command.error.value"
        :title="command.error.value"
        type="error"
        :closable="false"
      />
      <el-form label-position="top" :disabled="command.pending.value">
        <el-form-item label="分类名称（必填）">
          <el-input v-model="form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="父分类">
          <el-select v-model="form.parentId" clearable placeholder="一级分类">
            <el-option
              v-for="item in roots"
              :key="item.id"
              :value="item.id"
              :label="item.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :precision="0" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="enabled">启用</el-radio><el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
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
      </template>
    </el-dialog>
  </section>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { listCategories, saveCategory } from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
const auth = useAuthStore()
const canWrite = computed(() => auth.hasPermission('mall.products.write'))
const items = ref([]),
  loading = ref(false),
  error = ref(''),
  opened = ref(false)
const form = reactive({}),
  command = useMallCommand()
const roots = computed(() =>
  items.value.filter((c) => !c.parentId && c.id !== form.id)
)
const parentName = (id) =>
  items.value.find((c) => c.id === id)?.name || (id ? `分类 ${id}` : '—')
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
      parentId: null,
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
        parentId: form.parentId || null,
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
</style>
