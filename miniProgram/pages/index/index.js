const authService = require('../../services/auth-service')
const sessionService = require('../../services/session-service')

Page({
  restoring: false,

  async onShow() {
    if (this.restoring) return
    this.restoring = true

    try {
      let session = sessionService.getCurrentSession()
      if (sessionService.getAccessToken()) {
        session = await authService.restoreSession()
      }
      this.openEntry(sessionService.getEntry(session))
    } catch (error) {
      sessionService.clearAuthenticatedSession()
      this.openEntry({
        type: 'reLaunch',
        url: '/pages/auth/login/index'
      })
    } finally {
      this.restoring = false
    }
  },

  openEntry(entry) {
    if (entry.type === 'switchTab') wx.switchTab({ url: entry.url })
    else wx.reLaunch({ url: entry.url })
  }
})
