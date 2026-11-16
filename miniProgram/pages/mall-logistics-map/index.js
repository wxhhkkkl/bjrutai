const mallOrderService = require('../../services/mall-order-service')
const sessionService = require('../../services/session-service')

function validMapUrl(value) {
  return typeof value === 'string'
    && value.length <= 2048
    && /^https:\/\/[^\s]+$/i.test(value)
}

Page({
  data: {
    orderId: '',
    state: 'loading',
    stateMessage: '',
    mapUrl: ''
  },

  onLoad(options = {}) {
    const orderId = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(orderId)) {
      this.setData({ state: 'error', stateMessage: '订单编号无效，请返回物流页重试' })
      return
    }
    this.setData({ orderId })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadMap()
  },

  async loadMap() {
    if (!this.data.orderId || this.loadingMap) return
    this.loadingMap = true
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const snapshot = await mallOrderService.getMyMallLogistics(this.data.orderId)
      if (validMapUrl(snapshot && snapshot.mapUrl)) {
        this.setData({ state: 'ready', mapUrl: snapshot.mapUrl })
      } else {
        this.setData({
          state: 'empty',
          stateMessage: '本次查询暂未返回地图轨迹，请返回物流页下拉刷新后重试'
        })
      }
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      this.setData({
        state: 'error',
        stateMessage: error && error.message ? error.message : '地图轨迹暂时无法加载'
      })
    } finally {
      this.loadingMap = false
    }
  },

  retry() {
    return this.loadMap()
  },

  onWebError() {
    this.setData({
      state: 'error',
      stateMessage: '地图页面加载失败，请检查网络或域名配置后重试'
    })
  }
})
