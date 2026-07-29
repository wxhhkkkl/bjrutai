const { BINDING_RECORDS } = require('../../models/binding-records');
const {
  normalizeResultState,
  getResultStateForRecord,
  getBindingResultViewModel
} = require('../../models/binding-result');

Page({
  data: {
    state: 'matching',
    record: BINDING_RECORDS[1],
    viewModel: getBindingResultViewModel('matching')
  },

  onLoad(options = {}) {
    const record = BINDING_RECORDS.find(
      (item) => item.id === options.id
    ) || BINDING_RECORDS[1];
    const state = options.state
      ? normalizeResultState(options.state)
      : getResultStateForRecord(record);

    this.setData({
      state,
      record,
      viewModel: getBindingResultViewModel(state)
    });
  },

  handleBack() {
    wx.navigateBack();
  },

  returnToRecords() {
    const pages = getCurrentPages();
    const previous = pages[pages.length - 2];

    if (previous && previous.route === 'pages/binding-records/index') {
      wx.navigateBack();
      return;
    }

    wx.redirectTo({ url: '/pages/binding-records/index' });
  },

  modifyCustomer() {
    wx.redirectTo({
      url: `/pages/customer-edit/index?recordId=${this.data.record.id}`
    });
  },

  continueBinding() {
    wx.navigateTo({ url: '/pages/customer-binding/index' });
  },

  contactAdmin() {
    wx.showModal({
      title: '联系管理员',
      content: '请联系儒泰业务管理员协助核对客户信息及匹配状态。',
      showCancel: false,
      confirmText: '我知道了'
    });
  }
});
