<template>
  <div class="order-facts">
    <section class="facts-section">
      <h3 class="section-title">买家与订单信息</h3>
      <dl class="facts-grid">
        <div class="fact-pair">
          <dt>买家</dt>
          <dd>{{ order.buyer?.displayName }}（编号 {{ order.buyer?.id }}）</dd>
        </div>
        <div class="fact-pair">
          <dt>履约方式</dt>
          <dd>{{ order.deliveryMethod === 'virtual' ? '虚拟商品 · 后台人工交付' : '实物商品 · 快递发货' }}</dd>
        </div>
        <div v-if="order.address" class="fact-pair">
          <dt>地区编码</dt>
          <dd>{{ order.address.regionCodes.join(' / ') || '—' }}</dd>
        </div>
        <div v-if="order.address" class="fact-pair">
          <dt>收件信息</dt>
          <dd data-test="order-recipient-summary">
            {{ recipientSummary.name }} {{ recipientSummary.phone }} · {{ recipientSummary.address }}
          </dd>
        </div>
        <div class="fact-pair">
          <dt>买家备注</dt>
          <dd>{{ order.buyerNote || '未填写' }}</dd>
        </div>
        <div class="fact-pair">
          <dt>下单 / 到期</dt>
          <dd>{{ time(order.createdAt) }} / {{ time(order.expiresAt) }}</dd>
        </div>
        <div class="fact-pair">
          <dt>内部备注</dt>
          <dd>{{ order.internalNote || '未填写' }}</dd>
        </div>
        <div class="fact-pair">
          <dt>关闭时间</dt>
          <dd>{{ time(order.closedAt) }}</dd>
        </div>
        <div class="fact-pair">
          <dt>关闭原因</dt>
          <dd>{{ order.closeReason || '—' }}</dd>
        </div>
        <div class="fact-pair">
          <dt>支付单</dt>
          <dd>{{ order.paymentId || '尚无付款请求' }}</dd>
        </div>
        <div class="fact-pair">
          <dt>售后 / 发票申请</dt>
          <dd>{{ order.aftersaleIds.length ? order.aftersaleIds.join('、') : '尚无售后' }} / {{ order.invoiceRequestId || '尚无开票申请' }}</dd>
        </div>
      </dl>
    </section>

    <section class="facts-section">
      <h3 class="section-title">购买商品</h3>
      <el-table :data="order.items" class="ledger-table" row-key="id">
        <el-table-column prop="productName" label="商品" min-width="220" />
        <el-table-column prop="optionsText" label="规格" min-width="180">
          <template #default="{ row }">{{ row.optionsText || '默认规格' }}</template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" min-width="100" />
        <el-table-column label="单价" min-width="140">
          <template #default="{ row }">¥{{ money(row.unitPriceCent) }}</template>
        </el-table-column>
        <el-table-column label="小计" min-width="140" align="right">
          <template #default="{ row }">¥{{ money(row.lineAmountCent) }}</template>
        </el-table-column>
      </el-table>
    </section>

    <section class="facts-section">
      <h3 class="section-title">履约核对</h3>
      <dl class="fulfillment-grid">
        <div class="fulfillment-fact">
          <dt>付款状态</dt>
          <dd>{{ paymentStates[order.paymentStatus] || '待核实' }}</dd>
        </div>
        <div class="fulfillment-fact">
          <dt>订单状态</dt>
          <dd>{{ orderStatusLabel(order) }}</dd>
        </div>
        <div class="fulfillment-fact">
          <dt>商品数量</dt>
          <dd>{{ itemCount }}</dd>
        </div>
        <div v-if="order.address" class="fulfillment-fact recipient-information">
          <dt>收件信息</dt>
          <dd class="recipient-summary">
            <template v-if="plainRecipientVisible">
              <div class="recipient-detail-list" data-test="fulfillment-address-full">
                <span>收件人：{{ order.address.recipientName }}</span>
                <span>联系电话：{{ order.address.phone }}</span>
                <span>收件地址：{{ plainRecipientAddress }}</span>
              </div>
            </template>
            <template v-else-if="fulfillmentReleased">
              <div class="recipient-detail-list" data-test="fulfillment-release-data">
                <span>收件人：{{ fulfillmentReleased.recipientName }}</span>
                <span>联系电话：{{ fulfillmentReleased.phone }}</span>
                <span>收件地址：{{ fullRecipientAddress }}</span>
                <span class="release-expiry">资料仅用于本单履约，将于 {{ fulfillmentSecondsRemaining }} 秒后清除</span>
              </div>
              <el-button
                class="clear-recipient-data"
                data-test="clear-fulfillment-release"
                link
                type="primary"
                @click="$emit('clear-fulfillment-release')"
              >
                立即清除
              </el-button>
            </template>
            <template v-else>
              <span>{{ order.address.phoneMasked }} · {{ order.address.addressMasked }}</span>
              <el-button
                v-if="canRequestFulfillmentRelease"
                data-test="release-fulfillment"
                link
                type="primary"
                :disabled="!order.fulfillmentCheck.businessReady || fulfillmentReleaseBusy"
                :loading="fulfillmentReleaseBusy"
                @click="$emit('request-fulfillment-release')"
              >
                查看完整信息
              </el-button>
              <span
                v-if="canRequestFulfillmentRelease && !order.fulfillmentCheck.businessReady"
                class="release-hint"
              >
                当前订单尚未满足发货条件
              </span>
              <span v-else-if="fulfillmentReleaseUiEnabled" class="release-hint">
                当前账号没有履约资料查看权限
              </span>
              <span v-else class="release-hint">
                完整信息查看功能暂未启用
              </span>
            </template>
          </dd>
        </div>
        <div class="fulfillment-fact">
          <dt>订单金额</dt>
          <dd>¥{{ money(order.payableAmountCent) }}</dd>
        </div>
        <div class="fulfillment-fact fulfillment-status">
          <dt>{{ order.deliveryMethod === 'virtual' ? '交付条件' : '发货条件' }}</dt>
          <dd>
            <el-tag :type="fulfillmentStatus.type" effect="light">
              {{ fulfillmentStatus.label }}
            </el-tag>
          </dd>
        </div>
      </dl>
      <div class="shipment-summary">
        <span class="shipment-summary-label">{{ order.deliveryMethod === 'virtual' ? '交付记录' : '包裹记录' }}</span>
        <template v-if="order.shipment">
          <span>{{ courierName(order.shipment.courierCode) }} · {{ order.shipment.trackingNo }}</span>
          <span>出库 {{ time(order.shipment.shippedAt) }}</span>
          <span>自动收货 {{ time(order.shipment.autoReceiveAt) }}</span>
        </template>
        <template v-else-if="order.virtualDelivery">
          <span>商家手工交付</span>
          <span>交付时间 {{ time(order.virtualDelivery.deliveredAt) }}</span>
        </template>
        <span v-else class="muted">{{ order.deliveryMethod === 'virtual' ? '尚未交付' : '尚无发货记录' }}</span>
      </div>
      <OrderLogistics v-if="order.shipment" :key="`${order.id}:${order.shipment.id}:${order.shipment.version}`" :order-id="order.id" />
      <div v-if="order.virtualDelivery" class="virtual-delivery-content">
        <strong>买家可见的交付内容</strong>
        <pre>{{ order.virtualDelivery.content }}</pre>
      </div>
      <p v-if="order.deliveryMethod !== 'virtual'" class="fulfillment-note">
        发货操作只登记本地发货事实。
      </p>
    </section>

    <section class="facts-section timeline-section">
      <h3 class="section-title">处理时间线</h3>
      <div v-if="order.fulfillmentCheck.blockingReasons.length" class="timeline-warnings">
        <div
          v-for="reason in order.fulfillmentCheck.blockingReasons"
          :key="reason.code"
          class="timeline-warning"
        >
          <span class="warning-indicator" aria-hidden="true" />
          <span>{{ reason.message }}</span>
        </div>
      </div>
      <el-timeline v-if="order.timeline.length" class="order-timeline">
        <el-timeline-item
          v-for="event in order.timeline"
          :key="event.id"
          :timestamp="time(event.occurredAt)"
        >
          {{ event.label }} · {{ event.actorLabel }}
        </el-timeline-item>
      </el-timeline>
      <p v-else-if="!order.fulfillmentCheck.blockingReasons.length" class="muted empty-timeline">
        暂无办理记录
      </p>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { money, time, paymentStates, orderStatusLabel } from './order-view'
