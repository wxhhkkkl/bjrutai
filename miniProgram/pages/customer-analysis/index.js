const customerService = require('../../services/customer-service')
const {
  CUSTOMER_ANALYSIS_TABS,
  adaptCustomerAnalysis,
  getBindingDistribution
} = require('../../models/customer-analysis')

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,
  data: {
    state: 'loading',
    stateMessage: '',
    periods: CUSTOMER_ANALYSIS_TABS,
    selectedPeriod: 'month',
    period: null,
    distribution: [],
    selectedDate: '2026-08-08'
  },

  onReady() { this.loadAnalysis('month') },
  onUnload() { this.requestVersion += 1 },

  async loadAnalysis(selectedPeriod) {
    const version = ++this.requestVersion
    const tab = CUSTOMER_ANALYSIS_TABS.find((item) => item.id === selectedPeriod) || CUSTOMER_ANALYSIS_TABS[0]
    this.setData({ state: 'loading', stateMessage: '', selectedPeriod })
    try {
      const adapted = adaptCustomerAnalysis(await customerService.getCustomerAnalysis(tab.apiPeriod))
      if (version !== this.requestVersion) return
      this.setData({ state: 'success', period: adapted, distribution: getBindingDistribution(adapted) })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({ state: errorState(error), stateMessage: error.message || '请稍后再试' })
    }
  },

  selectPeriod(e) {
    const selectedPeriod = e.currentTarget.dataset.id
    if (selectedPeriod !== this.data.selectedPeriod) this.loadAnalysis(selectedPeriod)
  },

  onDateChange(e) {
    this.setData({ selectedDate: e.detail.value })
  },

  openAttention(e) {
    if (e.currentTarget.dataset.type === 'matching') {
      wx.navigateTo({ url: '/pages/binding-records/index?filter=matching' })
      return
    }
    wx.switchTab({ url: '/pages/customers/index' })
  },

  retry() {
    this.loadAnalysis(this.data.selectedPeriod)
  },

  handleBack() {
    wx.navigateBack()
  }
})
