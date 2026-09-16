const bindingCodeService = require('../../services/customer-binding-code-service')

function tokenFromOptions(options = {}) {
  return decodeURIComponent(String(options.refToken || options.scene || '').trim())
}

Page({
  data: {
    refToken: '',
    state: 'loading',
    stateMessage: '',
    codeInfo: {},
    name: '',
    consentConfirmed: false,
    submitting: false,
    result: null
  },

  onLoad(options) {
    const refToken = tokenFromOptions(options)
    this.setData({ refToken })
    if (!refToken) {
      this.setData({ state: 'invalid', stateMessage: '客户绑定码参数不完整' })
      return
    }
    this.loadCodeInfo()
  },

  async loadCodeInfo() {
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const codeInfo = await bindingCodeService.getCodeInfo(this.data.refToken)
      this.setData({ state: 'ready', codeInfo })
    } catch (error) {
      this.setData({ state: 'invalid', stateMessage: error.message || '客户绑定码已失效' })
    }
  },

  onNameInput(event) {
    this.setData({ name: event.detail.value })
  },

  toggleConsent() {
    this.setData({ consentConfirmed: !this.data.consentConfirmed })
  },

  requestPhoneAuthorization() {
    if (!this.data.consentConfirmed) {
      wx.showToast({ title: '请先同意客户资料授权', icon: 'none' })
    }
  },

  async submit(event) {
    if (!this.data.consentConfirmed) {
      wx.showToast({ title: '请先同意客户资料授权', icon: 'none' })
      return
    }
    const phoneCode = event && event.detail && event.detail.code
    if (!phoneCode) {
      wx.showToast({ title: '需要授权手机号才能完成绑定', icon: 'none' })
      return
    }
    if (this.data.submitting) return
    this.setData({ submitting: true })
    try {
      const result = await bindingCodeService.claimCustomer(this.data.refToken, {
        phoneCode,
        name: String(this.data.name || '').trim() || undefined,
        consentConfirmed: true
      })
      this.setData({ state: 'success', result })
    } catch (error) {
      wx.showToast({ title: error.message || '绑定失败，请稍后重试', icon: 'none' })
    } finally {
      this.setData({ submitting: false })
    }
  },

  handleBack() {
    if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 })
    else wx.reLaunch({ url: '/pages/index/index' })
  }
})
