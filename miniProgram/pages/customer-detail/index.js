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
    blockedMessage: '服务记录、消费明细和跟进功能暂不可用，请以后端权限校验为准。'
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
        currentTab: normalizeCustomerDetailTab(tab) === 'info' ? 'info' : 'info',
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

  selectTab(e) {
    const currentTab = normalizeCustomerDetailTab(e.currentTarget.dataset.id)
    if (currentTab !== 'info') {
      wx.showToast({ title: this.data.blockedMessage, icon: 'none' })
      return
    }
    this.setData({ currentTab, heroAvatar: this.data.customer.avatar })
    wx.pageScrollTo({ scrollTop: 0, duration: 180 })
  },

  selectContributionFilter(e) {
    this.setData({ selectedContributionFilter: e.currentTarget.dataset.id, contributions: [] })
    wx.showToast({ title: this.data.blockedMessage, icon: 'none' })
  },

  editCustomer() {
    wx.navigateTo({ url: `/pages/customer-edit/index?id=${this.data.customer.id}` })
  },

  openBindingRecords() {
    wx.navigateTo({ url: '/pages/binding-records/index' })
  },

  openService() {
    wx.showToast({ title: this.data.blockedMessage, icon: 'none' })
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
    wx.showToast({ title: this.data.blockedMessage, icon: 'none' })
  },

  handleBack() {
    wx.navigateBack()
  }
})
