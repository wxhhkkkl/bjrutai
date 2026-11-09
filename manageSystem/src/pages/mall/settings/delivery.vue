<template>
  <section class="mall-settings-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">商城设置</p>
        <h2>配送设置</h2>
        <p class="page-subtitle">配置仓库联系信息和配送说明；已保存地址只显示掩码。</p>
      </div>
      <el-button data-test="settings-reload" :loading="loading" @click="load">
        重新读取
      </el-button>
    </header>

    <nav class="settings-nav" aria-label="商城设置页面">
      <el-button type="primary" disabled>配送设置</el-button>
      <el-button @click="router.push('/mall/settings/trade')">交易设置</el-button>
    </nav>

    <el-alert
      v-if="loadError"
      data-test="settings-load-error"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
    />
    <el-alert
      v-if="validationError"
      :title="validationError"
      type="warning"
      show-icon
      :closable="false"
    />
    <el-alert
      v-if="command.error.value"
      data-test="settings-save-error"
      :title="command.error.value"
      type="error"
      show-icon
      :closable="false"
    />
    <el-alert
      v-if="command.pending.value"
      title="设置提交结果未确认。请重试原操作，系统会沿用相同请求编号和内容。"
      type="warning"
      show-icon
      :closable="false"
    />

    <template v-if="settings">
      <el-alert type="info" show-icon :closable="false">
        <template #title><strong>隐私保护</strong></template>
        后台只返回“已配置”状态，不会读取历史联系人、电话或门牌。只有勾选“替换地址”后才提交新地址；不勾选的已存地址会保留。
      </el-alert>

      <el-card shadow="never" class="settings-card">
        <template #header>
          <div class="card-heading">
            <div><strong>发货地址</strong><p>用于订单履约与物流信息登记。</p></div>
            <el-tag :type="settings.dispatchAddressMasked ? 'success' : 'info'" effect="plain">
              {{ settings.dispatchAddressMasked || '尚未配置' }}
            </el-tag>
          </div>
        </template>
        <el-checkbox
          v-if="canWrite"
          v-model="replaceDispatch"
          data-test="replace-dispatch"
          :disabled="command.busy.value"
        >
          替换发货地址
        </el-checkbox>
        <p v-else class="readonly-note">当前账号仅可查看是否已配置。</p>
        <WarehouseAddressForm
          v-if="replaceDispatch"
          v-model="form.dispatch"
          prefix="dispatch"
          :disabled="command.busy.value"
        />
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header>
          <div class="card-heading">
            <div><strong>退货地址</strong><p>用于买家寄回商品时的收件信息。</p></div>
            <el-tag :type="settings.returnAddressMasked ? 'success' : 'info'" effect="plain">
              {{ settings.returnAddressMasked || '尚未配置' }}
            </el-tag>
          </div>
        </template>
        <el-checkbox
          v-if="canWrite"
          v-model="replaceReturn"
          data-test="replace-return"
          :disabled="command.busy.value"
        >
          替换退货地址
        </el-checkbox>
        <p v-else class="readonly-note">当前账号仅可查看是否已配置。</p>
        <WarehouseAddressForm
          v-if="replaceReturn"
          v-model="form.returnAddress"
          prefix="return"
          :disabled="command.busy.value"
        />
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header><div class="card-heading"><div><strong>退货说明</strong><p>仅写必要的退货指引，不要填写顾客个人信息。</p></div></div></template>
        <el-input
          v-model="form.returnInstructions"
          data-test="return-instructions"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          :disabled="!canWrite || command.busy.value"
        />
      </el-card>

      <div v-if="canWrite" class="save-bar">
        <el-input
          v-model="form.reason"
          data-test="settings-reason"
          maxlength="500"
          placeholder="填写本次变更原因（必填）"
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
          data-test="save-delivery-settings"
          type="primary"
          :loading="command.busy.value"
          :disabled="command.pending.value || loading"
          @click="save"
        >
          保存配送设置
        </el-button>
      </div>
      <p v-else class="readonly-note">当前账号只有读取权限，设置修改入口已隐藏。</p>
    </template>

    <el-skeleton v-else-if="loading" :rows="7" animated />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getMallSettings, saveMallSettings } from '@/api/mall-settings'
import { useMallCommand } from '@/composables/useMallCommand'
import WarehouseAddressForm from './WarehouseAddressForm.vue'

const auth = useAuthStore()
const router = useRouter()
const command = useMallCommand()
const canWrite = computed(() => auth.hasPermission('mall.settings.write'))
const loading = ref(false)
const settings = ref(null)
const loadError = ref('')
const validationError = ref('')
const replaceDispatch = ref(false)
const replaceReturn = ref(false)
const blankAddress = () => ({
  contactName: '',
  phone: '',
  regionCodes: ['', '', ''],
  addressLine: '',
})
const form = reactive({
  dispatch: blankAddress(),
  returnAddress: blankAddress(),
  returnInstructions: '',
  reason: '',
})

