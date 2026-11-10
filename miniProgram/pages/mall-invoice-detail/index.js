const invoiceService = require('../../services/mall-invoice-service')
const mallCheckoutService = require('../../services/mall-checkout-service')
const sessionService = require('../../services/session-service')
const mallIntentService = require('../../services/mall-intent-service')
const { getMallPurposeNotice } = require('../../models/legal-document')
const { createRequestKeyManager } = require('../../utils/request-key')
const { setMallFormError } = require('../../utils/mall-form-error')
const { sha256Hex } = require('../../utils/sha256')

const REQUEST_LABELS = {
  submitted: '待财务处理',
  needs_info: '待补充资料',
  issuing: '开票处理中',
  unknown: '开票结果核实中',
  delivered: '已处理，可下载',
  withdrawn: '申请已撤回',
  closed: '申请已关闭'
}

const INVOICE_STATUS_LABELS = {
  valid: '有效',
  red_pending: '待红冲',
  awaiting_counterparty: '待对方确认',
  partially_red: '部分红冲',
  fully_red: '已全额红冲'
}

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

function normalizeRequest(value = {}) {
  const { taxNo, email, ...safe } = value
  const invoices = Array.isArray(safe.invoices) ? safe.invoices.map((invoice) => ({
    ...invoice,
    totalText: money(invoice.totalCent),
    kindLabel: invoice.kind === 'red' ? '红票' : '蓝票',
    chainLabel: invoice.kind === 'red'
      ? '原蓝票的红票'
      : invoice.replacementForId ? '重开蓝票' : '蓝票',
    statusLabel: INVOICE_STATUS_LABELS[invoice.status] || '票据状态处理中',
    canDownload: Boolean(invoice.fileId),
    canCorrect: invoice.kind === 'blue' && invoice.status === 'valid'
  })) : []
  const status = String(safe.status || '')
  return {
    ...safe,
    invoices,
    statusLabel: REQUEST_LABELS[status] || '开票状态处理中',
    buyerTypeLabel: safe.buyerType === 'company' ? '企业抬头' : '个人抬头',
    invoiceTypeLabel: safe.invoiceType === 'manual_special_request' ? '专票需求（财务人工核实）' : '普通数电票',
    netPaidText: money(safe.netPaidCent),
    canSupplement: status === 'needs_info',
    canWithdraw: ['submitted', 'needs_info'].includes(status)
  }
}

function downloadFile(url) {
  return new Promise((resolve, reject) => {
    if (typeof wx.downloadFile !== 'function') {
      reject(new Error('当前微信版本暂不支持下载票据'))
      return
    }
    wx.downloadFile({
      url,
      success(result) {
        const statusCode = Number(result && result.statusCode) || 0
        if (statusCode >= 200 && statusCode < 300 && result.tempFilePath) resolve(result.tempFilePath)
        else reject(new Error('票据下载失败'))
      },
      fail: reject
    })
  })
}

function openPdf(filePath) {
  return new Promise((resolve, reject) => {
    if (typeof wx.openDocument !== 'function') {
      reject(new Error('当前微信版本暂不支持打开PDF票据'))
      return
    }
    wx.openDocument({ filePath, fileType: 'pdf', showMenu: true, success: resolve, fail: reject })
  })
}

