<template>
  <el-form label-position="top" class="address-form">
    <div class="address-grid">
      <el-form-item label="联系人">
        <el-input
          :model-value="modelValue.contactName"
          :maxlength="50"
          :disabled="disabled"
          :data-test="`${prefix}-name`"
          @update:model-value="update('contactName', $event)"
        />
      </el-form-item>
      <el-form-item label="联系电话">
        <el-input
          :model-value="modelValue.phone"
          :maxlength="20"
          :disabled="disabled"
          :data-test="`${prefix}-phone`"
          @update:model-value="update('phone', $event)"
        />
      </el-form-item>
    </div>
    <div class="address-grid address-grid--regions">
      <el-form-item v-for="(label, index) in regionLabels" :key="label" :label="label">
        <el-input
          :model-value="modelValue.regionCodes[index]"
          :maxlength="6"
          inputmode="numeric"
          :placeholder="regionPlaceholders[index]"
          :disabled="disabled"
          :data-test="`${prefix}-region-${index}`"
          @update:model-value="updateRegion(index, $event)"
        />
      </el-form-item>
    </div>
    <el-form-item label="详细地址">
      <el-input
        :model-value="modelValue.addressLine"
        :maxlength="200"
        :disabled="disabled"
        :data-test="`${prefix}-address-line`"
        @update:model-value="update('addressLine', $event)"
      />
    </el-form-item>
    <p class="address-help">按省、市、区县顺序填写6位行政区划代码。已存地址不会自动填入。</p>
  </el-form>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Object, required: true },
  prefix: { type: String, required: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
const regionLabels = ['省级代码', '市级代码', '区县代码']
const regionPlaceholders = ['110000', '110100', '110101']

function update(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function updateRegion(index, value) {
  const regionCodes = [...(props.modelValue.regionCodes || ['', '', ''])]
  regionCodes[index] = value
  update('regionCodes', regionCodes)
}
</script>

<style scoped>
.address-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.address-grid--regions { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.address-help { margin: 2px 0 0; color: #87928b; font-size: 12px; }
@media (max-width: 680px) { .address-grid, .address-grid--regions { grid-template-columns: 1fr; gap: 0; } }
</style>
