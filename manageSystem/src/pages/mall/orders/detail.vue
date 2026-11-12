<template>
  <section class="mall-page mall-management-page order-detail-page">
    <el-button
      v-if="command.pending.value"
      class="retry-command"
      :loading="command.busy.value"
      @click="retry"
    >
      重试原操作
    </el-button>
    <div v-loading="loading" class="order-detail-content">
      <template v-if="order">
        <div class="order-navigation">
          <el-button type="primary" link @click="router.push('/mall/orders')">
            <el-icon><ArrowLeft /></el-icon>
            返回订单列表
          </el-button>
          <span class="navigation-divider" aria-hidden="true" />
          <h1>订单台账</h1>
        </div>

        <main class="order-ledger">
          <section class="ledger-overview">
            <div class="ledger-identity">
              <div class="order-number-line">
                <span class="order-number-label">订单号</span>
                <strong class="order-number">{{ order.orderNo }}</strong>
                <el-tag :type="orderStatusType(order.status)" effect="light">
                  {{ orderStatusLabel(order) }}
                </el-tag>
                <el-tag :type="paymentStatusType(order.paymentStatus)" effect="light">
                  {{ paymentStates[order.paymentStatus] || '待核实' }}
                </el-tag>
              </div>
              <p class="order-created">下单时间：{{ timeLabel(order.createdAt) }}</p>
            </div>
            <div class="ledger-actions">
              <el-form
                v-if="can('noteMallOrder')"
                class="note-form"
                :disabled="command.pending.value"
                @submit.prevent="save"
              >
                <el-form-item>
                  <el-input
                    v-model="noteText"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 3 }"
                    maxlength="200"
                    show-word-limit
                    placeholder="请输入内部备注（选填）"
                  />
                </el-form-item>
                <el-button
                  data-test="save-note"
                  type="primary"
                  plain
                  :loading="command.busy.value"
                  @click="save"
                >
                  保存备注
                </el-button>
              </el-form>
              <el-button
                v-if="can('cancelAdminMallOrder')"
                data-test="cancel-order"
                type="danger"
                plain
                :disabled="command.pending.value"
                @click="cancelOpen = true"
              >
                申请取消订单
              </el-button>
            </div>
          </section>

          <section class="amount-strip" aria-label="订单金额汇总">
            <div class="amount-summary amount-total">
              <span>订单金额</span>
              <strong>¥{{ money(order.payableAmountCent) }}</strong>
            </div>
            <div class="amount-summary">
              <span>应付</span>
              <strong>¥{{ money(order.payableAmountCent) }}</strong>
            </div>
            <div class="amount-summary">
              <span>实收 / 净收</span>
              <strong>¥{{ money(order.paidAmountCent) }} / ¥{{ money(order.netReceivedCent) }}</strong>
            </div>
            <div class="amount-summary">
              <span>退款处理中占用</span>
              <strong>¥{{ money(order.refundReservedCent) }}</strong>
            </div>
            <div class="amount-summary">
              <span>商品 / 运费</span>
              <strong>¥{{ money(order.goodsAmountCent) }} / ¥{{ money(order.freightAmountCent) }}</strong>
            </div>
          </section>

          <OrderFacts
            :order="order"
            :fulfillment-released="fulfillmentReleased"
            :fulfillment-seconds-remaining="fulfillmentSecondsRemaining"
            :fulfillment-release-busy="fulfillmentReleaseBusy"
            :fulfillment-release-ui-enabled="fulfillmentReleaseUiEnabled"
            :can-request-fulfillment-release="canRequestFulfillmentRelease"
            @request-fulfillment-release="fulfillmentReleaseOpen = true"
            @clear-fulfillment-release="fulfillmentData.clear()"
          />
        </main>

        <section
          v-if="hasOrderOperations"
          class="order-operations"
        >
          <header class="operations-heading">
            <div>
              <h2>订单操作</h2>
              <p>根据当前订单状态和账号权限显示可办理事项。</p>
            </div>
            <el-button
              v-if="order.invoiceRequestId && auth.hasPermission('mall.invoices.read')"
              data-test="open-invoice-request"
              @click="router.push(`/mall/invoices/${order.invoiceRequestId}`)"
            >
              查看发票办理
            </el-button>
          </header>

          <div class="operation-grid">
            <el-form
              v-if="can('shipMallOrder')"
              label-position="top"
              class="operation-panel shipment-form"
              :disabled="command.pending.value"
          >
              <h3 class="operation-title">登记已发货</h3>
              <p class="operation-description">仅记录本地发货事实；收件资料需在履约核对中单独授权查看。</p>
              <el-form-item label="快递服务商">
                <el-select
                  v-model="shipmentForm.courierCode"
                  data-test="shipment-courier"
                  filterable
                  clearable
                  placeholder="请选择快递服务商"
                  style="width: 100%"
                >
                  <el-option
                    v-for="courier in courierOptions"
                    :key="courier.code"
                    :label="courier.name"
                    :value="courier.code"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="运单号">
                <el-input v-model="shipmentForm.trackingNo" maxlength="64" />
              </el-form-item>
              <el-button
                data-test="ship-order"
                type="primary"
                :loading="command.busy.value"
                @click="registerShipment"
              >
                确认登记已发货
              </el-button>
            </el-form>
            <el-form
              v-if="can('deliverVirtualMallOrder')"
              label-position="top"
              class="operation-panel virtual-delivery-form"
              :disabled="command.pending.value"
              @submit.prevent="deliverVirtual"
            >
              <h3 class="operation-title">手工交付虚拟商品</h3>
              <p class="operation-description">提交后订单会完成，交付内容将立即对该订单买家可见。</p>
              <el-form-item label="交付内容" required>
                <el-input
                  v-model="virtualDeliveryContent"
                  type="textarea"
                  :rows="6"
                  maxlength="5000"
                  show-word-limit
                  placeholder="填写兑换码、下载方式或其他本单交付内容"
                />
              </el-form-item>
              <el-button
                data-test="deliver-virtual-order"
                type="primary"
                :loading="command.busy.value"
                @click="deliverVirtual"
              >
                确认交付并完成订单
              </el-button>
            </el-form>
            <el-form
              v-if="can('correctMallTracking')"
              label-position="top"
              class="operation-panel shipment-form"
              :disabled="command.pending.value"
          >
              <h3 class="operation-title">更正运单</h3>
              <div class="tracking-fields">
                <el-form-item label="快递服务商">
                  <el-select
                    v-model="trackingForm.courierCode"
                    data-test="tracking-courier"
                    filterable
                    clearable
                    placeholder="请选择快递服务商"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="courier in courierOptions"
                      :key="courier.code"
                      :label="courier.name"
                      :value="courier.code"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="运单号">
                  <el-input v-model="trackingForm.trackingNo" maxlength="64" />
                </el-form-item>
                <el-form-item label="更正原因">
                  <el-input v-model="trackingForm.reason" maxlength="200" />
                </el-form-item>
              </div>
              <el-button
                data-test="correct-tracking"
                class="tracking-submit"
                :loading="command.busy.value"
                @click="correctTracking"
              >
                保存运单更正
              </el-button>
            </el-form>
          </div>
        </section>
      </template>
      <el-empty v-else-if="!loading && !error" description="订单暂不可用" />
    </div>
    <section v-if="receipt" class="command-receipt">
      <el-alert
        :title="receiptLabel"
        :type="receipt.status === 'completed' ? 'success' : 'warning'"
        :closable="false"
      />
      <el-button
        v-if="receipt.status !== 'completed'"
        :loading="checking"
        @click="checkProgress"
      >
        查询取消进度
      </el-button>
    </section>
    <el-dialog
      v-model="cancelOpen"
      class="mall-management-overlay"
      title="申请取消订单"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="!command.pending.value"
    >
      <p>
        有付款请求的订单会先核实关闭，确认后释放库存。已收款的订单需人工核实或办理售后。
      </p>
      <el-input
        v-model="cancelReason"
        type="textarea"
        maxlength="500"
        placeholder="请填写取消原因"
        :disabled="command.pending.value"
      />
      <template #footer>
        <el-button
          :disabled="command.pending.value"
          @click="cancelOpen = false"
        >
          返回
        </el-button><el-button
          type="danger"
          :disabled="command.pending.value"
          @click="cancel"
        >
          提交取消申请
        </el-button>
      </template>
    </el-dialog>
    <el-dialog
      v-model="fulfillmentReleaseOpen"
      class="mall-management-overlay"
      title="确认查看本单履约资料"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="!fulfillmentReleaseBusy"
    >
      <p>
        仅为当前订单办理面单。后端会重新核验订单、权限和用途同意；成功后资料仅在本页临时显示 60 秒。
      </p>
      <template #footer>
        <el-button :disabled="fulfillmentReleaseBusy" @click="fulfillmentReleaseOpen = false">
          返回
        </el-button>
        <el-button
          data-test="confirm-fulfillment-release"
          type="primary"
          :loading="fulfillmentReleaseBusy"
          @click="releaseFulfillmentData"
        >
          确认并查看
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-orders'
import { commandKey, useMallCommand } from '@/composables/useMallCommand'
import { useExpiringSensitiveData } from '@/composables/useExpiringSensitiveData'
import { useMallToast } from '@/composables/useMallToast'
import { ArrowLeft } from '@element-plus/icons-vue'
import { money, paymentStates, orderStatusType, orderStatusLabel } from './order-view'
import { courierOptions } from './couriers'
import OrderFacts from './OrderFacts.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
const fulfillmentReleaseUiEnabled =
  import.meta.env.VITE_MALL_DATA_RELEASE_UI_ENABLED === 'true'
