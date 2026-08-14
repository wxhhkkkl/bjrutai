const customerService = require('../../services/customer-service')
const { adaptCustomerDetail } = require('../../models/customer-detail')

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,
  data: {
    state: 'loading',
    stateMessage: '',
    customer: {},
    heroAvatar: '/assets/images/customer-avatar-purple.png'
  },

  onLoad(options = {}) {
    this.customerId = options.id || ''
    this.requestDetail()
  },

  onUnload() {
    this.requestVersion += 1
  },

  async requestDetail() {
    const version = ++this.requestVersion
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const payload = await customerService.getCustomer(this.customerId)
      if (version !== this.requestVersion) return
      const customer = adaptCustomerDetail(payload)
      this.setData({
        state: 'success',
        customer,
        heroAvatar: customer.avatar
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' })
    }
  },

  retry() {
    this.requestDetail()
  },

  editCustomer() {
    wx.navigateTo({ url: `/pages/customer-edit/index?id=${this.data.customer.id}` })
  },

  handleBack() {
    wx.navigateBack()
  }
})
