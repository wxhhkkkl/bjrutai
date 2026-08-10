const workbenchService = require('../../services/customer-service')
const {
  adaptCustomerList,
  filterCustomers,
  sortCustomers
} = require('../../models/customer-list')
const { adaptCustomerAnalysis } = require('../../models/customer-analysis')
const { updateTabBar, openAction } = require('../../services/navigation-service')
const { getCurrentSession } = require('../../services/session-service')

const FILTERS = [
  { id: 'all', label: '全部', status: undefined },
  { id: 'matching', label: '待匹配', status: 'pending' },
  { id: 'followup', label: '待跟进', status: 'unbound' }
]

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,
  overviewRequestVersion: 0,

  data: {
    state: 'loading',
    stateMessage: '',
    list: [],
    visibleList: [],
    overview: { bound: '—', matching: '—', followup: '—' },
    filters: FILTERS.map((item) => Object.assign({}, item, { count: '' })),
    selectedFilter: 'all',
    keyword: '',
    sortMode: 'recent',
    nextCursor: '',
    hasMore: false
  },

  onShow() {
    updateTabBar(this, 'customers')
    this.loadCustomers({ reset: true })
    this.loadOverview()
  },

  onHide() {
    this.requestVersion += 1
    this.overviewRequestVersion += 1
  },

  onUnload() {
    this.requestVersion += 1
    this.overviewRequestVersion += 1
  },

  async loadOverview() {
    const version = ++this.overviewRequestVersion
    try {
      const payload = await workbenchService.getCustomerAnalysis('30d')
      if (version !== this.overviewRequestVersion) return
      this.setData({ overview: adaptCustomerAnalysis(payload).overview })
    } catch (error) {
      // 客户列表仍可独立使用，概览请求失败时保留占位符并允许下次 onShow 重试。
      if (version !== this.overviewRequestVersion) return
      this.setData({ overview: { bound: '—', matching: '—', followup: '—' } })
    }
  },

  async loadCustomers({ reset = false } = {}) {
    const version = ++this.requestVersion
    const filter = FILTERS.find((item) => item.id === this.data.selectedFilter) || FILTERS[0]
    const cursor = reset ? undefined : this.data.nextCursor
    this.setData({ state: reset ? 'loading' : this.data.state, stateMessage: '' })

    try {
      const payload = await workbenchService.listCustomers({
        status: filter.status,
        keyword: this.data.keyword,
        cursor,
        pageSize: 20
      })
      if (version !== this.requestVersion) return

      const adapted = adaptCustomerList(payload)
      const list = reset ? adapted.items : this.data.list.concat(adapted.items)
      const filters = FILTERS.map((item) => Object.assign({}, item, {
        count: item.id === 'all' ? list.length : ''
      }))
      this.setData({
        state: 'success',
        list,
        visibleList: this.getVisibleList(list),
        filters,
        nextCursor: adapted.nextCursor,
        hasMore: adapted.hasMore
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' })
    }
  },

  getVisibleList(list = this.data.list, overrides = {}) {
    const selectedFilter = overrides.selectedFilter || this.data.selectedFilter
    const keyword = overrides.keyword === undefined ? this.data.keyword : overrides.keyword
    const sortMode = overrides.sortMode || this.data.sortMode
    return sortCustomers(filterCustomers(list, selectedFilter, keyword), sortMode)
  },

  retry() {
    this.loadCustomers({ reset: true })
    this.loadOverview()
  },

  onSearch(e) {
    const keyword = e.detail.value
    this.setData({ keyword })
    this.loadCustomers({ reset: true })
  },

  selectFilter(e) {
    const selectedFilter = e.currentTarget.dataset.id
    this.setData({ selectedFilter, list: [], visibleList: [], nextCursor: '' })
    this.loadCustomers({ reset: true })
  },

  loadMore() {
    if (this.data.hasMore && this.data.nextCursor) this.loadCustomers()
  },

  openSort() {
    wx.showActionSheet({
      itemList: ['按最近更新排序', '按姓名排序'],
      success: ({ tapIndex }) => {
        const sortMode = tapIndex === 1 ? 'name' : 'recent'
        this.setData({ sortMode, visibleList: this.getVisibleList(this.data.list, { sortMode }) })
      }
    })
  },

  openAnalysis() {
    this.openActionPage('customer-analysis')
  },

  bindCustomer() {
    this.openActionPage('bind-client')
  },

  openActionPage(actionId) {
    const result = openAction(actionId, getCurrentSession())
    if (result.ok) wx.navigateTo({ url: result.url })
    else wx.showToast({ title: result.message, icon: 'none' })
  },

  openCustomer(e) {
    wx.navigateTo({ url: `/pages/customer-detail/index?id=${e.currentTarget.dataset.id}` })
  }
})
