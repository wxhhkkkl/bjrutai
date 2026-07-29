const demo = require('../../../mock/demo-control');
const {
  validateLoginAuthorization,
  createPendingProfileSession
} = require('../../../models/auth-onboarding');

Page({
  data: {
    agreed: false,
    phoneAuthorized: false,
    phoneLabel: '授权手机号',
    loggingIn: false
  },

  toggleAgreement() {
    this.setData({
      agreed: !this.data.agreed
    });
  },

  openDocument(event) {
    const type = event.currentTarget.dataset.type;
    const title = type === 'privacy' ? '隐私政策' : '用户协议';

    wx.showModal({
      title,
      content: `${title}演示文本，正式环境将展示完整协议内容。`,
      showCancel: false,
      confirmText: '知道了'
    });
  },

  authorizePhone(event) {
    const detail = event.detail || {};
    const authorized = /:ok$/.test(detail.errMsg || '');

    if (!authorized) {
      wx.showToast({
        title: '手机号授权未完成',
        icon: 'none'
      });
      return;
    }

    this.setData({
      phoneAuthorized: true,
      phoneLabel: '手机号已授权'
    });
    wx.showToast({
      title: '授权成功',
      icon: 'success'
    });
  },

  login() {
    const validation = validateLoginAuthorization(this.data);

    if (!validation.ok) {
      wx.showToast({
        title: validation.message,
        icon: 'none'
      });
      return;
    }

    if (this.data.loggingIn) return;
    this.setData({ loggingIn: true });

    wx.login({
      success: () => {
        demo.setDemoSession(createPendingProfileSession('138****1028'));
        wx.navigateTo({
          url: '/pages/auth/profile-setup/index'
        });
      },
      fail: () => {
        wx.showToast({
          title: '登录失败，请重试',
          icon: 'none'
        });
      },
      complete: () => {
        this.setData({ loggingIn: false });
      }
    });
  }
});
