<template>
  <section class="mall-settings-page mall-management-page">
    <header class="page-heading page-header">
      <div>
        <p class="eyebrow">商城设置</p>
        <h2 class="page-title">配送设置</h2>
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
              <strong>发货地址</strong>
              <p>用于订单履约与物流信息登记。</p>
            </div>
            <div class="address-status-actions">
              <el-button
                v-if="canWrite && !settings.dispatchAddressMasked && !replaceDispatch"
                type="primary"
                link
                data-test="configure-dispatch-address"
                :disabled="
                  loading ||
                  command.busy.value ||
                  command.pending.value ||
                  replaceReturn
                "
                @click="beginDispatchEdit"
              >
                配置
              </el-button>
              <el-button
                v-else-if="canWrite && !replaceDispatch"
                type="primary"
                link
                data-test="edit-dispatch-address"
                :disabled="
                  loading ||
                  command.busy.value ||
                  command.pending.value ||
                  replaceReturn
                "
                @click="beginDispatchEdit"
              >
                修改配置
              </el-button>
            </div>
          </div>
        </template>
        <template v-if="replaceDispatch">
          <WarehouseAddressForm
            v-model="form.dispatch"
            prefix="dispatch"
            :disabled="command.busy.value"
          />
          <div class="address-edit-actions">
            <div class="address-edit-buttons">
              <el-button
                v-if="command.pending.value"
                type="warning"
                :loading="command.busy.value"
                @click="retry"
              >
                重试原操作
              </el-button>
              <template v-else>
                <el-button
                  :disabled="command.busy.value"
                  @click="cancelDispatchEdit"
                >
                  取消
                </el-button>
                <el-button
                  type="primary"
                  data-test="save-dispatch-address"
                  :loading="command.busy.value"
                  :disabled="loading"
                  @click="save"
                >
                  保存发货地址
                </el-button>
              </template>
            </div>
          </div>
        </template>
        <div
          v-else
          class="address-status-row"
          :data-test="
            settings.dispatchAddressMasked ? undefined : 'dispatch-address-empty'
          "
        >
          <el-tag
            :type="settings.dispatchAddressMasked ? 'success' : 'info'"
            effect="plain"
            data-test="dispatch-address-status"
          >
            {{ settings.dispatchAddressMasked || '暂未配置' }}
          </el-tag>
          <dl
            v-if="settings.dispatchAddress"
            class="warehouse-address-summary"
            data-test="dispatch-address-details"
          >
            <div>
              <dt>联系人</dt>
              <dd>{{ settings.dispatchAddress.contactName }}</dd>
            </div>
            <div>
              <dt>联系电话</dt>
              <dd>{{ settings.dispatchAddress.phone }}</dd>
            </div>
            <div class="warehouse-address-summary__full">
              <dt>地址</dt>
              <dd>{{ fullAddress(settings.dispatchAddress) }}</dd>
            </div>
          </dl>
          <p
            v-if="settings.dispatchAddressMasked && !canWrite"
            class="readonly-note"
          >
            当前账号仅可查看是否已配置。
          </p>
        </div>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header>
          <div class="card-heading">
            <div>
              <strong>退货地址</strong>
              <p>用于买家寄回商品时的收件信息。</p>
            </div>
            <div class="address-status-actions">
              <el-button
                v-if="canWrite && !settings.returnAddressMasked && !replaceReturn"
                type="primary"
                link
                data-test="configure-return-address"
                :disabled="
                  loading ||
                  command.busy.value ||
                  command.pending.value ||
                  replaceDispatch
                "
                @click="beginReturnEdit"
              >
                配置
              </el-button>
              <el-button
                v-else-if="canWrite && !replaceReturn"
                type="primary"
                link
                data-test="edit-return-address"
                :disabled="
                  loading ||
                  command.busy.value ||
                  command.pending.value ||
                  replaceDispatch
                "
                @click="beginReturnEdit"
              >
                修改配置
              </el-button>
            </div>
          </div>
        </template>
        <template v-if="replaceReturn">
          <WarehouseAddressForm
            v-model="form.returnAddress"
            prefix="return"
            :disabled="command.busy.value"
          />
          <div class="address-edit-actions">
            <div class="address-edit-buttons">
              <el-button
                v-if="command.pending.value"
                type="warning"
                :loading="command.busy.value"
                @click="retry"
              >
                重试原操作
              </el-button>
              <template v-else>
                <el-button
                  :disabled="command.busy.value"
                  @click="cancelReturnEdit"
                >
                  取消
                </el-button>
                <el-button
                  type="primary"
                  data-test="save-return-address"
                  :loading="command.busy.value"
                  :disabled="loading"
                  @click="save"
                >
                  保存退货地址
                </el-button>
              </template>
            </div>
          </div>
        </template>
        <div
          v-else
          class="address-status-row"
          :data-test="
            settings.returnAddressMasked ? undefined : 'return-address-empty'
          "
        >
          <el-tag
            :type="settings.returnAddressMasked ? 'success' : 'info'"
            effect="plain"
            data-test="return-address-status"
          >
            {{ settings.returnAddressMasked || '暂未配置' }}
          </el-tag>
          <dl
            v-if="settings.returnAddress"
            class="warehouse-address-summary"
            data-test="return-address-details"
          >
            <div>
              <dt>联系人</dt>
              <dd>{{ settings.returnAddress.contactName }}</dd>
            </div>
            <div>
              <dt>联系电话</dt>
              <dd>{{ settings.returnAddress.phone }}</dd>
            </div>
            <div class="warehouse-address-summary__full">
              <dt>地址</dt>
              <dd>{{ fullAddress(settings.returnAddress) }}</dd>
            </div>
          </dl>
          <p
            v-if="settings.returnAddressMasked && !canWrite"
            class="readonly-note"
          >
            当前账号仅可查看是否已配置。
          </p>
        </div>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header
          ><div class="card-heading">
            <div>
              <strong>退货说明</strong>
              <p>仅写必要的退货指引，不要填写顾客个人信息。</p>
            </div>
          </div></template
        >
        <el-input
          v-model="form.returnInstructions"
          data-test="return-instructions"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          :disabled="
            !canWrite || command.busy.value || command.pending.value
          "
        />
        <div
          v-if="canWrite && !replaceReturn && !replaceDispatch"
          class="instructions-save-row"
        >
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
            v-else
            data-test="save-delivery-settings"
            type="primary"
            :loading="command.busy.value"
            :disabled="loading || !returnInstructionsDirty"
            @click="save"
          >
            保存退货说明
          </el-button>
        </div>
      </el-card>
      <p v-if="!canWrite" class="readonly-note">
        当前账号只有读取权限，设置修改入口已隐藏。
      </p>
    </template>

    <el-skeleton v-else-if="loading" :rows="7" animated />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getMallSettings, saveMallSettings } from '@/api/mall-settings'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
