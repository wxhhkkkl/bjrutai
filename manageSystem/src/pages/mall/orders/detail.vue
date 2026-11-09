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
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-orders'
import { useMallCommand } from '@/composables/useMallCommand'
import OrderFacts from './OrderFacts.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
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
const command = useMallCommand()
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
async function load() {
  if (command.pending.value) return
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
    shipmentNotice.value = '本地发货事实已登记；微信平台同步和物流轨迹查询尚未启用。'
    shipmentForm.value = { courierCode: '', trackingNo: '' }
  } else if (operation === 'tracking') {
    shipmentNotice.value = '运单已更正；历史出库未重复执行。'
    trackingForm.value = { courierCode: '', trackingNo: '', reason: '' }
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
    receipt.value = null
    shipmentNotice.value = ''
    shipmentForm.value = { courierCode: '', trackingNo: '' }
    trackingForm.value = { courierCode: '', trackingNo: '', reason: '' }
    cancelOpen.value = false
    cancelReason.value = ''
    load()
  }
)
onMounted(load)
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
</style>
