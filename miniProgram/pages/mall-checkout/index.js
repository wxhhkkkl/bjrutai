const mallService = require('../../services/mall-checkout-service')
const mallIntent = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')
const { getMallPurposeNotice } = require('../../models/legal-document')

function money(value) {
  return Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '--'
}

function operationKey() {
  return typeof mallIntent.createIdempotencyKey === 'function'
    ? mallIntent.createIdempotencyKey()
    : `mall_order_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`
}

function isUncertain(error) {
  return Boolean(error && ['NETWORK', 'TIMEOUT', 'SERVER', 'MALFORMED'].includes(error.kind))
}

function formatQuote(quote) {
  if (!quote) return null
  const items = Array.isArray(quote.items) ? quote.items.map((item) => ({
    ...item,
    unitPriceText: money(item.unitPriceCent),
    lineAmountText: money(item.lineAmountCent)
  })) : []
  return {
    ...quote,
    items,
    goodsAmountText: money(quote.goodsAmountCent),
    freightText: Number(quote.freightAmountCent) > 0 ? `¥${money(quote.freightAmountCent)}` : '免运费',
    payableAmountText: money(quote.payableAmountCent)
  }
}

Page({
  data: {
    state: 'loading',
    stateMessage: '',
    settings: null,
    draft: null,
    addresses: [],
    selectedAddressId: '',
    quote: null,
    quoteState: 'idle',
    quoteMessage: '',
    buyerNote: '',
    invoiceIntent: false,
    paymentNotice: getMallPurposeNotice('payment'),
    fulfillmentNotice: getMallPurposeNotice('fulfillment'),
    purchaseConsent: false,
    submitting: false,
    pendingSubmission: false,
    purchaseAvailable: false
  },

  onLoad() {
    return this.loadCheckout()
  },

  onShow() {
    if (this.returnedFromAddress && sessionService.getAccessToken()) {
      this.returnedFromAddress = false
      this.loadCheckout()
    }
  },

  async loadCheckout() {
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      return
    }
    let draft = mallIntent.getCheckoutDraft()
    const pending = mallIntent.getPendingIntent()
    if ((!draft || !draft.items || !draft.items.length) && pending && pending.action === 'buy_now') {
      draft = mallIntent.saveCheckoutDraft({
        items: [{ skuId: pending.skuId, quantity: pending.quantity }],
        source: 'buy_now'
      })
    }
    if (!draft || !Array.isArray(draft.items) || !draft.items.length) {
      this.setData({ state: 'empty', stateMessage: '沒有可結算的商品，請從購物車重新選擇' })
      return
    }
    this.draft = draft
    this.setData({ state: 'loading', draft, quote: null, quoteState: 'loading', stateMessage: '' })
    try {
      const [settings, addressPage] = await Promise.all([
        mallService.getCheckoutSettings(),
        mallService.listAddresses({ pageSize: 100 })
      ])
      const addresses = Array.isArray(addressPage && addressPage.items) ? addressPage.items.map((item) => ({
        ...item,
        id: String(item.id),
        regionText: Array.isArray(item.regionNames) && item.regionNames.length === 3 ? item.regionNames.join(' ') : '收货地区已保存'
      })) : []
      const savedSubmission = mallIntent.getOrderSubmission()
      const currentAddress = addresses.find((item) => String(item.id) === String(draft.addressId))
        || addresses.find((item) => item.isDefault)
        || addresses[0]
      const selectedAddressId = currentAddress ? String(currentAddress.id) : ''
      this.setData({
        state: 'success',
        settings,
        addresses,
        selectedAddressId,
        purchaseAvailable: Boolean(settings && settings.purchasingAvailable),
        pendingSubmission: Boolean(savedSubmission),
        buyerNote: savedSubmission ? savedSubmission.buyerNote : this.data.buyerNote,
        invoiceIntent: savedSubmission ? savedSubmission.invoiceIntent : this.data.invoiceIntent,
        quoteState: savedSubmission ? 'pending_submission' : 'idle'
      })
      if (!savedSubmission && selectedAddressId) await this.refreshQuote()
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
        return
      }
      this.setData({ state: 'recoverable-error', stateMessage: (error && error.message) || '结算信息加载失败，请重试' })
    }
  },

  retry() {
    return this.loadCheckout()
  },

  async refreshQuote() {
    if (!this.draft || !this.data.selectedAddressId) {
      this.setData({ quote: null, quoteState: 'idle' })
      return
    }
    const version = (this.quoteVersion || 0) + 1
    this.quoteVersion = version
    this.setData({ quoteState: 'loading', quoteMessage: '', quote: null })
    try {
      const quote = await mallService.quoteOrder({
        addressId: this.data.selectedAddressId,
        items: this.draft.items.map((item) => ({ skuId: item.skuId, quantity: item.quantity }))
      })
      if (version !== this.quoteVersion) return
      this.setData({ quote: formatQuote(quote), quoteState: 'ready', quoteMessage: '' })
    } catch (error) {
      if (version !== this.quoteVersion) return
      this.setData({ quote: null, quoteState: 'error', quoteMessage: (error && error.message) || '报价已变化，请重新获取' })
    }
  },

  chooseAddress(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    if (!this.data.addresses.some((address) => String(address.id) === id)) return
    this.draft = mallIntent.saveCheckoutDraft({ ...this.draft, addressId: id })
    this.setData({ draft: this.draft, selectedAddressId: id }, () => this.refreshQuote())
  },

  openAddresses() {
    this.returnedFromAddress = true
    wx.navigateTo({ url: '/pages/mall-address/index?returnTo=checkout' })
  },

  onNoteInput(event) {
    this.setData({ buyerNote: String(event && event.detail && event.detail.value || '') })
  },

  toggleInvoiceIntent() {
    this.setData({ invoiceIntent: !this.data.invoiceIntent })
  },

  togglePurchaseConsent() {
    this.setData({ purchaseConsent: !this.data.purchaseConsent })
  },

  async submitOrder() {
    if (this.data.submitting) return
    const existing = mallIntent.getOrderSubmission()
    if (!existing && !this.data.purchaseConsent) {
      wx.showToast({ title: '请确认商品、金额与配送信息', icon: 'none' })
      return
    }
    if (!existing && (!this.data.quote || this.data.quoteState !== 'ready')) {
      wx.showToast({ title: '请先获取有效报价', icon: 'none' })
      return
    }
    if (!existing && !this.data.purchaseAvailable) {
      wx.showToast({ title: '商城暂未开放购买', icon: 'none' })
      return
    }
    if (!existing) {
      const intent = {
        quoteToken: this.data.quote.quoteToken,
        consentVersion: this.data.quote.policyVersion || this.data.settings.policyVersion,
        consentConfirmed: this.data.purchaseConsent === true,
        invoiceIntent: this.data.invoiceIntent,
        buyerNote: this.data.buyerNote,
        idempotencyKey: operationKey()
      }
      try {
        mallIntent.saveOrderSubmission(intent)
      } catch (error) {
        wx.showToast({ title: (error && error.message) || '订单凭证准备失败，请重新报价', icon: 'none' })
        return
      }
    }
    const submission = existing || mallIntent.getOrderSubmission()
    if (!submission) return
    this.setData({ submitting: true, quoteState: 'submitting', quoteMessage: '' })
    try {
      const order = await mallService.createOrder(submission, submission.idempotencyKey)
      if (!order || !/^[1-9][0-9]*$/.test(String(order.id || ''))) throw new Error('订单结果异常，请查询原订单')
      mallIntent.clearOrderSubmission()
      mallIntent.clearCheckoutDraft()
      mallIntent.clearPendingIntent()
      if (typeof mallIntent.savePendingOrder === 'function') mallIntent.savePendingOrder(order.id)
      wx.redirectTo({ url: `/pages/mall-payment-result/index?id=${encodeURIComponent(order.id)}` })
    } catch (error) {
      if (isUncertain(error)) {
        this.setData({
          pendingSubmission: true,
          quoteState: 'unknown',
          quoteMessage: '订单提交结果待确认。继续操作会用同一凭证查询或重放，不会重复创建订单。'
        })
        return
      }
      mallIntent.clearOrderSubmission()
      this.setData({ pendingSubmission: false, quoteState: 'error', quoteMessage: (error && error.message) || '订单提交失败，请重新获取报价' })
      if (error && error.kind === 'AUTH') wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      else if (error && error.kind === 'CONFLICT') this.refreshQuote()
    } finally {
      this.setData({ submitting: false })
    }
  },

  backToCart() {
    wx.navigateBack({ delta: 1 })
  },

  goBack() {
    if (this.data.pendingSubmission) {
      wx.showToast({ title: '订单结果待确认，请先继续确认提交', icon: 'none' })
      return
    }
    wx.navigateBack({ delta: 1 })
  }
})
