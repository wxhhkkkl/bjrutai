<template>
  <el-dialog
    v-model="visible"
    title="解除绑定"
    width="480px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-alert
      v-if="hasSettlements"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>
        该客户存在未结算的业绩贡献，解绑可能导致业绩数据不完整。
      </template>
    </el-alert>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="auto">
      <el-form-item label="客户信息">
        <span>{{ customerName || '-' }}</span>
      </el-form-item>
      <el-form-item label="当前推广员">
        <span>{{ promoterName || '-' }}</span>
      </el-form-item>
      <el-form-item label="解绑原因" prop="reason">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入解绑原因（必填）"
        />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="form.confirmed">
          我确认要解除此绑定关系，此操作不可撤销
        </el-checkbox>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="danger" :loading="submitting" :disabled="!form.confirmed" @click="handleSubmit">
        确认解绑
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  requestId: { type: [String, Number], default: '' },
  customerName: { type: String, default: '' },
  promoterName: { type: String, default: '' },
  hasSettlements: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = ref(props.modelValue)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  reason: '',
  confirmed: false,
})

const rules = {
  reason: [{ required: true, message: '请输入解绑原因', trigger: 'blur' }],
}

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    form.reason = ''
    form.confirmed = false
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

function handleClose() {
  form.reason = ''
  form.confirmed = false
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  if (!form.confirmed) {
    ElMessage.warning('请确认解绑操作')
    return
  }

  submitting.value = true
  try {
    emit('success', { reason: form.reason })
  } finally {
    submitting.value = false
  }
}
</script>
