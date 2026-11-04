const bindingCodeService = require('../../services/customer-binding-code-service')
const authService = require('../../services/auth-service')
const pendingBindingService = require('../../services/pending-binding-service')

function tokenFromOptions(options = {}) {
  try {
    return decodeURIComponent(String(options.refToken || options.scene || '').trim())
  } catch (error) { return '' }
}

Page({
  data: {
    refToken: '',
    state: 'loading',
    stateMessage: '',
    codeInfo: {},
    submitting: false,
    bindingErrorMessage: '',
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

  onUnload() {
    this._unloaded = true
    clearTimeout(this._redirectTimer)
  },

  async loadCodeInfo() {
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const codeInfo = await pendingBindingService.loadScannedCode(this.data.refToken)
      if (this._unloaded) {
        pendingBindingService.resumePendingBinding()
        return
      }
      this.setData({ state: 'ready', codeInfo })
    } catch (error) {
      if (this._unloaded) return
      this.setData({ state: 'invalid', stateMessage: error.message || '客户绑定码已失效' })
    }
  },

  getWechatCode() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: ({ code }) => {
          if (code) resolve(code)
          else reject(new Error('获取微信凭证失败'))
        },
        fail: () => reject(new Error('获取微信凭证失败'))
      })
    })
  },

  async submit(event) {
    const phoneCode = event && event.detail && event.detail.code
    if (!phoneCode) {
      wx.showToast({ title: '需要授权手机号才能完成绑定', icon: 'none' })
      return
    }
    if (this.data.submitting) return
    this.setData({ submitting: true })
    try {
      const wechatCode = await this.getWechatCode()
      const result = await bindingCodeService.claimCustomer(this.data.refToken, {
        wechatCode,
        phoneCode,
        consentConfirmed: true
      })
      const pending = pendingBindingService.getPendingBinding()
      if (pending && pending.refToken === this.data.refToken) pendingBindingService.clearPendingBinding(pending)
      await authService.establishSession(result.session)
      wx.showToast({ title: '绑定成功', icon: 'success' })
      wx.switchTab({ url: '/pages/home/index' })
    } catch (error) {
      if ([40023, 40024].includes(Number(error.code)) || ['NOT_FOUND', 'VALIDATION', 'FORBIDDEN'].includes(error.kind)) {
        const pending = pendingBindingService.getPendingBinding()
        if (pending && pending.refToken === this.data.refToken) pendingBindingService.clearPendingBinding(pending)
      }
      if (this._unloaded) return
      if (Number(error.code) === 40024) {
        this.setData({ bindingErrorMessage: error.message || '该手机号已是客户顾问账号，不能作为客户绑定' })
        this._redirectTimer = setTimeout(() => {
          wx.switchTab({ url: '/pages/home/index' })
        }, 3000)
      } else {
        wx.showToast({ title: error.message || '绑定失败，请稍后重试', icon: 'none' })
      }
    } finally {
      if (!this._unloaded) this.setData({ submitting: Boolean(this.data.bindingErrorMessage) })
    }
  },

  handleBack() {
    if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 })
    else wx.reLaunch({ url: '/pages/index/index' })
  }
})
