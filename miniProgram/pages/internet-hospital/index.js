const { updateTabBar } = require('../../services/navigation-service')
const sessionService = require('../../services/session-service')
const hospitalService = require('../../services/hospital-service')

function reportVisit(event) {
  hospitalService.reportEvent(event).catch(() => {})
}

Page({
  data: {
    qrVisible: false,
    qrFailed: false
  },

  onShow() {
    updateTabBar(this, 'internet-hospital')
  },

  openHospitalQr() {
    const session = sessionService.getCurrentSession()
    if (!sessionService.getAccessToken() || !session.userId) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=internet-hospital' })
      return
    }
    reportVisit(hospitalService.EVENTS.ENTRY_TAP)
    this.setData({ qrVisible: true, qrFailed: false })
  },

  closeHospitalQr() {
    this.setData({ qrVisible: false })
  },

  onQrError() {
    this.setData({ qrFailed: true })
  },

  onQrLongPress() {
    reportVisit(hospitalService.EVENTS.QR_LONGPRESS)
  }
})
