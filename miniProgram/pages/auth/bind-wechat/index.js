const authService = require('../../../services/auth-service');
const sessionService = require('../../../services/session-service');

Page({
  data: {
    binding: false
  },

  // 首登强制绑定微信（FR-027）：用 wx.login 换取 code 后调用 /auth/bind-wechat。
  bindWechat() {
    if (this.data.binding) return;
    this.setData({ binding: true });

    wx.login({
      success: async ({ code }) => {
        try {
          const result = await authService.bindWechat(
            code,
            authService.getAccessToken()
          );
          if (result.accessToken) {
            authService.setTokens(result.accessToken, result.refreshToken);
          }
          await authService.restoreSession({
            preserveSession: sessionService.getCurrentSession(),
            wechatBound: true
          });
          wx.showToast({ title: '微信绑定成功', icon: 'success', duration: 900 });
          setTimeout(() => {
            wx.switchTab({ url: '/pages/home/index' });
          }, 900);
        } catch (err) {
          wx.showToast({ title: (err && err.message) || '绑定失败，请重试', icon: 'none' });
          this.setData({ binding: false });
        }
      },
      fail: () => {
        wx.showToast({ title: '获取微信凭证失败', icon: 'none' });
        this.setData({ binding: false });
      }
    });
  },

  handleBack() {
    wx.reLaunch({ url: '/pages/auth/login/index' });
  }
});