import { courierName } from './couriers'
import OrderLogistics from './OrderLogistics.vue'

const props = defineProps({
  order: { type: Object, required: true },
  fulfillmentReleased: { type: Object, default: null },
  fulfillmentSecondsRemaining: { type: Number, default: 0 },
  fulfillmentReleaseBusy: { type: Boolean, default: false },
  fulfillmentReleaseUiEnabled: { type: Boolean, default: false },
  canRequestFulfillmentRelease: { type: Boolean, default: false },
})
defineEmits(['request-fulfillment-release', 'clear-fulfillment-release'])
const itemCount = computed(() =>
  props.order.items.reduce((total, item) => total + item.quantity, 0)
)
const fullRecipientAddress = computed(() => {
  if (!props.fulfillmentReleased) return ''
  const regionNames = Array.isArray(props.fulfillmentReleased.regionNames)
    ? props.fulfillmentReleased.regionNames
    : []
  return [...regionNames, props.fulfillmentReleased.addressLine]
    .filter(Boolean)
    .join('')
})
const plainRecipientVisible = computed(() => Boolean(props.order.address?.phone))
const fulfillmentStatus = computed(() => {
  if (props.order.shipment) return { label: '已发货', type: 'success' }
  if (props.order.virtualDelivery) return { label: '已交付', type: 'success' }
  return props.order.fulfillmentCheck.businessReady
    ? { label: '业务条件已满足', type: 'success' }
    : { label: '需要核对', type: 'warning' }
})
const plainRecipientAddress = computed(() => {
  const address = props.order.address
  if (!address?.phone) return ''
  const regionNames = Array.isArray(address.regionNames) ? address.regionNames : []
  return [...regionNames, address.addressLine].filter(Boolean).join('')
})
const recipientSummary = computed(() => {
  const address = props.order.address
  if (!address) return { name: '', phone: '', address: '' }
  if (plainRecipientVisible.value) {
    return {
      name: address.recipientName,
      phone: address.phone,
      address: plainRecipientAddress.value,
    }
  }
  if (props.fulfillmentReleased) {
    return {
      name: props.fulfillmentReleased.recipientName,
      phone: props.fulfillmentReleased.phone,
      address: fullRecipientAddress.value,
    }
  }
  return {
    name: address.recipientName,
    phone: address.phoneMasked,
    address: address.addressMasked,
  }
})
</script>

<style scoped>
.virtual-delivery-content {
  margin-top: 16px;
  padding: 16px 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.virtual-delivery-content strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.virtual-delivery-content pre {
  margin: 10px 0 0;
  color: var(--el-text-color-regular);
  font: inherit;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
