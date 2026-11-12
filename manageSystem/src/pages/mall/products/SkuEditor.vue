<template>
  <section>
    <div class="product-section-heading">
      <h3 class="product-section-title">商品规格</h3>
      <el-button type="primary" plain :disabled="disabled || skus.length >= 20" @click="addSpec">
        添加规格
      </el-button>
    </div>
    <div class="product-surface product-table spec-scroll">
      <table class="spec-table">
        <thead>
          <tr>
            <th scope="col">商品条形码</th>
            <th scope="col">规格</th>
            <th scope="col">市场价（元）</th>
            <th scope="col">销售价（元）</th>
            <th scope="col">成本价（元）</th>
            <th scope="col">库存</th>
            <th scope="col">预警数量</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(sku, index) in skus" :key="sku.id || `new-${index}`">
            <td>
              <el-input
                v-model="sku.barcode"
                maxlength="64"
                placeholder="选填"
                aria-label="商品条形码"
                :disabled="disabled"
              />
            </td>
            <td>
              <el-input
                v-for="option in sku.options.length ? sku.options : [{ name: '规格', value: '' }]"
                :key="option.name"
                :model-value="option.value"
                :placeholder="sku.options.length ? option.name : '默认规格'"
                :aria-label="option.name"
                maxlength="64"
                :disabled="disabled"
                @update:model-value="updateOption(sku, option, $event)"
              />
            </td>
            <td>
              <el-input
                v-model="sku.marketPrice"
                inputmode="decimal"
                placeholder="选填"
                aria-label="市场价（元）"
                :disabled="disabled"
              />
            </td>
            <td>
              <el-input
                v-model="sku.price"
                inputmode="decimal"
                placeholder="必填"
                aria-label="销售价（元），必填"
                :disabled="disabled"
              />
            </td>
            <td>
              <el-input
                v-model="sku.costPrice"
                inputmode="decimal"
                placeholder="选填"
                aria-label="成本价（元）"
                :disabled="disabled"
              />
            </td>
            <td>
              <el-input-number
                v-if="!sku.id"
                v-model="sku.initialStock"
                aria-label="初始库存"
                :min="0"
                :max="2147483647"
                :precision="0"
                :disabled="disabled"
              />
              <span v-else>可售 {{ sku.availableQuantity }} / 待付占用 {{ sku.reservedQuantity }}</span>
            </td>
            <td>
              <el-input-number
                v-model="sku.warningQuantity"
                aria-label="预警数量"
                :min="0"
                :max="2147483647"
                :precision="0"
                :disabled="disabled"
              />
            </td>
            <td>
              <el-button
                v-if="!sku.id"
                link
                type="danger"
                :disabled="disabled || skus.length <= 1"
                @click="removeSpec(index)"
              >
                移除
              </el-button>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="product-hint spec-hint">至少保留 1 条，最多添加 20 条规格。已有规格的库存请在库存管理中调整。</p>
  </section>
</template>
<script setup>
import { blankSku } from '../product-form'
const props = defineProps({ skus: { type: Array, required: true }, disabled: Boolean })
const emit = defineEmits(['update:skus'])

function updateOption(sku, option, value) {
  if (sku.options.length) option.value = value
  else sku.options.push({ name: option.name, value })
}

function addSpec() {
  const spec = blankSku()
  const dimensions = props.skus.find((row) => row.options.length)?.options
  spec.options = (dimensions || [{ name: '规格' }]).map(({ name }) => ({ name, value: '' }))
  emit('update:skus', [...props.skus, spec])
}

function removeSpec(index) {
  if (props.disabled || props.skus.length <= 1) return
  emit('update:skus', props.skus.filter((_, i) => i !== index))
}
</script>
<style scoped>
.spec-scroll {
  overflow-x: auto;
}
.spec-table {
  width: 100%;
  min-width: 1000px;
  border-collapse: collapse;
}
.spec-table th,
.spec-table td {
  border-bottom: 1px solid var(--el-table-border-color);
  padding: 8px 12px;
  text-align: left;
}
.spec-table th {
  background: var(--el-table-header-bg-color);
  color: var(--el-table-header-text-color);
  white-space: nowrap;
}
.spec-table tr:last-child td {
  border-bottom: 0;
}
.spec-table td:last-child {
  white-space: nowrap;
}
.spec-table td:nth-child(-n + 2) {
  min-width: 140px;
}
.spec-table td .el-input + .el-input {
  margin-top: 6px;
}
.spec-hint {
  margin: 12px 0 0;
}
</style>
