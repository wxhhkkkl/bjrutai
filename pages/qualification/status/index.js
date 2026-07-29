const {
  getQualificationView
} = require('../../../models/qualification-status');

Page({
  data: {
    status: getQualificationView('reviewing')
  },

  onLoad(options = {}) {
    this.setData({
      status: getQualificationView(options.state)
    });
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.switchTab({ url: '/pages/profile/index' });
  },

  viewFile() {
    wx.showModal({
      title: this.data.status.file.name,
      content: `${this.data.status.file.meta}\n演示环境暂不打开本地资质文件。`,
      showCancel: false,
      confirmText: '知道了'
    });
  },

  handlePrimaryAction() {
    if (this.data.status.actionType === 'view') {
      this.viewFile();
      return;
    }

    wx.navigateTo({
      url: `/pages/qualification/update/index?source=${this.data.status.id}`
    });
  }
});
