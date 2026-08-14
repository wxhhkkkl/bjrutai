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
    confirmed: false,
    invalidField: '',
    saving: false
  },

  onLoad() {
    const session = getCurrentSession();

    this.setData({
      session,
      form: createProfileForm(session)
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

  toggleConfirmation() {
    this.setData({
      confirmed: !this.data.confirmed,
      invalidField: ''
    });
  },

  async submitProfile() {
    const validation = validateProfileForm(
      this.data.form,
      this.data.confirmed
    );

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
      wx.switchTab({ url: '/pages/home/index' });
    } catch (error) {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },

  skipProfile() {
    wx.switchTab({ url: '/pages/home/index' });
  }
});