const canRequestFulfillmentRelease = computed(
  () =>
    fulfillmentReleaseUiEnabled &&
    auth.hasPermission('mall.fulfillment.release')
)
const order = ref(null),
  loading = ref(false),
  error = ref(''),
  noteText = ref('')
useMallToast(error)
const cancelReason = ref(''),
  cancelOpen = ref(false),
  receipt = ref(null),
  checking = ref(false)
const shipmentForm = ref({ courierCode: '', trackingNo: '' })
const trackingForm = ref({ courierCode: '', trackingNo: '', reason: '' })
const virtualDeliveryContent = ref('')
const shipmentNotice = ref('')
useMallToast(shipmentNotice, 'success')
const command = useMallCommand()
const fulfillmentData = useExpiringSensitiveData((data) => ({
  recipientName: data.recipientName,
  phone: data.phone,
  regionNames: data.regionNames,
  addressLine: data.addressLine,
  auditId: data.auditId,
}))
const fulfillmentReleased = fulfillmentData.value
const fulfillmentSecondsRemaining = fulfillmentData.secondsRemaining
const fulfillmentReleaseOpen = ref(false)
const fulfillmentReleaseBusy = ref(false)
let operation = null
let loadGeneration = 0
const receiptLabel = computed(
  () =>
    ({
      pending: '关闭确认中，库存暂未释放',
      running: '关闭确认中，库存暂未释放',
      manual: '取消申请需人工处理，请先核实收款情况',
      completed: '订单已确认关闭',
    })[receipt.value?.status] || '进度待核实'
)
function can(action) {
  const permission = ['shipMallOrder', 'correctMallTracking'].includes(action)
    ? 'mall.shipments.write'
    : 'mall.orders.write'
  return (
    auth.hasPermission(permission) &&
    order.value?.availableActions.includes(action)
  )
}
const hasOrderOperations = computed(
  () =>
    !!order.value &&
    ((order.value.invoiceRequestId &&
        auth.hasPermission('mall.invoices.read')) ||
      can('shipMallOrder') ||
      can('deliverVirtualMallOrder') ||
      can('correctMallTracking') ||
      !!order.value.shipment)
)
function timeLabel(value) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) return '时间待核实'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
function paymentStatusType(status) {
  return {
    not_started: 'info',
    creating: 'primary',
    pending: 'warning',
    unknown: 'warning',
    succeeded: 'success',
    closed: 'info',
    failed: 'danger',
  }[status] || 'info'
}
async function load() {
  if (command.pending.value) return
  fulfillmentData.clear()
  const generation = ++loadGeneration,
    identity = props.id
  loading.value = true
  error.value = ''
  order.value = null
  try {
    const result = await api.getOrder(identity)
    if (generation === loadGeneration && props.id === identity) {
      order.value = result
      noteText.value = result.internalNote || ''
    }
  } catch (failure) {
    if (generation === loadGeneration)
      error.value = failure.userMessage || failure.message || '订单读取失败'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}
async function after(result) {
  if (!result) return
  if (operation === 'cancel') {
    receipt.value = result
    cancelOpen.value = false
  } else if (operation === 'ship') {
    shipmentNotice.value = '本地发货事实已登记。'
    shipmentForm.value = { courierCode: '', trackingNo: '' }
  } else if (operation === 'tracking') {
    shipmentNotice.value = '运单已更正；历史出库未重复执行。'
    trackingForm.value = { courierCode: '', trackingNo: '', reason: '' }
  } else if (operation === 'virtual-delivery') {
    shipmentNotice.value = '虚拟商品已交付完成，买家可在订单详情查看内容。'
    virtualDeliveryContent.value = ''
  }
  await load()
}
async function save() {
  if (!can('noteMallOrder') || command.pending.value) return
  operation = 'note'
  await after(
    await command.run(api.saveNote, {
      id: props.id,
      expectedVersion: order.value.version,
      internalNote: noteText.value,
    })
  )
}
async function cancel() {
  if (!can('cancelAdminMallOrder') || command.pending.value) return
  if (!cancelReason.value.trim()) {
    error.value = '请填写取消原因'
    return
  }
  operation = 'cancel'
  await after(
    await command.run(api.cancelOrder, {
      id: props.id,
      expectedVersion: order.value.version,
      reason: cancelReason.value.trim(),
    })
  )
}
async function registerShipment() {
  if (!can('shipMallOrder') || command.pending.value) return
  const courierCode = shipmentForm.value.courierCode.trim().toLowerCase()
  const trackingNo = shipmentForm.value.trackingNo.trim()
  if (!courierCode || !trackingNo) {
    error.value = '请选择快递服务商并填写运单号'
    return
  }
  operation = 'ship'
  await after(
    await command.run(api.registerShipment, {
      id: props.id,
      expectedVersion: order.value.version,
      courierCode,
      trackingNo,
    })
  )
}
async function deliverVirtual() {
  const content = virtualDeliveryContent.value.trim()
  if (!can('deliverVirtualMallOrder') || command.pending.value) return
  if (!content) {
    error.value = '请填写交付内容'
    return
  }
  operation = 'virtual-delivery'
  await after(
    await command.run(api.deliverVirtualOrder, {
      id: props.id,
      expectedVersion: order.value.version,
      deliveryContent: content,
    })
  )
}
async function correctTracking() {
  if (!can('correctMallTracking') || command.pending.value) return
  const courierCode = trackingForm.value.courierCode.trim().toLowerCase()
  const trackingNo = trackingForm.value.trackingNo.trim()
  const reason = trackingForm.value.reason.trim()
  if (!courierCode || !trackingNo || !reason) {
    error.value = '请选择快递服务商、填写运单号和更正原因'
    return
  }
  operation = 'tracking'
  await after(
    await command.run(api.correctTracking, {
      shipmentId: order.value.shipment.id,
      expectedVersion: order.value.version,
      shipmentVersion: order.value.shipment.version,
      courierCode,
      trackingNo,
      reason,
    })
  )
}
async function releaseFulfillmentData() {
  if (
    !fulfillmentReleaseUiEnabled ||
    !auth.hasPermission('mall.fulfillment.release') ||
    !order.value?.fulfillmentCheck?.businessReady ||
    fulfillmentReleaseBusy.value
  )
    return
  const identity = props.id
  const generation = fulfillmentData.beginRequest()
  fulfillmentReleaseBusy.value = true
  error.value = ''
  try {
    const result = await api.releaseFulfillment(
      {
        id: identity,
        expectedVersion: order.value.version,
        purpose: 'shipping_label',
        reason: '为当前订单办理面单',
      },
      commandKey()
    )
    if (
      fulfillmentData.isCurrent(generation) &&
      props.id === identity &&
      document.visibilityState !== 'hidden'
    ) {
      if (!fulfillmentData.show(result, generation)) {
        error.value = '资料响应已过期或无效，请重新核实订单后再试。'
      } else {
        fulfillmentReleaseOpen.value = false
      }
    }
  } catch {
    if (fulfillmentData.isCurrent(generation)) {
      error.value = '暂无法读取本单资料，请核实授权、订单状态和用途告知配置。'
    }
  } finally {
    fulfillmentReleaseBusy.value = false
  }
}
async function retry() {
  await after(await command.retry())
}
async function checkProgress() {
  if (!receipt.value || checking.value || command.pending.value) return
  checking.value = true
  const identity = props.id,
    commandId = receipt.value.commandId
  try {
    const result = await api.getCommand(commandId)
    if (props.id === identity && receipt.value?.commandId === commandId) {
      receipt.value = result
      await load()
    }
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '进度读取失败'
  } finally {
    checking.value = false
  }
}
function guard() {
  fulfillmentData.clear()
  fulfillmentReleaseOpen.value = false
  if (fulfillmentReleaseBusy.value) {
    error.value = '安全读取正在完成，请稍后离开本页'
    return false
  }
  if (command.pending.value) {
    error.value = '操作结果待确认，请先重试原操作'
    return false
  }
  return true
}
onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)
watch(
  () => props.id,
  () => {
    fulfillmentData.clear()
    fulfillmentReleaseOpen.value = false
    receipt.value = null
    shipmentNotice.value = ''
    shipmentForm.value = { courierCode: '', trackingNo: '' }
    trackingForm.value = { courierCode: '', trackingNo: '', reason: '' }
    cancelOpen.value = false
    cancelReason.value = ''
    load()
  }
)
function onVisibilityChange() {
  if (document.visibilityState === 'hidden') {
    fulfillmentData.clear()
    fulfillmentReleaseOpen.value = false
  }
}
onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  load()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  fulfillmentData.clear()
})
</script>
<style scoped>
.order-detail-page > .order-detail-content,
.order-detail-page > .retry-command,
.order-detail-page > .command-receipt {
  width: 100%;
  max-width: 1480px;
  justify-self: center;
}

