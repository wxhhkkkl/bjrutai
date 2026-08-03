const authService = require('../../../services/auth-service');
const sessionService = require('../../../services/session-service');
const { validateLoginAuthorization } = require('../../../models/auth-onboarding');

Page({
  data: {
    agreed: false,
    phone: '',
    password: '',
    loggingIn: false
  },

  toggleAgreement() {
    this.setData({ agreed: !this.data.agreed });
  },

  onPhoneInput(event) {
    this.setData({ phone: event.detail.value });
  },

  onPasswordInput(event) {
    this.setData({ password: event.detail.value });
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

  // ── Distributor phone + password login (T052 / FR-027) ─────────
  async login() {
    const validation = validateLoginAuthorization(this.data);
    if (!validation.ok) {
      wx.showToast({ title: validation.message, icon: 'none' });
      return;
    }

    const phone = String(this.data.phone || '').trim();
    const password = String(this.data.password || '').trim();
    if (!/^\d{11}$/.test(phone)) {
      wx.showToast({ title: '请输入 11 位手机号', icon: 'none' });
      return;
    }
    if (password.length < 8) {
      wx.showToast({ title: '密码至少 8 位', icon: 'none' });
      return;
    }

    if (this.data.loggingIn) return;
    this.setData({ loggingIn: true });
    try {
      await this.completeLogin(await authService.distributorLogin(phone, password));
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '登录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ loggingIn: false });
    }
  },

  // ── WeChat quick login (existing flow, wired to real API) ──────
  wechatLogin() {
    const validation = validateLoginAuthorization(this.data);
    if (!validation.ok) {
      wx.showToast({ title: validation.message, icon: 'none' });
      return;
    }
    if (this.data.loggingIn) return;
    this.setData({ loggingIn: true });

    wx.login({
      success: async ({ code }) => {
        try {
          const result = await authService.wechatLogin(code);
          await this.completeLogin(result);
        } catch (err) {
          wx.showToast({ title: (err && err.message) || '登录失败，请重试', icon: 'none' });
        }
      },
      fail: () => wx.showToast({ title: '获取微信凭证失败', icon: 'none' }),
      complete: () => this.setData({ loggingIn: false })
    });
  },

  // Share token storage + session building + routing between both paths.
  async completeLogin(result) {
    const accessToken = result.accessToken;
    const refreshToken = result.refreshToken;
    authService.setTokens(accessToken, refreshToken);

    let user = {};
    if (result.user) {
      user = result.user;
    } else if (accessToken) {
      try {
        const session = await authService.getSession(accessToken);
        user = session.user || {};
      } catch {
        // session fetch optional — fall back to the login payload
      }
    }

    const distributor = result.distributor || {};
    sessionService.setSession(
      sessionService.buildDistributorSession(user, distributor)
    );

    if (result.requiresWechatBinding) {
      wx.redirectTo({ url: '/pages/auth/bind-wechat/index' });
      return;
    }
    wx.switchTab({ url: '/pages/home/index' });
  }
});
