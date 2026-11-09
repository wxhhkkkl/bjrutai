<template>
  <el-drawer
    v-model="opened"
    title="库存管理"
    size="min(700px, 95vw)"
    :before-close="close"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <template v-if="sku">
      <h3>{{ sku.skuCode }}</h3>
      <p>
        可售 {{ sku.availableQuantity }} / 待付占用 {{ sku.reservedQuantity }}
      </p>
      <p>仅调整可售库存；待付占用不受盘点覆盖。减库存请输入负数。</p>
      <el-alert
        v-if="command.error.value"
        :title="command.error.value"
        type="error"
        :closable="false"
      />
      <el-form
        v-if="canWrite"
        label-position="top"
        :disabled="command.pending.value"
      >
        <el-form-item label="可售库存增减量">
          <el-input-number
            v-model="delta"
            :min="-2147483647"
            :max="2147483647"
            :precision="0"
          />
        </el-form-item>
        <el-form-item label="调整原因（必填）">
          <el-input v-model="reason" maxlength="200" />
        </el-form-item>
      </el-form>
      <el-button
        v-if="command.pending.value"
        :loading="command.busy.value"
        @click="retry"
      >
        重试原操作
      </el-button>
      <el-button v-else-if="canWrite" type="primary" @click="save">
        确认调整
      </el-button>
      <h3>库存记录</h3>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-button
        v-if="canRead || canWrite"
        :disabled="command.pending.value || loading"
        @click="refresh"
      >
        刷新库存与记录
      </el-button>
      <p v-else>无库存记录查看权限</p>
      <el-table
        v-if="canRead"
        v-loading="loading"
        :data="items"
        empty-text="暂无库存记录"
      >
        <el-table-column label="时间（北京时间）" min-width="180">
          <template #default="{ row }">
            {{
              formatTime(row.createdAt)
            }}
          </template>
        </el-table-column>
        <el-table-column prop="availableDelta" label="可售变化" />
        <el-table-column prop="reservedDelta" label="占用变化" />
        <el-table-column prop="reason" label="原因" />
      </el-table>
      <el-button v-if="cursor" :disabled="loading" @click="load(true)">
        加载更多记录
      </el-button>
    </template>
  </el-drawer>
</template>
<script setup>
import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { adjustStock, getProduct, listStockMovements } from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
const auth = useAuthStore(),
  command = useMallCommand(),
  emit = defineEmits(['changed'])
const canWrite = computed(() => auth.hasPermission('mall.stock.write'))
const canRead = computed(() => auth.hasPermission('mall.stock.read'))
const opened = ref(false),
  sku = ref(null),
  items = ref([]),
  cursor = ref(null)
const loading = ref(false),
  error = ref(''),
  delta = ref(0),
  reason = ref('')
const formatTime = (value) =>
  value
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        dateStyle: 'short',
        timeStyle: 'medium',
        hour12: false,
      }).format(new Date(value))
    : '—'
let productId
async function open(product, item) {
  if (command.pending.value) return
  productId = product.id
  sku.value = { ...item }
  delta.value = 0
  reason.value = ''
  command.error.value = ''
  error.value = ''
  items.value = []
  cursor.value = null
  opened.value = true
  await load()
}
function close(done) {
  if (!command.pending.value) done()
}
async function load(more = false) {
  if (!canRead.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await listStockMovements(sku.value.id, {
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
async function refresh() {
  try {
    const product = await getProduct(productId)
    const latest = product.skus.find((item) => item.id === sku.value.id)
    if (!latest) throw new Error('规格已归档，请刷新商品列表')
    sku.value = latest
    await load()
  } catch (e) {
    error.value = e.userMessage || e.message
  }
}
async function finish(result) {
  if (result) {
    delta.value = 0
    reason.value = ''
    emit('changed')
    await refresh()
  }
}
async function save() {
  if (!canWrite.value || command.pending.value) return
  if (
    !Number.isInteger(delta.value) ||
    delta.value === 0 ||
    !reason.value.trim()
  ) {
    command.error.value = '请填写非零整数增减量及原因'
    return
  }
  await finish(
    await command.run(adjustStock, {
      id: sku.value.id,
      expectedVersion: sku.value.version,
      deltaAvailableQuantity: delta.value,
      reason: reason.value.trim(),
    })
  )
}
async function retry() {
  await finish(await command.retry())
}
defineExpose({ open })
</script>