.retry-command {
  justify-self: start;
  margin-top: -6px;
}

.order-detail-content {
  display: grid;
  min-width: 0;
  gap: 12px;
}

.order-navigation {
  display: flex;
  min-height: 34px;
  align-items: center;
  gap: 14px;
}

.order-navigation :deep(.el-button) {
  font-size: 14px;
  font-weight: 600;
}

.navigation-divider {
  width: 1px;
  height: 20px;
  background: var(--app-border-color);
}

.order-navigation h1 {
  margin: 0;
  color: var(--app-text-primary);
  font-size: 22px;
  font-weight: 700;
  line-height: 1.35;
}

.order-ledger {
  display: grid;
  min-width: 0;
  gap: 22px;
  padding: 18px 20px 22px;
  background: var(--app-bg-card);
  border: 1px solid var(--app-border-color);
  border-radius: var(--app-radius-lg);
  box-shadow: var(--app-shadow-sm);
}

.ledger-overview {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 22px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--app-border-color);
}

.ledger-identity {
  min-width: 0;
}

.order-number-line {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.order-number-label {
  color: var(--app-text-regular);
  font-size: 16px;
  font-weight: 600;
}

.order-number {
  max-width: min(460px, 100%);
  color: #111827;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
}

.order-created {
  margin: 7px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.ledger-actions {
  display: flex;
  min-width: 0;
  flex: 0 1 720px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 9px;
}

.note-form {
  display: flex;
  min-width: 240px;
  flex: 1 1 390px;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
}

.note-form .el-form-item {
  min-width: 0;
  flex: 1;
  margin: 0;
}

.note-form :deep(.el-form-item__content) {
  min-width: 0;
}

.note-form :deep(.el-textarea__inner) {
  min-height: 38px !important;
  padding-top: 8px;
  padding-bottom: 8px;
  resize: vertical;
}

.note-form :deep(.el-input__count) {
  line-height: 1.2;
}

.amount-strip {
  display: grid;
  min-width: 0;
  grid-template-columns: 1fr 1fr 1.35fr 1.3fr 1.35fr;
  align-items: stretch;
  overflow: hidden;
  background: #eff4fd;
  border: 1px solid #e2eaf8;
  border-radius: var(--app-radius-md);
}

.amount-summary {
  display: grid;
  min-width: 0;
  align-content: center;
  gap: 5px;
  padding: 11px 14px;
  border-right: 1px solid #cbd8ec;
}

.amount-summary:last-child {
  border-right: 0;
}

.amount-summary > span {
  color: var(--app-text-regular);
  font-size: 13px;
  line-height: 1.4;
}

.amount-summary > strong {
  color: var(--app-text-primary);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.45;
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
}

.amount-summary.amount-total > strong {
  color: var(--el-color-primary);
  font-size: 22px;
  font-weight: 750;
}

.order-operations {
  display: grid;
  min-width: 0;
  gap: 12px;
}

.operations-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.operations-heading h2 {
  margin: 0;
  color: var(--app-text-primary);
  font-size: 18px;
  font-weight: 650;
}

.operations-heading p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.operation-grid {
  display: grid;
  min-width: 0;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr));
  align-items: start;
  gap: 12px;
}

