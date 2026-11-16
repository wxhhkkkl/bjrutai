const aftersaleService = require('../../services/mall-aftersale-service')
const sessionService = require('../../services/session-service')
const mallIntentService = require('../../services/mall-intent-service')
const { createRequestKeyManager } = require('../../utils/request-key')
const { setMallFormError } = require('../../utils/mall-form-error')
const { courierOptions: COURIERS } = require('../../utils/courier')


Page({
  data: {
    aftersaleId: '', aftersale: null, couriers: COURIERS, courierIndex: -1,
    trackingNo: '', state: 'loading', stateMessage: '', focusField: '', errorTarget: '', submitting: false
  },

  onLoad(options = {}) {
    const id = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(id)) {
      this.setData({ state: 'recoverable-error', stateMessage: '售后编号无效，请返回售后进度重试' })
      return
    }
    this.setData({ aftersaleId: id })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadAftersale()
  },

  async loadAftersale() {
    if (this.loadingAftersale) return
    this.loadingAftersale = true
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const aftersale = await aftersaleService.getMyMallAftersale(this.data.aftersaleId)
      if (aftersale.status !== 'awaiting_return' || aftersale.returnTrackingNo) {
        this.setData({ state: 'recoverable-error', aftersale, stateMessage: '当前售后记录无需提交退货运单，请刷新售后进度' })
        return
      }
      this.setData({ state: 'success', aftersale, returnAddressAvailable: Boolean(aftersale.returnInstructions), stateMessage: '' })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      this.setData({ state: 'recoverable-error', stateMessage: error && error.message || '售后信息暂时无法读取，请重试' })
    } finally {
      this.loadingAftersale = false
    }
  },

  retry() { return this.loadAftersale() },

  onCourierChange(event) {
    const index = Number(event && event.detail && event.detail.value)
    if (!Number.isInteger(index) || index < 0 || index >= COURIERS.length) return
    this.setData({ courierIndex: index, stateMessage: '', focusField: '', errorTarget: '' })
  },

  onTrackingInput(event) {
    this.setData({ trackingNo: String(event.detail && event.detail.value || '').trim().slice(0, 64), stateMessage: '', errorTarget: '' })
  },

  onTrackingBlur() {
    if (this.data.focusField === 'trackingNo') this.setData({ focusField: '' })
  },

  submitReturnShipment() {
    if (this.data.state !== 'success' || this.data.submitting) return Promise.resolve()
    const courier = COURIERS[this.data.courierIndex]
    const trackingNo = this.data.trackingNo.trim()
    if (!courier) {
      setMallFormError(this, '请选择承运商', { target: 'courier' })
      return Promise.resolve()
    }
    if (!this.data.aftersale.returnInstructions) {
      setMallFormError(this, '商家退货地址尚未提供，请先联系商家确认', { target: 'return-address' })
      return Promise.resolve()
    }
    if (!/^[A-Za-z0-9_-]{4,64}$/.test(trackingNo)) {
      setMallFormError(this, '请填写4至64位字母、数字、短横线或下划线组成的运单号', { field: 'trackingNo' })
      return Promise.resolve()
    }
    const shipment = { expectedVersion: this.data.aftersale.version, courierCode: courier.code, trackingNo }
    return new Promise((resolve) => wx.showModal({
      title: '确认退货运单信息？',
      content: `${courier.name} · ${trackingNo}\n请确认已按商家提供的地址寄出。`,
      confirmText: '提交运单',
      success: async ({ confirm }) => {
        if (!confirm) { resolve(); return }
        const flowId = `mall-return-shipment:${this.data.aftersaleId}:${JSON.stringify(shipment)}`
        this.requestKeyManager = this.requestKeyManager || createRequestKeyManager(() => mallIntentService.createIdempotencyKey())
        const key = this.requestKeyManager.begin(flowId)
        this.setData({ submitting: true, stateMessage: '' })
        try {
          await aftersaleService.sendMallReturn(this.data.aftersaleId, shipment, key)
          this.requestKeyManager.markSucceeded(flowId)
          wx.redirectTo({ url: `/pages/mall-aftersale-detail/index?id=${encodeURIComponent(this.data.aftersaleId)}` })
        } catch (error) {
          if (error && ['VALIDATION', 'AUTH', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'].includes(error.kind)) this.requestKeyManager.markFailed(flowId)
          else this.requestKeyManager.markUnknown(flowId)
          setMallFormError(this, error && error.message || '提交结果待核实，可保持运单号后重试', { target: 'error-message' })
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
