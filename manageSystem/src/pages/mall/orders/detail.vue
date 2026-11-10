<template>
  <section class="mall-page">
    <header>
      <h2>交易订单详情</h2>
      <el-button
        data-test="reload"
        :disabled="command.pending.value || loading"
        @click="load"
      >
        刷新订单
      </el-button>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="command.error.value"
      :title="command.error.value"
      type="error"
      :closable="false"
    />
    <el-button
      v-if="command.pending.value"
      :loading="command.busy.value"
      @click="retry"
    >
      重试原操作
    </el-button>
    <div v-loading="loading">
      <template v-if="order">
        <OrderFacts :order="order" />
        <el-card
          v-if="fulfillmentReleaseUiEnabled && auth.hasPermission('mall.fulfillment.release')"
          class="release-card"
          data-test="fulfillment-release-card"
        >
          <template #header>本单履约资料</template>
          <p>
            仅为当前已付款订单办理面单。资料只在本页临时显示，最长 60 秒；离开页面或切换标签后立即清除。请勿截图、复制或另存。
          </p>
          <el-button
            v-if="!fulfillmentReleased"
            data-test="release-fulfillment"
            type="primary"
            :disabled="!order.fulfillmentCheck.businessReady || fulfillmentReleaseBusy"
            :loading="fulfillmentReleaseBusy"
            @click="fulfillmentReleaseOpen = true"
          >
            查看本单收件资料
          </el-button>
          <el-alert
            v-if="fulfillmentReleased"
            type="warning"
            :closable="false"
            data-test="fulfillment-release-data"
          >
            <template #title>收件资料（{{ fulfillmentSecondsRemaining }} 秒后清除）</template>
            <dl class="released-fields">
              <div><dt>收件人</dt><dd>{{ fulfillmentReleased.recipientName }}</dd></div>
              <div><dt>联系电话</dt><dd>{{ fulfillmentReleased.phone }}</dd></div>
              <div><dt>收件地址</dt><dd>{{ fulfillmentReleased.addressLine }}</dd></div>
              <div><dt>访问审计号</dt><dd>{{ fulfillmentReleased.auditId }}</dd></div>
            </dl>
            <el-button data-test="clear-fulfillment-release" @click="fulfillmentData.clear()">
              立即清除
            </el-button>
          </el-alert>
        </el-card>
        <el-button
          v-if="order.invoiceRequestId && auth.hasPermission('mall.invoices.read')"
          data-test="open-invoice-request"
          @click="router.push(`/mall/invoices/${order.invoiceRequestId}`)"
        >
          查看发票办理
        </el-button>
        <el-form
          v-if="can('noteMallOrder')"
          label-position="top"
          :disabled="command.pending.value"
        >
          <el-form-item label="内部备注（仅后台可见）">
            <el-input
              v-model="noteText"
              type="textarea"
              maxlength="200"
              show-word-limit
              placeholder="仅填写订单办理事项，请勿填写联系方式或医疗资料"
            />
          </el-form-item>
          <el-button
            data-test="save-note"
            type="primary"
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
        <el-form
          v-if="can('shipMallOrder')"
          label-position="top"
          class="shipment-form"
          :disabled="command.pending.value"
        >
          <h3>登记已发货</h3>
          <p>仅记录本地发货事实；页面不展示收件人原文，也不会调用微信发货或快递100。</p>
          <el-form-item label="承运商编码">
            <el-input v-model="shipmentForm.courierCode" maxlength="32" />
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
          v-if="can('correctMallTracking')"
          label-position="top"
          class="shipment-form"
          :disabled="command.pending.value"
        >
          <h3>更正运单</h3>
          <el-form-item label="承运商编码">
            <el-input v-model="trackingForm.courierCode" maxlength="32" />
          </el-form-item>
          <el-form-item label="运单号">
            <el-input v-model="trackingForm.trackingNo" maxlength="64" />
          </el-form-item>
          <el-form-item label="更正原因">
            <el-input v-model="trackingForm.reason" maxlength="200" />
          </el-form-item>
          <el-button
            data-test="correct-tracking"
            :loading="command.busy.value"
            @click="correctTracking"
          >
            保存运单更正
          </el-button>
        </el-form>
        <el-card
          v-if="order.shipment"
          class="shipment-form"
          data-test="platform-shipment-report"
        >
          <template #header>微信平台发货登记</template>
          <p>
            请先在微信小程序后台手工录入本包裹的发货信息，再回本页确认。此处只记录员工确认，不调用微信发货 API，也不代表平台回执或确认收货。
          </p>
          <el-tag
            :type="order.shipment.platformReportStatus === 'manual_reported' ? 'success' : 'warning'"
            data-test="platform-report-status"
          >
            {{ platformReportLabels[order.shipment.platformReportStatus] || '登记状态待核实' }}
          </el-tag>
          <p v-if="order.shipment.platformReportedAt" data-test="platform-report-time">
            商城记录时间：{{ timeLabel(order.shipment.platformReportedAt) }}
          </p>
          <el-button
            v-if="can('recordMallPlatformShipmentReport')"
            data-test="confirm-platform-report"
            type="primary"
            :disabled="command.pending.value"
            @click="platformReportOpen = true"
          >
            确认已在微信后台登记
          </el-button>
        </el-card>
      </template>
      <el-empty v-else-if="!loading && !error" description="订单暂不可用" />
    </div>
    <el-alert
      v-if="receipt"
      :title="receiptLabel"
      :type="receipt.status === 'completed' ? 'success' : 'warning'"
      :closable="false"
    />
    <el-alert
      v-if="shipmentNotice"
      :title="shipmentNotice"
      type="success"
      :closable="false"
    />
    <el-button
      v-if="receipt && receipt.status !== 'completed'"
      :loading="checking"
      @click="checkProgress"
    >
      查询取消进度
    </el-button>
    <el-dialog
      v-model="cancelOpen"
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
    <el-dialog
      v-model="platformReportOpen"
      title="确认微信平台发货登记"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="!command.pending.value"
    >
      <p>
        请确认已在微信小程序后台为当前包裹完成发货信息录入。商城只保存员工声明、时间和包裹版本，不会代你提交到微信平台。
      </p>
      <template #footer>
        <el-button :disabled="command.pending.value" @click="platformReportOpen = false">
          返回
        </el-button>
        <el-button
          data-test="submit-platform-report"
          type="primary"
          :disabled="command.pending.value"
          :loading="command.busy.value"
          @click="recordPlatformReport"
        >
          确认已完成登记
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
import OrderFacts from './OrderFacts.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
const fulfillmentReleaseUiEnabled =
  import.meta.env.VITE_MALL_DATA_RELEASE_UI_ENABLED === 'true'
