const {
  getCurrentSession
} = require('../../../services/session-service');
const authService = require('../../../services/auth-service');
const profileService = require('../../../services/profile-service');
const {
  createProfileForm,
  validateProfileForm
} = require('../../../models/auth-onboarding');

Page({
  data: {
    session: {},
    form: createProfileForm(),
    invalidField: '',
    saving: false,
    from: '',
    articleId: ''
  },

  onLoad(options = {}) {
    const session = getCurrentSession();
    const from = options.from === 'profile' || options.from === 'comment' ? options.from : '';
    const articleId = from === 'comment' && /^[1-9]\d*$/.test(String(options.articleId || ''))
      ? String(options.articleId) : '';

    this.setData({
      session,
      form: createProfileForm(session),
      from,
      articleId
    });
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.reLaunch({
      url: '/pages/auth/login/index'
    });
  },

  onFieldInput(event) {
    const field = event.currentTarget.dataset.field;
    if (field !== 'name') return;
    const value = event.detail.value;
    const patch = {};

    patch[`form.${field}`] = value;
    if (this.data.invalidField === field) patch.invalidField = '';
    this.setData(patch);
  },

  async submitProfile() {
    const validation = validateProfileForm(this.data.form);

    if (!validation.ok) {
      this.setData({ invalidField: validation.field });
      wx.showToast({
        title: validation.message,
        icon: 'none'
      });
      return;
    }

    if (this.data.saving) return;
    this.setData({ saving: true });

    try {
      const sessionService = require('../../../services/session-service');
      const session = sessionService.getCurrentSession();
      const profile = await profileService.getProfile();
      const result = await profileService.updateProfile({
        name: this.data.form.name.trim(),
        version: profile.version
      });
      sessionService.setSession(Object.assign({}, session, {
        profileCompleted: true,
        name: result.name || this.data.form.name,
        organization: result.organization || session.organization || this.data.form.organization
      }));
      if (this.data.from === 'profile') {
        wx.switchTab({ url: '/pages/profile/index' });
      } else if (this.data.from === 'comment' && typeof getCurrentPages === 'function' && getCurrentPages().length > 1) {
        wx.navigateBack({ delta: 1 });
      } else if (this.data.from === 'comment' && this.data.articleId) {
        wx.redirectTo({ url: `/pages/article-detail/index?articleId=${this.data.articleId}` });
      } else {
        wx.switchTab({ url: '/pages/home/index' });
      }
    } catch (error) {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  }
});
