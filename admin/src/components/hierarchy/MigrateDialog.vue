<template>
  <el-dialog
    v-model="visible"
    title="迁移分支"
    width="450px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-alert
      title="迁移警告"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #default>
        <p style="margin: 0; line-height: 1.6">
          将节点 <strong>{{ nodeData?.name }}</strong> 及其所有子节点迁移到新的父节点下。
          <br />此操作会创建快照记录，请谨慎操作。
        </p>
      </template>
    </el-alert>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      label-position="right"
    >
      <el-form-item label="目标父节点ID" prop="targetParentId">
        <el-input-number
          v-model="form.targetParentId"
          :min="1"
          placeholder="输入目标父节点ID"
          style="width: 100%"
          controls-position="right"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="warning" :loading="submitting" @click="handleSubmit">
        确认迁移
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useHierarchyStore } from '@/stores/hierarchy'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  nodeData: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'success'])

const store = useHierarchyStore()
const visible = ref(props.modelValue)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  targetParentId: null,
})

const rules = {
  targetParentId: [
    { required: true, message: '请输入目标父节点ID', trigger: 'blur' },
  ],
}

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })

function handleClosed() {
  form.targetParentId = null
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  if (!props.nodeData) return

  submitting.value = true
  try {
    await store.migrateBranch(props.nodeData.nodeId, Number(form.targetParentId))
    visible.value = false
    emit('success')
  } finally {
    submitting.value = false
  }
}
</script>
