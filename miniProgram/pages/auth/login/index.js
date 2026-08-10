const authService = require('../../../services/auth-service');
const sessionService = require('../../../services/session-service');
const { validateLoginConsent } = require('../../../models/auth-onboarding');

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
    if (type !== 'agreement' && type !== 'privacy') return;
    wx.navigateTo({ url: `/pages/legal-document/index?type=${type}` });
  },

  // ── Distributor phone + password login (T052 / FR-027) ─────────
  async login() {
    const validation = validateLoginConsent(this.data);
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

  // ── WeChat phone authorization + login ─────────────────────────
  wechatLogin(event) {
    const validation = validateLoginConsent(this.data);
    if (!validation.ok) {
      wx.showToast({ title: validation.message, icon: 'none' });
      return;
    }
    const phoneCode = event && event.detail && event.detail.code;
    if (!phoneCode) {
      wx.showToast({ title: '请授权手机号后继续登录', icon: 'none' });
      return;
    }
    if (this.data.loggingIn) return;
    this.setData({ loggingIn: true });

    wx.login({
      success: async ({ code }) => {
        try {
          const result = await authService.wechatLogin(code, phoneCode);
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
    const established = await authService.establishSession(result);

    if (established.requiresWechatBinding) {
      wx.redirectTo({ url: '/pages/auth/bind-wechat/index' });
      return;
    }
    if (established.isNewUser || !established.session.profileCompleted) {
      wx.redirectTo({ url: '/pages/auth/profile-setup/index' });
      return;
    }
    wx.switchTab({ url: '/pages/home/index' });
  }
});
