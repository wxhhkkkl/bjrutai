const mallPaymentService = require('../../services/mall-payment-service')
const mallIntentService = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')

const STATUS_COPY = {
  loading: ['正在核实支付状态', '请稍候，正在查询原订单和原支付请求。'],
  succeeded: ['支付已确认', '服务器已核实收款，订单已进入后续履约。'],
  pending: ['订单仍待支付', '支付结果以服务器核实状态为准。'],
  unknown: ['支付结果确认中', '当前无法确认资金结果。请查询原订单，避免重复发起新的支付。'],
  not_started: ['订单尚未发起付款', '订单仍保留，可以稍后继续付款。'],
  failed: ['支付暂未完成', '请先查询原订单状态，再决定是否继续付款。'],
  closed: ['订单已关闭', '该订单不能继续付款。'],
  error: ['暂时无法核实', '网络恢复后请查询原订单状态。']
}

function paymentKey(orderId, version) {
  if (typeof mallIntentService.paymentIdempotencyKey === 'function') {
    return mallIntentService.paymentIdempotencyKey(orderId, version)
  }
  return `mall_payment_${orderId}_${version}`
}

Page({
  data: {
    orderId: '',
    order: null,
    payment: null,
    state: 'loading',
    title: STATUS_COPY.loading[0],
    message: STATUS_COPY.loading[1],
    querying: false,
    paying: false,
    canContinuePayment: false,
    statusLabel: ''
  },

  onLoad(options = {}) {
    const id = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(id)) {
      this.setData({ state: 'error', title: '订单编号无效', message: '请返回商城后从订单入口重新打开。' })
      return
    }
    this.setData({ orderId: id })
    if (!sessionService.getAccessToken()) {
      mallIntentService.savePendingOrder(id)
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      return
    }
    return this.queryPayment()
  },

  async queryPayment() {
    if (!this.data.orderId || this.data.querying) return
    if (!sessionService.getAccessToken()) {
      mallIntentService.savePendingOrder(this.data.orderId)
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      return
    }
    this.setData({ querying: true })
    try {
      const result = await mallPaymentService.reconcilePayment(this.data.orderId)
      this.applyResult(result)
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        mallIntentService.savePendingOrder(this.data.orderId)
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
        return
      }
      this.setData({ state: 'error', title: STATUS_COPY.error[0], message: (error && error.message) || STATUS_COPY.error[1], canContinuePayment: false })
    } finally {
      this.setData({ querying: false })
    }
  },

  applyResult(result) {
    const state = result && STATUS_COPY[result.status] ? result.status : 'unknown'
    const outcome = result && result.requestPaymentOutcome
    let message = STATUS_COPY[state][1]
    if (state === 'pending' && outcome === 'cancelled') message = '你已取消本次支付，订单仍待支付；如需付款可继续使用原订单。'
    else if (state === 'pending' && outcome === 'not_invoked') message = '支付入口当前不可用，订单仍待支付；稍后可查询原订单。'
    else if (state === 'not_started' && result && result.canInvoke === false) message = '支付入口当前不可用，订单仍待支付；稍后可查询原订单。'
    const order = result && result.order || null
    const payment = result && result.payment || null
    const canContinuePayment = Boolean(
      order && order.status === 'pending_payment'
      && ['not_started', 'pending', 'failed'].includes(state)
      && result.canInvoke !== false
    )
    if (state === 'succeeded' || state === 'closed') mallIntentService.clearPendingOrder()
    this.setData({
      state,
      title: STATUS_COPY[state][0],
      message,
      order: order ? { ...order, payableAmountText: Number.isSafeInteger(order.payableAmountCent) ? (order.payableAmountCent / 100).toFixed(2) : '--' } : null,
      payment,
      canContinuePayment,
      statusLabel: state === 'succeeded' ? '已收款' : state === 'closed' ? '已关闭' : state === 'unknown' ? '待核实' : '待支付'
    })
    if (state === 'succeeded') this.leaveAfterSuccess()
  },

  leaveAfterSuccess() {
    if (this.leavingAfterSuccess) return
    this.leavingAfterSuccess = true
    const orderId = this.data.orderId
    const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
    const previous = pages.length > 1 ? pages[pages.length - 2] : null
    if (previous && previous.route === 'pages/mall-order-detail/index' && String(previous.data && previous.data.orderId) === orderId) {
      wx.navigateBack({ delta: 1 })
      if (typeof previous.loadOrder === 'function') previous.loadOrder(true)
      return
    }
    wx.redirectTo({ url: `/pages/mall-order-detail/index?id=${encodeURIComponent(orderId)}` })
  },

  async continuePayment() {
    if (this.data.paying || !this.data.order) return
    const version = Number(this.data.order.version)
    if (!Number.isInteger(version) || version < 1) {
      wx.showToast({ title: '订单版本缺失，请先查询原订单', icon: 'none' })
      return
    }
    this.setData({ paying: true })
    try {
      const result = await mallPaymentService.payOrder(
        this.data.orderId,
        version,
        paymentKey(this.data.orderId, version)
      )
      this.applyResult(result)
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        mallIntentService.savePendingOrder(this.data.orderId)
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      } else {
        this.setData({ state: 'unknown', title: STATUS_COPY.unknown[0], message: (error && error.message) || STATUS_COPY.unknown[1], canContinuePayment: false })
      }
    } finally {
      this.setData({ paying: false })
    }
  },

  backToMall() {
    wx.switchTab({ url: '/pages/mall/index' })
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  }
})
