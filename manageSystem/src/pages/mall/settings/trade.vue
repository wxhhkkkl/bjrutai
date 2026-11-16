<template>
  <section class="mall-settings-page mall-management-page">
    <header class="page-heading page-header">
      <div>
        <p class="eyebrow">商城设置</p>
        <h2 class="page-title">交易设置</h2>
        <p class="page-subtitle">
          维护商城开关、运费和订单履约时限；变更会留下操作记录。
        </p>
      </div>
    </header>

    <el-alert
      v-if="command.pending.value"
      title="设置提交结果未确认。请重试原操作，系统会沿用相同请求编号和内容。"
      type="warning"
      show-icon
      :closable="false"
    />

    <template v-if="settings">
      <el-card shadow="never" class="settings-card">
        <template #header>
          <div class="card-heading">
            <div>
              <strong>商城状态</strong>
              <p>商城服务与下单入口分开控制。</p>
            </div>
            <el-tag v-if="canWrite" type="success" effect="plain"
              >可编辑</el-tag
            >
            <el-tag v-else type="info" effect="plain">仅查看</el-tag>
          </div>
        </template>
        <div class="switch-list">
          <div class="switch-row">
            <div>
              <strong>商城启用</strong>
              <p>关闭后商城商品入口不可用。</p>
            </div>
            <el-switch
              v-model="form.enabled"
              data-test="mall-enabled"
              :disabled="!canWrite || command.busy.value"
            />
          </div>
          <div class="switch-row">
            <div>
              <strong>允许购买</strong>
              <p>控制后台配置层的下单开关；服务器总开关仍可关闭购买。</p>
            </div>
            <el-switch
              v-model="form.purchaseEnabled"
              data-test="purchase-enabled"
              :disabled="!canWrite || command.busy.value"
            />
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header
          ><div class="card-heading"><strong>支付设置</strong></div></template
        >
        <el-form label-position="top" class="settings-form">
          <el-form-item label="支付有效时长（分钟）">
            <el-input-number
              v-model="form.paymentMinutes"
              :min="1"
              :disabled="!canWrite || command.busy.value"
            />
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header
          ><div class="card-heading">
            <div>
              <strong>订单履约与政策</strong>
              <p>时间从相应订单状态确认时开始计算。</p>
            </div>
          </div></template
        >
        <el-form label-position="top" class="settings-form">
          <el-form-item label="自动确认收货（天）">
            <el-input-number
              v-model="form.autoReceiveDays"
              :min="1"
              :disabled="!canWrite || command.busy.value"
            />
          </el-form-item>
          <el-form-item label="售后申请期限（天）">
            <el-input-number
              v-model="form.aftersaleDays"
              :min="1"
              :disabled="!canWrite || command.busy.value"
            />
          </el-form-item>
          <el-form-item label="商城联系说明">
            <el-input
              v-model="form.contactText"
              data-test="contact-text"
              maxlength="500"
              :disabled="!canWrite || command.busy.value"
            />
          </el-form-item>
        </el-form>
      </el-card>

      <div v-if="canWrite" class="save-bar">
        <el-input
          v-model="form.reason"
          data-test="settings-reason"
          maxlength="500"
          placeholder="填写本次变更原因（选填）"
          :disabled="command.busy.value"
        />
        <el-button
          v-if="command.pending.value"
          data-test="retry-settings"
          type="warning"
          :loading="command.busy.value"
          @click="retry"
        >
          重试原操作
        </el-button>
        <el-button
          data-test="save-trade-settings"
          type="primary"
          :loading="command.busy.value"
          :disabled="command.pending.value || loading"
          @click="save"
        >
          保存交易设置
        </el-button>
      </div>
      <p v-else class="readonly-note">
        当前账号只有读取权限，设置修改入口已隐藏。
      </p>
    </template>

    <el-skeleton v-else-if="loading" :rows="8" animated />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  getMallSettings,
  saveMallSettings,
} from '@/api/mall-settings'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'

