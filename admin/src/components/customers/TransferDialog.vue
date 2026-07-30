<template>
  <el-dialog
    v-model="visible"
    title="转移绑定"
    width="520px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-descriptions :column="1" border size="small" style="margin-bottom: 16px">
      <el-descriptions-item label="客户">
        {{ customerName || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="当前推广员">
        {{ currentPromoterName || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="绑定状态">
        <el-tag :type="statusType" size="small">{{ statusLabel }}</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="auto">
      <el-form-item label="新推广员" prop="newPromoterId">
        <el-select
          v-model="form.newPromoterId"
          filterable
          remote
          reserve-keyword
          placeholder="搜索并选择推广员"
          :remote-method="searchPromoters"
          :loading="searching"
          style="width: 100%"
        >
          <el-option
            v-for="item in promoterOptions"
            :key="item.promoterId"
            :label="`${item.displayName} (${item.orgNodeName || '-'})`"
            :value="item.promoterId"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="转移原因" prop="reason">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="选填：转移原因说明"
        />
      </el-form-item>
      <el-form-item>
        <div class="transfer-summary" v-if="form.newPromoterId">
          <p>转移确认：将客户从「{{ currentPromoterName }}」转移到所选推广员</p>
          <p v-if="settlementWarning" class="text-warning">{{ settlementWarning }}</p>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!form.newPromoterId" @click="handleSubmit">
        确认转移
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useBindingStore } from '@/stores/binding'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  requestId: { type: [String, Number], default: '' },
  customerName: { type: String, default: '' },
  currentPromoterName: { type: String, default: '' },
  statusLabel: { type: String, default: '' },
  statusType: { type: String, default: 'info' },
  settlementWarning: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'success'])

const bindingStore = useBindingStore()
const visible = ref(props.modelValue)
const submitting = ref(false)
const searching = ref(false)
const formRef = ref(null)
const promoterOptions = ref([])

const form = reactive({
  newPromoterId: '',
  reason: '',
})

const rules = {
  newPromoterId: [{ required: true, message: '请选择新推广员', trigger: 'change' }],
}

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    form.newPromoterId = ''
    form.reason = ''
    promoterOptions.value = []
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

function handleClose() {
  form.newPromoterId = ''
  form.reason = ''
  promoterOptions.value = []
}

async function searchPromoters(keyword) {
  if (!keyword || keyword.length < 1) {
    promoterOptions.value = []
    return
  }
  searching.value = true
  try {
    const data = await bindingStore.fetchSelectablePromoters({ keyword, limit: 20 })
    promoterOptions.value = data.items || []
  } catch {
    promoterOptions.value = []
  } finally {
    searching.value = false
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    emit('success', {
      newPromoterId: form.newPromoterId,
      reason: form.reason || undefined,
    })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.transfer-summary {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.text-warning {
  color: #e6a23c;
}
</style>
