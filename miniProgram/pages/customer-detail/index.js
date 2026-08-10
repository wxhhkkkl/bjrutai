const customerService = require('../../services/customer-service')
const {
  CUSTOMER_DETAIL_TABS,
  CONTRIBUTION_FILTERS,
  normalizeCustomerDetailTab,
  filterContributionRecords,
  adaptCustomerDetail
} = require('../../models/customer-detail')

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,
  data: {
    state: 'loading',
    stateMessage: '',
    tabs: CUSTOMER_DETAIL_TABS,
    currentTab: 'info',
    customer: {},
    heroAvatar: '/assets/images/customer-avatar-purple.png',
    services: [],
    contributionFilters: CONTRIBUTION_FILTERS,
    selectedContributionFilter: 'all',
    contributions: [],
    blockedMessage: ''
  },

  onLoad(options = {}) {
    this.customerId = options.id || ''
    this.requestDetail(options.tab)
  },

  onUnload() {
    this.requestVersion += 1
  },

  async requestDetail(tab) {
    const version = ++this.requestVersion
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const payload = await customerService.getCustomer(this.customerId)
      if (version !== this.requestVersion) return
      const customer = adaptCustomerDetail(payload)
      this.setData({
        state: 'success',
        currentTab: normalizeCustomerDetailTab(tab),
        customer,
        heroAvatar: customer.avatar
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' })
    }
  },

  retry() {
    this.requestDetail(this.data.currentTab)
  },

  async selectTab(e) {
    const currentTab = normalizeCustomerDetailTab(e.currentTarget.dataset.id)
    this.setData({ currentTab, heroAvatar: this.data.customer.avatar })
    try {
      if (currentTab === 'service') {
        const payload = await customerService.getServiceRecords(this.customerId)
        this.setData({ services: (payload.items || []).map((item) => ({ id: item.id, title: item.title || item.billNo || '服务记录', time: String(item.serviceDate || item.createdAt || '').replace('T', ' ').slice(0, 16), status: item.status || '已完成', statusTone: 'blue', tone: 'blue', icon: 'records' })) })
      }
      if (currentTab === 'contribution') {
        const payload = await customerService.getCustomerContributions(this.customerId)
        this.setData({ contributions: (payload.items || []).map((item) => ({ id: item.id, category: 'service', title: item.title || '消费记录', time: String(item.occurredAt || '').replace('T', ' ').slice(0, 16), points: (Number(item.amountCent || 0) / 100).toFixed(2), tone: 'blue', icon: 'bill-o' })) })
      }
    } catch (error) { wx.showToast({ title: error.message || '记录加载失败', icon: 'none' }) }
    wx.pageScrollTo({ scrollTop: 0, duration: 180 })
  },

  selectContributionFilter(e) {
    this.setData({ selectedContributionFilter: e.currentTarget.dataset.id })
  },

  editCustomer() {
    wx.navigateTo({ url: `/pages/customer-edit/index?id=${this.data.customer.id}` })
  },

  openBindingRecords() {
    wx.navigateTo({ url: '/pages/binding-records/index' })
  },

  openService() {
    wx.showToast({ title: '服务详情以儒泰侧记录为准', icon: 'none' })
  },

  contactCustomer() {
    wx.showModal({
      title: `联系${this.data.customer.name}`,
      content: `客户手机号：${this.data.customer.phone}`,
      showCancel: false,
      confirmText: '我知道了'
    })
  },

  recordFollowup() {
    wx.navigateTo({ url: `/pages/followup-record/index?id=${this.customerId}` })
  },

  handleBack() {
    wx.navigateBack()
  }
})
