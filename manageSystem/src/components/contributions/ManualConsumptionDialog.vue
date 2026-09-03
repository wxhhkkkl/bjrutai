<template>
  <el-dialog
    :model-value="modelValue"
    title="录入消费"
    width="560px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :before-close="handleClose"
    @open="focusCustomer"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <el-form-item label="客户" prop="customerId">
        <el-select
          ref="customerSelectRef"
          v-model="form.customerId"
          filterable
          remote
          clearable
          reserve-keyword
          :remote-method="searchCustomers"
          :loading="customerLoading"
          no-data-text="未匹配到有效人员"
          placeholder="请输入姓名、手机号或身份证号"
          style="width: 100%"
          @change="selectCustomer"
        >
          <el-option
            v-for="item in customerOptions"
            :key="item.customerId"
            :label="`${item.name || '未命名客户'}（${item.phoneMasked || '无手机号'}）`"
            :value="item.customerId"
          >
            <div class="customer-option">
              <div>
                <strong>{{ item.name || '未命名客户' }}</strong>
                <span>{{ item.phoneMasked || '无手机号' }}</span>
              </div>
              <small>{{ item.idCardMasked || '未填写身份证号' }} · {{ item.personName }} / {{ item.orgName }}</small>
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <template v-if="selectedCustomer">
        <el-form-item label="客户信息">
          <div class="customer-summary">
            <span>{{ selectedCustomer.name || '未命名客户' }}</span>
            <span>{{ selectedCustomer.phoneMasked || '无手机号' }}</span>
            <span>{{ selectedCustomer.idCardMasked || '未填写身份证号' }}</span>
          </div>
        </el-form-item>
        <el-form-item label="归属人员">
          <el-input data-testid="person-name" :model-value="selectedCustomer.personName || '-'" disabled />
        </el-form-item>
        <el-form-item label="所属组织">
          <el-input data-testid="org-name" :model-value="selectedCustomer.orgName || '-'" disabled />
        </el-form-item>
      </template>

      <el-form-item label="消费时间" prop="consumedAt">
        <el-date-picker
          v-model="form.consumedAt"
          type="datetime"
          placeholder="请选择消费时间"
          :disabled-date="disableFutureDate"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="实付金额（元）" prop="amountYuan">
        <el-input v-model="form.amountYuan" inputmode="decimal" placeholder="请输入大于 0 的金额">
          <template #prefix>¥</template>
        </el-input>
      </el-form-item>

      <el-form-item label="备注" prop="note">
        <el-input
          v-model="form.note"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="选填，例如线下收款原因"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">确认录入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { contributionDashboardApi } from '@/api/contributions'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'success'])

const formRef = ref(null)
const customerSelectRef = ref(null)
const customerLoading = ref(false)
const submitting = ref(false)
const customerOptions = ref([])
const selectedCustomer = ref(null)
const idempotencyKey = ref('')
const lastAttemptFingerprint = ref('')

const form = reactive({
  customerId: '',
  consumedAt: new Date(),
  amountYuan: '',
  note: '',
})

function makeIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function currentFingerprint() {
  return JSON.stringify({
    customerId: form.customerId,
    consumedAt: form.consumedAt instanceof Date ? form.consumedAt.toISOString() : form.consumedAt,
    amountYuan: String(form.amountYuan).trim(),
    note: form.note.trim(),
  })
}

function resetForm() {
  form.customerId = ''
  form.consumedAt = new Date()
  form.amountYuan = ''
  form.note = ''
  customerOptions.value = []
  selectedCustomer.value = null
  idempotencyKey.value = makeIdempotencyKey()
  lastAttemptFingerprint.value = ''
  nextTick(() => formRef.value?.clearValidate())
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) resetForm()
  },
  { immediate: true },
)

async function focusCustomer() {
  await nextTick()
  customerSelectRef.value?.focus?.()
}

