const authService = require('../../../services/auth-service');
const sessionService = require('../../../services/session-service');

Page({
  data: {
    binding: false,
    from: '',
    articleId: ''
  },

  onLoad(options = {}) {
    const from = options.from === 'profile' || options.from === 'comment' ? options.from : '';
    const articleId = from === 'comment' && /^[1-9]\d*$/.test(String(options.articleId || ''))
      ? String(options.articleId) : '';
    this.setData({ from, articleId });
  },

  returnQuery() {
    if (!this.data.from) return '';
    return `?from=${this.data.from}${this.data.articleId ? `&articleId=${this.data.articleId}` : ''}`;
  },

  finishBinding(session) {
    const entry = sessionService.getEntry(session);
    if (entry.type === 'reLaunch') {
      const url = entry.url === '/pages/auth/profile-setup/index'
        ? `${entry.url}${this.returnQuery()}` : entry.url;
      wx.redirectTo({ url });
      return;
    }
    if (this.data.from === 'profile') {
      wx.switchTab({ url: '/pages/profile/index' });
      return;
    }
    if (this.data.from === 'comment') {
      if (typeof getCurrentPages === 'function' && getCurrentPages().length > 1) {
        wx.navigateBack({ delta: 1 });
      } else if (this.data.articleId) {
        wx.redirectTo({ url: `/pages/article-detail/index?articleId=${this.data.articleId}` });
      } else {
        wx.switchTab({ url: '/pages/home/index' });
      }
      return;
    }
    wx.switchTab({ url: entry.url });
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
          const session = await authService.restoreSession({
            preserveSession: sessionService.getCurrentSession(),
            wechatBound: true
          });
          wx.showToast({ title: '微信绑定成功', icon: 'success', duration: 900 });
          setTimeout(() => {
            this.finishBinding(session);
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
    wx.reLaunch({ url: `/pages/auth/login/index${this.returnQuery()}` });
  }
});
