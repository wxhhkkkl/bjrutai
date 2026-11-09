const aftersaleService = require('../../services/mall-aftersale-service')
const mallOrderService = require('../../services/mall-order-service')
const sessionService = require('../../services/session-service')
const mallIntentService = require('../../services/mall-intent-service')
const { createRequestKeyManager } = require('../../utils/request-key')

const STATUS_LABELS = {
  submitted: '等待商家审核',
  awaiting_return: '等待寄回',
  awaiting_receipt: '等待商家验收',
  awaiting_refund: '退款待处理',
  refunding: '退款处理中',
  completed: '售后完成',
  succeeded: '售后完成',
  rejected: '申请未通过',
  withdrawn: '申请已撤回',
  disputed: '等待人工核实',
  closed: '售后已关闭'
}

const REFUND_LABELS = {
  prepared: '退款待发起', processing: '退款处理中', unknown: '退款状态待核实',
  abnormal: '退款异常，待处理', succeeded: '退款已确认到账', closed: '退款已关闭',
  not_exposed: '状态未提供'
}

const INVOICE_LABELS = {
  not_exposed: '状态未提供', not_requested: '未申请', pending: '待处理',
  processing: '开票处理中', issued: '已开具', failed: '处理异常', correction_pending: '待红冲处理'
}

function money(value) {
  return Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '--'
}

function viewAftersale(value) {
  const progress = aftersaleService.getFinancialProgress(value || {})
  const status = value && value.status || 'not_exposed'
  const preliminary = ['submitted', 'disputed'].includes(status)
  const items = Array.isArray(value && value.items) ? value.items.map((item) => ({
    ...item,
    goodsRefundText: money(item.goodsRefundCent)
  })) : []
  return {
    ...value,
    status,
    statusLabel: STATUS_LABELS[status] || '售后状态处理中',
    methodLabel: value && value.method === 'return_refund' ? '退货退款' : '仅退款',
    goodsRefundText: money(value && value.goodsRefundCent),
    freightRefundText: money(value && value.freightRefundCent),
    amountTitle: preliminary ? (status === 'disputed' ? '申请金额（待核实）' : '申请金额（待审核）') : '商家核定退款金额',
    refundStatusLabel: REFUND_LABELS[progress.refundStatus] || '状态待核实',
    invoiceStatusLabel: INVOICE_LABELS[progress.invoiceStatus] || '状态待核实',
    items,
    canSendReturn: status === 'awaiting_return',
    canWithdraw: ['submitted', 'awaiting_return'].includes(status) && !value.returnTrackingNo,
    receiptLabel: value && value.receiptResult === 'accepted' ? '验收通过'
      : value && value.receiptResult === 'partially_accepted' ? '部分验收'
        : value && value.receiptResult === 'disputed' ? '验收有异议' : ''
  }
}

Page({
  data: { aftersaleId: '', aftersale: null, state: 'loading', stateMessage: '', withdrawing: false },

  onLoad(options = {}) {
    const id = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(id)) {
      this.setData({ state: 'recoverable-error', stateMessage: '售后编号无效，请返回订单详情重试' })
      return
    }
    this.setData({ aftersaleId: id })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadAftersale()
  },

  async loadAftersale(silent = false) {
    if (!this.data.aftersaleId || this.loadingAftersale) return
    this.loadingAftersale = true
    if (!silent) this.setData({ state: 'loading', stateMessage: '' })
    try {
      const value = await aftersaleService.getMyMallAftersale(this.data.aftersaleId)
      let invoiceStatus = 'not_exposed'
      try {
        const order = await mallOrderService.getMyMallOrder(String(value.orderId))
        invoiceStatus = typeof order.invoiceStatus === 'string' && order.invoiceStatus ? order.invoiceStatus : invoiceStatus
      } catch (error) {
        if (error && error.kind === 'AUTH') throw error
      }
      this.setData({ aftersale: viewAftersale({ ...value, invoiceStatus }), state: 'success', stateMessage: '' })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      this.setData({ state: silent ? 'success' : 'recoverable-error', stateMessage: error && error.message || '售后进度暂时无法读取，请重试' })
    } finally {
      this.loadingAftersale = false
    }
  },

  retry() { return this.loadAftersale() },
  refresh() { return this.loadAftersale(true) },
  onPullDownRefresh() {
    const result = this.refresh()
    if (result && result.finally) result.finally(() => wx.stopPullDownRefresh())
    else wx.stopPullDownRefresh()
  },

  openReturnShipment() {
    if (!this.data.aftersale || !this.data.aftersale.canSendReturn) return
    wx.navigateTo({ url: `/pages/mall-return-shipment/index?id=${encodeURIComponent(this.data.aftersaleId)}` })
  },

  withdrawAftersale() {
    const aftersale = this.data.aftersale
    if (!aftersale || !aftersale.canWithdraw || this.data.withdrawing) return Promise.resolve()
    return new Promise((resolve) => wx.showModal({
      title: '撤回售后申请？',
      content: '撤回后，已提交的申请会结束；如仍需处理，可以重新申请。',
      confirmText: '确认撤回',
      success: async ({ confirm }) => {
        if (!confirm) { resolve(); return }
        const flowId = `mall-aftersale-withdraw:${this.data.aftersaleId}:${aftersale.version}`
        this.withdrawKeyManager = this.withdrawKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
        const key = this.withdrawKeyManager.begin(flowId)
        this.setData({ withdrawing: true, stateMessage: '' })
        try {
          await aftersaleService.withdrawMallAftersale(this.data.aftersaleId, {
            expectedVersion: aftersale.version, reason: '买家主动撤回申请'
          }, key)
          this.withdrawKeyManager.markSucceeded(flowId)
          await this.loadAftersale(true)
          wx.showToast({ title: '已撤回申请', icon: 'success' })
        } catch (error) {
          this.withdrawKeyManager.markUnknown(flowId)
          this.setData({ stateMessage: error && error.message || '撤回结果待核实，请刷新进度' })
          await this.loadAftersale(true)
        } finally {
          this.setData({ withdrawing: false })
          resolve()
        }
      },
      fail: resolve
    }))
  },

  openOrder() {
    if (!this.data.aftersale || !this.data.aftersale.orderId) return
    wx.navigateTo({ url: `/pages/mall-order-detail/index?id=${encodeURIComponent(this.data.aftersale.orderId)}` })
  },

  goBack() { wx.navigateBack({ delta: 1 }) }
})