const auth = useAuthStore()
const command = useMallCommand()
const canWrite = computed(() => auth.hasPermission('mall.settings.write'))
const loading = ref(false)
const settings = ref(null)
const loadError = ref('')
const validationError = ref('')
useMallToast(loadError)
useMallToast(validationError, 'warning')
const form = reactive({
  enabled: false,
  purchaseEnabled: false,
  paymentMinutes: 30,
  autoReceiveDays: 15,
  aftersaleDays: 15,
  contactText: '',
  returnInstructions: '',
  reason: '',
})
function setForm(value) {
  settings.value = value
  form.enabled = Boolean(value.enabled)
  form.purchaseEnabled = Boolean(value.purchaseEnabled)
  form.paymentMinutes = Number(value.paymentMinutes || 30)
  form.autoReceiveDays = Number(value.autoReceiveDays || 15)
  form.aftersaleDays = Number(value.aftersaleDays || 15)
  form.contactText = value.contactText || ''
  form.returnInstructions = value.returnInstructions || ''
  form.reason = ''
}

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  validationError.value = ''
  try {
    const value = await getMallSettings()
    setForm(value)
  } catch (failure) {
    settings.value = null
    loadError.value =
      failure.userMessage || failure.message || '读取交易设置失败，请重试。'
  } finally {
    loading.value = false
  }
}

function buildPayload() {
  if (!settings.value) throw new Error('请先读取当前配置。')
  const reason = form.reason.trim()
  for (const [value, label] of [
    [form.paymentMinutes, '支付有效时长'],
    [form.autoReceiveDays, '自动确认收货天数'],
    [form.aftersaleDays, '售后申请期限'],
  ]) {
    if (
      !Number.isSafeInteger(Number(value)) ||
      Number(value) < 1 ||
      Number(value) > 2147483647
    ) {
      throw new Error(`${label}须为1至2147483647之间的整数。`)
    }
  }
  const current = settings.value
  return {
    expectedVersion: current.version,
    reason,
    settings: {
      version: current.version,
      enabled: Boolean(form.enabled),
      purchaseEnabled: Boolean(form.purchaseEnabled),
      freightMode: current.freightMode,
      freightCent: current.freightCent,
      defaultBlockedRegionCodes: current.defaultBlockedRegionCodes,
      paymentMinutes: Number(form.paymentMinutes),
      autoReceiveDays: Number(form.autoReceiveDays),
      aftersaleDays: Number(form.aftersaleDays),
      contactText: form.contactText.trim(),
      dispatchAddressMasked: current.dispatchAddressMasked || '',
      returnAddressMasked: current.returnAddressMasked || '',
      returnInstructions: form.returnInstructions.trim(),
    },
  }
}

function finish(result) {
  if (!result) return
  setForm(result)
}

async function save() {
  if (!canWrite.value || command.busy.value || command.pending.value) return
  validationError.value = ''
  let body
  try {
    body = buildPayload()
  } catch (failure) {
    validationError.value = failure.message || '请检查设置内容。'
    return
  }
  const result = await command.run(saveMallSettings, body)
  finish(result)
}

async function retry() {
  const result = await command.retry()
  finish(result)
}

onMounted(load)
</script>

<style scoped>
.eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.page-subtitle {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.settings-card {
  border-color: var(--app-border-color);
  border-radius: var(--app-radius-lg);
}
.settings-card :deep(.el-card__header) {
  padding: 18px 20px 14px;
}
.settings-card :deep(.el-card__body) {
  padding: 8px 20px 20px;
}
.card-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.card-heading strong {
  color: var(--app-text-primary);
  font-size: 15px;
}
.card-heading p {
  margin: 4px 0 0;
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 400;
}
.switch-list {
  display: grid;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 0;
  border-bottom: 1px solid var(--app-border-color);
}
.switch-row:last-child {
  border-bottom: 0;
}
.switch-row strong {
  color: var(--app-text-primary);
  font-size: 14px;
}
.switch-row p {
  margin: 4px 0 0;
  color: var(--app-text-secondary);
  font-size: 12px;
}
.settings-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 22px;
}
.settings-form :deep(.el-form-item) {
  margin-bottom: 18px;
}
.settings-form :deep(.el-input-number),
.settings-form :deep(.el-input) {
  width: 100%;
}
.settings-form small {
  display: block;
  margin-top: 5px;
  color: var(--app-text-secondary);
  line-height: 1.5;
}
.save-bar {
  position: sticky;
  bottom: -20px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 24px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(10px);
}
.save-bar :deep(.el-input) {
  max-width: 360px;
  margin-right: auto;
}
.readonly-note {
  color: var(--app-text-secondary);
  font-size: 13px;
}
@media (max-width: 680px) {
  .settings-form {
    grid-template-columns: 1fr;
  }
  .save-bar {
    bottom: -12px;
    flex-wrap: wrap;
    padding-right: 16px;
    padding-left: 16px;
  }
  .save-bar :deep(.el-input) {
    max-width: none;
    width: 100%;
  }
}
</style>
