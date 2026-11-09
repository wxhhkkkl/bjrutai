<template>
  <el-descriptions :column="2" border>
    <el-descriptions-item label="订单号">
      {{
        order.orderNo
      }}
    </el-descriptions-item>
    <el-descriptions-item label="状态">
      {{ orderStates[order.status] || '待核实' }} /
      {{ paymentStates[order.paymentStatus] || '待核实' }}
    </el-descriptions-item>
    <el-descriptions-item label="买家">
      {{ order.buyer?.displayName }}（编号
      {{ order.buyer?.id }}）
    </el-descriptions-item>
    <el-descriptions-item label="应付">
      ¥{{ money(order.payableAmountCent) }}
    </el-descriptions-item>
    <el-descriptions-item label="商品 / 运费">
      ¥{{ money(order.goodsAmountCent) }} / ¥{{
        money(order.freightAmountCent)
      }}
    </el-descriptions-item>
    <el-descriptions-item label="实收 / 净收">
      ¥{{ money(order.paidAmountCent) }} / ¥{{
        money(order.netReceivedCent)
      }}
    </el-descriptions-item>
    <el-descriptions-item label="商品退款 / 运费退款">
      ¥{{ money(order.refundedGoodsCent) }} / ¥{{
        money(order.refundedFreightCent)
      }}
    </el-descriptions-item>
    <el-descriptions-item label="退款处理中占用">
      ¥{{ money(order.refundReservedCent) }}
    </el-descriptions-item>
    <el-descriptions-item label="收件信息">
      {{ order.address.recipientName }} {{ order.address.phoneMasked }} ·
      {{ order.address.addressMasked }}
    </el-descriptions-item>
    <el-descriptions-item label="地区编码">
      {{
        order.address.regionCodes.join(' / ')
      }}
    </el-descriptions-item>
    <el-descriptions-item label="买家备注">
      {{
        order.buyerNote || '未填写'
      }}
    </el-descriptions-item>
    <el-descriptions-item label="内部备注">
      {{
        order.internalNote || '未填写'
      }}
    </el-descriptions-item>
    <el-descriptions-item label="下单 / 到期">
      {{ time(order.createdAt) }} /
      {{ time(order.expiresAt) }}
    </el-descriptions-item>
    <el-descriptions-item label="支付 / 收货">
      {{ time(order.paidAt) }} /
      {{ time(order.receivedAt) }}
    </el-descriptions-item>
    <el-descriptions-item label="关闭时间">
      {{
        time(order.closedAt)
      }}
    </el-descriptions-item>
    <el-descriptions-item label="关闭原因">
      {{
        order.closeReason || '—'
      }}
    </el-descriptions-item>
    <el-descriptions-item label="支付单">
      {{
        order.paymentId || '尚无付款请求'
      }}
    </el-descriptions-item>
    <el-descriptions-item label="售后 / 发票申请">
      {{
        order.aftersaleIds.length ? order.aftersaleIds.join('、') : '尚无售后'
      }}
      / {{ order.invoiceRequestId || '尚无开票申请' }}
    </el-descriptions-item>
  </el-descriptions>
  <h3>成交商品</h3>
  <el-table :data="order.items">
    <el-table-column prop="productName" label="商品" />
    <el-table-column prop="optionsText" label="规格" />
    <el-table-column prop="quantity" label="数量" />
    <el-table-column label="单价">
      <template #default="{ row }">
        ¥{{ money(row.unitPriceCent) }}
      </template>
    </el-table-column>
    <el-table-column label="小计">
      <template #default="{ row }">
        ¥{{ money(row.lineAmountCent) }}
      </template>
    </el-table-column>
  </el-table>
  <h3>发货前检查</h3>
  <el-alert
    v-if="order.fulfillmentCheck.businessReady"
    title="业务条件已满足"
    type="success"
    :closable="false"
  />
  <el-alert
    v-for="reason in order.fulfillmentCheck.blockingReasons"
    :key="reason.code"
    :title="reason.message"
    type="warning"
    :closable="false"
  />
  <p class="muted">
    发货操作只登记本地发货事实；微信平台发货与快递100物流查询尚未启用。
  </p>
  <p v-if="order.shipment">
    包裹：{{ order.shipment.courierCode }}
    {{ order.shipment.trackingNo }}；出库时间
    {{ time(order.shipment.shippedAt) }}；自动收货时间
    {{ time(order.shipment.autoReceiveAt) }}
  </p>
  <p v-else class="muted">尚无发货记录</p>
  <h3>办理记录</h3>
  <el-timeline v-if="order.timeline.length">
    <el-timeline-item
      v-for="event in order.timeline"
      :key="event.id"
      :timestamp="time(event.occurredAt)"
    >
      {{ event.label }} · {{ event.actorLabel }}
    </el-timeline-item>
  </el-timeline>
  <p v-else class="muted">暂无办理记录</p>
</template>

<script setup>
import { money, time, orderStates, paymentStates } from './order-view'
defineProps({ order: { type: Object, required: true } })
</script>
<style scoped>
h3 {
  margin-top: 24px;
}
.muted {
  color: #606266;
  font-size: 14px;
}
.el-alert {
  margin-bottom: 8px;
}
</style>
