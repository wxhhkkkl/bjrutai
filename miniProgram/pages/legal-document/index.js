const { getLegalDocument } = require('../../models/legal-document');
const { getCurrentSession } = require('../../services/session-service');

Page({
  data: { document: null },

  onLoad(options) {
    const session = getCurrentSession();
    const document = getLegalDocument(options && options.type, session.role);
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
