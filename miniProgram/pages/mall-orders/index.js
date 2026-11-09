const mallOrderService = require('../../services/mall-order-service')
const sessionService = require('../../services/session-service')

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '待付款', value: 'pending_payment' },
  { label: '待发货', value: 'pending_shipment' },
  { label: '待收货', value: 'pending_receipt' },
  { label: '已完成', value: 'completed' },
  { label: '已关闭', value: 'closed' }
]

const STATUS_LABELS = {
  pending_payment: '待付款',
  pending_shipment: '待发货',
  pending_receipt: '待收货',
  completed: '已完成',
  closed: '已关闭'
}

function money(value) {
  return Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '--'
}

function timeLabel(value) {
  if (typeof value !== 'string') return '时间未提供'
  return value.replace('T', ' ').replace(/(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$/, '').slice(0, 16) || '时间未提供'
}

function viewOrder(order) {
  const items = Array.isArray(order && order.items) ? order.items : []
  const itemNames = items.slice(0, 2).map((item) => {
    const name = typeof item.productName === 'string' ? item.productName : '商品'
    const quantity = Number.isInteger(item.quantity) && item.quantity > 0 ? item.quantity : 1
    return `${name} ×${quantity}`
  })
  return {
    ...order,
    id: String(order && order.id || ''),
    statusLabel: STATUS_LABELS[order && order.status] || '订单处理中',
    createdLabel: timeLabel(order && order.createdAt),
    amountText: money(order && order.payableAmountCent),
    itemCount: items.reduce((total, item) => total + (Number(item.quantity) || 0), 0),
    itemSummary: itemNames.join('、') + (items.length > 2 ? ` 等${items.length}件` : '')
  }
}

Page({
  data: {
    state: 'loading',
    stateMessage: '',
    statusOptions: STATUS_OPTIONS,
    activeStatus: '',
    orders: [],
    nextCursor: null,
    total: 0,
    refreshing: false,
    loadingMore: false,
    hasMore: false
  },

  onLoad() {
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall-orders' })
      return
    }
    return this.loadOrders(true)
  },

  async loadOrders(reset = true) {
    if (!reset && (!this.data.hasMore || this.data.loadingMore)) return
    const requestVersion = (this.requestVersion || 0) + 1
    this.requestVersion = requestVersion
    const cursor = reset ? '' : this.data.nextCursor
    if (reset) {
      this.setData({
        state: this.data.orders.length ? 'success' : 'loading',
        stateMessage: '',
        refreshing: this.data.orders.length > 0,
        loadingMore: false
      })
    } else {
      this.loadingMore = true
      this.setData({ loadingMore: true, stateMessage: '' })
    }
    try {
      const page = await mallOrderService.listMyMallOrders({
        pageSize: 20,
        ...(this.data.activeStatus ? { status: this.data.activeStatus } : {}),
        ...(cursor ? { cursor } : {})
      })
      if (requestVersion !== this.requestVersion) return
      const received = Array.isArray(page && page.items) ? page.items.map(viewOrder) : []
      const previous = reset ? [] : this.data.orders
      const known = new Set(previous.map((item) => item.id))
      const orders = previous.concat(received.filter((item) => item.id && !known.has(item.id)))
      const nextCursor = page && page.nextCursor ? String(page.nextCursor) : null
      this.setData({
        state: orders.length ? 'success' : 'empty',
        stateMessage: '',
        orders,
        nextCursor,
        total: Number.isSafeInteger(page && page.total) ? page.total : orders.length,
        hasMore: Boolean(nextCursor),
        refreshing: false,
        loadingMore: false
      })
    } catch (error) {
      if (requestVersion !== this.requestVersion) return
      const retained = this.data.orders
      this.setData({
        state: retained.length ? 'success' : 'recoverable-error',
        stateMessage: error && error.message ? error.message : '订单加载失败，请重试',
        refreshing: false,
        loadingMore: false
      })
    } finally {
      if (!reset) this.loadingMore = false
    }
  },

  selectStatus(event) {
    const status = String(event && event.currentTarget && event.currentTarget.dataset.status || '')
    if (status === this.data.activeStatus) return
    this.requestVersion = (this.requestVersion || 0) + 1
    this.loadingMore = false
    this.setData({ activeStatus: status, orders: [], nextCursor: null, hasMore: false, total: 0, state: 'loading', stateMessage: '' })
    return this.loadOrders(true)
  },

  retry() {
    return this.loadOrders(true)
  },

  refresh() {
    return this.loadOrders(true)
  },

  onPullDownRefresh() {
    const result = this.refresh()
    if (result && result.finally) result.finally(() => wx.stopPullDownRefresh())
    else wx.stopPullDownRefresh()
  },

  onReachBottom() {
    return this.loadOrders(false)
  },

  openOrder(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    if (!/^[1-9][0-9]*$/.test(id)) return
    wx.navigateTo({ url: `/pages/mall-order-detail/index?id=${encodeURIComponent(id)}` })
  },

  browseMall() {
    wx.switchTab({ url: '/pages/mall/index' })
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  }
})
