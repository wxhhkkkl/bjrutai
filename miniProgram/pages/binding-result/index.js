const { getBindingResultViewModel } = require('../../models/binding-result')

Page({
  data: {
    state: 'blocked',
    record: {},
    viewModel: getBindingResultViewModel('matching'),
    blockedMessage: '绑定详情、重试和审计事件暂不可用，请以绑定记录列表状态为准。'
  },

  onLoad(options = {}) {
    this.setData({ record: { id: options.id || '' } })
  },

  handleBack() { wx.navigateBack() },
  returnToRecords() { wx.redirectTo({ url: '/pages/binding-records/index' }) },
  modifyCustomer() { wx.showToast({ title: this.data.blockedMessage, icon: 'none' }) },
  continueBinding() { wx.navigateTo({ url: '/pages/customer-binding/index' }) },
  contactAdmin() { wx.showModal({ title: '联系管理员', content: this.data.blockedMessage, showCancel: false, confirmText: '我知道了' }) }
})
