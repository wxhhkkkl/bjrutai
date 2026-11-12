const mallOrderService = require('../../services/mall-order-service')
const aftersaleService = require('../../services/mall-aftersale-service')
const sessionService = require('../../services/session-service')
const mallIntentService = require('../../services/mall-intent-service')
const { createRequestKeyManager } = require('../../utils/request-key')
const { imageMeta } = require('../../services/cos-upload')

const METHODS = [
  { value: 'refund_only', label: '仅退款', hint: '无需寄回商品' },
  { value: 'return_refund', label: '退货退款', hint: '商家审核通过后按地址寄回' }
]

function safeError(error, fallback) {
  return error && typeof error.message === 'string' && error.message ? error.message : fallback
}

function showAftersaleToast(page, message, { field = '', target = field } = {}) {
  page.setData({ stateMessage: '', focusField: '', errorTarget: '' }, () => {
    page.setData({
      focusField: field,
      errorTarget: target ? `mall-field-${target}` : ''
    })
  })
  wx.showToast({ title: message, icon: 'none' })
}

Page({
  data: {
    orderId: '', order: null, items: [], methods: METHODS, method: 'refund_only',
    scope: 'goods', reason: '', proofs: [], proofFileIds: [],
    state: 'loading', stateMessage: '', focusField: '', errorTarget: '', submitting: false, uploading: false
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
      const order = await mallOrderService.getMyMallOrder(this.data.orderId)
      const items = Array.isArray(order.items) ? order.items.map((item) => ({
        ...item,
        id: String(item.id),
        availableAftersaleQuantity: Math.max(0, Number(item.availableAftersaleQuantity) || 0),
        applyQuantity: 0,
        lineAmountText: Number.isSafeInteger(item.lineAmountCent) ? (item.lineAmountCent / 100).toFixed(2) : '--'
      })) : []
      const freightOnlyAvailable = order.status === 'pending_shipment' && Number(order.freightAmountCent) >
        Number(order.refundedFreightCent || 0) + Number(order.refundReservedCent || 0)
      const goodsAvailable = ['pending_shipment', 'pending_receipt', 'completed'].includes(order.status) &&
        items.some((item) => item.availableAftersaleQuantity > 0)
      if (!goodsAvailable && !freightOnlyAvailable) {
        this.setData({ state: 'empty', order, items, stateMessage: '当前订单没有可申请的售后商品或运费' })
        return
      }
      this.setData({
        state: 'success', order, items, freightOnlyAvailable, goodsAvailable,
        scope: goodsAvailable ? 'goods' : 'freight_only',
        method: 'refund_only', stateMessage: ''
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

  selectScope(event) {
    const scope = event && event.currentTarget && event.currentTarget.dataset.scope
    if (scope === 'freight_only' && !this.data.freightOnlyAvailable) return
    if (!['goods', 'freight_only'].includes(scope)) return
    this.setData({
      scope,
      method: scope === 'freight_only' ? 'refund_only' : this.data.method,
      items: scope === 'freight_only' ? this.data.items.map((item) => ({ ...item, applyQuantity: 0 })) : this.data.items,
      stateMessage: '', focusField: '', errorTarget: ''
    })
  },

  selectMethod(event) {
    const method = event && event.currentTarget && event.currentTarget.dataset.method
    if (this.data.scope !== 'goods' || !METHODS.some((item) => item.value === method)) return
    if (method === 'return_refund' && this.data.items.some((item) => item.applyQuantity > 0 && item.supportsReturn === false)) {
      showAftersaleToast(this, '所选商品不支持退货退款，可申请仅退款')
      return
    }
    this.setData({ method, stateMessage: '', focusField: '', errorTarget: '' })
  },

  changeQuantity(event) {
    const dataset = event && event.currentTarget && event.currentTarget.dataset || {}
    const id = String(dataset.id || '')
    const delta = Number(dataset.delta)
    if (![-1, 1].includes(delta)) return
    const items = this.data.items.map((item) => {
      if (item.id !== id || (delta > 0 && this.data.method === 'return_refund' && item.supportsReturn === false)) return item
      return { ...item, applyQuantity: Math.min(item.availableAftersaleQuantity, Math.max(0, item.applyQuantity + delta)) }
    })
    this.setData({ items, stateMessage: '', focusField: '', errorTarget: '' })
  },

  onReasonInput(event) { this.setData({ reason: String(event.detail && event.detail.value || '').slice(0, 200), stateMessage: '', errorTarget: '' }) },

  onReasonBlur() {
    if (this.data.focusField === 'reason') this.setData({ focusField: '' })
  },

  async chooseProofImages() {
    if (this.data.uploading || this.data.proofs.length >= 3) return
    return new Promise((resolve) => wx.chooseImage({
      count: 3 - this.data.proofs.length,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: async (result) => {
        const paths = Array.isArray(result && result.tempFilePaths) ? result.tempFilePaths : []
        if (!paths.length) { resolve(); return }
        this.setData({ uploading: true, stateMessage: '' })
        try {
          const proofs = [...this.data.proofs]
          let duplicate = false
          for (let index = 0; index < paths.length && proofs.length < 3; index += 1) {
            const filePath = paths[index]
            const file = result.tempFiles && result.tempFiles[index] || {}
            const meta = imageMeta(filePath, file)
            const fileSize = Number(file.size) > 0 ? Number(file.size) : undefined
            if (!filePath || !['image/jpeg', 'image/png'].includes(meta.contentType) || (fileSize && fileSize > 5 * 1024 * 1024)) {
              throw new Error('凭证仅支持5MB以内的JPG或PNG图片')
            }
            const sha256 = await aftersaleService.computeProofSha256(filePath)
            if (proofs.some((proof) => proof.sha256 === sha256)) {
              duplicate = true
              continue
            }
            const ticketFlow = `mall-aftersale-proof-ticket:${this.data.orderId}:${filePath}:${fileSize}`
            this.proofKeyManager = this.proofKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
            const ticketKey = this.proofKeyManager.begin(ticketFlow)
            const ticket = await aftersaleService.getAftersaleProofUploadTicket({
              orderId: this.data.orderId, fileName: meta.fileName, contentType: meta.contentType, filePath, fileSize
            }, ticketKey)
            await aftersaleService.uploadAftersaleProofFile(ticket.uploadUrl, filePath, meta.contentType)
            const verifyFlow = `mall-aftersale-proof-verify:${ticket.fileId}`
            const verifyKey = this.proofKeyManager.begin(verifyFlow)
            const verified = await aftersaleService.verifyAftersaleProof(ticket.fileId, verifyKey)
            if (verified.status !== 'verified') throw new Error('图片暂未通过校验，请重新选择')
            this.proofKeyManager.markSucceeded(ticketFlow)
            this.proofKeyManager.markSucceeded(verifyFlow)
            proofs.push({ id: String(verified.id || ticket.fileId), path: filePath, sha256, status: 'verified' })
          }
          this.setData({
            proofs,
            proofFileIds: proofs.map((proof) => proof.id),
            stateMessage: ''
          })
          if (duplicate) showAftersaleToast(this, '这张图片已经添加过了')
        } catch (error) {
          showAftersaleToast(this, safeError(error, '凭证上传或校验失败，请重试'))
        } finally {
          this.setData({ uploading: false })
          resolve()
        }
      },
      fail: () => { showAftersaleToast(this, '未选择图片'); resolve() }
    }))
  },

  previewProof(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    const urls = this.data.proofs.map((proof) => proof.path).filter(Boolean)
    if (!urls.length) return
    const selected = this.data.proofs.find((proof) => proof.id === id)
    wx.previewImage({ current: selected && selected.path || urls[0], urls })
  },

  removeProof(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    const proofs = this.data.proofs.filter((proof) => proof.id !== id)
    this.setData({ proofs, proofFileIds: proofs.map((proof) => proof.id) })
  },

  buildApplication() {
    const items = this.data.scope === 'goods' ? this.data.items
      .filter((item) => item.applyQuantity > 0)
      .map((item) => ({ orderItemId: item.id, quantity: item.applyQuantity })) : []
    return {
      orderId: this.data.orderId,
      expectedOrderVersion: this.data.order.version,
      method: this.data.scope === 'freight_only' ? 'refund_only' : this.data.method,
      scope: this.data.scope,
      items,
      reason: this.data.reason.trim(),
      proofFileIds: this.data.proofFileIds.slice()
    }
  },

  submitApplication() {
    if (this.data.state !== 'success' || this.data.submitting || this.data.uploading) return Promise.resolve()
    const application = this.buildApplication()
    if (!application.reason) {
      showAftersaleToast(this, '请填写售后原因', { field: 'reason' })
      return Promise.resolve()
    }
    if (application.scope === 'goods' && !application.items.length) {
      showAftersaleToast(this, '请至少选择一件可申请售后的商品', { target: 'items' })
      return Promise.resolve()
    }
    return new Promise((resolve) => wx.showModal({
      title: '确认提交售后申请？',
      content: '申请金额以商家审核结果为准。提交后可在售后进度中查看处理状态。',
      confirmText: '提交申请',
      success: async ({ confirm }) => {
        if (!confirm) { resolve(); return }
        const flowId = `mall-aftersale-apply:${this.data.orderId}:${JSON.stringify(application)}`
        this.applyKeyManager = this.applyKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
        const key = this.applyKeyManager.begin(flowId)
        this.setData({ submitting: true, stateMessage: '' })
        try {
          const result = await aftersaleService.createMallAftersale(application, key)
          this.applyKeyManager.markSucceeded(flowId)
          const id = String(result && result.id || '')
          if (!/^[1-9][0-9]*$/.test(id)) throw new Error('申请已提交，但售后编号暂未返回，请到订单详情查看')
          wx.redirectTo({ url: `/pages/mall-aftersale-detail/index?id=${encodeURIComponent(id)}` })
        } catch (error) {
          if (error && ['VALIDATION', 'AUTH', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'].includes(error.kind)) this.applyKeyManager.markFailed(flowId)
          else this.applyKeyManager.markUnknown(flowId)
          showAftersaleToast(this, safeError(error, '提交结果待核实，可保持内容后重试'))
        } finally {
          this.setData({ submitting: false })
          resolve()
        }
      },
      fail: resolve
    }))
  },

  goBack() { wx.navigateBack({ delta: 1 }) }
})
