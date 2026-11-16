<template>
  <el-drawer
    v-model="opened"
    title="库存管理"
    class="mall-management-overlay product-overlay"
    size="min(700px, 95vw)"
    :before-close="close"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <div v-if="sku" class="stock-panel">
      <section class="product-surface stock-section">
        <h3 class="product-section-title">{{ specLabel(sku) }}</h3>
        <dl class="stock-metrics">
          <div>
            <dt>可售库存</dt>
            <dd>{{ sku.availableQuantity }}</dd>
          </div>
          <div>
            <dt>待付占用</dt>
            <dd>{{ sku.reservedQuantity }}</dd>
          </div>
        </dl>
      </section>

      <section v-if="canWrite" class="product-surface stock-section">
        <h3 class="product-section-title">调整库存</h3>
        <p class="product-hint stock-hint">仅调整可售库存。增加填正数，减少填负数。</p>
        <el-form
          class="stock-form"
          label-position="top"
          :disabled="command.pending.value"
          @submit.prevent="save"
        >
          <div class="stock-fields">
            <el-form-item label="增减数量">
              <el-input-number
                v-model="delta"
                :min="-2147483647"
                :max="2147483647"
                :precision="0"
              />
            </el-form-item>
            <el-form-item label="调整原因" required>
              <el-input
                v-model="reason"
                maxlength="200"
                placeholder="例如：到货补充、盘点修正"
              />
            </el-form-item>
          </div>
          <div class="product-toolbar stock-actions">
            <el-button
              v-if="command.pending.value"
              :loading="command.busy.value"
              @click="retry"
            >
              重试原操作
            </el-button>
            <el-button v-else type="primary" native-type="submit">
              确认调整
            </el-button>
          </div>
        </el-form>
      </section>

      <section class="product-surface stock-section">
        <header class="product-section-heading">
          <h3 class="product-section-title">库存记录</h3>
        </header>
        <p v-if="!canRead" class="product-hint stock-hint">无库存记录查看权限</p>
        <el-table
          v-if="canRead"
          class="product-table"
          v-loading="loading"
          :data="items"
          empty-text="暂无库存记录"
        >
          <el-table-column label="时间（北京时间）" min-width="160">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column prop="availableDelta" label="可售变化" width="88" align="right" />
          <el-table-column prop="reservedDelta" label="占用变化" width="88" align="right" />
          <el-table-column prop="reason" label="原因" min-width="120" />
        </el-table>
        <div v-if="cursor" class="product-toolbar stock-actions stock-more">
          <el-button :disabled="loading" @click="load(true)">加载更多记录</el-button>
        </div>
      </section>
    </div>
  </el-drawer>
</template>
<script setup>
import { specLabel } from '../product-form'
import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { MALL_PAGE_SIZE } from '@/components/mall/mall-pagination'
import { adjustStock, getProduct, listStockMovements } from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
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
useMallToast(error)
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
      pageSize: MALL_PAGE_SIZE,
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


<style scoped>
.stock-panel {
  display: grid;
  gap: 16px;
}

.stock-section {
  padding: 16px;
}

.stock-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 12px 0 0;
}

.stock-metrics > div {
  padding: 12px;
  border-radius: var(--app-radius-md);
  background: var(--el-fill-color-light);
}

.stock-metrics dt {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.stock-metrics dd {
  margin: 4px 0 0;
  color: var(--el-text-color-primary);
  font-size: 24px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.stock-hint {
  margin: 6px 0 0;
}

.stock-form,
.stock-section .el-alert {
  margin-top: 12px;
}

.stock-fields {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 12px;
}

.stock-fields .el-input-number {
  width: 100%;
}

.stock-actions {
  justify-content: flex-end;
}

.stock-more {
  margin-top: 12px;
}

@media (max-width: 520px) {
  .stock-fields {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