.operation-panel {
  min-width: 0;
  max-width: none;
  padding: 16px;
  margin: 0;
  background: var(--app-bg-card);
  border: 1px solid var(--app-border-color);
  border-radius: var(--app-radius-lg);
}

.operation-title {
  margin: 0 0 10px;
  color: var(--app-text-primary);
  font-size: 16px;
  font-weight: 650;
}

.operation-description {
  margin: 0 0 14px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.operation-panel .el-form-item {
  margin-bottom: 14px;
}

.tracking-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0 16px;
}

.tracking-fields .el-form-item {
  min-width: 0;
}

.tracking-submit {
  margin-top: 2px;
}

.command-receipt {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

@media (max-width: 1280px) {
  .ledger-overview {
    align-items: flex-start;
    flex-direction: column;
  }

  .ledger-actions {
    width: 100%;
    flex: 1 1 auto;
    justify-content: flex-start;
  }

  .note-form {
    flex: 1 1 460px;
  }

  .amount-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .amount-summary:nth-child(3) {
    border-right: 0;
  }

  .amount-summary:nth-child(n + 4) {
    border-top: 1px solid #cbd8ec;
  }
}

@media (max-width: 780px) {
  .order-ledger {
    gap: 18px;
    padding: 14px 12px 16px;
  }

  .order-number {
    font-size: 17px;
  }

  .amount-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .amount-summary:nth-child(odd) {
    border-right: 1px solid #cbd8ec;
  }

  .amount-summary:nth-child(even) {
    border-right: 0;
  }

  .amount-summary:nth-child(n + 3) {
    border-top: 1px solid #cbd8ec;
  }

  .operation-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .tracking-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 520px) {
  .order-navigation h1 {
    font-size: 19px;
  }

  .ledger-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .note-form {
    min-width: 0;
    flex-basis: auto;
  }

  .operations-heading {
    align-items: flex-start;
  }

  .amount-summary {
    padding: 10px;
  }

  .amount-summary > strong {
    font-size: 14px;
  }

  .amount-summary.amount-total > strong {
    font-size: 19px;
  }
}

.order-detail-page :deep(.order-facts) {
  display: grid;
  gap: 22px;
}

.order-detail-page :deep(.facts-section) {
  min-width: 0;
  padding-top: 2px;
}

.order-detail-page :deep(.section-title) {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 14px;
  color: var(--app-text-primary);
  font-size: 18px;
  font-weight: 650;
  line-height: 1.4;
}

.order-detail-page :deep(.section-title::before) {
  width: 4px;
  height: 20px;
  flex: none;
  border-radius: 3px;
  background: var(--el-color-primary);
  content: '';
}

.order-detail-page :deep(.facts-grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  border-top: 1px solid var(--app-border-color);
  border-left: 1px solid var(--app-border-color);
}

.order-detail-page :deep(.fact-pair) {
  display: grid;
  grid-template-columns: minmax(118px, 27%) minmax(0, 1fr);
  min-width: 0;
  min-height: 42px;
  border-right: 1px solid var(--app-border-color);
  border-bottom: 1px solid var(--app-border-color);
}

.order-detail-page :deep(.fact-pair dt),
.order-detail-page :deep(.fact-pair dd) {
  display: flex;
  min-width: 0;
  align-items: center;
  padding: 9px 13px;
  font-size: 14px;
  line-height: 1.5;
}

.order-detail-page :deep(.fact-pair dt) {
  color: var(--app-text-regular);
  background: #f6f8fb;
  font-weight: 600;
}

.order-detail-page :deep(.fact-pair dd) {
  margin: 0;
  color: var(--app-text-primary);
  overflow-wrap: anywhere;
}

.order-detail-page :deep(.ledger-table) {
  width: 100%;
}

.order-detail-page :deep(.ledger-table .el-table__header th) {
  height: 42px;
  background: #f1f5fd;
  color: var(--app-text-regular);
  font-weight: 650;
}

.order-detail-page :deep(.ledger-table .el-table__cell) {
  padding: 10px 0;
}

.order-detail-page :deep(.fulfillment-grid) {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0;
  border-top: 1px solid var(--app-border-color);
  border-left: 1px solid var(--app-border-color);
}

.order-detail-page :deep(.fulfillment-fact) {
  display: grid;
  grid-template-columns: minmax(102px, 31%) minmax(0, 1fr);
  min-width: 0;
  min-height: 46px;
  border-right: 1px solid var(--app-border-color);
  border-bottom: 1px solid var(--app-border-color);
}

.order-detail-page :deep(.fulfillment-fact dt),
.order-detail-page :deep(.fulfillment-fact dd) {
  display: flex;
  min-width: 0;
  align-items: center;
  padding: 9px 12px;
  font-size: 14px;
  line-height: 1.45;
}

.order-detail-page :deep(.fulfillment-fact dt) {
  color: var(--app-text-regular);
  background: #f6f8fb;
  font-weight: 600;
}

.order-detail-page :deep(.fulfillment-fact dd) {
  margin: 0;
  color: var(--app-text-primary);
  overflow-wrap: anywhere;
}

.order-detail-page :deep(.recipient-information) {
  grid-column: 1 / -1;
  grid-template-columns: minmax(102px, 150px) minmax(0, 1fr);
}

.order-detail-page :deep(.recipient-information dt) {
  align-items: flex-start;
  padding-top: 12px;
}

.order-detail-page :deep(.recipient-summary) {
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.order-detail-page :deep(.recipient-detail-list) {
  display: grid;
  min-width: 0;
  flex: 1;
  align-content: center;
  gap: 4px;
  line-height: 1.5;
}

.order-detail-page :deep(.release-expiry),
.order-detail-page :deep(.release-hint) {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.order-detail-page :deep(.clear-recipient-data) {
  flex: none;
  align-self: flex-start;
}

.order-detail-page :deep(.fulfillment-status .el-tag) {
  font-weight: 600;
}

.order-detail-page :deep(.shipment-summary) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
  padding: 12px 14px;
  margin-top: 12px;
  color: var(--app-text-regular);
  background: #f7f9fc;
  border: 1px solid var(--app-border-color);
  border-radius: var(--app-radius-sm);
  font-size: 13px;
}

.order-detail-page :deep(.shipment-summary-label) {
  color: var(--app-text-primary);
  font-weight: 650;
}

.order-detail-page :deep(.fulfillment-note),
.order-detail-page :deep(.muted) {
  margin: 10px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.order-detail-page :deep(.timeline-warnings) {
  display: grid;
  gap: 7px;
  margin-bottom: 18px;
}

.order-detail-page :deep(.timeline-warning) {
  display: flex;
  min-height: 38px;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  color: #b45309;
  background: #fff7e9;
  border: 1px solid #f7e5c6;
  border-radius: var(--app-radius-sm);
  font-size: 14px;
}

.order-detail-page :deep(.warning-indicator) {
  width: 9px;
  height: 9px;
  flex: none;
  border: 2px solid #f59e0b;
  border-radius: 50%;
}

.order-detail-page :deep(.order-timeline) {
  padding: 4px 2px 0;
}

.order-detail-page :deep(.empty-timeline) {
  padding: 14px 0 0;
}

@media (max-width: 1000px) {
  .order-detail-page :deep(.fulfillment-grid) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .order-detail-page :deep(.facts-grid),
  .order-detail-page :deep(.fulfillment-grid) {
    grid-template-columns: minmax(0, 1fr);
  }

  .order-detail-page :deep(.fact-pair),
  .order-detail-page :deep(.fulfillment-fact) {
    grid-template-columns: 118px minmax(0, 1fr);
  }
}
</style>
