const mallOrderService = require('../../services/mall-order-service')
const sessionService = require('../../services/session-service')
const { courierName } = require('../../utils/courier')
const { formatChinaDateTime } = require('../../utils/date-time')

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
  if (event.timeText) {
    const timeText = String(event.timeText)
    if (/T\d{2}:\d{2}/.test(timeText)) {
      return formatChinaDateTime(timeText, { includeSeconds: true }) || timeText
    }
    return timeText
  }
  return formatChinaDateTime(event.occurredAt, { includeSeconds: true }) || '时间未提供'
}

function buildMap(snapshot) {
  if (!snapshot || snapshot.mapAvailable !== true || !snapshot.route) return null
  const source = Array.isArray(snapshot.route.points) ? snapshot.route.points : []
  const valid = source.filter((point) => (
    point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
  ))
  if (valid.length < 2) return null
  const latitudes = valid.map((point) => point.latitude)
  const longitudes = valid.map((point) => point.longitude)
  const minLat = Math.min.apply(null, latitudes)
  const maxLat = Math.max.apply(null, latitudes)
  const minLng = Math.min.apply(null, longitudes)
  const maxLng = Math.max.apply(null, longitudes)
  const span = Math.max(maxLat - minLat, maxLng - minLng)
  const scale = span > 8 ? 4 : span > 3 ? 5 : span > 1 ? 7 : span > 0.2 ? 9 : 12
  const passed = valid.filter((point) => point.stateName !== '预估途径节点')
  const current = valid.find((point) => point.stateName === '当前停留节点') || passed[passed.length - 1] || valid[0]
  const padLat = Math.max((maxLat - minLat) * 0.15, 0.01)
  const padLng = Math.max((maxLng - minLng) * 0.15, 0.01)
  return {
    latitude: (minLat + maxLat) / 2,
    longitude: (minLng + maxLng) / 2,
    scale,
    points: [
      { latitude: minLat - padLat, longitude: minLng - padLng },
      { latitude: maxLat + padLat, longitude: maxLng + padLng }
    ],
    currentName: typeof snapshot.route.currentName === 'string' ? snapshot.route.currentName : '',
    markers: [{
      id: 1,
      latitude: current.latitude,
      longitude: current.longitude,
      iconPath: '/assets/images/mall-map-current-pin.png',
      width: 26,
      height: 34,
      anchor: { x: 0.5, y: 1 },
      callout: { content: '当前节点', display: 'ALWAYS', padding: 6, borderRadius: 6, fontSize: 11, bgColor: '#FFFFFF', color: '#1677FF' }
    }],
    polyline: [{
      points: valid.map((point) => ({ latitude: point.latitude, longitude: point.longitude })),
      color: '#1677FF',
      width: 6,
      arrowLine: false
    }]
  }
}

function viewSnapshot(snapshot) {
  const source = snapshot && snapshot.source
  let sourceLabel = '尚未查询到真实物流轨迹'
  if (source === 'fake') sourceLabel = '测试模拟轨迹'
  else if (source === 'live') sourceLabel = '快递100真实查询'
  const status = snapshot && snapshot.queryStatus
  const map = buildMap(snapshot)
  return {
    ...snapshot,
    courierName: snapshot && snapshot.courierName || courierName(snapshot && snapshot.courierCode),
    sourceLabel,
    statusLabel: QUERY_STATUS_LABELS[status] || '物流状态待确认',
    updatedAtText: formatChinaDateTime(snapshot && snapshot.updatedAt, { includeSeconds: true }),
    estimatedArrivalText: typeof (snapshot && snapshot.estimatedArrivalText) === 'string' ? snapshot.estimatedArrivalText : '',
    mapAvailable: Boolean(map),
    map,
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
    mapAvailable: false,
    map: null,
    estimatedArrivalText: ''
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
        map: view.map || null,
        estimatedArrivalText: view.estimatedArrivalText,
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