import WarehouseAddressForm from './WarehouseAddressForm.vue'

const auth = useAuthStore()
const command = useMallCommand()
const canWrite = computed(() => auth.hasPermission('mall.settings.write'))
const loading = ref(false)
const settings = ref(null)
const loadError = ref('')
useMallToast(loadError)
const replaceDispatch = ref(false)
const replaceReturn = ref(false)
const blankAddress = () => ({
  contactName: '',
  phone: '',
  regionCodes: ['', '', ''],
  regionNames: ['', '', ''],
  addressLine: '',
})
const form = reactive({
  dispatch: blankAddress(),
  returnAddress: blankAddress(),
  returnInstructions: '',
})
const returnInstructionsDirty = computed(
  () =>
    Boolean(settings.value) &&
    form.returnInstructions.trim() !==
      (settings.value.returnInstructions || '').trim()
)

function setSettings(value) {
  settings.value = value
  form.dispatch = blankAddress()
  form.returnAddress = blankAddress()
  form.returnInstructions = value.returnInstructions || ''
  replaceDispatch.value = false
  replaceReturn.value = false
}

function beginDispatchEdit() {
  if (
    !canWrite.value ||
    loading.value ||
    command.busy.value ||
    command.pending.value ||
    replaceReturn.value
  ) {
    return
  }
  form.dispatch = editableAddress(settings.value.dispatchAddress)
  replaceDispatch.value = true
}

function cancelDispatchEdit() {
  if (command.busy.value || command.pending.value) return
  form.dispatch = blankAddress()
  replaceDispatch.value = false
}

function beginReturnEdit() {
  if (
    !canWrite.value ||
    loading.value ||
    command.busy.value ||
    command.pending.value ||
    replaceDispatch.value
  ) {
    return
  }
  form.returnAddress = editableAddress(settings.value.returnAddress)
  replaceReturn.value = true
}

function editableAddress(address) {
  const value = address || blankAddress()
  return {
    contactName: String(value.contactName || ''),
    phone: String(value.phone || ''),
    regionCodes: Array.isArray(value.regionCodes)
      ? [...value.regionCodes]
      : ['', '', ''],
    regionNames: Array.isArray(value.regionNames)
      ? [...value.regionNames]
      : ['', '', ''],
    addressLine: String(value.addressLine || ''),
  }
}

function fullAddress(address) {
  const regionNames = Array.isArray(address.regionNames)
    ? address.regionNames.map((name) => String(name || '').trim()).filter(Boolean)
    : []
  const regions = regionNames.length
    ? regionNames.join(' ')
    : (address.regionCodes || []).join(' ')
  return [regions, address.addressLine].filter(Boolean).join(' ')
}

function cancelReturnEdit() {
  if (command.busy.value || command.pending.value) return
  form.returnAddress = blankAddress()
  replaceReturn.value = false
}

async function load() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    setSettings(await getMallSettings())
  } catch (failure) {
    settings.value = null
    loadError.value =
      failure.userMessage || failure.message || '读取配送设置失败，请重试。'
  } finally {
    loading.value = false
  }
}

