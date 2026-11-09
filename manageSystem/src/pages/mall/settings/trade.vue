<template>
  <section class="mall-settings-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">商城设置</p>
        <h2>交易设置</h2>
        <p class="page-subtitle">维护商城开关、运费和订单履约时限；变更会留下操作记录。</p>
      </div>
      <el-button data-test="settings-reload" :loading="loading" @click="load">
        重新读取
      </el-button>
    </header>

    <nav class="settings-nav" aria-label="商城设置页面">
      <el-button @click="router.push('/mall/settings/delivery')">配送设置</el-button>
      <el-button type="primary" disabled>交易设置</el-button>
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
      <el-alert class="policy-note" type="info" show-icon :closable="false">
        <template #title>
          对外购买状态：<strong>{{ effectiveLabel }}</strong>
        </template>
        <template #default>
          对外是否可购买还受服务器环境开关控制；此处状态以买家结算接口的有效结果为准。
        </template>
      </el-alert>

      <el-card shadow="never" class="settings-card">
        <template #header>
          <div class="card-heading">
            <div><strong>商城状态</strong><p>商城服务与下单入口分开控制。</p></div>
            <el-tag v-if="canWrite" type="success" effect="plain">可编辑</el-tag>
            <el-tag v-else type="info" effect="plain">仅查看</el-tag>
          </div>
        </template>
        <div class="switch-list">
          <div class="switch-row">
            <div><strong>商城启用</strong><p>关闭后商城商品入口不可用。</p></div>
            <el-switch v-model="form.enabled" data-test="mall-enabled" :disabled="!canWrite || command.busy.value" />
          </div>
          <div class="switch-row">
            <div><strong>允许购买</strong><p>控制后台配置层的下单开关；服务器总开关仍可关闭购买。</p></div>
            <el-switch v-model="form.purchaseEnabled" data-test="purchase-enabled" :disabled="!canWrite || command.busy.value" />
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header><div class="card-heading"><div><strong>支付与运费</strong><p>金额以人民币元编辑，保存为精确分值。</p></div></div></template>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="运费方式">
            <el-radio-group v-model="form.freightMode" :disabled="!canWrite || command.busy.value">
              <el-radio-button value="free">包邮</el-radio-button>
              <el-radio-button value="fixed">固定运费</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="固定运费（元）">
            <el-input
              v-model="form.freightYuan"
              data-test="freight-yuan"
              inputmode="decimal"
              maxlength="14"
              :disabled="!canWrite || command.busy.value || form.freightMode === 'free'"
            >
              <template #prepend>¥</template>
            </el-input>
          </el-form-item>
          <el-form-item label="支付有效时长（分钟）">
            <el-input-number v-model="form.paymentMinutes" :min="1" :disabled="!canWrite || command.busy.value" />
          </el-form-item>
          <el-form-item label="不配送地区代码">
            <el-input
              v-model="form.blockedRegionCodesText"
              data-test="blocked-regions"
              type="textarea"
              :rows="3"
              maxlength="4000"
              placeholder="多个6位区县代码可用逗号或换行分隔"
              :disabled="!canWrite || command.busy.value"
            />
            <small>请填写区县级6位行政区划代码。留空表示不设置限制。</small>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header><div class="card-heading"><div><strong>订单履约与政策</strong><p>时间从相应订单状态确认时开始计算。</p></div></div></template>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="自动确认收货（天）">
            <el-input-number v-model="form.autoReceiveDays" :min="1" :disabled="!canWrite || command.busy.value" />
          </el-form-item>
          <el-form-item label="售后申请期限（天）">
            <el-input-number v-model="form.aftersaleDays" :min="1" :disabled="!canWrite || command.busy.value" />
          </el-form-item>
          <el-form-item label="商城联系说明">
            <el-input v-model="form.contactText" data-test="contact-text" maxlength="500" :disabled="!canWrite || command.busy.value" />
          </el-form-item>
          <el-form-item label="规则版本号">
            <el-input v-model="form.policyVersion" data-test="policy-version" maxlength="100" :disabled="!canWrite || command.busy.value" />
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header><div class="card-heading"><div><strong>配送与退货说明</strong><p>买家在提交订单或申请退货时可查看。</p></div></div></template>
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
          data-test="save-trade-settings"
          type="primary"
          :loading="command.busy.value"
          :disabled="command.pending.value || loading"
          @click="save"
        >
          保存交易设置
        </el-button>
      </div>
      <p v-else class="readonly-note">当前账号只有读取权限，设置修改入口已隐藏。</p>
    </template>

    <el-skeleton v-else-if="loading" :rows="8" animated />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getMallCheckoutSettings, getMallSettings, saveMallSettings } from '@/api/mall-settings'
import { useMallCommand } from '@/composables/useMallCommand'

const auth = useAuthStore()
const router = useRouter()
const command = useMallCommand()
const canWrite = computed(() => auth.hasPermission('mall.settings.write'))
const loading = ref(false)
const settings = ref(null)
const effectivePurchaseAvailable = ref(null)
const loadError = ref('')
const validationError = ref('')
const form = reactive({
  enabled: false,
  purchaseEnabled: false,
  freightMode: 'free',
  freightYuan: '0.00',
  blockedRegionCodesText: '',
  paymentMinutes: 30,
  autoReceiveDays: 15,
  aftersaleDays: 15,
  contactText: '',
  policyVersion: '',
  returnInstructions: '',
  reason: '',
})
const effectiveLabel = computed(() => {
  if (effectivePurchaseAvailable.value === null) return '暂未读取'
  return effectivePurchaseAvailable.value ? '可购买' : '暂未开放购买'
})

