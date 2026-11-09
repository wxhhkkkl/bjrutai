<template>
  <section>
    <h3>商品规格与价格</h3>
    <p>
      最多 20 个 SKU、每个最多两项规格。新增 SKU
      可填初始库存；已有库存请在库存管理中调整。
    </p>
    <el-button
      :disabled="disabled || skus.length >= 20"
      @click="$emit('update:skus', [...skus, blankSku()])"
    >
      新增 SKU
    </el-button>
    <el-card
      v-for="(sku, index) in skus"
      :key="sku.id || `new-${index}`"
      class="sku"
    >
      <el-form-item label="SKU 编码（必填）">
        <el-input v-model="sku.skuCode" maxlength="64" :disabled="disabled" />
      </el-form-item>
      <el-form-item label="售价（元，必填）">
        <el-input v-model="sku.price" inputmode="decimal" :disabled="disabled" />
      </el-form-item>
      <el-form-item v-if="!sku.id" label="初始库存">
        <el-input-number
          v-model="sku.initialStock"
          :min="0"
          :max="2147483647"
          :precision="0"
          :disabled="disabled"
        />
      </el-form-item>
      <p v-else>
        可售 {{ sku.availableQuantity }} / 待付占用 {{ sku.reservedQuantity }}
      </p>
      <el-form-item label="预警数量">
        <el-input-number
          v-model="sku.warningQuantity"
          :min="0"
          :max="2147483647"
          :precision="0"
          :disabled="disabled"
        />
      </el-form-item>
      <div v-for="(option, oi) in sku.options" :key="oi" class="option">
        <el-input
          v-model="option.name"
          placeholder="规格名，如容量"
          maxlength="32"
          :disabled="disabled"
          aria-label="规格名"
        />
        <el-input
          v-model="option.value"
          placeholder="规格值，如 500ml"
          maxlength="64"
          :disabled="disabled"
          aria-label="规格值"
        />
        <el-button :disabled="disabled" @click="sku.options.splice(oi, 1)">
          移除规格项
        </el-button>
      </div>
      <el-button
        :disabled="disabled || sku.options.length >= 2"
        @click="sku.options.push({ name: '', value: '' })"
      >
        添加规格项
      </el-button>
      <el-button
        v-if="!sku.id"
        :disabled="disabled"
        type="danger"
        @click="
          $emit(
            'update:skus',
            skus.filter((_, i) => i !== index)
          )
        "
      >
        移除新 SKU
      </el-button>
    </el-card>
  </section>
</template>
<script setup>
import { blankSku } from '../product-form'
defineProps({ skus: { type: Array, required: true }, disabled: Boolean })
defineEmits(['update:skus'])
</script>
<style scoped>
.sku {
  margin: 12px 0;
}
.option {
  display: flex;
  gap: 8px;
  margin: 12px 0;
}
p {
  color: #606266;
  font-size: 13px;
}
</style>
