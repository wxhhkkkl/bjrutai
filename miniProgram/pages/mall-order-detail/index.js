const mallOrderService = require('../../services/mall-order-service')
const mallIntentService = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')
const { createRequestKeyManager } = require('../../utils/request-key')

const STATUS_LABELS = {
  pending_payment: '等待付款',
  pending_shipment: '等待发货',
  pending_receipt: '等待收货',
  completed: '订单已完成',
  closed: '订单已关闭'
}

const PAYMENT_LABELS = {
  not_started: '未发起',
  pending: '确认中',
  processing: '处理中',
  succeeded: '已确认收款',
  failed: '未完成',
  closed: '已关闭',
  unknown: '待核实',
  abnormal: '需人工核实'
}

const INVOICE_LABELS = {
  not_requested: '未申请',
  submitted: '待财务处理',
  needs_info: '待补充资料',
  issuing: '开票处理中',
  unknown: '开票结果核实中',
  delivered: '已出票，可取票',
  withdrawn: '申请已撤回',
  closed: '申请已关闭'
}

function money(value) {
  return Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '--'
}

function timeLabel(value) {
  if (typeof value !== 'string') return ''
  return value.replace('T', ' ').replace(/(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$/, '').slice(0, 16)
}

function viewOrder(order) {
  const address = order && order.address || {}
  const shipment = order && order.shipment || null
  const invoiceRequestId = String(order && order.invoiceRequestId || '')
  const paid = Number(order && order.paidAmountCent) || 0
  const refunded = (Number(order && order.refundedGoodsCent) || 0) + (Number(order && order.refundedFreightCent) || 0)
  const netPaidCent = Math.max(0, paid - refunded)
  const canApplyInvoice = order && order.paymentStatus === 'succeeded' && netPaidCent > 0 && !/^[1-9][0-9]*$/.test(invoiceRequestId)
  const platformStatus = shipment && shipment.platformSyncStatus
  const platformSyncLabels = {
    not_required: '平台同步不适用',
    pending: '平台发货同步待处理',
    succeeded: '平台已确认发货',
    failed: '平台发货同步失败',
    unknown: '平台发货状态待核实'
  }
  return {
    ...order,
    statusLabel: STATUS_LABELS[order && order.status] || '订单处理中',
    paymentStatusLabel: PAYMENT_LABELS[order && order.paymentStatus] || '付款状态待核实',
    invoiceStatusLabel: INVOICE_LABELS[order && order.invoiceStatus] || (order && order.invoiceStatus ? '开票状态处理中' : '未申请'),
    invoiceRequestId: /^[1-9][0-9]*$/.test(invoiceRequestId) ? invoiceRequestId : '',
    netPaidCent,
    netPaidText: money(netPaidCent),
    canApplyInvoice: Boolean(canApplyInvoice),
    canOpenInvoice: Boolean(canApplyInvoice || /^[1-9][0-9]*$/.test(invoiceRequestId)),
    invoiceActionLabel: /^[1-9][0-9]*$/.test(invoiceRequestId) ? '查看发票进度' : canApplyInvoice ? '申请发票' : '暂不可申请',
    invoiceHint: /^[1-9][0-9]*$/.test(invoiceRequestId)
      ? '查看财务办理进度及真实蓝票、红票链'
      : netPaidCent <= 0 && paid > 0 ? '当前订单无剩余可开票金额' : '付款成功后可申请发票',
    amountText: money(order && order.payableAmountCent),
    goodsAmountText: money(order && order.goodsAmountCent),
    freightAmountText: money(order && order.freightAmountCent),
    paidAmountText: money(order && order.paidAmountCent),
    refundedAmountText: money((Number(order && order.refundedGoodsCent) || 0) + (Number(order && order.refundedFreightCent) || 0)),
    createdLabel: timeLabel(order && order.createdAt),
    paidLabel: timeLabel(order && order.paidAt),
    receivedLabel: timeLabel(order && order.receivedAt),
    address: {
      ...address,
      regionLabel: Array.isArray(address.regionNames) ? address.regionNames.filter(Boolean).join(' ') : '',
      addressLineLabel: address.addressMasked || '详细地址已保存'
    },
    shipment: shipment ? { ...shipment, platformSyncLabel: platformSyncLabels[platformStatus] || '平台发货状态待核实' } : null,
    items: Array.isArray(order && order.items) ? order.items.map((item) => ({
      ...item,
      unitPriceText: money(item.unitPriceCent),
      lineAmountText: money(item.lineAmountCent)
    })) : [],
    timeline: Array.isArray(order && order.timeline) ? order.timeline.map((event) => ({
      ...event,
      timeLabel: timeLabel(event.occurredAt)
    })) : [],
    canContinuePayment: order && order.status === 'pending_payment',
    canConfirmReceipt: Boolean(order && order.status === 'pending_receipt' && Array.isArray(order.availableActions) && order.availableActions.includes('confirmMallReceipt')),
    canApplyAftersale: Boolean(order && ['pending_shipment', 'pending_receipt', 'completed'].includes(order.status) && (
      (Array.isArray(order.items) && order.items.some((item) => Number(item.availableAftersaleQuantity) > 0)) ||
      (order.status === 'pending_shipment' && Number(order.freightAmountCent) > Number(order.refundedFreightCent || 0) + Number(order.refundReservedCent || 0))
    )),
    aftersaleRecords: Array.isArray(order && order.aftersaleIds) ? order.aftersaleIds.map((id) => ({ id: String(id) })) : []
  }
}

Page({
  data: {
    orderId: '',
    order: null,
    state: 'loading',
    stateMessage: '',
    confirming: false
  },

  onLoad(options = {}) {
    const orderId = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(orderId)) {
      this.setData({ state: 'recoverable-error', stateMessage: '订单编号无效，请返回订单列表重试' })
      return
    }
    this.setData({ orderId })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadOrder()
  },

  async loadOrder(silent = false) {
    if (!this.data.orderId || this.loadingOrder) return
    this.loadingOrder = true
    if (!silent) this.setData({ state: 'loading', stateMessage: '' })
    try {
      const order = await mallOrderService.getMyMallOrder(this.data.orderId)
      this.setData({ state: 'success', order: viewOrder(order), stateMessage: '' })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      if (!silent) this.setData({ state: 'recoverable-error', stateMessage: error && error.message ? error.message : '订单暂时无法读取，请重试' })
      else this.setData({ stateMessage: error && error.message ? error.message : '订单状态暂未刷新，请稍后重试' })
    } finally {
      this.loadingOrder = false
    }
  },

  retry() {
    return this.loadOrder()
  },

  openLogistics() {
    if (!this.data.order || !this.data.order.shipment) return
    wx.navigateTo({ url: `/pages/mall-logistics/index?id=${encodeURIComponent(this.data.orderId)}` })
  },

  openAftersale() {
    if (!this.data.order || !this.data.order.canApplyAftersale) return
    wx.navigateTo({ url: `/pages/mall-aftersale-apply/index?orderId=${encodeURIComponent(this.data.orderId)}` })
  },

  openAftersaleRecord(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    if (!/^[1-9][0-9]*$/.test(id)) return
    wx.navigateTo({ url: `/pages/mall-aftersale-detail/index?id=${encodeURIComponent(id)}` })
  },

  openInvoice() {
    const order = this.data.order
    if (!order || !order.canOpenInvoice) return
    if (order.invoiceRequestId) {
      wx.navigateTo({ url: `/pages/mall-invoice-detail/index?id=${encodeURIComponent(order.invoiceRequestId)}` })
      return
    }
    wx.navigateTo({ url: `/pages/mall-invoice-apply/index?orderId=${encodeURIComponent(this.data.orderId)}` })
  },

  continuePayment() {
    if (!this.data.order || !this.data.order.canContinuePayment) return
    wx.navigateTo({ url: `/pages/mall-payment-result/index?id=${encodeURIComponent(this.data.orderId)}` })
  },

  confirmReceipt() {
    const order = this.data.order
    if (!order || !order.canConfirmReceipt || this.data.confirming) return Promise.resolve()
    return new Promise((resolve) => {
      wx.showModal({
        title: '确认收到商品？',
        content: '确认后订单会进入已完成状态，请先核对包裹。',
        confirmText: '确认收货',
        success: async ({ confirm }) => {
          if (!confirm) { resolve(); return }
          const flowId = `mall-receipt:${this.data.orderId}:${order.version}`
          this.receiptKeyManager = this.receiptKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
          const idempotencyKey = this.receiptKeyManager.begin(flowId)
          this.setData({ confirming: true, stateMessage: '' })
          try {
            await mallOrderService.confirmMallReceipt(this.data.orderId, order.version, idempotencyKey)
            this.receiptKeyManager.markSucceeded(flowId)
            await this.loadOrder(true)
            wx.showToast({ title: '已提交确认', icon: 'success' })
          } catch (error) {
            this.receiptKeyManager.markUnknown(flowId)
            this.setData({ stateMessage: (error && error.message) || '确认结果待核实，正在查询订单状态' })
            await this.loadOrder(true)
          } finally {
            this.setData({ confirming: false })
            resolve()
          }
        },
        fail: resolve
      })
    })
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  }
})
