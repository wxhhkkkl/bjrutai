<template>
  <div class="permission-tree">
    <el-tree
      ref="treeRef"
      :data="treeData"
      :props="treeProps"
      show-checkbox
      node-key="key"
      default-expand-all
      :default-checked-keys="modelValue"
      :check-strictly="false"
      @check="onCheck"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { PERMISSION_MODULES } from '@/constants/permissions'

const props = defineProps({
  /** Array of permission key strings currently selected (v-model) */
  modelValue: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:modelValue'])

const treeRef = ref(null)

// Build tree data from PERMISSION_MODULES
const treeData = computed(() =>
  PERMISSION_MODULES.map((mod) => ({
    key: `__module__${mod.module}`,
    label: mod.label,
    children: mod.permissions.map((p) => ({
      key: p.key,
      label: p.label,
    })),
  }))
)

const treeProps = {
  children: 'children',
  label: 'label',
}

function onCheck() {
  if (!treeRef.value) return
  // getCheckedKeys(false) returns only leaf-node keys.
  // We also filter out any __module__ parent keys as a safety net.
  const checked = treeRef.value
    .getCheckedKeys(false)
    .filter((key) => !key.startsWith('__module__'))
  emit('update:modelValue', checked)
}

/** Programmatically set checked keys (useful for reset) */
function setCheckedKeys(keys) {
  treeRef.value?.setCheckedKeys(keys)
}

defineExpose({ setCheckedKeys })
</script>

<style scoped>
.permission-tree {
  max-height: 420px;
  overflow-y: auto;
  padding: 4px 0;
}
</style>
