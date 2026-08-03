<template>
  <el-dialog :model-value="modelValue" title="更改推广员" width="480px" :close-on-click-modal="false" @close="reset" @open="init">
    <el-form :model="form" label-width="90px" size="small" ref="formRef" :rules="rules">
      <el-form-item label="客户">
        <el-input :model-value="customerName || '-'" disabled />
      </el-form-item>
      <el-form-item label="当前推广员">
        <el-input :model-value="currentPromoter || '-'" disabled />
      </el-form-item>
      <el-form-item label="新推广员" prop="newDistributorId">
        <el-select v-model="form.newDistributorId" filterable placeholder="选择新推广员" style="width: 100%" :loading="distLoading">
          <el-option
            v-for="d in availableDistributors"
            :key="d.distributorId"
            :value="d.distributorId"
            :label="`${d.name}（${d.phone}）`"
          />
        </el-select>
        <div v-if="!distLoading && availableDistributors.length === 0" class="hint">该组织下无其他可用推广员</div>
      </el-form-item>
      <el-form-item label="变更原因" prop="reason">
        <el-input v-model="form.reason" type="textarea" :rows="2" maxlength="500" placeholder="变更原因（必填）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="small" @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button size="small" type="primary" :loading="saving" @click="submit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { distributorApi } from '@/api/org'
import { adminCustomerApi } from '@/api/customers'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  customerId: { type: [String, Number], default: null },
  customerName: { type: String, default: '' },
  currentPromoter: { type: String, default: '' },
  currentDistributorId: { type: [String, Number], default: null },
  orgId: { type: [String, Number], default: null },
})
const emit = defineEmits(['update:modelValue', 'success'])

const formRef = ref(null)
const saving = ref(false)
const distLoading = ref(false)
const distributors = ref([])

const form = reactive({ newDistributorId: null, reason: '' })

const availableDistributors = computed(() => {
  const currentId = String(props.currentDistributorId ?? '')
  return distributors.value.filter((d) => String(d.distributorId) !== currentId)
})

const rules = {
  newDistributorId: [{ required: true, message: '请选择新推广员', trigger: 'change' }],
  reason: [{ required: true, message: '请填写变更原因', trigger: 'blur' }],
}

async function init() {
  if (!props.orgId) return
  distLoading.value = true
  try {
    const data = await distributorApi.list(props.orgId, { limit: 100, includeSubtree: true })
    distributors.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载推广员失败')
  } finally {
    distLoading.value = false
  }
}

function reset() {
  form.newDistributorId = null
  form.reason = ''
  distributors.value = []
}

async function submit() {
  await formRef.value.validate().catch(() => { throw new Error('invalid') })
  saving.value = true
  try {
    await adminCustomerApi.transfer(props.customerId, {
      newDistributorId: form.newDistributorId,
      reason: form.reason,
    })
    ElMessage.success('推广员已变更')
    emit('success')
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '变更推广员失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.hint { color: #e6a23c; font-size: 12px; line-height: 1.4; margin-top: 4px; }
</style>
