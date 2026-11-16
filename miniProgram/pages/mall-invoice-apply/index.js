const mallOrderService = require('../../services/mall-order-service')
const invoiceService = require('../../services/mall-invoice-service')
const sessionService = require('../../services/session-service')
const mallIntentService = require('../../services/mall-intent-service')
const mallCheckoutService = require('../../services/mall-checkout-service')
const { getMallPurposeNotice } = require('../../models/legal-document')
const { createRequestKeyManager } = require('../../utils/request-key')
const { setMallFormError } = require('../../utils/mall-form-error')
const { sha256Hex } = require('../../utils/sha256')

const TAX_NO_PATTERN = /^[A-Za-z0-9]{8,32}$/
const INVOICE_TYPES = [
  { value: 'digital_normal', label: '普通数电票', hint: '适用于个人或企业普通发票' },
  { value: 'manual_special_request', label: '专票需求', hint: '提交后由财务按经营主体能力人工核实' }
]

function safeError(error, fallback) {
  return error && typeof error.message === 'string' && error.message ? error.message : fallback
}

function money(value) {
  return Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '--'
}

function payloadFingerprint(value) {
  const encoded = unescape(encodeURIComponent(JSON.stringify(value)))
  const bytes = new Uint8Array(encoded.length)
  for (let index = 0; index < encoded.length; index += 1) bytes[index] = encoded.charCodeAt(index)
  return sha256Hex(bytes)
}

Page({
  data: {
    orderId: '', order: null, state: 'loading', stateMessage: '',
    focusField: '', errorTarget: '',
    netPaidText: '--', buyerType: 'personal', title: '', taxNo: '',
    invoiceType: 'digital_normal', invoiceTypes: INVOICE_TYPES,
    policyVersion: '', purposeNotice: getMallPurposeNotice('invoice'), consentConfirmed: false,
    submitting: false
  },

  onLoad(options = {}) {
    const orderId = String(options.orderId || '')
    if (!/^[1-9][0-9]*$/.test(orderId)) {
      this.setData({ state: 'recoverable-error', stateMessage: '订单编号无效，请返回订单详情重试' })
      return
    }
    this.setData({ orderId })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadOrder()
  },

  async loadOrder() {
    if (this.loadingOrder) return
    this.loadingOrder = true
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const [order, settings] = await Promise.all([
        mallOrderService.getMyMallOrder(this.data.orderId),
        mallCheckoutService.getCheckoutSettings()
      ])
      const paid = Number(order && order.paidAmountCent) || 0
      const refunded = (Number(order && order.refundedGoodsCent) || 0) + (Number(order && order.refundedFreightCent) || 0)
      const netPaid = Math.max(0, paid - refunded)
      const canApply = order && order.paymentStatus === 'succeeded' && netPaid > 0
      this.setData({
        order,
        policyVersion: settings && settings.policyVersion || '',
        netPaidCent: netPaid,
        netPaidText: money(netPaid),
        state: canApply ? 'success' : 'ineligible',
        stateMessage: canApply ? '' : order && order.paymentStatus === 'succeeded'
          ? '当前订单没有剩余可开票金额'
          : '付款成功后可申请发票'
      })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      this.setData({ state: 'recoverable-error', stateMessage: safeError(error, '订单信息暂时无法读取，请重试') })
    } finally {
      this.loadingOrder = false
    }
  },

  retry() { return this.loadOrder() },

  selectBuyerType(event) {
    const type = event && event.currentTarget && event.currentTarget.dataset.type
    if (!['personal', 'company'].includes(type)) return
    this.setData({ buyerType: type, taxNo: '', stateMessage: '', focusField: '', errorTarget: '' })
  },

  selectInvoiceType(event) {
    const type = event && event.currentTarget && event.currentTarget.dataset.type
    if (!INVOICE_TYPES.some((item) => item.value === type)) return
    this.setData({ invoiceType: type, stateMessage: '', focusField: '', errorTarget: '' })
  },

  togglePurposeConsent() {
    this.setData({ consentConfirmed: !this.data.consentConfirmed, stateMessage: '', focusField: '', errorTarget: '' })
  },

  onTitleInput(event) { this.setData({ title: String(event.detail && event.detail.value || '').slice(0, 200), stateMessage: '', errorTarget: '' }) },
  onTaxNoInput(event) { this.setData({ taxNo: String(event.detail && event.detail.value || '').trim().slice(0, 32).toUpperCase(), stateMessage: '', errorTarget: '' }) },
  onFieldBlur(event) {
    const field = event && event.currentTarget && event.currentTarget.dataset.field
    if (field && this.data.focusField === field) this.setData({ focusField: '' })
  },
  buildApplication() {
    const title = String(this.data.title || '').trim()
    const taxNo = String(this.data.taxNo || '').trim().toUpperCase()
    if (!title || title.length > 200) throw new Error('请填写正确的发票抬头')
    if (this.data.buyerType === 'company' && !TAX_NO_PATTERN.test(taxNo)) throw new Error('企业抬头请填写纳税人识别号')
    if (this.data.buyerType === 'personal' && taxNo) throw new Error('个人抬头无需填写纳税人识别号')
    const order = this.data.order || {}
    return {
      orderId: this.data.orderId,
      expectedOrderVersion: order.version,
      buyerType: this.data.buyerType,
      title,
      ...(this.data.buyerType === 'company' ? { taxNo } : {}),
      invoiceType: this.data.invoiceType,
      consentVersion: this.data.policyVersion,
      consentConfirmed: this.data.consentConfirmed === true
    }
  },

  async submitApplication() {
    if (this.data.state !== 'success' || this.data.submitting) return
    let application
    try {
      application = this.buildApplication()
    } catch (error) {
      const title = String(this.data.title || '').trim()
      const taxNo = String(this.data.taxNo || '').trim().toUpperCase()
      const field = !title ? 'title'
        : this.data.buyerType === 'company' && !TAX_NO_PATTERN.test(taxNo) ? 'taxNo'
          : this.data.buyerType === 'personal' && taxNo ? 'taxNo' : ''
      setMallFormError(this, safeError(error, '请检查开票资料'), {
        field,
        target: field || 'error-message'
      })
      return
    }
    const flowId = `mall-invoice-apply:${this.data.orderId}:${payloadFingerprint(application)}`
    this.applyKeyManager = this.applyKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
    const key = this.applyKeyManager.begin(flowId)
    this.setData({ submitting: true, stateMessage: '' })
    try {
      const result = await invoiceService.createMallInvoiceRequest(application, key)
      const requestId = String(result && result.id || '')
      if (!/^[1-9][0-9]*$/.test(requestId)) {
        this.applyKeyManager.markUnknown(flowId)
        throw new Error('申请结果待核实，请从订单详情查询')
      }
      this.applyKeyManager.markSucceeded(flowId)
      wx.redirectTo({ url: `/pages/mall-invoice-detail/index?id=${encodeURIComponent(requestId)}` })
    } catch (error) {
      if (error && ['VALIDATION', 'AUTH', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'].includes(error.kind)) this.applyKeyManager.markFailed(flowId)
      else this.applyKeyManager.markUnknown(flowId)
      setMallFormError(this, safeError(error, '提交结果待核实，可保持资料后重试'), { target: 'error-message' })
    } finally {
      this.setData({ submitting: false })
    }
  },

  goBack() { wx.navigateBack({ delta: 1 }) }
})
