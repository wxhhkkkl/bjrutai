const { getLegalDocument } = require('../../models/legal-document');

Page({
  data: { document: null },

  onLoad(options) {
    const document = getLegalDocument(options && options.type);
    if (!document) {
      wx.showToast({ title: '协议暂不可用', icon: 'none' });
      return;
    }
    this.setData({ document });
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }
    wx.reLaunch({ url: '/pages/auth/login/index' });
  }
});