async function searchCustomers(keyword) {
  const value = String(keyword || '').trim()
  if (!value) {
    customerOptions.value = []
    return
  }
  customerLoading.value = true
  try {
    const data = await contributionDashboardApi.searchCustomers({ keyword: value, pageSize: 20 })
    customerOptions.value = data.items || []
  } catch (error) {
    customerOptions.value = []
    ElMessage.error(error.userMessage || error.response?.data?.message || '搜索客户失败')
  } finally {
    customerLoading.value = false
  }
}

async function selectCustomer(customerId) {
  selectedCustomer.value = customerOptions.value.find((item) => item.customerId === customerId) || null
  await nextTick()
}

function amountInCents() {
  const text = String(form.amountYuan || '').trim()
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null
  const [yuan, fraction = ''] = text.split('.')
  const cents = Number(yuan) * 100 + Number(fraction.padEnd(2, '0'))
  return Number.isSafeInteger(cents) && cents > 0 ? cents : null
}

function validateAmount(_rule, _value, callback) {
  if (amountInCents() === null) callback(new Error('请输入大于 0 且最多两位小数的金额'))
  else callback()
}

function validateTime(_rule, value, callback) {
  const date = value instanceof Date ? value : new Date(value)
  if (!value || Number.isNaN(date.getTime())) callback(new Error('请选择有效的消费时间'))
  else if (date.getTime() > Date.now()) callback(new Error('消费时间不能晚于当前时间'))
  else callback()
}

const rules = {
  customerId: [{ required: true, message: '请选择客户', trigger: 'change' }],
  consumedAt: [{ validator: validateTime, trigger: 'change' }],
  amountYuan: [{ validator: validateAmount, trigger: 'blur' }],
}

function disableFutureDate(date) {
  return date.getTime() > Date.now()
}

function handleClose(done) {
  if (submitting.value) return
  emit('update:modelValue', false)
  if (typeof done === 'function') done()
}

async function submit() {
  if (submitting.value) return
  submitting.value = true
  try {
    await formRef.value?.validate()
    if (!selectedCustomer.value) throw new Error('请选择客户')

    const amountCent = amountInCents()
    const date = form.consumedAt instanceof Date ? form.consumedAt : new Date(form.consumedAt)
    if (amountCent === null) throw new Error('请输入有效金额')
    if (date.getTime() > Date.now()) throw new Error('消费时间不能晚于当前时间')

    const fingerprint = currentFingerprint()
    if (lastAttemptFingerprint.value && lastAttemptFingerprint.value !== fingerprint) {
      idempotencyKey.value = makeIdempotencyKey()
    }

    await ElMessageBox.confirm(
      `请确认：${selectedCustomer.value.name || '未命名客户'}，${selectedCustomer.value.personName} / ${selectedCustomer.value.orgName}，实付 ¥${form.amountYuan}`,
      '确认录入消费',
      { confirmButtonText: '确认录入', cancelButtonText: '返回修改', type: 'warning' },
    )

    lastAttemptFingerprint.value = fingerprint
    const payload = {
      customerId: selectedCustomer.value.customerId,
      customerVersion: selectedCustomer.value.customerVersion,
      consumedAt: date.toISOString(),
      amountCent,
      note: form.note.trim() || null,
    }
    const result = await contributionDashboardApi.createManual(payload, idempotencyKey.value)
    ElMessage.success('消费录入成功')
    emit('success', result)
    emit('update:modelValue', false)
    resetForm()
    return result
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    const code = error.response?.data?.code
    if (code === 40920 || code === 40921) {
      form.customerId = ''
      selectedCustomer.value = null
      customerOptions.value = []
    }
    ElMessage.error(error.userMessage || error.response?.data?.message || error.message || '消费录入失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({
  form,
  customerOptions,
  selectedCustomer,
  searchCustomers,
  selectCustomer,
  submit,
})
</script>

<style scoped>
.customer-option { display: flex; flex-direction: column; gap: 2px; line-height: 1.35; }
.customer-option div { display: flex; justify-content: space-between; gap: 12px; }
.customer-option span, .customer-option small { color: var(--el-text-color-secondary); }
.customer-summary { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--el-text-color-regular); }
</style>