const order = ref(null),
  loading = ref(false),
  error = ref(''),
  noteText = ref('')
const cancelReason = ref(''),
  cancelOpen = ref(false),
  receipt = ref(null),
  checking = ref(false)
const shipmentForm = ref({ courierCode: '', trackingNo: '' })
const trackingForm = ref({ courierCode: '', trackingNo: '', reason: '' })
const shipmentNotice = ref('')
const platformReportOpen = ref(false)
const platformReportLabels = {
  pending: '待登记微信平台发货信息',
  manual_reported: '已记录员工确认',
  unknown: '历史登记状态待核实',
}
const command = useMallCommand()
const fulfillmentData = useExpiringSensitiveData((data) => ({
  recipientName: data.recipientName,
  phone: data.phone,
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
  const permission = [
    'shipMallOrder',
    'correctMallTracking',
    'recordMallPlatformShipmentReport',
  ].includes(action)
    ? 'mall.shipments.write'
    : 'mall.orders.write'
  return (
    auth.hasPermission(permission) &&
    order.value?.availableActions.includes(action)
  )
}
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
    shipmentNotice.value = '本地发货事实已登记；请继续完成微信后台手工登记并核验物流轨迹。'
    shipmentForm.value = { courierCode: '', trackingNo: '' }
  } else if (operation === 'tracking') {
    shipmentNotice.value = '运单已更正；历史出库未重复执行。'
    trackingForm.value = { courierCode: '', trackingNo: '', reason: '' }
  } else if (operation === 'platform-report') {
    shipmentNotice.value = '已记录本次包裹的微信后台人工登记确认。'
    platformReportOpen.value = false
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
    error.value = '请填写承运商编码和运单号'
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
async function correctTracking() {
  if (!can('correctMallTracking') || command.pending.value) return
  const courierCode = trackingForm.value.courierCode.trim().toLowerCase()
  const trackingNo = trackingForm.value.trackingNo.trim()
  const reason = trackingForm.value.reason.trim()
  if (!courierCode || !trackingNo || !reason) {
    error.value = '请填写承运商编码、运单号和更正原因'
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
async function recordPlatformReport() {
  if (
    !can('recordMallPlatformShipmentReport') ||
    command.pending.value ||
    !order.value?.shipment
  )
    return
  operation = 'platform-report'
  await after(
    await command.run(api.recordPlatformShipmentReport, {
      shipmentId: order.value.shipment.id,
      expectedVersion: order.value.shipment.version,
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
.mall-page {
  padding: 20px;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.el-form {
  margin: 24px 0;
  max-width: 680px;
}
.el-alert {
  margin: 12px 0;
}
.release-card {
  margin: 16px 0;
}
.released-fields {
  display: grid;
  gap: 8px;
  margin: 0 0 12px;
}
.released-fields div {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 12px;
}
.released-fields dt {
  color: #6b7280;
}
.released-fields dd {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