function setSettings(value) {
  settings.value = value
  form.dispatch = blankAddress()
  form.returnAddress = blankAddress()
  form.returnInstructions = value.returnInstructions || ''
  form.reason = ''
  replaceDispatch.value = false
  replaceReturn.value = false
}

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  validationError.value = ''
  try {
    setSettings(await getMallSettings())
  } catch (failure) {
    settings.value = null
    loadError.value = failure.userMessage || failure.message || '读取配送设置失败，请重试。'
  } finally {
    loading.value = false
  }
}

function normalizeAddress(address, label) {
  const contactName = address.contactName.trim()
  const phone = address.phone.trim()
  const addressLine = address.addressLine.trim()
  const regionCodes = address.regionCodes.map((code) => String(code).trim())
  if (!contactName || contactName.length > 50) throw new Error(`${label}联系人须填写，最多50个字符。`)
  if (!/^[0-9+()\-\s]{6,20}$/.test(phone)) throw new Error(`${label}电话格式不正确。`)
  if (regionCodes.length !== 3 || regionCodes.some((code) => !/^\d{6}$/.test(code))) {
    throw new Error(`${label}地区须按省、市、区县顺序填写3个6位行政区划代码。`)
  }
  if (!addressLine || addressLine.length > 200) throw new Error(`${label}详细地址须填写，最多200个字符。`)
  return { contactName, phone, regionCodes, addressLine }
}

function buildPayload() {
  if (!settings.value) throw new Error('请先读取当前配置。')
  const reason = form.reason.trim()
  if (!reason) throw new Error('请填写本次变更原因。')
  if (!replaceDispatch.value && !replaceReturn.value &&
    form.returnInstructions.trim() === (settings.value.returnInstructions || '').trim()) {
    throw new Error('请替换一个配送地址，或修改退货说明后再保存。')
  }
  const body = {
    expectedVersion: settings.value.version,
    reason,
    settings: {
      version: settings.value.version,
      enabled: Boolean(settings.value.enabled),
      purchaseEnabled: Boolean(settings.value.purchaseEnabled),
      freightMode: settings.value.freightMode,
      freightCent: Number(settings.value.freightCent),
      blockedRegionCodes: settings.value.blockedRegionCodes || [],
      paymentMinutes: Number(settings.value.paymentMinutes),
      autoReceiveDays: Number(settings.value.autoReceiveDays),
      aftersaleDays: Number(settings.value.aftersaleDays),
      contactText: settings.value.contactText || '',
      policyVersion: settings.value.policyVersion || '',
      dispatchAddressMasked: settings.value.dispatchAddressMasked || '',
      returnAddressMasked: settings.value.returnAddressMasked || '',
      returnInstructions: form.returnInstructions.trim(),
    },
  }
  if (replaceDispatch.value) body.dispatchAddress = normalizeAddress(form.dispatch, '发货')
  if (replaceReturn.value) body.returnAddress = normalizeAddress(form.returnAddress, '退货')
  return body
}

function applyResult(value) {
  if (value && typeof value.version === 'number') setSettings(value)
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
  applyResult(await command.run(saveMallSettings, body))
}

async function retry() {
  applyResult(await command.retry())
}

onMounted(load)
</script>

<style scoped>
.mall-settings-page { display: grid; gap: 16px; max-width: 1080px; margin: 0 auto; }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 4px 0 0; }
.eyebrow { margin: 0 0 6px; color: #688277; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 0 0 6px; color: #1d3028; font-size: 24px; }
.page-subtitle { margin: 0; color: #718078; font-size: 13px; }
.settings-nav { display: flex; gap: 8px; }
.settings-card { border-color: #e6ece8; border-radius: 12px; }
.settings-card :deep(.el-card__header) { padding: 18px 20px 14px; }
.settings-card :deep(.el-card__body) { padding: 8px 20px 20px; }
.card-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 15px; }
.card-heading strong { color: #24372e; font-size: 15px; }
.card-heading p { margin: 4px 0 0; color: #89958e; font-size: 12px; font-weight: 400; }
.address-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.address-grid--regions { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.address-help, .readonly-note { margin: 2px 0 0; color: #87928b; font-size: 12px; }
.save-bar { position: sticky; bottom: -20px; display: flex; justify-content: flex-end; gap: 10px; padding: 14px 0; background: rgba(246, 248, 246, .96); backdrop-filter: blur(10px); }
.save-bar :deep(.el-input) { max-width: 360px; margin-right: auto; }
.readonly-note { font-size: 13px; }
@media (max-width: 680px) { .page-heading { align-items: flex-start; flex-direction: column; } .address-grid, .address-grid--regions { grid-template-columns: 1fr; gap: 0; } .save-bar { bottom: -12px; flex-wrap: wrap; } .save-bar :deep(.el-input) { max-width: none; width: 100%; } }
</style>