function setForm(value) {
  settings.value = value
  form.enabled = Boolean(value.enabled)
  form.purchaseEnabled = Boolean(value.purchaseEnabled)
  form.freightMode = value.freightMode || 'free'
  form.freightYuan = (Number(value.freightCent || 0) / 100).toFixed(2)
  form.blockedRegionCodesText = (value.blockedRegionCodes || []).join(', ')
  form.paymentMinutes = Number(value.paymentMinutes || 30)
  form.autoReceiveDays = Number(value.autoReceiveDays || 15)
  form.aftersaleDays = Number(value.aftersaleDays || 15)
  form.contactText = value.contactText || ''
  form.policyVersion = value.policyVersion || ''
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
    try {
      const checkout = await getMallCheckoutSettings()
      effectivePurchaseAvailable.value = Boolean(checkout.purchasingAvailable)
    } catch {
      effectivePurchaseAvailable.value = null
    }
  } catch (failure) {
    settings.value = null
    loadError.value = failure.userMessage || failure.message || '读取交易设置失败，请重试。'
  } finally {
    loading.value = false
  }
}

function regionCodes() {
  return form.blockedRegionCodesText
    .split(/[\s,，;；]+/)
    .map((value) => value.trim())
    .filter(Boolean)
}

function freightCent() {
  const value = String(form.freightYuan).trim()
  if (!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error('固定运费须为非负金额，最多两位小数。')
  const [whole, fraction = ''] = value.split('.')
  const cent = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  if (cent > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('固定运费超出可保存范围。')
  return Number(cent)
}

function buildPayload() {
  if (!settings.value) throw new Error('请先读取当前配置。')
  const reason = form.reason.trim()
  if (!reason) throw new Error('请填写本次变更原因。')
  if (!form.policyVersion.trim()) throw new Error('请填写规则版本号。')
  const regions = regionCodes()
  for (const [value, label] of [
    [form.paymentMinutes, '支付有效时长'],
    [form.autoReceiveDays, '自动确认收货天数'],
    [form.aftersaleDays, '售后申请期限'],
  ]) {
    if (!Number.isSafeInteger(Number(value)) || Number(value) < 1 || Number(value) > 2147483647) {
      throw new Error(`${label}须为1至2147483647之间的整数。`)
    }
  }
  if (regions.some((code) => !/^\d{6}$/.test(code))) throw new Error('不配送地区须填写6位区县代码。')
  if (new Set(regions).size !== regions.length) throw new Error('不配送地区代码不能重复。')
  const current = settings.value
  return {
    expectedVersion: current.version,
    reason,
    settings: {
      version: current.version,
      enabled: Boolean(form.enabled),
      purchaseEnabled: Boolean(form.purchaseEnabled),
      freightMode: form.freightMode,
      freightCent: freightCent(),
      blockedRegionCodes: regions,
      paymentMinutes: Number(form.paymentMinutes),
      autoReceiveDays: Number(form.autoReceiveDays),
      aftersaleDays: Number(form.aftersaleDays),
      contactText: form.contactText.trim(),
      policyVersion: form.policyVersion.trim(),
      dispatchAddressMasked: current.dispatchAddressMasked || '',
      returnAddressMasked: current.returnAddressMasked || '',
      returnInstructions: form.returnInstructions.trim(),
    },
  }
}

async function finish(result) {
  if (!result) return
  setForm(result)
  try {
    const checkout = await getMallCheckoutSettings()
    effectivePurchaseAvailable.value = Boolean(checkout.purchasingAvailable)
  } catch {
    effectivePurchaseAvailable.value = null
  }
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
  await finish(result)
}

async function retry() {
  const result = await command.retry()
  await finish(result)
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
.policy-note { margin: 0; }
.policy-note :deep(.el-alert__description) { margin-top: 4px; }
.settings-card { border-color: #e6ece8; border-radius: 12px; }
.settings-card :deep(.el-card__header) { padding: 18px 20px 14px; }
.settings-card :deep(.el-card__body) { padding: 8px 20px 20px; }
.card-heading { display: flex; justify-content: space-between; align-items: flex-start; }
.card-heading strong { color: #24372e; font-size: 15px; }
.card-heading p { margin: 4px 0 0; color: #89958e; font-size: 12px; font-weight: 400; }
.switch-list { display: grid; }
.switch-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 16px 0; border-bottom: 1px solid #eff2ef; }
.switch-row:last-child { border-bottom: 0; }
.switch-row strong { color: #33463c; font-size: 14px; }
.switch-row p { margin: 4px 0 0; color: #87928b; font-size: 12px; }
.settings-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 22px; }
.settings-form :deep(.el-form-item) { margin-bottom: 18px; }
.settings-form :deep(.el-input-number), .settings-form :deep(.el-input) { width: 100%; }
.settings-form small { display: block; margin-top: 5px; color: #87928b; line-height: 1.5; }
.save-bar { position: sticky; bottom: -20px; display: flex; justify-content: flex-end; gap: 10px; padding: 14px 0; background: rgba(246, 248, 246, .96); backdrop-filter: blur(10px); }
.save-bar :deep(.el-input) { max-width: 360px; margin-right: auto; }
.readonly-note { color: #89958e; font-size: 13px; }
@media (max-width: 680px) { .page-heading { align-items: flex-start; flex-direction: column; } .settings-form { grid-template-columns: 1fr; } .save-bar { bottom: -12px; flex-wrap: wrap; } .save-bar :deep(.el-input) { max-width: none; width: 100%; } }
</style>
