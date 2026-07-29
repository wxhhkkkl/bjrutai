const demo = require('../../../mock/demo-control');
const {
  getCurrentSession
} = require('../../../services/session-service');
const {
  createProfileForm,
  validateProfileForm,
  completeProfileSession
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

  submitProfile() {
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

    const session = completeProfileSession(
      demo.getDemoSession(),
      this.data.form
    );
    demo.setDemoSession(session);

    wx.showToast({
      title: '资料已提交',
      icon: 'success',
      duration: 900
    });

    setTimeout(() => {
      wx.reLaunch({
        url: '/pages/qualification/status/index?state=reviewing'
      });
    }, 500);
  }
});