function normalizeAddress(address, label) {
  const contactName = address.contactName.trim()
  const phone = address.phone.trim()
  const addressLine = address.addressLine.trim()
  const regionCodes = address.regionCodes.map((code) => String(code).trim())
  const regionNames = (address.regionNames || []).map((name) => String(name || '').trim())
  const hasRegionNames = regionNames.some(Boolean)
  if (!contactName || contactName.length > 50)
    throw new Error(`${label}联系人须填写，最多50个字符。`)
  if (!/^[0-9+()\-\s]{6,20}$/.test(phone))
    throw new Error(`${label}电话格式不正确。`)
  if (
    regionCodes.length !== 3 ||
    regionCodes.some((code) => !/^\d{6}$/.test(code))
  ) {
    throw new Error(`${label}地区须按省、市、区县顺序填写3个6位行政区划代码。`)
  }
  if (
    hasRegionNames &&
    (regionNames.length !== 3 || regionNames.some((name) => !name || name.length > 20))
  ) {
    throw new Error(`${label}地区名称须按省、市、区县顺序完整填写，每项最多20个字符。`)
  }
  if (!addressLine || addressLine.length > 200)
    throw new Error(`${label}详细地址须填写，最多200个字符。`)
  return {
    contactName,
    phone,
    regionCodes,
    regionNames: hasRegionNames ? regionNames : null,
    addressLine,
  }
}

function buildPayload() {
  if (!settings.value) throw new Error('请先读取当前配置。')
  const returnInstructionsChanged =
    form.returnInstructions.trim() !==
    (settings.value.returnInstructions || '').trim()
  if (
    !replaceDispatch.value &&
    !replaceReturn.value &&
    !returnInstructionsChanged
  ) {
    throw new Error('请配置或修改一个配送地址，或修改退货说明后再保存。')
  }
  const body = {
    expectedVersion: settings.value.version,
    settings: {
      version: settings.value.version,
      enabled: Boolean(settings.value.enabled),
      purchaseEnabled: Boolean(settings.value.purchaseEnabled),
      freightMode: settings.value.freightMode,
      freightCent: Number(settings.value.freightCent),
      defaultBlockedRegionCodes: settings.value.defaultBlockedRegionCodes || [],
      paymentMinutes: Number(settings.value.paymentMinutes),
      autoReceiveDays: Number(settings.value.autoReceiveDays),
      aftersaleDays: Number(settings.value.aftersaleDays),
      contactText: settings.value.contactText || '',
      dispatchAddressMasked: settings.value.dispatchAddressMasked || '',
      returnAddressMasked: settings.value.returnAddressMasked || '',
      returnInstructions: form.returnInstructions.trim(),
    },
  }
  if (replaceDispatch.value)
    body.dispatchAddress = normalizeAddress(form.dispatch, '发货')
  if (replaceReturn.value)
    body.returnAddress = normalizeAddress(form.returnAddress, '退货')
  return body
}

function applyResult(value) {
  if (value && typeof value.version === 'number') {
    const successMessage = replaceDispatch.value
      ? '发货地址已保存'
      : replaceReturn.value
        ? '退货地址已保存'
        : '退货说明已保存'
    setSettings(value)
    ElMessage.success(successMessage)
  }
}

async function save() {
  if (!canWrite.value || command.busy.value || command.pending.value) return
  let body
  try {
    body = buildPayload()
  } catch (failure) {
    ElMessage.warning(failure.message || '请检查设置内容。')
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
.eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
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
  gap: 15px;
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
.address-status-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.address-status-row {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 10px;
  min-height: 24px;
}
.warehouse-address-summary {
  display: grid;
  flex: 1 1 440px;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 10px 24px;
  margin: 0;
  color: var(--app-text-primary);
  font-size: 13px;
}
.warehouse-address-summary > div {
  display: flex;
  gap: 10px;
  min-width: 0;
}
.warehouse-address-summary__full {
  grid-column: 1 / -1;
}
.warehouse-address-summary dt {
  flex: none;
  color: var(--app-text-secondary);
}
.warehouse-address-summary dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}
.address-status-row .readonly-note {
  margin: 0;
}
.address-edit-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
}
.address-edit-actions > :deep(.el-input) {
  max-width: 360px;
  margin-right: auto;
}
.address-edit-buttons {
  display: flex;
  gap: 10px;
}
.address-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
.address-grid--regions {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.address-help,
.readonly-note {
  margin: 2px 0 0;
  color: var(--app-text-secondary);
  font-size: 12px;
}
.instructions-save-row {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.readonly-note {
  font-size: 13px;
}
@media (max-width: 680px) {
  .address-grid,
  .address-grid--regions {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .warehouse-address-summary {
    flex-basis: 100%;
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .warehouse-address-summary__full {
    grid-column: auto;
  }
  .address-edit-actions {
    align-items: stretch;
    flex-direction: column;
  }
  .address-edit-actions > :deep(.el-input) {
    max-width: none;
    width: 100%;
  }
  .address-edit-buttons {
    justify-content: flex-end;
  }
  .instructions-save-row {
    flex-wrap: wrap;
  }
}
</style>
