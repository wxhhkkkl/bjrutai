const staffInviteService = require('../../services/staff-invite-service')

Page({
  data: { refToken: '', state: 'loading', stateMessage: '', info: {}, name: '', consentConfirmed: false, submitting: false, result: null },
  onLoad(options = {}) {
    const refToken = decodeURIComponent(String(options.refToken || options.scene || '').trim())
    this.setData({ refToken })
    if (!refToken) { this.setData({ state: 'invalid', stateMessage: '客户顾问加入码参数不完整' }); return }
    this.loadInfo()
  },
  async loadInfo() {
    try { this.setData({ state: 'loading' }); const info = await staffInviteService.getInviteInfo(this.data.refToken); this.setData({ state: 'ready', info }) }
    catch (error) { this.setData({ state: 'invalid', stateMessage: error.message || '客户顾问加入码已失效' }) }
  },
  onNameInput(event) { this.setData({ name: event.detail.value }) },
  toggleConsent() { this.setData({ consentConfirmed: !this.data.consentConfirmed }) },
  requestPhoneAuthorization() {
    if (!this.data.consentConfirmed) wx.showToast({ title: '请先同意加入组织授权', icon: 'none' })
  },
  async submit(event) {
    const name = String(this.data.name || '').trim()
    if (!name) { wx.showToast({ title: '请填写真实姓名', icon: 'none' }); return }
    if (!this.data.consentConfirmed) { wx.showToast({ title: '请先同意加入组织授权', icon: 'none' }); return }
    const phoneCode = event && event.detail && event.detail.code
    if (!phoneCode) { wx.showToast({ title: '需要授权手机号才能加入组织', icon: 'none' }); return }
    if (this.data.submitting) return
    this.setData({ submitting: true })
    try {
      const result = await staffInviteService.joinOrganization(this.data.refToken, { phoneCode, name, consentConfirmed: true })
      this.setData({ state: 'success', result })
    } catch (error) { wx.showToast({ title: error.message || '加入组织失败', icon: 'none' }) }
    finally { this.setData({ submitting: false }) }
  },
  handleBack() { if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 }); else wx.reLaunch({ url: '/pages/index/index' }) }
})
