const authService = require('../../services/auth-service')
const profileService = require('../../services/profile-service')
const sessionService = require('../../services/session-service')
const { createAccountProfileForm, getAccountProfileView, validateAccountProfile } = require('../../models/account-profile')

Page({
  data: { state: 'loading', stateMessage: '', session: {}, view: {}, form: createAccountProfileForm({}), phone: '', pendingAvatarPath: '', pendingAvatarFile: {}, invalidField: '', saving: false, phoneBinding: false },
  onLoad() { this.loadProfile() },
  async loadProfile() { try { const profile = await profileService.getProfile(); const session = Object.assign({}, sessionService.getCurrentSession(), profile, { userId: profile.userId, identityType: profile.userType === 'doctor' ? 'doctor' : 'promoter', phone: profile.phone, avatar: profile.avatar, organization: profile.organization }); this.setData({ state: 'success', session, view: getAccountProfileView(session), form: createAccountProfileForm(session), phone: profile.phone || '' }) } catch (error) { this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '请稍后再试' }) } },
  retry() { this.loadProfile() },
  handleBack() { if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 }); else wx.switchTab({ url: '/pages/profile/index' }) },
  onFieldInput(event) { const field = event.currentTarget.dataset.field; if (field !== 'name') return; this.setData({ [`form.${field}`]: event.detail.value, invalidField: '' }) },
  chooseAvatar() {
    if (this.data.saving) return
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed', 'original'],
      sourceType: ['album', 'camera'],
      success: ({ tempFilePaths, tempFiles }) => {
        const path = tempFilePaths && tempFilePaths[0]
        if (!path) return
        this.setData({
          pendingAvatarPath: path,
          pendingAvatarFile: tempFiles && tempFiles[0] ? tempFiles[0] : {},
          'form.avatar': path
        })
      },
      fail: (error) => {
        if (!error || !String(error.errMsg || '').includes('cancel')) wx.showToast({ title: '选择头像失败，请重试', icon: 'none' })
      }
    })
  },
  async authorizePhone(event) {
    const code = event && event.detail && event.detail.code
    if (!code) {
      wx.showToast({ title: '未获得手机号授权', icon: 'none' })
      return
    }
    if (this.data.phoneBinding) return

    this.setData({ phoneBinding: true })
    try {
      const result = await authService.phoneBind(code)
      const phone = result && result.phone ? String(result.phone) : ''
      const session = sessionService.getCurrentSession()
      sessionService.setSession(Object.assign({}, session, {
        phone,
        phoneAuthorized: Boolean(phone)
      }))
      this.setData({
        phone,
        session: Object.assign({}, this.data.session, { phone, phoneAuthorized: Boolean(phone) }),
        view: getAccountProfileView(Object.assign({}, this.data.session, { phone })),
        phoneBinding: false
      })
      wx.showToast({ title: '手机号授权成功', icon: 'success' })
    } catch (error) {
      this.setData({ phoneBinding: false })
      wx.showToast({ title: error.message || '手机号授权失败，请重试', icon: 'none' })
    }
  },
  async saveProfile() {
    const validation = validateAccountProfile(this.data.form)
    if (!validation.valid) { this.setData({ invalidField: validation.field }); wx.showToast({ title: validation.message, icon: 'none' }); return }
    const version = this.data.session.version
    if (!version) { wx.showToast({ title: '资料版本已失效，请刷新后重试', icon: 'none' }); return }
    if (this.data.saving) return

    this.setData({ saving: true, invalidField: '' })
    try {
      let avatar = this.data.session.avatar || ''
      const payload = {
        name: String(this.data.form.name).trim(),
        version
      }
      if (this.data.pendingAvatarPath) {
        const upload = await profileService.uploadAvatar(this.data.pendingAvatarPath, this.data.pendingAvatarFile)
        avatar = upload.fileUrl
        payload.avatar = avatar
      }
      const result = await profileService.updateProfile(payload)
      const nextSession = Object.assign({}, sessionService.getCurrentSession(), this.data.session, result, { avatar: result.avatar || avatar })
      sessionService.setSession(nextSession)
      this.setData({
        saving: false,
        session: nextSession,
        form: createAccountProfileForm(nextSession),
        view: getAccountProfileView(nextSession),
        pendingAvatarPath: '',
        pendingAvatarFile: {}
      })
      wx.showToast({ title: '资料保存成功', icon: 'success' })
      setTimeout(() => this.handleBack(), 650)
    } catch (error) {
      this.setData({ saving: false })
      wx.showToast({ title: error.message || '资料保存失败，请重试', icon: 'none' })
    }
  }
})
