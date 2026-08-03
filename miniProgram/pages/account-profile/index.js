const demo = require('../../mock/demo-control');
const {
  getCurrentSession
} = require('../../services/session-service');
const {
  createAccountProfileForm,
  getAccountProfileView,
  validateAccountProfile,
  saveAccountProfile
} = require('../../models/account-profile');

Page({
  data: {
    session: {},
    view: {},
    form: createAccountProfileForm(),
    phone: '138****1028',
    invalidField: '',
    saving: false
  },

  onLoad() {
    const session = Object.assign(
      {},
      getCurrentSession(),
      demo.getDemoSession()
    );
    const view = getAccountProfileView(session);

    this.setData({
      session,
      view,
      form: createAccountProfileForm(session),
      phone: view.phone
    });
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.switchTab({
      url: '/pages/profile/index'
    });
  },

  onFieldInput(event) {
    const field = event.currentTarget.dataset.field;
    const patch = {};

    patch[`form.${field}`] = event.detail.value;
    if (this.data.invalidField === field) patch.invalidField = '';
    this.setData(patch);
  },

  chooseAvatar() {
    if (!wx.chooseMedia) {
      wx.showToast({
        title: '当前微信版本暂不支持头像选择',
        icon: 'none'
      });
      return;
    }

    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success: ({ tempFiles }) => {
        const selected = tempFiles && tempFiles[0];
        if (!selected || !selected.tempFilePath) return;

        this.setData({
          'form.avatar': selected.tempFilePath
        });
        wx.showToast({
          title: '头像已更新',
          icon: 'success'
        });
      }
    });
  },

  authorizePhone(event) {
    const detail = event.detail || {};

    if (!/:ok$/.test(detail.errMsg || '')) {
      wx.showToast({
        title: '手机号授权未完成',
        icon: 'none'
      });
      return;
    }

    this.setData({
      phone: '139****6688'
    });
    wx.showToast({
      title: '手机号已更新',
      icon: 'success'
    });
  },

  saveProfile() {
    const validation = validateAccountProfile(this.data.form);

    if (!validation.valid) {
      this.setData({
        invalidField: validation.field
      });
      wx.showToast({
        title: validation.message,
        icon: 'none'
      });
      return;
    }

    if (this.data.saving) return;
    this.setData({
      saving: true,
      invalidField: ''
    });

    demo.setDemoSession(
      saveAccountProfile(
        demo.getDemoSession(),
        this.data.form,
        this.data.phone
      )
    );
    wx.showToast({
      title: '资料已保存',
      icon: 'success',
      duration: 900
    });

    setTimeout(() => {
      this.setData({ saving: false });
      this.handleBack();
    }, 500);
  }
});