Page({
  data: {
    requestId: '', request: null, invoices: [], state: 'loading', stateMessage: '', focusField: '', errorTarget: '',
    supplementTitle: '', supplementTaxNo: '', submittingSupplement: false,
    policyVersion: '', purposeNotice: getMallPurposeNotice('invoice'), supplementConsentConfirmed: false,
    correctionInvoiceId: '', correctionReason: '', correctionMessage: '', submittingCorrection: false,
    showWithdrawForm: false, withdrawReason: '', submittingWithdraw: false,
    downloadingInvoiceId: '', downloadMessage: ''
  },

  onLoad(options = {}) {
    const requestId = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(requestId)) {
      this.setData({ state: 'recoverable-error', stateMessage: '开票申请编号无效，请从订单详情重试' })
      return
    }
    this.setData({ requestId })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadRequest()
  },

  async loadRequest() {
    if (this.loadingRequest) return
    this.loadingRequest = true
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const [requestValue, settings] = await Promise.all([
        invoiceService.getMyMallInvoiceRequest(this.data.requestId),
        mallCheckoutService.getCheckoutSettings()
      ])
      const request = normalizeRequest(requestValue)
      this.setData({
        state: 'success', request, invoices: request.invoices,
        supplementTitle: request.title || '', supplementTaxNo: '', stateMessage: '',
        policyVersion: settings && settings.policyVersion || '', supplementConsentConfirmed: false
      })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      this.setData({ state: 'recoverable-error', stateMessage: safeError(error, '开票进度暂时无法读取，请重试') })
    } finally {
      this.loadingRequest = false
    }
  },

  retry() { return this.loadRequest() },
  onTitleInput(event) { this.setData({ supplementTitle: String(event.detail && event.detail.value || '').slice(0, 200), stateMessage: '', focusField: '', errorTarget: '' }) },
  onTaxNoInput(event) { this.setData({ supplementTaxNo: String(event.detail && event.detail.value || '').trim().slice(0, 32).toUpperCase(), stateMessage: '', focusField: '', errorTarget: '' }) },
  toggleSupplementConsent() { this.setData({ supplementConsentConfirmed: !this.data.supplementConsentConfirmed, stateMessage: '', focusField: '', errorTarget: '' }) },

  async submitSupplement() {
    const request = this.data.request
    if (!request || !request.canSupplement || this.data.submittingSupplement) return
    if (!this.data.supplementConsentConfirmed || !this.data.policyVersion) {
      setMallFormError(this, '请阅读并确认当前开票资料用途告知', { target: 'supplementConsent' })
      return
    }
    const title = String(this.data.supplementTitle || '').trim()
    const taxNo = String(this.data.supplementTaxNo || '').trim().toUpperCase()
    if (!title) { setMallFormError(this, '请填写发票抬头', { field: 'supplementTitle' }); return }
    if (request.buyerType === 'company' && !/^[A-Za-z0-9]{8,32}$/.test(taxNo)) {
      setMallFormError(this, '企业抬头请重新填写纳税人识别号', { field: 'supplementTaxNo' })
      return
    }
    if (request.buyerType === 'personal' && taxNo) { setMallFormError(this, '个人抬头无需填写纳税人识别号', { field: 'supplementTaxNo' }); return }
    const changes = {
      expectedVersion: request.version,
      title,
      ...(request.buyerType === 'company' ? { taxNo } : {}),
      consentVersion: this.data.policyVersion,
      consentConfirmed: true
    }
    const flowId = `mall-invoice-supplement:${request.id}:${payloadFingerprint(changes)}`
    this.supplementKeyManager = this.supplementKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
    const key = this.supplementKeyManager.begin(flowId)
    this.setData({ submittingSupplement: true, stateMessage: '' })
    try {
      const updated = normalizeRequest(await invoiceService.updateMallInvoiceRequest(request.id, changes, key))
      this.supplementKeyManager.markSucceeded(flowId)
      this.setData({
        request: updated, invoices: updated.invoices, supplementTaxNo: '', supplementConsentConfirmed: false,
        stateMessage: '资料已提交，后台会继续处理。'
      })
    } catch (error) {
      if (error && ['VALIDATION', 'AUTH', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'].includes(error.kind)) this.supplementKeyManager.markFailed(flowId)
      else this.supplementKeyManager.markUnknown(flowId)
      this.setData({ stateMessage: safeError(error, '提交结果待核实，保留资料后可重试') })
    } finally {
      this.setData({ submittingSupplement: false })
    }
  },

  startCorrection(event) {
    const invoiceId = String(event && event.currentTarget && event.currentTarget.dataset.invoiceId || '')
    const invoice = this.data.invoices.find((item) => item.id === invoiceId)
    if (!invoice || !invoice.canCorrect) return
    this.setData({ correctionInvoiceId: invoiceId, correctionReason: '', correctionMessage: '', stateMessage: '' })
  },

  onCorrectionReasonInput(event) { this.setData({ correctionReason: String(event.detail && event.detail.value || '').slice(0, 500), stateMessage: '', focusField: '', errorTarget: '' }) },

  async submitCorrection() {
    const invoice = this.data.invoices.find((item) => item.id === this.data.correctionInvoiceId)
    const reason = String(this.data.correctionReason || '').trim()
    if (!invoice || !invoice.canCorrect || this.data.submittingCorrection) return
    if (!reason) { setMallFormError(this, '请填写需要更正的原因', { field: 'correctionReason' }); return }
    const action = { expectedVersion: invoice.version, reason }
    const flowId = `mall-invoice-correction:${invoice.id}:${payloadFingerprint(action)}`
    this.correctionKeyManager = this.correctionKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
    const key = this.correctionKeyManager.begin(flowId)
    this.setData({ submittingCorrection: true, correctionMessage: '' })
    try {
      const result = await invoiceService.requestMallInvoiceCorrection(invoice.id, action, key)
      if (!result || result.status !== 'manual') throw new Error('更正诉求结果待核实，请重新查询')
      this.correctionKeyManager.markSucceeded(flowId)
      this.setData({
        correctionInvoiceId: '', correctionMessage: '已提交更正诉求，等待财务核实。原票状态保持不变。'
      })
    } catch (error) {
      if (error && ['VALIDATION', 'AUTH', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'].includes(error.kind)) this.correctionKeyManager.markFailed(flowId)
      else this.correctionKeyManager.markUnknown(flowId)
      this.setData({ correctionMessage: safeError(error, '提交结果待核实，可保持原因后重试') })
    } finally {
      this.setData({ submittingCorrection: false })
    }
  },

  cancelCorrection() { this.setData({ correctionInvoiceId: '', correctionReason: '', correctionMessage: '' }) },

  startWithdraw() {
    if (!this.data.request || !this.data.request.canWithdraw || this.data.submittingWithdraw) return
    this.setData({ showWithdrawForm: true, withdrawReason: '', stateMessage: '' })
  },

  onWithdrawReasonInput(event) { this.setData({ withdrawReason: String(event.detail && event.detail.value || '').slice(0, 500), stateMessage: '', focusField: '', errorTarget: '' }) },

  async submitWithdraw() {
    const request = this.data.request
    const reason = String(this.data.withdrawReason || '').trim()
    if (!request || !request.canWithdraw || this.data.submittingWithdraw) return
    if (!reason) { setMallFormError(this, '请填写撤回原因', { field: 'withdrawReason' }); return }
    const action = { expectedVersion: request.version, reason }
    const flowId = `mall-invoice-withdraw:${request.id}:${payloadFingerprint(action)}`
    this.withdrawKeyManager = this.withdrawKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
    const key = this.withdrawKeyManager.begin(flowId)
    this.setData({ submittingWithdraw: true, stateMessage: '' })
    try {
      const updated = normalizeRequest(await invoiceService.withdrawMallInvoiceRequest(request.id, action, key))
      this.withdrawKeyManager.markSucceeded(flowId)
      this.setData({ request: updated, invoices: updated.invoices, showWithdrawForm: false, stateMessage: '开票申请已撤回。' })
    } catch (error) {
      if (error && ['VALIDATION', 'AUTH', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'].includes(error.kind)) this.withdrawKeyManager.markFailed(flowId)
      else this.withdrawKeyManager.markUnknown(flowId)
      this.setData({ stateMessage: safeError(error, '撤回结果待核实，保持原因后可重试') })
    } finally {
      this.setData({ submittingWithdraw: false })
    }
  },

  async downloadInvoice(event) {
    const dataset = event && event.currentTarget && event.currentTarget.dataset || {}
    const fileId = String(dataset.fileId || '')
    const invoiceId = String(dataset.invoiceId || '')
    if (!/^[1-9][0-9]*$/.test(fileId) || !/^[1-9][0-9]*$/.test(invoiceId) || this.data.downloadingInvoiceId) return
    this.setData({ downloadingInvoiceId: invoiceId, downloadMessage: '' })
    try {
      // Each attempt obtains a new 60-second private link; a failed download never reuses a stale URL.
      const access = await invoiceService.getMallInvoiceFileAccess(fileId)
      if (!access || typeof access.accessUrl !== 'string' || !/^https:\/\//i.test(access.accessUrl)) throw new Error('票据临时链接无效')
      const tempFilePath = await downloadFile(access.accessUrl)
      await openPdf(tempFilePath)
    } catch (_) {
      this.setData({ downloadMessage: '票据下载失败，请重试；重试时会重新获取临时链接。' })
    } finally {
      this.setData({ downloadingInvoiceId: '' })
    }
  },

  goBack() { wx.navigateBack({ delta: 1 }) }
})
