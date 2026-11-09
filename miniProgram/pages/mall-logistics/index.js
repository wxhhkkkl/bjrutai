const mallOrderService = require('../../services/mall-order-service')
const sessionService = require('../../services/session-service')

const QUERY_STATUS_LABELS = {
  pending: '物流查询已排队',
  available: '物流轨迹已更新',
  stale: '显示最近一次轨迹',
  no_record: '暂未查到物流记录',
  verification_failed: '快递信息需要核验',
  permission_denied: '当前账号暂不可查询',
  service_error: '物流服务暂不可用',
  config_required: '物流查询暂未开放'
}

function eventTime(event) {
  if (!event) return ''
  if (event.timeText) return String(event.timeText)
  if (typeof event.occurredAt !== 'string') return '时间未提供'
  return event.occurredAt.replace('T', ' ').replace(/(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$/, '').slice(0, 16)
}

function viewSnapshot(snapshot) {
  const source = snapshot && snapshot.source
  let sourceLabel = '尚未查询到真实物流轨迹'
  if (source === 'fake') sourceLabel = '测试模拟轨迹'
  else if (source === 'live') sourceLabel = '快递100真实查询'
  const status = snapshot && snapshot.queryStatus
  return {
    ...snapshot,
    sourceLabel,
    statusLabel: QUERY_STATUS_LABELS[status] || '物流状态待确认',
    events: Array.isArray(snapshot && snapshot.events) ? snapshot.events.map((event) => ({
      ...event,
      displayTime: eventTime(event),
      displayDescription: typeof event.description === 'string' ? event.description : '物流信息待更新'
    })) : []
  }
}

Page({
  data: {
    orderId: '',
    snapshot: null,
    sourceLabel: '',
    statusLabel: '',
    events: [],
    state: 'loading',
    stateMessage: '',
    refreshing: false,
    mapAvailable: false
  },

  onLoad(options = {}) {
    const orderId = String(options.id || '')
    if (!/^[1-9][0-9]*$/.test(orderId)) {
      this.setData({ state: 'recoverable-error', stateMessage: '订单编号无效，请返回订单详情重试' })
      return
    }
    this.setData({ orderId })
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadLogistics()
  },

  async loadLogistics() {
    if (!this.data.orderId || this.loadingLogistics) return
    this.loadingLogistics = true
    this.setData({ state: this.data.snapshot ? 'success' : 'loading', stateMessage: '', refreshing: Boolean(this.data.snapshot) })
    try {
      const snapshot = await mallOrderService.getMyMallLogistics(this.data.orderId)
      const view = viewSnapshot(snapshot)
      this.setData({
        state: 'success',
        snapshot: view,
        sourceLabel: view.sourceLabel,
        statusLabel: view.statusLabel,
        events: view.events,
        mapAvailable: view.mapAvailable === true,
        refreshing: false,
        stateMessage: ''
      })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
        return
      }
      this.setData({
        state: error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error',
        stateMessage: error && error.message ? error.message : '物流信息暂时无法读取',
        refreshing: false
      })
    } finally {
      this.loadingLogistics = false
    }
  },

  retry() {
    return this.loadLogistics()
  },

  refresh() {
    return this.loadLogistics()
  },

  onPullDownRefresh() {
    const result = this.refresh()
    if (result && result.finally) result.finally(() => wx.stopPullDownRefresh())
    else wx.stopPullDownRefresh()
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  }
})
