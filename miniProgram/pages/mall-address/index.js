const mallService = require('../../services/mall-checkout-service')
const mallIntent = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')
const { createRequestKeyManager } = require('../../utils/request-key')
const { setMallFormError } = require('../../utils/mall-form-error')
const { getMallPurposeNotice } = require('../../models/legal-document')

function key() {
  return mallIntent.createIdempotencyKey()
}

function regionText(address) {
  return Array.isArray(address && address.regionNames) && address.regionNames.length === 3
    ? address.regionNames.join(' ')
    : '收货地区已保存'
}

Page({
  data: {
    state: 'loading',
    stateMessage: '',
    focusField: '',
    errorTarget: '',
    addresses: [],
    formVisible: false,
    policyVersion: '',
    purposeNotice: getMallPurposeNotice('recipient'),
    returnToCheckout: false,
    recipientName: '',
    phone: '',
    regionNames: [],
    regionCodes: [],
    regionText: '请选择省、市、区',
    addressLine: '',
    isDefault: false,
    consentConfirmed: false,
    saving: false,
    busyId: ''
  },

  onLoad(options = {}) {
    this.returnToCheckout = options.returnTo === 'checkout'
    this.setData({ returnToCheckout: this.returnToCheckout })
    return this.loadAddresses()
  },

  onShow() {
    if (sessionService.getAccessToken() && this.data.state !== 'loading') this.loadAddresses()
  },

  async loadAddresses() {
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      return
    }
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const [page, settings] = await Promise.all([
        mallService.listAddresses({ pageSize: 100 }),
        mallService.getCheckoutSettings()
      ])
      const addresses = Array.isArray(page && page.items)
        ? page.items.map((item) => ({ ...item, id: String(item.id), regionText: regionText(item) }))
        : []
      this.setData({
        state: addresses.length ? 'success' : 'empty',
        addresses,
        policyVersion: settings && settings.policyVersion || ''
      })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
        return
      }
      this.setData({ state: 'recoverable-error', stateMessage: (error && error.message) || '地址加载失败，请重试' })
    }
  },

  retry() {
    return this.loadAddresses()
  },

  showAddressForm() {
    this.setData({
      formVisible: true,
      recipientName: '',
      phone: '',
      regionNames: [],
      regionCodes: [],
      regionText: '请选择省、市、区',
      addressLine: '',
      isDefault: this.data.addresses.length === 0,
      consentConfirmed: false,
      stateMessage: '',
      focusField: '',
      errorTarget: ''
    })
  },

  hideAddressForm() {
    this.setData({ formVisible: false, stateMessage: '', focusField: '', errorTarget: '' })
  },

  onFieldInput(event) {
    const field = event && event.currentTarget && event.currentTarget.dataset.field
    if (!['recipientName', 'phone', 'addressLine'].includes(field)) return
    this.setData({
      [field]: String(event.detail && event.detail.value || ''),
      stateMessage: '',
      errorTarget: ''
    })
  },

  onFieldBlur(event) {
    const field = event && event.currentTarget && event.currentTarget.dataset.field
    if (field && this.data.focusField === field) this.setData({ focusField: '' })
  },

  onRegionChange(event) {
    const detail = event && event.detail || {}
    const codes = Array.isArray(detail.code) ? detail.code.map(String) : []
    const names = Array.isArray(detail.value) ? detail.value.map(String) : []
    if (codes.length !== 3 || names.length !== 3 || codes.some((code) => !/^[0-9]{6}$/.test(code))) {
      this.setData({ regionCodes: [], regionNames: [], regionText: '地区编码获取失败，请重新选择', stateMessage: '', focusField: '', errorTarget: '' })
      return
    }
    this.setData({ regionCodes: codes, regionNames: names, regionText: names.join(' '), stateMessage: '', focusField: '', errorTarget: '' })
  },

  toggleDefault() {
    this.setData({ isDefault: !this.data.isDefault })
  },

  toggleConsent() {
    this.setData({ consentConfirmed: !this.data.consentConfirmed, stateMessage: '', focusField: '', errorTarget: '' })
  },

  async saveAddress() {
    if (this.data.saving) return
    if (!String(this.data.recipientName || '').trim()) {
      setMallFormError(this, '请填写收件人姓名', { field: 'recipientName' })
      return
    }
    if (!/^1[3-9][0-9]{9}$/.test(String(this.data.phone || '').trim())) {
      setMallFormError(this, '请填写正确的11位手机号', { field: 'phone' })
      return
    }
    if (!this.data.consentConfirmed) {
      setMallFormError(this, '请确认收货资料仅用于商城订单履约', { target: 'consent' })
      return
    }
    if (this.data.regionCodes.length !== 3 || this.data.regionNames.length !== 3) {
      setMallFormError(this, '请完整选择省、市、区后再保存', { target: 'region' })
      return
    }
    if (!String(this.data.addressLine || '').trim()) {
      setMallFormError(this, '请填写街道、楼栋或门牌号', { field: 'addressLine' })
      return
    }
    if (!this.data.policyVersion) {
      setMallFormError(this, '商城资料说明尚未配置，暂不能保存', { target: 'policy' })
      return
    }
    this.setData({ saving: true, stateMessage: '' })
    try {
      const address = await mallService.createAddress({
        recipientName: this.data.recipientName,
        phone: this.data.phone,
        regionCodes: this.data.regionCodes,
        regionNames: this.data.regionNames,
        addressLine: this.data.addressLine,
        isDefault: this.data.isDefault,
        consentVersion: this.data.policyVersion,
        consentConfirmed: this.data.consentConfirmed
      }, key())
      if (this.returnToCheckout) {
        const draft = mallIntent.getCheckoutDraft()
        if (draft) mallIntent.saveCheckoutDraft({ ...draft, addressId: address.id })
      }
      this.setData({ formVisible: false })
      await this.loadAddresses()
      if (this.returnToCheckout) this.returnToCheckoutPage()
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      } else {
        this.setData({ stateMessage: (error && error.message) || '地址保存失败，请重试' })
      }
    } finally {
      this.setData({ saving: false })
    }
  },

  async setDefault(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    const address = this.data.addresses.find((item) => item.id === id)
    if (!address || address.isDefault || this.data.busyId) return
    const flowId = `mall-address-default:${id}:${address.version}`
    const manager = this.keyManager || (this.keyManager = createRequestKeyManager())
    const requestKey = manager.begin(flowId)
    this.setData({ busyId: id })
    try {
      await mallService.updateAddress(id, { expectedVersion: address.version, isDefault: true }, requestKey)
      manager.markSucceeded(flowId)
      await this.loadAddresses()
    } catch (error) {
      manager.markUnknown(flowId)
      this.setData({ stateMessage: (error && error.message) || '默认地址更新未确认，请刷新' })
    } finally {
      this.setData({ busyId: '' })
    }
  },

  selectAddress(event) {
    if (!this.returnToCheckout) return
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    const draft = mallIntent.getCheckoutDraft()
    if (!draft || !id) return
    mallIntent.saveCheckoutDraft({ ...draft, addressId: id })
    this.returnToCheckoutPage()
  },

  returnToCheckoutPage() {
    const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
    if (pages.length > 1) {
      wx.navigateBack({ delta: 1 })
      return
    }
    wx.redirectTo({ url: '/pages/mall-checkout/index' })
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  }
})
