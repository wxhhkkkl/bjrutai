const notificationService = require('../../services/notification-service')
const { CATEGORY_LABELS, adaptNotifications } = require('../../models/notification')

const FILTERS = Object.freeze([
  { id: 'all', label: CATEGORY_LABELS.all },
  { id: 'unread', label: '未读' },
  ...['system', 'binding', 'promotion', 'bill', 'followup', 'qualification'].map((id) => ({ id, label: CATEGORY_LABELS[id] }))
])

Page({
  requestVersion: 0,
  data: {
    state: 'loading',
    stateMessage: '',
    items: [],
    unreadCount: 0,
    filters: FILTERS,
    selectedFilter: 'all',
    nextCursor: '',
    hasMore: false,
    loadingMore: false
  },

  onShow() { this.loadNotifications(true) },
  onHide() { this.requestVersion += 1 },
  onUnload() { this.requestVersion += 1 },

  async loadNotifications(reset = true) {
    const version = ++this.requestVersion
    const selectedFilter = this.data.selectedFilter
    const unreadOnly = selectedFilter === 'unread'
    const category = !unreadOnly && selectedFilter !== 'all' ? selectedFilter : undefined
    this.setData({
      state: reset ? 'loading' : this.data.state,
      stateMessage: '',
      loadingMore: !reset
    })

    try {
      const payload = await notificationService.listNotifications({
        category,
        unreadOnly,
        cursor: reset ? undefined : this.data.nextCursor,
        pageSize: 20
      })
      if (version !== this.requestVersion) return
      const adapted = adaptNotifications(payload)
      const items = reset ? adapted.items : this.data.items.concat(adapted.items)
      this.setData({
        state: items.length ? 'success' : 'empty',
        items,
        unreadCount: adapted.unreadCount,
        nextCursor: adapted.nextCursor,
        hasMore: adapted.hasMore,
        loadingMore: false
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({
        state: error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error',
        stateMessage: error && error.message ? error.message : '消息加载失败，请稍后再试',
        loadingMore: false
      })
    }
  },

  retry() { this.loadNotifications(true) },

  selectFilter(event) {
    const selectedFilter = event.currentTarget.dataset.id
    if (!FILTERS.some((item) => item.id === selectedFilter)) return
    this.setData({ selectedFilter, items: [], nextCursor: '', hasMore: false })
    this.loadNotifications(true)
  },

  loadMore() {
    if (!this.data.hasMore || this.data.loadingMore) return
    this.loadNotifications(false)
  },

  async markAllRead() {
    if (!this.data.unreadCount) return
    try {
      await notificationService.markAllRead()
      this.setData({
        unreadCount: 0,
        items: this.data.items.map((item) => Object.assign({}, item, { isRead: true }))
      })
      wx.showToast({ title: '已全部标记为已读', icon: 'none' })
    } catch (error) {
      wx.showToast({ title: error && error.message ? error.message : '操作失败，请重试', icon: 'none' })
    }
  },

  async openNotification(event) {
    const index = event.currentTarget.dataset.index
    const item = this.data.items[index]
    if (!item) return

    if (!item.isRead) {
      try {
        await notificationService.markRead(item.id)
        this.setData({ unreadCount: Math.max(0, this.data.unreadCount - 1) })
      } catch (error) {
        wx.showToast({ title: '消息状态更新失败，请重试', icon: 'none' })
        return
      }
      this.setData({ [`items.${index}.isRead`]: true })
    }

    if (item.targetPath) wx.navigateTo({ url: item.targetPath })
  },

  handleBack() { wx.navigateBack({ delta: 1 }) }
})
